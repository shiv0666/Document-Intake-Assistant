from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.document_generator import DocumentGenerator
from app.llm_service import LLMRateLimitError, LLMServiceError, get_llm_service
from app.models import ConversationRequest, ConversationResponse, PersonalWishesState
from app.mongo_service import MongoService, MongoServiceError
from app.service import IntakeService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

service = IntakeService()
mongo_service = MongoService()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await mongo_service.connect()
    yield


app = FastAPI(title="Document Intake Assistant", lifespan=lifespan)
allowed_origins = [origin.strip() for origin in get_settings().frontend_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def make_response(
    session_id: str,
    state: PersonalWishesState,
    assistant_message: str,
    *,
    clarification: bool = False,
    follow_up: list[str] | None = None,
    status: str = "ok",
) -> ConversationResponse:
    questions = follow_up or []
    return ConversationResponse(
        assistant_message=assistant_message,
        state=state,
        structured_state=state,
        document=DocumentGenerator.generate(state),
        session_id=session_id,
        is_clarification_needed=clarification,
        needs_follow_up=bool(questions),
        follow_up_questions=questions,
        status=status,
    )


async def save_clarification(
    request: ConversationRequest,
    state: PersonalWishesState,
    conversation: list[dict[str, str]],
    question: str,
) -> ConversationResponse:
    conversation.extend([
        {"role": "user", "content": request.message.strip()},
        {"role": "assistant", "content": question},
    ])
    await mongo_service.save_session(request.session_id, state, conversation)
    return make_response(
        request.session_id,
        state,
        question,
        clarification=True,
        follow_up=[question],
        status="clarify",
    )


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "mongo_configured": mongo_service.db is not None, "app_revision": "model-patch-v8"}


@app.get("/api/state")
async def get_state(session_id: str) -> PersonalWishesState:
    try:
        return await mongo_service.load_state(session_id) or PersonalWishesState()
    except MongoServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/chat", response_model=ConversationResponse)
async def chat(request: ConversationRequest) -> ConversationResponse:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Please enter a message.")

    try:
        loaded_state, conversation = await mongo_service.load_session(request.session_id)
        current_state = loaded_state or PersonalWishesState()
        llm_response = await get_llm_service().extract(
            message,
            current_state.model_dump(),
            conversation=conversation,
        )
    except LLMRateLimitError as exc:
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after is not None else None
        raise HTTPException(status_code=429, detail=str(exc), headers=headers) from exc
    except (MongoServiceError, LLMServiceError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    decision = llm_response.decision
    if decision is None:
        raise HTTPException(status_code=422, detail="The language service returned no structured state transition.")

    if decision.needs_clarification:
        question = decision.clarification_question or "Could you clarify that information?"
        try:
            return await save_clarification(request, current_state, conversation, question)
        except MongoServiceError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        updated_state = service.apply_decision(current_state, decision)
    except ValueError as exc:
        try:
            return await save_clarification(request, current_state, conversation, str(exc))
        except MongoServiceError as storage_error:
            raise HTTPException(status_code=503, detail=str(storage_error)) from storage_error

    follow_up = service.missing_fields(updated_state)
    assistant_message = service.assistant_message(follow_up)
    conversation.extend([
        {"role": "user", "content": message},
        {"role": "assistant", "content": assistant_message},
    ])
    try:
        await mongo_service.save_session(request.session_id, updated_state, conversation)
    except MongoServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    logger.info("Validated model patch and saved state")
    return make_response(
        request.session_id,
        updated_state,
        assistant_message,
        follow_up=follow_up,
    )


@app.get("/api/document")
async def get_document(session_id: str = "default") -> dict[str, str]:
    try:
        state = await mongo_service.load_state(session_id) or PersonalWishesState()
    except MongoServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"document": DocumentGenerator.generate(state)}
