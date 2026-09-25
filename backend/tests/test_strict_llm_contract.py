import asyncio
import json
from types import SimpleNamespace

import pytest

from app.llm_service import GroqLLMService, LLMRateLimitError, LLMServiceError
from app.models import PersonalWishesState


def keep_decision(**overrides):
    payload = {
        "full_name": {"operation": "keep", "value": None},
        "home_address": {"operation": "keep", "value": None},
        "covers_worldwide_assets": {"operation": "keep", "value": None},
        "has_children": {"operation": "keep", "value": None},
        "children_names": {"operations": []},
        "executor_name": {"operation": "keep", "value": None},
        "executor_relationship": {"operation": "keep", "value": None},
        "specific_gifts": {"operations": []},
        "additional_wishes": {"operations": []},
        "needs_clarification": False,
        "clarification_question": None,
    }
    payload.update(overrides)
    return payload


class FakeCompletions:
    def __init__(self, payload, primary_error=None):
        self.payload = payload
        self.primary_error = primary_error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.primary_error and len(self.calls) == 1:
            raise self.primary_error
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(self.payload)))]
        )


class SequenceCompletions:
    def __init__(self, payloads):
        self.payloads = iter(payloads)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(next(self.payloads))))]
        )


class RateError(Exception):
    status_code = 429

    def __init__(self, retry_after="4"):
        self.response = SimpleNamespace(headers={"retry-after": retry_after})
        super().__init__("429 rate limit")


class BadGenerationError(Exception):
    status_code = 400


def make_service(completions, fallback="openai/gpt-oss-20b"):
    service = GroqLLMService.__new__(GroqLLMService)
    service.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    service.model = "openai/gpt-oss-120b"
    service.fallback_model = fallback
    return service


def test_provider_receives_state_history_and_strict_json_schema():
    completions = FakeCompletions(
        keep_decision(
            executor_name={"operation": "set", "value": "Nikhil"},
            executor_relationship={"operation": "set", "value": "friend"},
        )
    )
    service = make_service(completions)
    state = PersonalWishesState(full_name="Leena")
    response = asyncio.run(
        service.extract(
            "Please appoint the person I just described.",
            state.model_dump(),
            [{"role": "assistant", "content": "Who should be executor?"}],
        )
    )
    assert response.decision.executor_name.value == "Nikhil"
    sent = completions.calls[0]
    assert sent["response_format"]["type"] == "json_schema"
    assert sent["response_format"]["json_schema"]["strict"] is True
    assert sent["include_reasoning"] is False
    assert sent["max_completion_tokens"] == 500
    assert len(completions.calls) == 1
    context = json.loads(sent["messages"][1]["content"])
    assert context["current_state"]["full_name"] == "Leena"
    assert len(context["recent_conversation"]) == 1
    assert context["recent_conversation"][-1]["content"] == "Who should be executor?"


def test_rate_limited_primary_returns_safe_error_without_fallback():
    completions = FakeCompletions(keep_decision(), primary_error=RateError())
    with pytest.raises(LLMRateLimitError) as error:
        asyncio.run(make_service(completions).extract("hello", PersonalWishesState().model_dump()))
    assert error.value.retry_after == 4
    assert [call["model"] for call in completions.calls] == ["openai/gpt-oss-120b"]


def test_one_structured_generation_rejection_is_retried():
    completions = FakeCompletions(keep_decision(), primary_error=BadGenerationError("generation rejected"))
    response = asyncio.run(make_service(completions).extract("hello", PersonalWishesState().model_dump()))
    assert response.decision is not None
    assert [call["model"] for call in completions.calls] == [
        "openai/gpt-oss-120b",
        "openai/gpt-oss-120b",
    ]


def test_rate_limit_is_safe_when_no_fallback_is_configured():
    completions = FakeCompletions(keep_decision(), primary_error=RateError("9"))
    with pytest.raises(LLMRateLimitError) as error:
        asyncio.run(make_service(completions, fallback=None).extract("hello", PersonalWishesState().model_dump()))
    assert error.value.retry_after == 9


def test_invalid_model_semantics_are_rejected_even_if_json_is_valid():
    bad = keep_decision(full_name={"operation": "keep", "value": "made up"})
    with pytest.raises(LLMServiceError, match="invalid answer"):
        asyncio.run(make_service(FakeCompletions(bad)).extract("hello", PersonalWishesState().model_dump()))


def test_semantically_invalid_first_decision_gets_one_model_repair():
    bad = keep_decision(full_name={"operation": "keep", "value": "made up"})
    good = keep_decision(full_name={"operation": "set", "value": "Maya Sen"})
    completions = SequenceCompletions([bad, good])
    response = asyncio.run(make_service(completions).extract("Please update it.", PersonalWishesState().model_dump()))
    assert response.decision.full_name.value == "Maya Sen"
    assert len(completions.calls) == 2
    assert "application invariants" in completions.calls[1]["messages"][-1]["content"]
