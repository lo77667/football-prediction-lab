"""services/ollama_inference.py

Local Ollama-based inference pipeline for win-probability estimation.

Features:
- Primary Reasoner: llama3.1:8b
- News Analyzer: qwen2.5:7b (used to summarize/extract availability/injury signals)
- Backup: mistral-nemo:12b (used if primary fails)
- All inference is local via Ollama HTTP API (default: http://127.0.0.1:11434)
- Timeout per request: 30s
- Retry logic and exponential backoff
- SQLite caching to avoid re-processing same match
- Approximate token usage logging
- Logs errors and failures to data_errors.log via data_harvester.utils.get_logger

Usage:
  await estimate_win_probability(match_id, xg_data, news_snippets)

Return:
  dict {"prob": float, "confidence": float} on success, or raises RuntimeError on failure.

"""

# ruff: noqa: E501

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from datetime import datetime
from typing import Any

import aiohttp
from data_harvester.utils import get_logger

logger = get_logger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
CACHE_DB = os.getenv("OLLAMA_CACHE_DB", "data_harvester.db")  # reuse existing sqlite
REQUEST_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "30"))  # seconds

PRIMARY_REASONER = "llama3.1:8b"
NEWS_ANALYZER = "qwen2.5:7b"
BACKUP_REASONER = "mistral-nemo:12b"

# cache table name
CACHE_TABLE = "ollama_inference"


# heuristics for token estimation: approximate tokens = chars / 4
def _estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / 4))


