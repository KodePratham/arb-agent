"""
Ingestion/base_parser.py
────────────────────────────────────────────────────────────────────
Ollama parser factory for ingestion-time ETL.

Reads MODEL and OLLAMA_BASE_URL from .env. When MODEL is empty, the
user gets an interactive picker of locally available Ollama models.
In non-interactive mode, it falls back to "llama3".

The LLM is used only for market-text extraction at ingestion time.
It is not used in matching or execution logic.
────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time as _time
from typing import TypeVar

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# ── Config ────────────────────────────────────────────────────────

LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama").lower()
MODEL: str = os.getenv("MODEL", "")
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Will be set at runtime by pick_ollama_model() or CLI --model flag
_active_model: str = MODEL


def set_model(model_name: str) -> None:
    """Override the active model (called from CLI --model flag)."""
    global _active_model  # noqa: PLW0603
    _active_model = model_name


def get_active_model() -> str:
    """Return the currently-selected model name."""
    return _active_model


# ── Interactive Ollama model picker ──────────────────────────────


def pick_ollama_model(base_url: str | None = None) -> str:
    """
    Query ``ollama list`` and present a numbered menu so the user
    can choose which local model to use for ingestion.

    Falls back to ``"llama3"`` when:
      • stdin is not a TTY  (headless / CI)
      • no models are installed locally
      • the Ollama server is unreachable
    """
    url = base_url or OLLAMA_BASE_URL
    fallback = "llama3"

    try:
        import ollama as _ollama
        client = _ollama.Client(host=url)
        response = client.list()

        # ollama-python ≥0.4 returns a ListResponse with .models
        models_list = getattr(response, "models", None)
        if models_list is None:
            # Older API returned a dict
            models_list = response.get("models", []) if isinstance(response, dict) else []

        if not models_list:
            log.warning("No Ollama models found. Pull one first: ollama pull llama3")
            return fallback

        names: list[str] = []
        for m in models_list:
            name = getattr(m, "model", None) or (m.get("model") if isinstance(m, dict) else None) or str(m)
            names.append(name)

        if not sys.stdin.isatty():
            log.info("Non-interactive mode — using first available model: %s", names[0])
            return names[0]

        print("\n╔══════════════════════════════════════════╗")
        print("║  Available Ollama Models                 ║")
        print("╠══════════════════════════════════════════╣")
        for i, name in enumerate(names, 1):
            print(f"║  [{i}]  {name:<35s}║")
        print("╚══════════════════════════════════════════╝")
        print()

        while True:
            choice = input(f"Select model [1-{len(names)}] (or type a name): ").strip()
            if not choice:
                continue
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(names):
                    selected = names[idx]
                    print(f"→ Using model: {selected}\n")
                    return selected
                print(f"  Invalid number. Enter 1-{len(names)}.")
            else:
                # User typed a model name directly
                print(f"→ Using model: {choice}\n")
                return choice

    except ImportError:
        log.error("ollama package not installed. Run: pip install ollama")
        return fallback
    except Exception as exc:
        log.warning("Could not query Ollama at %s: %s — falling back to '%s'", url, exc, fallback)
        return fallback


# ── Ollama client ────────────────────────────────────────────────


class _OllamaParser:
    """Wraps the Ollama Python SDK for structured JSON extraction."""

    def __init__(self) -> None:
        try:
            import ollama  # noqa: F401
        except ImportError as exc:
            raise ImportError("pip install ollama") from exc

        self._base_url = OLLAMA_BASE_URL

        global _active_model  # noqa: PLW0603
        if not _active_model:
            _active_model = pick_ollama_model(self._base_url)

        self._model = _active_model
        log.info("LLM provider: Ollama (%s)  |  model: %s", self._base_url, self._model)

    def parse(
        self,
        system_prompt: str,
        user_text: str,
        response_model: type[T],
        _max_retries: int = 3,
    ) -> T:
        import ollama as _ollama

        schema_json = json.dumps(
            response_model.model_json_schema(), indent=2
        )
        full_system = (
            f"{system_prompt}\n\n"
            f"You MUST respond with a single JSON object that "
            f"strictly matches this schema:\n```json\n{schema_json}\n```\n"
            f"No markdown fences, no extra keys."
        )

        client = _ollama.Client(host=self._base_url)

        last_exc: Exception | None = None
        for attempt in range(1, _max_retries + 1):
            try:
                response = client.chat(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": full_system},
                        {"role": "user", "content": user_text},
                    ],
                    format="json",
                    options={"temperature": 0.0},
                )
                raw = response["message"]["content"]
                return response_model.model_validate_json(raw)
            except Exception as exc:
                last_exc = exc
                # Log as much detail as possible for 500-class errors
                resp_body = getattr(exc, "body", getattr(exc, "response", None))
                log.warning(
                    "Ollama request failed (attempt %d/%d): %s  |  detail: %s",
                    attempt, _max_retries, exc, resp_body,
                )
                if attempt < _max_retries:
                    backoff = 2 ** attempt  # 2s, 4s, 8s
                    log.info("Retrying in %ds…", backoff)
                    _time.sleep(backoff)

        raise RuntimeError(
            f"Ollama failed after {_max_retries} attempts: {last_exc}"
        ) from last_exc


# ── Factory ──────────────────────────────────────────────────────

_singleton: _OllamaParser | None = None


def get_parser() -> _OllamaParser:
    """
    Return a singleton Ollama parser.

    Usage::

        from Ingestion.base_parser import get_parser
        from Data.schemas import NormalizedMarket

        parser = get_parser()
        market = parser.parse(
            system_prompt="Extract market data …",
            user_text=raw_api_blob,
            response_model=NormalizedMarket,
        )
    """
    global _singleton  # noqa: PLW0603
    if _singleton is not None:
        return _singleton

    if LLM_PROVIDER != "ollama":
        raise ValueError(
            f"Unsupported LLM_PROVIDER={LLM_PROVIDER!r}. This project now supports only 'ollama'."
        )
    _singleton = _OllamaParser()
    return _singleton


# ── Convenience helper ────────────────────────────────────────────


def parse_market_text(
    raw_text: str,
    response_model: type[T],
    system_prompt: str = (
        "You are an expert data-extraction assistant.  "
        "Extract structured prediction-market data from the text below.  "
        "Return ONLY valid JSON.  Do NOT hallucinate fields that are not "
        "present in the source text."
    ),
) -> T:
    """One-call helper: route through the active LLM and return a model."""
    return get_parser().parse(system_prompt, raw_text, response_model)
