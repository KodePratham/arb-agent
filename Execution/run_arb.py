#!/usr/bin/env python3
"""
Execution/run_arb.py
────────────────────────────────────────────────────────────────
Read arb opportunities emitted by the C++ engine (arbs.json) and
submit them on-chain via the ArbExecutor smart contract on opBNB.

Usage
─────
    # Dry-run (default): just print what *would* be executed
    python -m Execution.run_arb

    # Live execution against opBNB mainnet
    python -m Execution.run_arb --execute --arbs Engine/build/arbs.json

    # Use a custom RPC or contract address
    python -m Execution.run_arb --execute --rpc https://opbnb-mainnet-rpc.bnbchain.org

Environment
───────────
    PRIVATE_KEY            Operator wallet private key (required for --execute)
    ARB_EXECUTOR_CONTRACT  Deployed ArbExecutor contract address
    OPBNB_RPC_URL          Default RPC (overridden by --rpc)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# ── Load .env from project root ──────────────────────────────────
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ── Minimal ABI for executeArb (matches Contracts/ArbExecutor.sol) ──
ARB_EXECUTOR_ABI: list[dict[str, Any]] = [
    {
        "inputs": [
            {"name": "amountUsdt",    "type": "uint256"},
            {"name": "conditionIdA",  "type": "bytes32"},
            {"name": "conditionIdB",  "type": "bytes32"},
            {"name": "platformAIsPF", "type": "bool"},
            {
                "name": "ordersA",
                "type": "tuple[]",
                "components": [
                    {"name": "salt",      "type": "uint256"},
                    {"name": "maker",     "type": "address"},
                    {"name": "signer",    "type": "address"},
                    {"name": "taker",     "type": "address"},
                    {"name": "tokenId",   "type": "uint256"},
                    {"name": "makerAmount", "type": "uint256"},
                    {"name": "takerAmount", "type": "uint256"},
                    {"name": "expiration",  "type": "uint256"},
                    {"name": "nonce",       "type": "uint256"},
                    {"name": "feeRateBps",  "type": "uint256"},
                    {"name": "side",        "type": "uint8"},
                    {"name": "signatureType", "type": "uint8"},
                    {"name": "signature",     "type": "bytes"},
                ],
            },
            {"name": "fillAmountsA", "type": "uint256[]"},
            {
                "name": "ordersB",
                "type": "tuple[]",
                "components": [
                    {"name": "salt",      "type": "uint256"},
                    {"name": "maker",     "type": "address"},
                    {"name": "signer",    "type": "address"},
                    {"name": "taker",     "type": "address"},
                    {"name": "tokenId",   "type": "uint256"},
                    {"name": "makerAmount", "type": "uint256"},
                    {"name": "takerAmount", "type": "uint256"},
                    {"name": "expiration",  "type": "uint256"},
                    {"name": "nonce",       "type": "uint256"},
                    {"name": "feeRateBps",  "type": "uint256"},
                    {"name": "side",        "type": "uint8"},
                    {"name": "signatureType", "type": "uint8"},
                    {"name": "signature",     "type": "bytes"},
                ],
            },
            {"name": "fillAmountsB", "type": "uint256[]"},
        ],
        "name": "executeArb",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]

# ── opBNB defaults ────────────────────────────────────────────────
DEFAULT_RPC      = "https://opbnb-mainnet-rpc.bnbchain.org"
DEFAULT_CHAIN_ID = 204


# ── Helpers ───────────────────────────────────────────────────────

def load_arbs(path: str) -> list[dict]:
    """Read the arbs.json file produced by the C++ engine."""
    p = Path(path)
    if not p.exists():
        print(f"[!] arbs file not found: {p}", file=sys.stderr)
        sys.exit(1)
    with open(p, "r") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        print(f"[!] Expected JSON array in {p}", file=sys.stderr)
        sys.exit(1)
    return data


def display_arbs(arbs: list[dict]) -> None:
    """Pretty-print the arb table to stdout."""
    print(f"\n{'='*72}")
    print(f"  Arbitrage Opportunities  ({len(arbs)} found)")
    print(f"{'='*72}")
    for i, arb in enumerate(arbs, 1):
        print(
            f"  #{i}  {arb.get('market_a_platform','?')}::{arb.get('market_a_id','?')}"
            f"  YES@{arb.get('market_a_yes_price',0):.4f}"
            f"  vs  {arb.get('market_b_platform','?')}::{arb.get('market_b_id','?')}"
            f"  YES@{arb.get('market_b_yes_price',0):.4f}"
            f"  | net Δ={arb.get('net_delta_bps',0):.1f}bps"
            f"  | gas≈{arb.get('estimated_gas_bnb',0):.6f} BNB"
            f"  | size=${arb.get('recommended_size_usdt',0):.0f}"
        )
    print(f"{'='*72}\n")


def execute_on_chain(arbs: list[dict], rpc: str, chain_id: int) -> None:
    """
    Submit each arb as an on-chain transaction via ArbExecutor.executeArb().

    NOTE: This is a *framework* — the actual CLOB order construction is
    platform-specific and needs signed limit-order data from each exchange.
    For the hackathon demo this function prints what it *would* do and
    only sends a tx if you supply real order data.
    """
    try:
        from web3 import Web3
    except ImportError:
        print("[!] web3 not installed. Run:  pip install web3", file=sys.stderr)
        sys.exit(1)

    private_key = os.getenv("PRIVATE_KEY", "")
    contract_address = (
        os.getenv("ARB_EXECUTOR_CONTRACT", "")
        or os.getenv("ARB_EXECUTOR_ADDRESS", "")
    )

    if not private_key:
        print("[!] PRIVATE_KEY not set in .env — cannot send transactions.", file=sys.stderr)
        sys.exit(1)
    if not contract_address:
        print("[!] ARB_EXECUTOR_ADDRESS not set in .env.", file=sys.stderr)
        sys.exit(1)

    w3 = Web3(Web3.HTTPProvider(rpc))
    if not w3.is_connected():
        print(f"[!] Cannot connect to RPC: {rpc}", file=sys.stderr)
        sys.exit(1)

    account = w3.eth.account.from_key(private_key)
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(contract_address),
        abi=ARB_EXECUTOR_ABI,
    )

    print(f"[*] Operator wallet: {account.address}")
    print(f"[*] ArbExecutor:     {contract_address}")
    print(f"[*] Chain:           opBNB (ID {chain_id})")
    print(f"[*] RPC:             {rpc}\n")

    for i, arb in enumerate(arbs, 1):
        if not arb.get("is_profitable", False):
            print(f"  #{i}  SKIP (not profitable)")
            continue

        size_usdt = arb.get("recommended_size_usdt", 0)
        if size_usdt <= 0:
            print(f"  #{i}  SKIP (zero size)")
            continue

        # ── Build the transaction ─────────────────────────────────
        # In a production system, you would:
        #   1. Query each CLOB exchange's REST API for the best available orders.
        #   2. Construct ordersA (buy YES on cheap side) and ordersB (buy NO).
        #   3. Call executeArb() atomically.
        #
        # For now, we log the intent and skip actual on-chain submission
        # because we need real signed order data from the exchange APIs.

        platform_a = arb.get("market_a_platform", "?")
        platform_b = arb.get("market_b_platform", "?")
        market_a   = arb.get("market_a_id", "?")
        market_b   = arb.get("market_b_id", "?")
        delta      = arb.get("net_delta_bps", 0)

        print(
            f"  #{i}  EXECUTE  {platform_a}::{market_a} ↔ {platform_b}::{market_b}"
            f"  | Δ={delta:.1f}bps  | size=${size_usdt:.0f}"
        )

        # TODO: Replace with actual order construction + tx submission
        # Example (pseudocode):
        #
        # amount_wei = w3.to_wei(size_usdt, 'mwei')  # USDT has 6 decimals on opBNB
        # condition_id_a = bytes.fromhex(market_a)    # if market_id is a condition hash
        # condition_id_b = bytes.fromhex(market_b)
        # platform_a_is_pf = (platform_a == "predictfun")
        #
        # tx = contract.functions.executeArb(
        #     amount_wei,
        #     condition_id_a,
        #     condition_id_b,
        #     platform_a_is_pf,
        #     orders_a,        # from exchange API
        #     fill_amounts_a,
        #     orders_b,
        #     fill_amounts_b,
        # ).build_transaction({
        #     'from':     account.address,
        #     'nonce':    w3.eth.get_transaction_count(account.address),
        #     'gas':      500_000,
        #     'gasPrice': w3.to_wei(0.001, 'gwei'),
        #     'chainId':  chain_id,
        # })
        # signed = w3.eth.account.sign_transaction(tx, private_key)
        # tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        # print(f"         TX: {tx_hash.hex()}")

        print(f"         → Order construction not yet implemented (needs exchange API integration)")

    print()


# ── CLI ───────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Execute arbitrage trades detected by the C++ engine.",
    )
    parser.add_argument(
        "--arbs",
        default="arbs.json",
        help="Path to arbs.json produced by the engine (default: arbs.json)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually submit transactions on-chain (default: dry-run only)",
    )
    parser.add_argument(
        "--rpc",
        default=(
            os.getenv("OPBNB_RPC_URL", "")
            or os.getenv("OPBNB_RPC", "")
            or DEFAULT_RPC
        ),
        help=f"opBNB JSON-RPC endpoint (default: {DEFAULT_RPC})",
    )
    parser.add_argument(
        "--chain-id",
        type=int,
        default=DEFAULT_CHAIN_ID,
        help=f"Chain ID (default: {DEFAULT_CHAIN_ID})",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    arbs = load_arbs(args.arbs)

    if not arbs:
        print("[*] No arb opportunities in file. Nothing to do.")
        return

    display_arbs(arbs)

    if args.execute:
        confirm = input("Submit transactions on-chain? [y/N] ").strip().lower()
        if confirm != "y":
            print("[*] Aborted.")
            return
        execute_on_chain(arbs, args.rpc, args.chain_id)
    else:
        print("[*] Dry-run complete. Pass --execute to submit transactions.\n")


if __name__ == "__main__":
    main()
