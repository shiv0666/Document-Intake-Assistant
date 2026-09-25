from __future__ import annotations

from typing import Any
import logging

from pymongo.errors import ConfigurationError

from app.config import get_settings
from app.models import PersonalWishesState

logger = logging.getLogger(__name__)


class MongoServiceError(RuntimeError):
    """A safe, user-facing persistence failure."""


class MongoService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = None
        self.db = None

    async def connect(self) -> None:
        if not self.settings.mongodb_uri:
            logger.warning("MongoDB URI is not configured")
            return
        try:
            from motor.motor_asyncio import AsyncIOMotorClient

            self.client = AsyncIOMotorClient(self.settings.mongodb_uri)
            try:
                self.db = self.client.get_default_database()
            except ConfigurationError:
                self.db = self.client["document_intake_assistant"]
            await self.client.admin.command("ping")
            logger.info("MongoDB connection established")
        except Exception as exc:
            logger.warning("MongoDB connection failed: %s", type(exc).__name__)
            self.client = None
            self.db = None

    async def save_state(self, session_id: str, state: PersonalWishesState) -> None:
        await self.save_session(session_id, state, [])

    async def save_session(
        self,
        session_id: str,
        state: PersonalWishesState,
        conversation: list[dict[str, str]],
    ) -> None:
        if self.db is None:
            raise MongoServiceError("MongoDB is not available. Please check MONGODB_URI.")
        try:
            await self.db.documents.update_one(
                {"session_id": session_id},
                {
                    "$set": {
                        "session_id": session_id,
                        "state": state.model_dump(),
                        "conversation": conversation[-12:],
                    }
                },
                upsert=True,
            )
            logger.info("State saved")
        except Exception as exc:
            logger.warning("MongoDB save failed: %s", type(exc).__name__)
            raise MongoServiceError("The session could not be saved. Please try again.") from exc

    async def load_state(self, session_id: str) -> PersonalWishesState | None:
        state, _ = await self.load_session(session_id)
        return state

    async def load_session(
        self,
        session_id: str,
    ) -> tuple[PersonalWishesState | None, list[dict[str, str]]]:
        if self.db is None:
            raise MongoServiceError("MongoDB is not available. Please check MONGODB_URI.")
        try:
            doc = await self.db.documents.find_one({"session_id": session_id})
            if not doc:
                return None, []
            state = PersonalWishesState.model_validate(doc["state"]) if doc.get("state") else None
            conversation = [
                item for item in doc.get("conversation", [])
                if isinstance(item, dict) and isinstance(item.get("role"), str) and isinstance(item.get("content"), str)
            ]
            return state, conversation
        except Exception as exc:
            logger.warning("MongoDB load failed: %s", type(exc).__name__)
            raise MongoServiceError("The session could not be loaded. Please try again.") from exc
