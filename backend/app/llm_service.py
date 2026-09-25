from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import time
from functools import lru_cache
from typing import Any

from pydantic import ValidationError

from app.config import get_settings
from app.models import IntakeDecision, LLMResponse

logger = logging.getLogger(__name__)


class LLMServiceError(RuntimeError):
    """A safe, user-facing LLM failure."""


class LLMRateLimitError(LLMServiceError):
    def __init__(self, retry_after: int | None = None):
        self.retry_after = retry_after
        wait = f"Try again in {retry_after} seconds." if retry_after is not None else "Please wait for the provider limit to reset before retrying."
        super().__init__(f"Groq's usage limit has been reached. {wait} Your saved information has not changed.")


class BaseLLMService:
    async def extract(
        self,
        message: str,
        state: dict[str, Any],
        conversation: list[dict[str, str]] | None = None,
    ) -> LLMResponse:
        raise NotImplementedError


def _is_rate_limit(exc: Exception) -> bool:
    return (
        "rate" in type(exc).__name__.lower()
        or "429" in str(exc)
        or getattr(exc, "status_code", None) == 429
    )


def _retry_after(exc: Exception) -> int | None:
    headers = getattr(getattr(exc, "response", None), "headers", {})
    for header in ("retry-after", "x-ratelimit-reset-tokens", "x-ratelimit-reset-requests"):
        raw_value = headers.get(header)
        if raw_value is None:
            continue
        try:
            return max(1, math.ceil(float(raw_value)))
        except (TypeError, ValueError, OverflowError):
            matches = re.findall(r"([0-9]+(?:\.[0-9]+)?)(ms|s|m|h)", str(raw_value).lower())
            if matches:
                multipliers = {"ms": 0.001, "s": 1, "m": 60, "h": 3600}
                seconds = sum(float(value) * multipliers[unit] for value, unit in matches)
                return max(1, math.ceil(seconds))
    return None


