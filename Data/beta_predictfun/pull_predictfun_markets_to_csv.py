from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from datetime import datetime

import httpx
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _headers(api_key: str) -> dict[str, str]:
    headers: dict[str, str] = {"Accept": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def fetch_all_markets(base_url: str, api_key: str, page_size: int, status: str | None) -> list[dict]:
    markets: list[dict] = []
    cursor: str | None = None

    with httpx.Client(base_url=base_url, headers=_headers(api_key), timeout=30) as client:
        while True:
            params: dict[str, str] = {"first": str(page_size)}
            if status:
                params["status"] = status
            if cursor:
                params["after"] = cursor

            response = client.get("/v1/markets", params=params)
            if response.status_code == 401:
                raise RuntimeError(
                    "PredictFun API returned 401 Unauthorized. Set PREDICTFUN_API_KEY in .env "
                    "or pass --api-key <KEY>."
                )
            response.raise_for_status()
            payload = response.json()

            page = payload.get("data", [])
            if not isinstance(page, list):
                break

            markets.extend(page)
            cursor = payload.get("cursor")

            if not cursor or len(page) < page_size:
                break

    return markets


def _to_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def write_csv(markets: list[dict], output_path: Path) -> None:
    fields: list[str] = []
    for market in markets:
        for key in market.keys():
            if key not in fields:
                fields.append(key)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for market in markets:
            writer.writerow({key: _to_cell(market.get(key)) for key in fields})


def write_json(markets: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(markets, ensure_ascii=False, indent=2), encoding="utf-8")


def _fallback_path_if_locked(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return path.with_name(f"{path.stem}_{stamp}{path.suffix}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pull PredictFun OPEN markets into JSON and CSV files.")
    parser.add_argument(
        "--base-url",
        default=os.getenv("PREDICTFUN_API_BASE", "https://api.predict.fun"),
        help="PredictFun API base URL.",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("PREDICTFUN_API_KEY", ""),
        help="PredictFun API key (defaults to PREDICTFUN_API_KEY from environment/.env).",
    )
    parser.add_argument(
        "--status",
        default="OPEN",
        help="Optional status filter (default: OPEN).",
    )
    parser.add_argument("--page-size", type=int, default=50, help="Items per page.")
    default_dir = Path(__file__).resolve().parent
    parser.add_argument(
        "--csv-output",
        default=str(default_dir / "predictfun_markets.csv"),
        help="Output CSV path.",
    )
    parser.add_argument(
        "--json-output",
        default=str(default_dir / "predictfun_markets.json"),
        help="Output JSON path.",
    )
    args = parser.parse_args()

    try:
        markets = fetch_all_markets(args.base_url, args.api_key, args.page_size, args.status)
        csv_path = Path(args.csv_output)
        json_path = Path(args.json_output)
        try:
            write_csv(markets, csv_path)
        except PermissionError:
            csv_path = _fallback_path_if_locked(csv_path)
            write_csv(markets, csv_path)

        try:
            write_json(markets, json_path)
        except PermissionError:
            json_path = _fallback_path_if_locked(json_path)
            write_json(markets, json_path)

        print(f"Wrote {len(markets)} markets to {csv_path} and {json_path}")
    except RuntimeError as error:
        print(str(error))
    except httpx.HTTPError as error:
        print(f"Request failed: {error}")


if __name__ == "__main__":
    main()