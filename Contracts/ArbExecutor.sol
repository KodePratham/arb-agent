// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "./interfaces/IConditionalTokens.sol";
import "./interfaces/ICLOBExchange.sol";

/**
 * @title  ArbExecutor
 * @author arb-agent hackathon team
 * @notice Atomically executes cross-platform prediction-market arbitrage
 *         on opBNB (Chain ID 204).
 *
 * ─── Architecture ────────────────────────────────────────────────
 *
 *  Off-chain C++ Engine detects an arb:
 *    - Market A (cheap YES) on Platform A
 *    - Market B (expensive YES → cheap NO) on Platform B
 *
 *  Engine calls  ArbExecutor.executeArb()  which:
 *    1. Pulls USDT from the operator wallet (via approve + transferFrom).
 *    2. Buys YES shares on the cheap side (Platform A CLOB).
 *    3. Buys NO  shares on the expensive side (Platform B CLOB).
 *    4. If both markets resolve the same way, one leg pays $1/share
 *       and the spread minus gas is pure profit.
 *    5. Tokens sit in this contract until redeemed after settlement.
 *
 * ─── opBNB Deployment ────────────────────────────────────────────
 *
 *  opBNB is a BNB Chain L2 (optimistic rollup):
 *    - Chain ID:  204
 *    - RPC:       https://opbnb-mainnet-rpc.bnbchain.org
 *    - Gas:       ~0.001 Gwei (extremely cheap)
 *    - Finality:  ~1 s block time
 *
 *  The ultra-low gas makes atomic multi-leg arb viable.
 *
 * ─── Security ────────────────────────────────────────────────────
 *
 *  - Only the `operator` (deployer) can execute arbs or withdraw.
 *  - ReentrancyGuard on all state-changing functions.
 *  - Emergency `withdraw()` for stuck tokens.
 */

// ═══════════════════════════════════════════════════════════════════
//  Minimal ERC20 interface (USDT on opBNB)
// ═══════════════════════════════════════════════════════════════════

interface IERC20 {
    function totalSupply() external view returns (uint256);
    function balanceOf(address account) external view returns (uint256);
    function transfer(address to, uint256 amount) external returns (bool);
    function allowance(address owner, address spender) external view returns (uint256);
    function approve(address spender, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}

// ═══════════════════════════════════════════════════════════════════
//  Minimal ERC1155 receiver (required to receive conditional tokens)
// ═══════════════════════════════════════════════════════════════════

interface IERC1155Receiver {
    function onERC1155Received(
        address operator_,
        address from,
        uint256 id,
        uint256 value,
        bytes calldata data
    ) external returns (bytes4);

