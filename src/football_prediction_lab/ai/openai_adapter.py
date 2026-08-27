"""Optional OpenAI-compatible adapter for guarded pre-match analysis."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .guardrails import AIAnalysisError, AnalysisRequest, validate_ai_output

Transport = Callable[[str, dict[str, str], bytes, float], bytes]


class AIProviderError(AIAnalysisError):
    """Raised when the provider cannot return a usable JSON response."""


def _default_transport(url: str, headers: dict[str, str], body: bytes, timeout: float) -> bytes:
    request = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read()
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise AIProviderError(f"AI provider request failed: {type(error).__name__}") from error


def _response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "schema_version": {"type": "string", "enum": ["ai-analysis-v1"]},
            "match_id": {"type": "string"},
            "as_of_utc": {"type": "string"},
            "status": {"type": "string", "enum": ["supported", "insufficient_evidence"]},
            "signals": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "value": {"type": "string"},
                        "evidence_ids": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["name", "value", "evidence_ids"],
                    "additionalProperties": False,
                },
            },
            "missing_information": {"type": "array", "items": {"type": "string"}},
            "unsupported_claims": {"type": "array", "items": {"type": "string"}},
            "limitations": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "schema_version",
            "match_id",
            "as_of_utc",
            "status",
            "signals",
            "missing_information",
            "unsupported_claims",
            "limitations",
        ],
        "additionalProperties": False,
    }


def _safe_context(context: dict[str, Any]) -> dict[str, Any]:
    """Allow only pre-match context and reject labels or provider secrets."""
    serialized = json.dumps(context, ensure_ascii=False, sort_keys=True)
    lowered = serialized.lower()
    forbidden = ("matchresults", '"result"', '"target"', '"odds"', '"ev"', '"roi"', '"stake"')
    if any(marker in lowered for marker in forbidden):
        raise AIAnalysisError("analysis context contains forbidden or post-match data")
    return context


class OpenAIJSONAnalyzer:
    """Call an OpenAI-compatible model and validate its response fail-closed."""

    def __init__(
        self,
        *,
        model: str = "gpt-5-mini",
        api_base: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
        transport: Transport | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.model = model
        configured_base = os.environ.get("OPENAI_API_BASE", "") if api_base is None else api_base
        configured_key = os.environ.get("OPENAI_API_KEY", "") if api_key is None else api_key
        self.api_base = configured_base.rstrip("/")
        self.api_key = configured_key
        self.timeout_seconds = timeout_seconds
        self.transport = transport or _default_transport

    def analyze(self, request: AnalysisRequest, *, context: dict[str, Any]) -> Any:
        request.validate_cutoff()
        safe_context = _safe_context(context)
        if not self.api_base or not self.api_key:
            raise AIProviderError("AI provider credentials are not configured")
        request_payload = {
            "match_id": request.match_id,
            "kickoff_utc": request.kickoff_utc.isoformat(),
            "as_of_utc": request.as_of_utc.isoformat(),
            "evidence": [item.model_dump(mode="json") for item in request.evidence],
            "context": safe_context,
        }
        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "حلل سياق ما قبل المباراة فقط. لا تخترع حقائق. "
                        "أخرج JSON مطابقاً للمخطط، واربط كل إشارة بدليل موجود. "
                        "إذا كان السياق يثبت fixture فقط ولا يثبت إصابة أو تشكيلاً أو أداءً، "
                        "أخرج status=insufficient_evidence وsignals=[] واذكر النقص. "
                        "لا تخرج نتيجة أو احتمالاً أو odds أو توصية مراهنة."
                    ),
                },
                {"role": "user", "content": json.dumps(request_payload, ensure_ascii=False)},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "guarded_pre_match_analysis",
                    "strict": True,
                    "schema": _response_schema(),
                },
            },
            "max_completion_tokens": 1200,
            "reasoning": {"effort": "minimal"},
        }
        try:
            raw_response = self.transport(
                f"{self.api_base}/chat/completions",
                {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                self.timeout_seconds,
            )
            decoded = json.loads(raw_response)
            content = decoded["choices"][0]["message"]["content"]
            output = json.loads(content) if isinstance(content, str) else content
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
            raise AIProviderError("AI provider response was not valid JSON chat output") from error
        return validate_ai_output(output, request)
