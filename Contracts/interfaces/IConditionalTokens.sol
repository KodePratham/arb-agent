// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title IConditionalTokens
 * @notice Minimal interface for Gnosis Conditional Tokens Framework (CTF).
 *         Both Predict.fun and Probable use CTF (ERC1155) on BNB Chain.
 */
interface IConditionalTokens {
    /// @notice Split collateral into conditional positions.
    function splitPosition(
        address collateralToken,
        bytes32 parentCollectionId,
        bytes32 conditionId,
        uint256[] calldata partition,
        uint256 amount
    ) external;

    /// @notice Merge conditional positions back into collateral.
    function mergePositions(
        address collateralToken,
        bytes32 parentCollectionId,
        bytes32 conditionId,
        uint256[] calldata partition,
        uint256 amount
    ) external;

    /// @notice Redeem positions for payout after resolution.
    function redeemPositions(
        address collateralToken,
        bytes32 parentCollectionId,
        bytes32 conditionId,
        uint256[] calldata indexSets
    ) external;

    /// @notice Get the collection ID for a condition + index set.
    function getCollectionId(
        bytes32 parentCollectionId,
        bytes32 conditionId,
        uint256 indexSet
    ) external view returns (bytes32);

    /// @notice Get the position ID for a collateral + collection.
    function getPositionId(
        address collateralToken,
        bytes32 collectionId
    ) external pure returns (uint256);

    /// @notice ERC1155 balance query.
    function balanceOf(address owner, uint256 id)
        external view returns (uint256);
}