    function onERC1155BatchReceived(
        address operator_,
        address from,
        uint256[] calldata ids,
        uint256[] calldata values,
        bytes calldata data
    ) external returns (bytes4);
}

// ═══════════════════════════════════════════════════════════════════
//  ArbExecutor
// ═══════════════════════════════════════════════════════════════════

contract ArbExecutor is IERC1155Receiver {

    // ── State ────────────────────────────────────────────────────

    address public immutable operator_;
    IERC20  public immutable usdt;

    /// @dev Platform exchange addresses (set at deploy, updatable)
    address public predictFunExchange;
    address public probableExchange;

    /// @dev Conditional Tokens Framework addresses
    address public predictFunCTF;
    address public probableCTF;

    /// @dev Reentrancy lock
    bool private _locked;

    // ── Events ───────────────────────────────────────────────────

    event ArbExecuted(
        bytes32 indexed marketAConditionId,
        bytes32 indexed marketBConditionId,
        uint256 amountUsdt,
        uint256 yesSharesBought,
        uint256 noSharesBought
    );

    event PlatformUpdated(
        string  platform,
        address exchange,
        address ctf
    );

    event EmergencyWithdraw(
        address token,
        uint256 amount
    );

    // ── Modifiers ────────────────────────────────────────────────

    modifier onlyOperator() {
        require(msg.sender == operator_, "ArbExecutor: not operator");
        _;
    }

    modifier nonReentrant() {
        require(!_locked, "ArbExecutor: reentrant");
        _locked = true;
        _;
        _locked = false;
    }

    // ── Constructor ──────────────────────────────────────────────

    /**
     * @param _usdt              USDT contract on opBNB
     * @param _predictFunExchange  Predict.fun CLOB exchange contract
     * @param _probableExchange    Probable CLOB exchange contract
     * @param _predictFunCTF       Predict.fun Conditional Tokens contract
     * @param _probableCTF         Probable Conditional Tokens contract
     */
    constructor(
        address _usdt,
        address _predictFunExchange,
        address _probableExchange,
        address _predictFunCTF,
        address _probableCTF
    ) {
        operator_           = msg.sender;
        usdt                = IERC20(_usdt);
        predictFunExchange  = _predictFunExchange;
        probableExchange    = _probableExchange;
        predictFunCTF       = _predictFunCTF;
        probableCTF         = _probableCTF;
    }

    // ── Core: Atomic Arb Execution ───────────────────────────────

    /**
     * @notice Execute a two-leg arb trade atomically.
     *
     * @param amountUsdt         Total USDT to deploy (split across legs)
     * @param conditionIdA       CTF condition ID of cheap-YES market
     * @param conditionIdB       CTF condition ID of expensive-YES market
     * @param platformAIsPF      true = Platform A is Predict.fun, false = Probable
     * @param ordersA            Signed CLOB orders to fill on Platform A (buy YES)
     * @param fillAmountsA       Fill amounts for each order on A
     * @param ordersB            Signed CLOB orders to fill on Platform B (buy NO)
     * @param fillAmountsB       Fill amounts for each order on B
     *
     * @dev The caller must have approved this contract to spend `amountUsdt`
     *      of USDT before calling.
     *
     * @dev Reverts if either leg fails, ensuring atomicity.
     */
    function executeArb(
        uint256 amountUsdt,
        bytes32 conditionIdA,
        bytes32 conditionIdB,
        bool    platformAIsPF,
        ICLOBExchange.Order[] calldata ordersA,
        uint256[] calldata fillAmountsA,
        ICLOBExchange.Order[] calldata ordersB,
        uint256[] calldata fillAmountsB
    ) external onlyOperator nonReentrant {
        // 1. Pull USDT from operator
        require(
            usdt.transferFrom(msg.sender, address(this), amountUsdt),
            "ArbExecutor: USDT transfer failed"
        );

        // 2. Determine platform addresses for each leg
        address exchangeA = platformAIsPF ? predictFunExchange : probableExchange;
        address exchangeB = platformAIsPF ? probableExchange   : predictFunExchange;
        address ctfA      = platformAIsPF ? predictFunCTF      : probableCTF;
        address ctfB      = platformAIsPF ? probableCTF        : predictFunCTF;

        // 3. Approve USDT spending on both exchanges
        uint256 halfAmount = amountUsdt / 2;
        usdt.approve(exchangeA, halfAmount);
        usdt.approve(exchangeB, amountUsdt - halfAmount);

        // 4. Leg A — Buy YES shares on cheap side
        uint256 yesBalBefore = _getYesBalance(ctfA, conditionIdA);
        ICLOBExchange(exchangeA).fillOrders(ordersA, fillAmountsA);
        uint256 yesBought = _getYesBalance(ctfA, conditionIdA) - yesBalBefore;

        // 5. Leg B — Buy NO shares on expensive side
        uint256 noBalBefore = _getNoBalance(ctfB, conditionIdB);
        ICLOBExchange(exchangeB).fillOrders(ordersB, fillAmountsB);
        uint256 noBought = _getNoBalance(ctfB, conditionIdB) - noBalBefore;

        // 6. Sanity check: we must have acquired shares on both legs
        require(yesBought > 0, "ArbExecutor: Leg A got 0 YES shares");
        require(noBought  > 0, "ArbExecutor: Leg B got 0 NO shares");

        emit ArbExecuted(conditionIdA, conditionIdB, amountUsdt, yesBought, noBought);
    }

    // ── Split-based arb (alternative path) ───────────────────────

    /**
     * @notice Alternative arb path using CTF splitPosition.
     *         Splits collateral into YES+NO, then sells the unwanted side.
     *
     * @param amountUsdt    USDT to split
     * @param conditionId   CTF condition ID
     * @param ctfAddress    Address of the CTF contract
     * @param partition     Partition array (e.g., [1, 2] for binary)
     */
    function splitAndHold(
        uint256 amountUsdt,
        bytes32 conditionId,
        address ctfAddress,
        uint256[] calldata partition
    ) external onlyOperator nonReentrant {
        require(
            usdt.transferFrom(msg.sender, address(this), amountUsdt),
            "ArbExecutor: USDT transfer failed"
        );

        usdt.approve(ctfAddress, amountUsdt);

        IConditionalTokens(ctfAddress).splitPosition(
            address(usdt),
            bytes32(0),         // root collection
            conditionId,
            partition,
            amountUsdt
        );
    }

    // ── Redeem after settlement ──────────────────────────────────

    /**
     * @notice Redeem winning positions after market resolution.
     */
    function redeemPositions(
        address ctfAddress,
        bytes32 conditionId,
        uint256[] calldata indexSets
    ) external onlyOperator nonReentrant {
        IConditionalTokens(ctfAddress).redeemPositions(
            address(usdt),
            bytes32(0),
            conditionId,
            indexSets
        );

        // Transfer any redeemed USDT back to operator
        uint256 bal = usdt.balanceOf(address(this));
        if (bal > 0) {
            usdt.transfer(operator_, bal);
        }
    }

    // ── Admin ────────────────────────────────────────────────────

    /**
     * @notice Update platform addresses (exchange + CTF contracts).
     */
    function updatePlatform(
        bool isPredictFun,
        address newExchange,
        address newCTF
    ) external onlyOperator {
        if (isPredictFun) {
            predictFunExchange = newExchange;
            predictFunCTF      = newCTF;
            emit PlatformUpdated("PredictFun", newExchange, newCTF);
        } else {
            probableExchange = newExchange;
            probableCTF      = newCTF;
            emit PlatformUpdated("Probable", newExchange, newCTF);
        }
    }

    /**
     * @notice Emergency: withdraw any ERC20 token stuck in this contract.
     */
    function withdraw(address token) external onlyOperator nonReentrant {
        uint256 bal = IERC20(token).balanceOf(address(this));
        require(bal > 0, "ArbExecutor: nothing to withdraw");
        IERC20(token).transfer(operator_, bal);
        emit EmergencyWithdraw(token, bal);
    }

    /**
     * @notice Emergency: withdraw native BNB.
     */
    function withdrawBNB() external onlyOperator nonReentrant {
        uint256 bal = address(this).balance;
        require(bal > 0, "ArbExecutor: no BNB");
        payable(operator_).transfer(bal);
    }

    // ── Internal helpers ─────────────────────────────────────────

    function _getYesBalance(address ctf, bytes32 conditionId)
        internal view returns (uint256)
    {
        // YES = indexSet 1 (first outcome bit)
        bytes32 collectionId = IConditionalTokens(ctf).getCollectionId(
            bytes32(0), conditionId, 1
        );
        uint256 positionId = IConditionalTokens(ctf).getPositionId(
            address(usdt), collectionId
        );
        return IConditionalTokens(ctf).balanceOf(address(this), positionId);
    }

    function _getNoBalance(address ctf, bytes32 conditionId)
        internal view returns (uint256)
    {
        // NO = indexSet 2 (second outcome bit)
        bytes32 collectionId = IConditionalTokens(ctf).getCollectionId(
            bytes32(0), conditionId, 2
        );
        uint256 positionId = IConditionalTokens(ctf).getPositionId(
            address(usdt), collectionId
        );
        return IConditionalTokens(ctf).balanceOf(address(this), positionId);
    }

    // ── ERC1155 Receiver (required for CTF tokens) ───────────────

    function onERC1155Received(
        address, address, uint256, uint256, bytes calldata
    ) external pure override returns (bytes4) {
        return this.onERC1155Received.selector;
    }

    function onERC1155BatchReceived(
        address, address, uint256[] calldata, uint256[] calldata, bytes calldata
    ) external pure override returns (bytes4) {
        return this.onERC1155BatchReceived.selector;
    }

    /// @notice Accept native BNB (for gas refunds etc.)
    receive() external payable {}
}
