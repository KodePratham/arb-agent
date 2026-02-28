// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/Ownable.sol";

contract BinaryPredictionAMM is Ownable {
    struct Market {
        string question;
        uint256 yesPool;
        uint256 noPool;
        bool exists;
        bool resolved;
        bool outcomeYes;
        uint256 totalYesShares;
        uint256 totalNoShares;
        uint256 finalPool;
        uint256 winningSharesAtResolution;
    }

    uint256 public marketCount;
    uint256 public immutable feeBps;
    uint256 public constant VIRTUAL_LIQUIDITY = 1 ether;

    mapping(uint256 => Market) public markets;
    mapping(uint256 => mapping(address => uint256)) public userYesShares;
    mapping(uint256 => mapping(address => uint256)) public userNoShares;

    event MarketCreated(uint256 indexed marketId, string question, uint256 seedLiquidity);
    event LiquidityAdded(uint256 indexed marketId, address indexed provider, uint256 amount);
    event YesBought(uint256 indexed marketId, address indexed trader, uint256 amountIn, uint256 sharesOut);
    event NoBought(uint256 indexed marketId, address indexed trader, uint256 amountIn, uint256 sharesOut);
    event YesSold(uint256 indexed marketId, address indexed trader, uint256 sharesIn, uint256 amountOut);
    event NoSold(uint256 indexed marketId, address indexed trader, uint256 sharesIn, uint256 amountOut);
    event MarketResolved(uint256 indexed marketId, bool outcomeYes);
    event WinningsClaimed(uint256 indexed marketId, address indexed user, uint256 amount);

    constructor(uint256 _feeBps) Ownable(msg.sender) {
        require(_feeBps < 10000, "fee too high");
        feeBps = _feeBps;
    }

    function createMarket(string calldata question, uint256 initialLiquidityWei) external payable onlyOwner returns (uint256) {
        require(bytes(question).length > 0, "question required");
        require(msg.value == initialLiquidityWei, "value != seed");

        uint256 marketId = marketCount;
        marketCount += 1;

        Market storage m = markets[marketId];
        m.question = question;
        m.exists = true;

        if (initialLiquidityWei > 0) {
            uint256 half = initialLiquidityWei / 2;
            m.yesPool = half;
            m.noPool = initialLiquidityWei - half;
        }

        emit MarketCreated(marketId, question, initialLiquidityWei);
        return marketId;
    }

    function addLiquidity(uint256 marketId) external payable {
        Market storage m = _getMarket(marketId);
        require(msg.value > 0, "amount 0");
        require(!m.resolved, "market resolved");

        uint256 half = msg.value / 2;
        m.yesPool += half;
        m.noPool += msg.value - half;

        emit LiquidityAdded(marketId, msg.sender, msg.value);
    }

    function buyYes(uint256 marketId) external payable returns (uint256 sharesOut) {
        Market storage m = _getMarket(marketId);
        require(msg.value > 0, "amount 0");
        require(m.yesPool > 0 && m.noPool > 0, "no liquidity");
        require(!m.resolved, "market resolved");

        uint256 amountInWithFee = (msg.value * (10000 - feeBps)) / 10000;
        sharesOut = _cpmmOut(amountInWithFee, m.yesPool + VIRTUAL_LIQUIDITY, m.noPool + VIRTUAL_LIQUIDITY);
        if (sharesOut > m.noPool) {
            sharesOut = m.noPool;
        }

        m.yesPool += amountInWithFee;
        m.noPool -= sharesOut;
        userYesShares[marketId][msg.sender] += sharesOut;
        m.totalYesShares += sharesOut;

        emit YesBought(marketId, msg.sender, msg.value, sharesOut);
    }

    function buyNo(uint256 marketId) external payable returns (uint256 sharesOut) {
        Market storage m = _getMarket(marketId);
        require(msg.value > 0, "amount 0");
        require(m.yesPool > 0 && m.noPool > 0, "no liquidity");
        require(!m.resolved, "market resolved");

        uint256 amountInWithFee = (msg.value * (10000 - feeBps)) / 10000;
        sharesOut = _cpmmOut(amountInWithFee, m.noPool + VIRTUAL_LIQUIDITY, m.yesPool + VIRTUAL_LIQUIDITY);
        if (sharesOut > m.yesPool) {
            sharesOut = m.yesPool;
        }

        m.noPool += amountInWithFee;
        m.yesPool -= sharesOut;
        userNoShares[marketId][msg.sender] += sharesOut;
        m.totalNoShares += sharesOut;

        emit NoBought(marketId, msg.sender, msg.value, sharesOut);
    }

    function sellYes(uint256 marketId, uint256 sharesIn) external returns (uint256 amountOut) {
        Market storage m = _getMarket(marketId);
        require(!m.resolved, "market resolved");
        require(sharesIn > 0, "shares 0");
        require(userYesShares[marketId][msg.sender] >= sharesIn, "insufficient yes shares");

        amountOut = _cpmmOut(sharesIn, m.noPool + VIRTUAL_LIQUIDITY, m.yesPool + VIRTUAL_LIQUIDITY);
        if (amountOut > m.yesPool) {
            amountOut = m.yesPool;
        }

        uint256 amountOutWithFee = (amountOut * (10000 - feeBps)) / 10000;

        userYesShares[marketId][msg.sender] -= sharesIn;
        m.totalYesShares -= sharesIn;

        m.noPool += sharesIn;
        m.yesPool -= amountOut;

        (bool success,) = payable(msg.sender).call{value: amountOutWithFee}("");
        require(success, "transfer failed");

        emit YesSold(marketId, msg.sender, sharesIn, amountOutWithFee);
    }

    function sellNo(uint256 marketId, uint256 sharesIn) external returns (uint256 amountOut) {
        Market storage m = _getMarket(marketId);
        require(!m.resolved, "market resolved");
        require(sharesIn > 0, "shares 0");
        require(userNoShares[marketId][msg.sender] >= sharesIn, "insufficient no shares");

        amountOut = _cpmmOut(sharesIn, m.yesPool + VIRTUAL_LIQUIDITY, m.noPool + VIRTUAL_LIQUIDITY);
        if (amountOut > m.noPool) {
            amountOut = m.noPool;
        }

        uint256 amountOutWithFee = (amountOut * (10000 - feeBps)) / 10000;

        userNoShares[marketId][msg.sender] -= sharesIn;
        m.totalNoShares -= sharesIn;

        m.yesPool += sharesIn;
        m.noPool -= amountOut;

        (bool success,) = payable(msg.sender).call{value: amountOutWithFee}("");
        require(success, "transfer failed");

        emit NoSold(marketId, msg.sender, sharesIn, amountOutWithFee);
    }

    function getMarket(uint256 marketId)
        external
        view
        returns (string memory question, uint256 yesPool, uint256 noPool, uint256 yesPriceBps)
    {
        Market storage m = _getMarket(marketId);
        question = m.question;
        yesPool = m.yesPool;
        noPool = m.noPool;
        yesPriceBps = _yesPriceBps(m.yesPool, m.noPool);
    }

    function getMarketStatus(uint256 marketId) external view returns (bool resolved, bool outcomeYes) {
        Market storage m = _getMarket(marketId);
        resolved = m.resolved;
        outcomeYes = m.outcomeYes;
    }

    function getUserShares(uint256 marketId, address user) external view returns (uint256 yesShares, uint256 noShares) {
        _getMarket(marketId);
        yesShares = userYesShares[marketId][user];
        noShares = userNoShares[marketId][user];
    }

    function resolveMarket(uint256 marketId, bool outcomeYes) external onlyOwner {
        Market storage m = _getMarket(marketId);
        require(!m.resolved, "already resolved");

        m.resolved = true;
        m.outcomeYes = outcomeYes;
        m.finalPool = m.yesPool + m.noPool;
        m.winningSharesAtResolution = outcomeYes ? m.totalYesShares : m.totalNoShares;

        emit MarketResolved(marketId, outcomeYes);
    }

    function getClaimable(uint256 marketId, address user) public view returns (uint256) {
        Market storage m = _getMarket(marketId);
        if (!m.resolved || m.winningSharesAtResolution == 0) {
            return 0;
        }

        uint256 winningShares = m.outcomeYes ? userYesShares[marketId][user] : userNoShares[marketId][user];
        if (winningShares == 0) {
            return 0;
        }

        return (m.finalPool * winningShares) / m.winningSharesAtResolution;
    }

    function claimWinnings(uint256 marketId) external returns (uint256 payout) {
        Market storage m = _getMarket(marketId);
        require(m.resolved, "market not resolved");
        require(m.winningSharesAtResolution > 0, "no winning shares");

        uint256 winningShares = m.outcomeYes ? userYesShares[marketId][msg.sender] : userNoShares[marketId][msg.sender];
        require(winningShares > 0, "nothing to claim");

        payout = (m.finalPool * winningShares) / m.winningSharesAtResolution;
        require(address(this).balance >= payout, "insufficient balance");

        if (m.outcomeYes) {
            userYesShares[marketId][msg.sender] = 0;
        } else {
            userNoShares[marketId][msg.sender] = 0;
        }

        (bool success,) = payable(msg.sender).call{value: payout}("");
        require(success, "transfer failed");

        emit WinningsClaimed(marketId, msg.sender, payout);
    }

    function _cpmmOut(uint256 amountIn, uint256 reserveIn, uint256 reserveOut) internal pure returns (uint256 amountOut) {
        uint256 k = reserveIn * reserveOut;
        uint256 newReserveIn = reserveIn + amountIn;
        uint256 newReserveOut = k / newReserveIn;
        amountOut = reserveOut - newReserveOut;
    }

    function _yesPriceBps(uint256 yesPool, uint256 noPool) internal pure returns (uint256) {
        uint256 total = yesPool + noPool;
        if (total == 0) {
            return 5000;
        }
        return (yesPool * 10000) / total;
    }

    function _getMarket(uint256 marketId) internal view returns (Market storage m) {
        m = markets[marketId];
        require(m.exists, "invalid market");
    }
}
