from __future__ import annotations

from typing import Literal
FieldStatus = Literal["NOT_PROVIDED", "CONFIRMED", "EXPLICIT_NONE", "UNKNOWN"]


from pydantic import BaseModel, ConfigDict, Field, model_validator


class TextSetPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["set"]
    value: str = Field(min_length=1)


class TextEmptyPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["keep", "clear", "unknown"]
    value: None


TextPatch = TextSetPatch | TextEmptyPatch


class BooleanSetPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["set"]
    value: bool


class BooleanEmptyPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["keep", "unknown"]
    value: None


BooleanPatch = BooleanSetPatch | BooleanEmptyPatch


class CollectionValuesOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["replace", "add", "remove"]
    values: list[str] = Field(min_length=1)


class CollectionEmptyOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["clear", "unknown"]
    values: list[None] = Field(max_length=0)


CollectionOperation = CollectionValuesOperation | CollectionEmptyOperation


class CollectionPatch(BaseModel):
    """Zero or more ordered edits; an empty list means keep the saved value."""

    model_config = ConfigDict(extra="forbid")

    operations: list[CollectionOperation]

    @model_validator(mode="after")
    def validate_operation_sequence(self) -> "CollectionPatch":
        if any(item.operation == "unknown" for item in self.operations) and len(self.operations) != 1:
            raise ValueError("An unknown collection value cannot be combined with other edits.")
        return self


class IntakeDecision(BaseModel):
    """Strict, model-generated state transition. Every untouched field uses keep."""

    model_config = ConfigDict(extra="forbid")

    full_name: TextPatch
    home_address: TextPatch
    covers_worldwide_assets: BooleanPatch
    has_children: BooleanPatch
    children_names: CollectionPatch
    executor_name: TextPatch
    executor_relationship: TextPatch
    specific_gifts: CollectionPatch
    additional_wishes: CollectionPatch
    needs_clarification: bool
    clarification_question: str | None

    @model_validator(mode="after")
    def validate_clarification(self) -> "IntakeDecision":
        if self.needs_clarification and not (self.clarification_question or "").strip():
            raise ValueError("A clarification decision requires a question.")
        if not self.needs_clarification and self.clarification_question is not None:
            raise ValueError("clarification_question must be null when clarification is not needed.")
        return self


class ExecutorModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    relationship: str | None = None


class PersonalWishesState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = None
    home_address: str | None = None
    covers_worldwide_assets: bool | None = None
    worldwide_assets_status: FieldStatus = "NOT_PROVIDED"
    has_children: bool | None = None
    children_names: list[str] = Field(default_factory=list)
    executor: ExecutorModel = Field(default_factory=ExecutorModel)
    specific_gifts: str | None = None
    additional_wishes: str | None = None
    additional_wishes_add: str | None = None
    specific_gifts_provided: bool = False
    additional_wishes_provided: bool = False
    children_names_status: FieldStatus = "NOT_PROVIDED"
    specific_gifts_status: FieldStatus = "NOT_PROVIDED"
    additional_wishes_status: FieldStatus = "NOT_PROVIDED"


class LLMResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "clarify", "error"] = "ok"
    message: str = ""
    decision: IntakeDecision


class ConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str
    session_id: str = Field(min_length=1, max_length=120)


class ConversationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assistant_message: str
    state: PersonalWishesState
    structured_state: PersonalWishesState
    document: str
    session_id: str
    is_clarification_needed: bool = False
    needs_follow_up: bool = False
    follow_up_questions: list[str] = Field(default_factory=list)
    status: str = "ok"

    @property
    def full_name(self) -> str | None:
        return self.state.full_name

    @property
    def home_address(self) -> str | None:
        return self.state.home_address

    @property
    def covers_worldwide_assets(self) -> bool | None:
        return self.state.covers_worldwide_assets

    @property
    def has_children(self) -> bool | None:
        return self.state.has_children

    @property
    def children_names(self) -> list[str]:
        return self.state.children_names

    @property
    def executor(self) -> ExecutorModel:
        return self.state.executor
