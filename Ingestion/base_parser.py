"""
Ingestion/base_parser.py
────────────────────────────────────────────────────────────────────
Dynamic LLM routing factory.

Reads LLM_PROVIDER and MODEL from .env and returns the appropriate
client.  Supports:

  • groq   → Groq cloud API  (requires GROQ_API_KEY)
  • ollama → local Ollama     (requires OLLAMA_BASE_URL)

The LLM is used ONLY for initial ETL parsing of unstructured market
text.  It never performs live trading logic or date/time math.
────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, TypeVar

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# ── Config ────────────────────────────────────────────────────────

LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "groq").lower()
MODEL: str = os.getenv("MODEL", "llama3-8b-8192")
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


# ── Groq client ──────────────────────────────────────────────────


class _GroqParser:
    """Wraps the Groq Python SDK for structured JSON extraction."""

    def __init__(self) -> None:
        try:
            from groq import Groq
        except ImportError as exc:
            raise ImportError("pip install groq") from exc

        if not GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is not set in .env")

        self._client = Groq(api_key=GROQ_API_KEY)
        log.info("LLM provider: Groq  |  model: %s", MODEL)

    def parse(
        self,
        system_prompt: str,
        user_text: str,
        response_model: type[T],
    ) -> T:
        """
        Send *user_text* through the LLM with a system prompt that
        enforces JSON output matching *response_model*.
        """
        schema_json = json.dumps(
            response_model.model_json_schema(), indent=2
        )
        full_system = (
            f"{system_prompt}\n\n"
            f"You MUST respond with a single JSON object that "
            f"strictly matches this schema:\n```json\n{schema_json}\n```\n"
            f"No markdown fences, no extra keys."
        )

        chat = self._client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": full_system},
                {"role": "user", "content": user_text},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )

        raw = chat.choices[0].message.content or "{}"
        return response_model.model_validate_json(raw)


# ── Ollama client ────────────────────────────────────────────────


class _OllamaParser:
    """Wraps the Ollama Python SDK for structured JSON extraction."""

    def __init__(self) -> None:
        try:
            import ollama  # noqa: F401
        except ImportError as exc:
            raise ImportError("pip install ollama") from exc

        self._base_url = OLLAMA_BASE_URL
        log.info("LLM provider: Ollama (%s)  |  model: %s", self._base_url, MODEL)

    def parse(
        self,
        system_prompt: str,
        user_text: str,
        response_model: type[T],
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
        response = client.chat(
            model=MODEL,
            messages=[
                {"role": "system", "content": full_system},
                {"role": "user", "content": user_text},
            ],
            format="json",
            options={"temperature": 0.0},
        )

        raw = response["message"]["content"]
        return response_model.model_validate_json(raw)


# ── Factory ──────────────────────────────────────────────────────

_ParserType = _GroqParser | _OllamaParser
_singleton: _ParserType | None = None


def get_parser() -> _ParserType:
    """
    Return a singleton LLM parser routed by LLM_PROVIDER env var.

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

    if LLM_PROVIDER == "groq":
        _singleton = _GroqParser()
    elif LLM_PROVIDER == "ollama":
        _singleton = _OllamaParser()
    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER={LLM_PROVIDER!r}. Use 'groq' or 'ollama'."
        )
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
