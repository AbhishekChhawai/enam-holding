"""LLM access with three cost controls built in:

1. Routing   - 'fast' (Flash-Lite) for bulk extraction, 'reason' (Flash) only where judgement is needed.
2. Caching   - every response is stored by hash(model, purpose, prompt, inputs); re-runs are free.
3. Degrading - with no API key the app still works; LLM-only features report themselves unavailable.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Literal, TypeVar

from pydantic import BaseModel
from sqlalchemy import func, select

from .config import GEMINI_API_KEY, LLM_TIMEOUT_S, MODEL_FAST, MODEL_REASON
from .db import LLMCall, session_scope, utcnow

log = logging.getLogger("finn.llm")
T = TypeVar("T", bound=BaseModel)
Tier = Literal["fast", "reason"]

_client = None


class LLMUnavailable(RuntimeError):
    pass


def available() -> bool:
    return bool(GEMINI_API_KEY)


def _get_client():
    global _client
    if _client is None:
        if not GEMINI_API_KEY:
            raise LLMUnavailable("GEMINI_API_KEY is not set")
        from google import genai
        from google.genai import types
        _client = genai.Client(api_key=GEMINI_API_KEY, http_options=types.HttpOptions(timeout=LLM_TIMEOUT_S * 1000))
    return _client


def model_for(tier: Tier) -> str:
    return MODEL_REASON if tier == "reason" else MODEL_FAST


def _key(model: str, purpose: str, system: str, prompt: str, blobs: list[bytes]) -> str:
    h = hashlib.sha256()
    for part in (model, purpose, system, prompt):
        h.update(part.encode())
        h.update(b"\x00")
    for b in blobs:
        h.update(hashlib.sha256(b).digest())
    return h.hexdigest()


def generate(schema: type[T], *, tier: Tier, purpose: str, prompt: str, system: str = "",
             pdf_bytes: list[bytes] | None = None, max_output_tokens: int = 4096) -> T:
    """Structured generation. Returns a validated instance of `schema`."""
    model = model_for(tier)
    blobs = pdf_bytes or []
    key = _key(model, purpose + ":" + schema.__name__, system, prompt, blobs)

    with session_scope() as s:
        hit = s.get(LLMCall, key)
        if hit is not None:
            hit.cache_hits += 1
            return schema.model_validate(hit.response)

    client = _get_client()
    from google.genai import types

    contents: list = [types.Part.from_bytes(data=b, mime_type="application/pdf") for b in blobs]
    contents.append(prompt)
    tokens = max_output_tokens
    last: Exception | None = None
    for attempt in range(5):
        config = types.GenerateContentConfig(
            system_instruction=system or None,
            response_mime_type="application/json",
            response_schema=schema,
            max_output_tokens=tokens,
        )
        try:
            resp = client.models.generate_content(model=model, contents=contents, config=config)
            parsed = resp.parsed if isinstance(resp.parsed, schema) else None
            if parsed is None:
                finish = str(getattr((resp.candidates or [None])[0], "finish_reason", "") or "")
                try:
                    parsed = schema.model_validate_json(resp.text or "")
                except Exception:
                    # Newer models spend output tokens on reasoning; a cut-off reply gets more room, not the same limit.
                    if "MAX_TOKENS" in finish and tokens < 16384:
                        tokens = min(tokens * 4, 16384)
                        continue
                    raise
            usage = getattr(resp, "usage_metadata", None)
            with session_scope() as s:
                s.merge(LLMCall(
                    key=key, model=model, purpose=purpose, response=parsed.model_dump(mode="json"),
                    input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
                    output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
                    created_at=utcnow(),
                ))
            return parsed
        except Exception as e:  # noqa: BLE001
            last = e
            msg = str(e)
            if "RESOURCE_EXHAUSTED" in msg or "429" in msg or "503" in msg or "UNAVAILABLE" in msg:
                time.sleep(4 * (attempt + 1))
                continue
            if attempt == 0 and ("validation" in msg.lower() or "json" in msg.lower()):
                continue  # one retry on malformed output
            break
    msg = str(last).replace(GEMINI_API_KEY, "***") if GEMINI_API_KEY else str(last)
    raise RuntimeError(f"LLM call failed ({purpose}, {model}): {msg[:300]}")


def usage_summary() -> dict:
    """Cost ledger for the settings screen: calls, tokens and cache hits per model."""
    with session_scope() as s:
        rows = s.execute(
            select(LLMCall.model, func.count(), func.sum(LLMCall.input_tokens),
                   func.sum(LLMCall.output_tokens), func.sum(LLMCall.cache_hits))
            .group_by(LLMCall.model)
        ).all()
        by_purpose = s.execute(
            select(LLMCall.purpose, func.count()).group_by(LLMCall.purpose)
        ).all()
    models = [
        {"model": m, "calls": c, "input_tokens": int(i or 0), "output_tokens": int(o or 0), "cache_hits": int(h or 0)}
        for m, c, i, o, h in rows
    ]
    return {
        "llm_enabled": available(),
        "routing": {"fast": MODEL_FAST, "reason": MODEL_REASON},
        "models": models,
        "by_purpose": {p: c for p, c in by_purpose},
        "total_calls": sum(m["calls"] for m in models),
        "total_cache_hits": sum(m["cache_hits"] for m in models),
    }


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
