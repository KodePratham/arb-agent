// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title ICLOBExchange
 * @notice Minimal interface for a CLOB (Central Limit Order Book) exchange
 *         used by Predict.fun and Probable for order matching.
 *
 *         Predict.fun uses EIP-712 signed limit orders matched off-chain
 *         then settled on-chain.  Probable uses an orderbook where trades
 *         are submitted on-chain.
 *
 *         This interface covers the common on-chain fill path.
 */
interface ICLOBExchange {
    struct Order {
        address maker;
        address taker;        // 0x0 = any taker
        uint256 tokenId;      // ERC1155 position id
        uint256 makerAmount;  // amount maker gives
        uint256 takerAmount;  // amount taker gives
        uint256 expiration;
        uint256 nonce;
        uint256 feeRateBps;
        bytes   signature;
    }

    /// @notice Fill a signed maker order.
    function fillOrder(
        Order calldata order,
        uint256 fillAmount
    ) external;

    /// @notice Fill multiple orders in a single TX.
    function fillOrders(
        Order[] calldata orders,
        uint256[] calldata fillAmounts
    ) external;
}