class GroqLLMService(BaseLLMService):
    def __init__(self, api_key: str, model: str, fallback_model: str | None = None, max_rate_limit_wait: int = 30):
        from groq import Groq

        self.client = Groq(api_key=api_key, max_retries=0, timeout=30.0)
        self.model = model
        self.fallback_model = fallback_model if fallback_model != model else None
        self.max_rate_limit_wait = max_rate_limit_wait
        self.rate_limit_deadline = 0.0

    async def extract(
        self,
        message: str,
        state: dict[str, Any],
        conversation: list[dict[str, str]] | None = None,
    ) -> LLMResponse:
        max_output_tokens = 500
        request_count = 0
        cooldown_remaining = math.ceil(getattr(self, "rate_limit_deadline", 0) - time.monotonic())
        if cooldown_remaining > 0:
            logger.info("Skipping Groq request during provider cooldown model=%s", self.model)
            raise LLMRateLimitError(cooldown_remaining)
        system_prompt = """You are the semantic state-transition engine for a fictional Personal Wishes Document intake assistant.

Read the current structured state, recent conversation, and latest user message. Return one typed patch for every scalar field. Use `keep` for every scalar the user did not address. Each collection has an ordered `operations` array; use an empty array when that collection is untouched.

Rules:
- Capture meaning, not wording. Values contain only the requested data, without conversational prefixes, commands, articles, or filler.
- Never invent a person, relationship, address, asset scope, child, gift, or wish.
- A clear correction replaces a scalar field. A complete revised list uses `replace`. An addition uses `add`. A removal names only the items to `remove`. A request for none or all removed uses `clear`. Preserve the user's order when one message contains several collection edits.
- Resolve references such as "that", "it", and short answers from the current state and the most recent assistant question only when the reference is unambiguous.
- Keep children, gifts, and wishes separate. A recipient or relationship mentioned as part of a gift does not become a child or executor.
- Normalize family relationships to the user's relationship to the executor when it is logically explicit.
- Use `unknown` only when the user explicitly says they do not know or are unsure. Do not repeatedly ask for an explicitly unknown optional detail.
- For uncertainty, conflicting instructions, an unnamed executor, or an ambiguous reference/removal, set needs_clarification to true, ask one concise question, set every scalar patch to `keep`, and make every collection operations array empty so the update is atomic.
- Do not treat a repeated addition as a replacement. The server will deduplicate exact values and verify removals against saved state.
- Always emit an explicit requested removal, even when the target is absent from current state. The server, not the model, decides whether the removal matches a saved item and returns the appropriate clarification.
"""
        latest_assistant_turn = next(
            (
                item
                for item in reversed(conversation or [])
                if item.get("role") == "assistant"
            ),
            None,
        )
        context = {
            "current_state": state,
            "recent_conversation": [latest_assistant_turn] if latest_assistant_turn else [],
            "latest_user_message": message,
        }

        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "personal_wishes_state_transition",
                "strict": True,
                "schema": IntakeDecision.model_json_schema(),
            },
        }

        def call(model: str, repair: tuple[str, ValidationError] | None = None) -> Any:
            nonlocal request_count
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(context)},
            ]
            if repair is not None:
                previous_json, validation_error = repair
                messages.extend([
                    {"role": "assistant", "content": previous_json},
                    {
                        "role": "user",
                        "content": "The JSON matched the transport schema but violated these application invariants: "
                        + json.dumps(validation_error.errors(include_url=False))
                        + ". Return the corrected complete state transition.",
                    },
                ])
            request_count += 1
            logger.info(
                "Calling Groq request_count=%s model=%s max_completion_tokens=%s context_turns=%s",
                request_count,
                model,
                max_output_tokens,
                len(context["recent_conversation"]),
            )
            return self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0,
                max_completion_tokens=max_output_tokens,
                include_reasoning=False,
                reasoning_effort="low",
                response_format=response_format,
            )

        async def invoke(model: str, repair: tuple[str, ValidationError] | None = None) -> Any:
            try:
                return await asyncio.to_thread(call, model, repair)
            except Exception as exc:
                if getattr(exc, "status_code", None) != 400:
                    raise
                logger.warning("Groq rejected one structured generation; retrying it once")
                return await asyncio.to_thread(call, model, repair)

        try:
            completion = await invoke(self.model)
            used_model = self.model
            raw = completion.choices[0].message.content
            if not raw:
                raise ValueError("Groq returned an empty response")
            try:
                decision = IntakeDecision.model_validate(json.loads(raw))
            except ValidationError as validation_error:
                logger.warning("Model decision violated application invariants; requesting one repair")
                repaired = await invoke(used_model, (raw, validation_error))
                repaired_raw = repaired.choices[0].message.content
                if not repaired_raw:
                    raise ValueError("Groq returned an empty repaired response")
                decision = IntakeDecision.model_validate(json.loads(repaired_raw))
            logger.info("Groq response received and validated")
            return LLMResponse(
                status="clarify" if decision.needs_clarification else "ok",
                message=decision.clarification_question or "Structured state transition completed.",
                decision=decision,
            )
        except Exception as exc:
            category = "validation error" if isinstance(exc, ValueError) else "API error"
            error_name = type(exc).__name__.lower()
            if "timeout" in error_name:
                category = "timeout"
            elif _is_rate_limit(exc):
                category = "rate limit"
            elif isinstance(exc, json.JSONDecodeError):
                category = "malformed JSON"
            logger.warning("Groq request failed (%s): %s", category, type(exc).__name__)
            if category == "rate limit":
                retry_after = _retry_after(exc)
                if retry_after is not None:
                    self.rate_limit_deadline = time.monotonic() + retry_after
                raise LLMRateLimitError(retry_after) from exc
            messages = {
                "timeout": "The language service timed out. Your saved information has not changed. Please try again.",
                "validation error": "The language service returned an invalid answer. Your saved information has not changed. Please rephrase your message.",
                "malformed JSON": "The language service returned an invalid answer. Your saved information has not changed. Please rephrase your message.",
            }
            raise LLMServiceError(messages.get(category, "The language service is unavailable. Your saved information has not changed. Please try again later.")) from exc


@lru_cache
def get_llm_service() -> BaseLLMService:
    settings = get_settings()
    if not settings.groq_api_key:
        raise LLMServiceError("GROQ_API_KEY is not configured.")
    try:
        return GroqLLMService(
            settings.groq_api_key,
            settings.groq_model,
            settings.groq_fallback_model,
            settings.groq_max_rate_limit_wait_seconds,
        )
    except Exception as exc:
        logger.warning("Groq client initialization failed: %s", type(exc).__name__)
        raise LLMServiceError("The Groq service could not be initialized.") from exc
