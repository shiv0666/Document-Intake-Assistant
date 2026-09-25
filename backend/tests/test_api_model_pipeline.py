import asyncio

import pytest
from fastapi import HTTPException

from app.llm_service import LLMRateLimitError
from app.models import ConversationRequest, IntakeDecision, LLMResponse, PersonalWishesState


def decision(**overrides):
    data = {
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
    data.update(overrides)
    return IntakeDecision.model_validate(data)


class Store:
    def __init__(self, state=None):
        self.state = state or PersonalWishesState()
        self.history = []

    async def load_session(self, session_id):
        return self.state.model_copy(deep=True), list(self.history)

    async def save_session(self, session_id, state, conversation):
        self.state = state.model_copy(deep=True)
        self.history = list(conversation)


class DecisionProvider:
    def __init__(self, decisions):
        self.decisions = iter(decisions)
        self.calls = []

    async def extract(self, message, state, conversation=None):
        self.calls.append({"message": message, "state": state, "conversation": list(conversation or [])})
        return LLMResponse(decision=next(self.decisions))


def test_every_message_uses_model_decisions_and_persists_validated_state(monkeypatch):
    import app.main as main

    store = Store()
    provider = DecisionProvider([
        decision(
            full_name={"operation": "set", "value": "Ada Lovelace"},
            home_address={"operation": "set", "value": "London"},
            has_children={"operation": "set", "value": True},
            children_names={"operations": [{"operation": "replace", "values": ["Anne", "Byron"]}]},
        ),
        decision(children_names={"operations": [{"operation": "remove", "values": ["Byron"]}]}),
        decision(
            specific_gifts={"operations": [{"operation": "add", "values": ["watch", "bicycle"]}]},
            additional_wishes={"operations": [{"operation": "add", "values": ["visit Kyoto"]}]},
        ),
        decision(specific_gifts={"operations": [{"operation": "remove", "values": ["bicycle"]}]}),
    ])
    monkeypatch.setattr(main, "mongo_service", store)
    monkeypatch.setattr(main, "get_llm_service", lambda: provider)

    async def run():
        messages = [
            "Here is a deliberately unseen free-form introduction.",
            "Please revise the family details I mentioned.",
            "There are two personal requests in this sentence.",
            "I changed my mind about one item.",
        ]
        for message in messages:
            await main.chat(ConversationRequest(session_id="model-pipeline", message=message))

    asyncio.run(run())
    assert len(provider.calls) == 4
    assert store.state.full_name == "Ada Lovelace"
    assert store.state.children_names == ["Anne"]
    assert store.state.specific_gifts == "watch"
    assert store.state.additional_wishes == "visit Kyoto"
    assert provider.calls[-1]["state"]["specific_gifts"] == "watch; bicycle"
    assert provider.calls[-1]["conversation"]


def test_model_clarification_and_invalid_removal_are_atomic(monkeypatch):
    import app.main as main

    initial = PersonalWishesState(
        full_name="Mina",
        specific_gifts="watch",
        specific_gifts_provided=True,
        specific_gifts_status="CONFIRMED",
    )
    store = Store(initial)
    provider = DecisionProvider([
        decision(needs_clarification=True, clarification_question="Which person do you mean?"),
        decision(specific_gifts={"operations": [{"operation": "remove", "values": ["car"]}]}),
    ])
    monkeypatch.setattr(main, "mongo_service", store)
    monkeypatch.setattr(main, "get_llm_service", lambda: provider)

    first = asyncio.run(main.chat(ConversationRequest(session_id="atomic", message="They should handle it.")))
    second = asyncio.run(main.chat(ConversationRequest(session_id="atomic", message="Remove the other item.")))
    assert first.status == "clarify"
    assert second.status == "clarify"
    assert store.state.full_name == "Mina"
    assert store.state.specific_gifts == "watch"


def test_rate_limit_leaves_saved_state_unchanged(monkeypatch):
    import app.main as main

    store = Store(PersonalWishesState(full_name="Safe State"))

    class LimitedProvider:
        async def extract(self, *args, **kwargs):
            raise LLMRateLimitError(12)

    monkeypatch.setattr(main, "mongo_service", store)
    monkeypatch.setattr(main, "get_llm_service", lambda: LimitedProvider())
    with pytest.raises(HTTPException) as error:
        asyncio.run(main.chat(ConversationRequest(session_id="limited", message="Any new wording")))
    assert error.value.status_code == 429
    assert error.value.headers["Retry-After"] == "12"
    assert store.state.full_name == "Safe State"
