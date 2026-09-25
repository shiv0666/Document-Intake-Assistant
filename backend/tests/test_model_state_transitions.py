import pytest
from pydantic import ValidationError

from app.models import IntakeDecision, PersonalWishesState
from app.service import IntakeService


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


def test_compound_decision_updates_every_domain_atomically():
    result = IntakeService().apply_decision(
        PersonalWishesState(),
        decision(
            full_name={"operation": "set", "value": "Vikram Rao"},
            home_address={"operation": "set", "value": "Dehradun"},
            covers_worldwide_assets={"operation": "set", "value": True},
            has_children={"operation": "set", "value": True},
            children_names={"operations": [{"operation": "replace", "values": ["Aman", "Siya"]}]},
            executor_name={"operation": "set", "value": "Mohit"},
            executor_relationship={"operation": "set", "value": "uncle"},
            specific_gifts={"operations": [{"operation": "clear", "values": []}]},
            additional_wishes={"operations": [{"operation": "add", "values": ["travel to Paris"]}]},
        ),
    )
    assert result.full_name == "Vikram Rao"
    assert result.home_address == "Dehradun"
    assert result.covers_worldwide_assets is True
    assert result.children_names == ["Aman", "Siya"]
    assert (result.executor.name, result.executor.relationship) == ("Mohit", "uncle")
    assert result.specific_gifts_status == "EXPLICIT_NONE"
    assert result.additional_wishes == "travel to Paris"


def test_collection_operations_are_ordered_deduplicated_and_exact():
    service = IntakeService()
    state = PersonalWishesState(
        specific_gifts="watch; bicycle",
        specific_gifts_provided=True,
        specific_gifts_status="CONFIRMED",
        additional_wishes="visit Japan",
        additional_wishes_provided=True,
        additional_wishes_status="CONFIRMED",
    )
    state = service.apply_decision(
        state,
        decision(
            specific_gifts={"operations": [{"operation": "add", "values": ["Watch", "necklace"]}]},
            additional_wishes={"operations": [{"operation": "replace", "values": ["visit London"]}]},
        ),
    )
    assert state.specific_gifts == "watch; bicycle; necklace"
    assert state.additional_wishes == "visit London"

    state = service.apply_decision(
        state,
        decision(specific_gifts={"operations": [{"operation": "remove", "values": ["bicycle", "necklace"]}]}),
    )
    assert state.specific_gifts == "watch"

    state = service.apply_decision(
        state,
        decision(
            specific_gifts={
                "operations": [
                    {"operation": "remove", "values": ["watch"]},
                    {"operation": "add", "values": ["painting"]},
                ]
            }
        ),
    )
    assert state.specific_gifts == "painting"


def test_missing_removal_and_cross_field_conflict_do_not_mutate_previous_state():
    service = IntakeService()
    original = PersonalWishesState(
        has_children=True,
        children_names=["Asha"],
        children_names_status="CONFIRMED",
        specific_gifts="watch",
        specific_gifts_provided=True,
        specific_gifts_status="CONFIRMED",
    )
    with pytest.raises(ValueError, match="car"):
        service.apply_decision(
            original,
            decision(specific_gifts={"operations": [{"operation": "remove", "values": ["car"]}]}),
        )
    with pytest.raises(ValueError, match="clarify whether you have children"):
        service.apply_decision(
            original,
            decision(
                has_children={"operation": "set", "value": False},
                children_names={"operations": [{"operation": "add", "values": ["Rohan"]}]},
            ),
        )
    assert original.children_names == ["Asha"]
    assert original.specific_gifts == "watch"


def test_unknown_child_names_and_optional_unknowns_are_not_reasked():
    service = IntakeService()
    state = service.apply_decision(
        PersonalWishesState(has_children=True),
        decision(
            children_names={"operations": [{"operation": "unknown", "values": []}]},
            covers_worldwide_assets={"operation": "unknown", "value": None},
            specific_gifts={"operations": [{"operation": "unknown", "values": []}]},
            additional_wishes={"operations": [{"operation": "clear", "values": []}]},
        ),
    )
    questions = " ".join(service.missing_fields(state)).casefold()
    assert state.children_names_status == "UNKNOWN"
    assert state.worldwide_assets_status == "UNKNOWN"
    assert state.specific_gifts_status == "UNKNOWN"
    assert "names of your children" not in questions
    assert "worldwide assets" not in questions
    assert "specific gifts" not in questions
    assert "additional wishes" not in questions


def test_replacing_executor_clears_stale_relationship_unless_new_one_is_supplied():
    service = IntakeService()
    old = PersonalWishesState(executor={"name": "James", "relationship": "brother"})
    changed = service.apply_decision(
        old,
        decision(executor_name={"operation": "set", "value": "Priya"}),
    )
    assert changed.executor.name == "Priya"
    assert changed.executor.relationship is None


def test_patch_schema_rejects_inconsistent_operations():
    with pytest.raises(ValidationError):
        decision(full_name={"operation": "keep", "value": "invented"})
    with pytest.raises(ValidationError):
        decision(specific_gifts={"operations": [{"operation": "add", "values": []}]})