def init_cache_db(path: str = CACHE_DB) -> None:
    """Ensure cache table exists in the SQLite DB."""
    try:
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        cur.executescript(
            f"""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS {CACHE_TABLE} (
                match_id TEXT PRIMARY KEY,
                model TEXT,
                prompt TEXT,
                response_text TEXT,
                prob REAL,
                confidence REAL,
                tokens_used INTEGER,
                created_at TEXT
            );
            """
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.exception("Failed to init cache DB: %s", exc)
        raise


def _get_cached(match_id: str, path: str = CACHE_DB) -> dict[str, Any] | None:
    try:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM {CACHE_TABLE} WHERE match_id = ?", (match_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return dict(row)
    except Exception as exc:
        logger.exception("Cache read failed for %s: %s", match_id, exc)
        return None


def _set_cache(
    match_id: str,
    model: str,
    prompt: str,
    response_text: str,
    prob: float,
    confidence: float,
    tokens: int,
    path: str = CACHE_DB,
) -> None:
    try:
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        cur.execute(
            f"INSERT OR REPLACE INTO {CACHE_TABLE} (match_id, model, prompt, response_text, prob, confidence, tokens_used, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",  # noqa: E501
            (
                match_id,
                model,
                prompt,
                response_text,
                prob,
                confidence,
                tokens,
                datetime.utcnow().isoformat() + "Z",
            ),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.exception("Cache write failed for %s: %s", match_id, exc)


async def _call_ollama(model: str, prompt: str, timeout: int = REQUEST_TIMEOUT) -> tuple[str, int]:
    """Call local Ollama HTTP API and return (text_response, estimated_tokens_used).

    Uses a conservative approach to extract text from the response. Supports common Ollama patterns.
    """
    url = OLLAMA_URL.rstrip("/") + "/api/generate"
    payload = {
        "model": model,
        # using a simple prompt mode; set temperature=0 for deterministic reasoning
        "prompt": prompt,
        "max_tokens": 1024,
        "temperature": 0.0,
    }

    # exponential backoff settings for transient HTTP errors
    tries = 3
    delay = 1.0

    for attempt in range(1, tries + 1):
        try:
            timeout_ctx = aiohttp.ClientTimeout(total=timeout)
            async with aiohttp.ClientSession(timeout=timeout_ctx) as session:
                async with session.post(url, json=payload) as resp:
                    text = await resp.text()
                    # best-effort: try to parse JSON and extract 'output'/'choices'
                    est_tokens = _estimate_tokens(prompt + "\n" + text)
                    # log status for monitoring
                    logger.info(
                        "Ollama model=%s status=%s tokens_est=%d", model, resp.status, est_tokens
                    )
                    return text, est_tokens
        except TimeoutError:
            logger.exception(
                "Ollama request timeout (model=%s) attempt %d/%d", model, attempt, tries
            )
            if attempt == tries:
                raise
        except Exception as exc:
            logger.exception(
                "Ollama request failed (model=%s) attempt %d/%d: %s", model, attempt, tries, exc
            )
            if attempt == tries:
                raise
            await asyncio.sleep(delay)
            delay *= 2
    # unreachable
    raise RuntimeError("Unreachable Ollama call failure")


def _build_news_prompt(news_snippets: list[str]) -> str:
    """Build prompt for news analyzer model (qwen2.5)."""
    if not news_snippets:
        return "No news snippets provided. Provide short summary 'none'."
    joined = "\n".join(f"- {s}" for s in news_snippets)
    prompt = (
        "You are a news analyzer. Given the following headlines and snippets in Arabic or English, "
        "create a concise summary (2-3 sentences) focused on injuries, suspensions, availability, and player fitness. "  # noqa: E501
        'Output ONLY the JSON object: {"news_summary": string} with minimal extra whitespace.\n\n'
        f"News:\n{joined}\n"
    )
    return prompt


def _build_reasoner_prompt(xg_data: dict[str, Any], news_summary: str) -> str:
    """Construct the deterministic prompt for the primary reasoner (llama3.1).

    Instruction: Output ONLY JSON: {"prob": float, "confidence": float}
    - prob: estimated win probability for Home Team (0..1)
    - confidence: 0..100
    """
    # xg_data can contain fields like recent_home_xg, recent_away_xg, model_probs, last5_home, last5_away, etc.  # noqa: E501
    xg_lines = []
    for k, v in xg_data.items():
        try:
            xg_lines.append(f"{k}: {v}")
        except Exception:
            xg_lines.append(f"{k}: (unprintable)")
    xg_block = "\n".join(xg_lines)

    prompt = (
        "You are a probabilistic football analyst. Using the provided expected goals (xG) trends and the news summary, "  # noqa: E501
        'estimate the win probability for the Home Team in JSON. Output ONLY the JSON object with two keys: {"prob": float, "confidence": float}. '  # noqa: E501
        "- prob should be between 0 and 1 (use 0.00..1.00).\n"
        "- confidence should be between 0 and 100 (percent).\n"
        "Be concise and strict: no extra text, no commentary, produce valid JSON only. If uncertain, supply a lower confidence.\n\n"  # noqa: E501
        "xG data (key:value):\n"
        f"{xg_block}\n\n"
        "News summary:\n"
        f"{news_summary}\n\n"
        'Return only the JSON object. Example: {"prob": 0.62, "confidence": 78.5}\n'
    )
    return prompt


async def _parse_json_response(text: str) -> dict[str, Any] | None:
    """Try to extract the first JSON object from text. Return dict or None."""
    # naive search for first { ... }
    try:
        # attempt direct parse
        stripped = text.strip()
        if stripped.startswith("{"):
            return json.loads(stripped)
        # attempt to find JSON substring
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            sub = text[start : end + 1]
            return json.loads(sub)
    except Exception as exc:
        logger.exception("JSON parse failure: %s", exc)
        return None
    return None


async def estimate_win_probability(
    match_id: str, xg_data: dict[str, Any], news_snippets: list[str], reuse_cache: bool = True
) -> dict[str, Any]:
    """High-level function to estimate win probability for Home Team for a match.

    Flow:
      - Check cache for match_id
      - (Optional) Analyze news via NEWS_ANALYZER to produce a concise summary
      - Build reasoner prompt and call PRIMARY_REASONER
      - If invalid response, retry with BACKUP_REASONER
      - Cache and return dict {"prob": float, "confidence": float, "model": used_model}
    """
    init_cache_db(CACHE_DB)
    if reuse_cache:
        cached = _get_cached(match_id, CACHE_DB)
        if cached:
            logger.info("Cache hit for match_id=%s model=%s", match_id, cached.get("model"))
            try:
                return {
                    "prob": float(cached.get("prob")),
                    "confidence": float(cached.get("confidence")),
                    "model": cached.get("model"),
                }
            except Exception:
                # if cache corrupted, continue
                logger.warning("Cache corrupted for %s, ignoring", match_id)

    # analyze news first using NEWS_ANALYZER (best-effort)
    news_summary = ""
    try:
        if news_snippets:
            news_prompt = _build_news_prompt(news_snippets)
            try:
                text, tokens = await _call_ollama(NEWS_ANALYZER, news_prompt)
                parsed = await _parse_json_response(text)
                if parsed and isinstance(parsed.get("news_summary"), str):
                    news_summary = parsed["news_summary"].strip()
                else:
                    # fallback: join snippets
                    news_summary = " ".join(news_snippets[:3])
                logger.info("News analyzed (tokens=%d) for %s", tokens, match_id)
            except Exception as exc:
                logger.exception("News analyzer failed for %s: %s", match_id, exc)
                news_summary = " ".join(news_snippets[:3])
        else:
            news_summary = "No notable news."
    except Exception as exc:
        logger.exception("Unexpected news analysis error: %s", exc)
        news_summary = "No notable news."

    # Build reasoner prompt
    reasoner_prompt = _build_reasoner_prompt(xg_data, news_summary)

    # Primary reasoner call
    used_model = PRIMARY_REASONER
    reasoner_text = None
    tokens_used = 0
    try_models = [PRIMARY_REASONER, BACKUP_REASONER]
    response = None
    for model in try_models:
        try:
            reasoner_text, tokens_used = await _call_ollama(
                model, reasoner_prompt, timeout=REQUEST_TIMEOUT
            )
            parsed = await _parse_json_response(reasoner_text)
            if parsed and isinstance(parsed, dict) and "prob" in parsed and "confidence" in parsed:
                # validate ranges
                prob = float(parsed["prob"])
                confidence = float(parsed["confidence"])
                if not (0.0 <= prob <= 1.0 and 0.0 <= confidence <= 100.0):
                    logger.warning(
                        "Reasoner returned out-of-range values model=%s parsed=%s", model, parsed
                    )
                    raise ValueError("Out of range")
                response = {"prob": prob, "confidence": confidence, "model": model}
                used_model = model
                break
            else:
                logger.warning("Invalid JSON from model %s: %s", model, reasoner_text[:200])
                # try next model
        except Exception as exc:
            logger.exception("Reasoner call failed for model %s: %s", model, exc)
            # try next
            continue

    if response is None:
        # final failure
        logger.error("All reasoners failed for match %s", match_id)
        raise RuntimeError(f"All reasoners failed for match {match_id}")

    # cache result
    try:
        _set_cache(
            match_id,
            used_model,
            reasoner_prompt,
            (reasoner_text or ""),
            response["prob"],
            response["confidence"],
            tokens_used,
            CACHE_DB,
        )
    except Exception as exc:
        logger.exception("Failed to write inference cache for %s: %s", match_id, exc)

    # log approximate token usage
    logger.info(
        "Inference complete match=%s model=%s prob=%.3f conf=%.2f tokens_est=%d",
        match_id,
        used_model,
        response["prob"],
        response["confidence"],
        tokens_used,
    )

    return response


# Example synchronous wrapper for convenience
def estimate_win_probability_sync(
    match_id: str, xg_data: dict[str, Any], news_snippets: list[str]
) -> dict[str, Any]:
    return asyncio.run(estimate_win_probability(match_id, xg_data, news_snippets))
