from __future__ import annotations

from typing import Any

from app.models import CollectionPatch, IntakeDecision, PersonalWishesState


class IntakeService:
    """Validates and applies model-selected operations to structured state."""

    def apply_decision(self, previous: PersonalWishesState, decision: IntakeDecision) -> PersonalWishesState:
        if decision.needs_clarification:
            return previous.model_copy(deep=True)

        merged = previous.model_copy(deep=True)
        self._apply_text_patch(merged, "full_name", decision.full_name)
        self._apply_text_patch(merged, "home_address", decision.home_address)

        old_executor_name = merged.executor.name
        self._apply_text_patch(merged.executor, "name", decision.executor_name)
        if (
            decision.executor_name.operation == "set"
            and old_executor_name
            and old_executor_name.casefold() != (merged.executor.name or "").casefold()
            and decision.executor_relationship.operation == "keep"
        ):
            merged.executor.relationship = None
        self._apply_text_patch(merged.executor, "relationship", decision.executor_relationship)

        if decision.covers_worldwide_assets.operation == "set":
            merged.covers_worldwide_assets = decision.covers_worldwide_assets.value
            merged.worldwide_assets_status = "CONFIRMED"
        elif decision.covers_worldwide_assets.operation == "unknown":
            merged.covers_worldwide_assets = None
            merged.worldwide_assets_status = "UNKNOWN"

        if decision.has_children.operation == "set":
            merged.has_children = decision.has_children.value
        elif decision.has_children.operation == "unknown":
            merged.has_children = None

        child_operations = [item.operation for item in decision.children_names.operations]
        if decision.has_children.operation == "set" and decision.has_children.value is False:
            if any(operation in {"add", "replace"} for operation in child_operations):
                raise ValueError("Please clarify whether you have children; the message also supplied child names.")
        self._apply_name_collection(merged, decision.children_names)
        if any(operation in {"replace", "add"} for operation in child_operations) and merged.children_names:
            merged.has_children = True

        if decision.has_children.operation == "set" and decision.has_children.value is False:
            merged.children_names = []
            merged.children_names_status = "EXPLICIT_NONE"

        self._apply_model_collection(merged, "specific_gifts", decision.specific_gifts)
        self._apply_model_collection(merged, "additional_wishes", decision.additional_wishes)
        return merged

    @staticmethod
    def _apply_text_patch(target: Any, field: str, patch: Any) -> None:
        if patch.operation == "set":
            setattr(target, field, patch.value.strip())
        elif patch.operation in {"clear", "unknown"}:
            setattr(target, field, None)

    @staticmethod
    def _deduplicate(values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for raw in values:
            value = raw.strip()
            key = value.casefold()
            if value and key not in seen:
                result.append(value)
                seen.add(key)
        return result

    def _apply_name_collection(self, state: PersonalWishesState, patch: CollectionPatch) -> None:
        for item in patch.operations:
            current = list(state.children_names)
            if item.operation == "replace":
                state.children_names = self._deduplicate(item.values)
                state.children_names_status = "CONFIRMED"
            elif item.operation == "add":
                state.children_names = self._deduplicate([*current, *item.values])
                state.children_names_status = "CONFIRMED"
            elif item.operation == "remove":
                existing = {value.casefold(): value for value in current}
                missing = [value for value in item.values if value.casefold() not in existing]
                if missing:
                    raise ValueError(f"I could not find this child in the record: {', '.join(missing)}.")
                removals = {value.casefold() for value in item.values}
                state.children_names = [value for value in current if value.casefold() not in removals]
                state.children_names_status = "CONFIRMED"
            elif item.operation == "clear":
                state.children_names = []
                state.children_names_status = "EXPLICIT_NONE"
                state.has_children = False
            elif item.operation == "unknown":
                state.children_names = []
                state.children_names_status = "UNKNOWN"

    def _apply_model_collection(self, state: PersonalWishesState, field: str, patch: CollectionPatch) -> None:
        current_text = getattr(state, field)
        updated = [] if not current_text or current_text == "None specified" else [
            value.strip() for value in current_text.split(";") if value.strip()
        ]
        for item in patch.operations:
            if item.operation == "unknown":
                setattr(state, field, None)
                setattr(state, field + "_provided", True)
                setattr(state, field + "_status", "UNKNOWN")
                return
            if item.operation == "clear":
                updated = []
            elif item.operation == "replace":
                updated = self._deduplicate(item.values)
            elif item.operation == "add":
                updated = self._deduplicate([*updated, *item.values])
            elif item.operation == "remove":
                existing = {value.casefold(): value for value in updated}
                missing = [value for value in item.values if value.casefold() not in existing]
                if missing:
                    label = "gift" if field == "specific_gifts" else "wish"
                    raise ValueError(f"I could not find this {label} in the record: {', '.join(missing)}.")
                removals = {value.casefold() for value in item.values}
                updated = [value for value in updated if value.casefold() not in removals]

        if patch.operations:
            setattr(state, field, "; ".join(updated) or "None specified")
            setattr(state, field + "_provided", True)
            setattr(state, field + "_status", "CONFIRMED" if updated else "EXPLICIT_NONE")

    def missing_fields(self, state: PersonalWishesState) -> list[str]:
        questions: list[str] = []
        if not state.full_name:
            questions.append("What is your full name?")
        if not state.home_address:
            questions.append("What is your home address?")
        if state.covers_worldwide_assets is None and state.worldwide_assets_status != "UNKNOWN":
            questions.append("Does this document cover worldwide assets?")
        if state.has_children is None:
            questions.append("Do you have any children?")
        elif state.has_children and state.children_names_status == "NOT_PROVIDED" and not state.children_names:
            questions.append("Please provide the names of your children.")
        if not state.executor.name:
            questions.append("Who would you like to appoint as executor?")
        if state.executor.name and not state.executor.relationship:
            questions.append("What is the executor's relationship to you?")
        if state.specific_gifts_status == "NOT_PROVIDED":
            questions.append("Are there any specific gifts you want to include?")
        if state.additional_wishes_status == "NOT_PROVIDED":
            questions.append("Are there any additional wishes to record?")
        return questions

    @staticmethod
    def assistant_message(follow_up: list[str]) -> str:
        if follow_up:
            return follow_up[0]
        return "Thank you — I have captured the information and updated the structured record."
