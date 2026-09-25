from __future__ import annotations

from app.models import PersonalWishesState


class DocumentGenerator:
    @staticmethod
    def _display_status(status: str, confirmed_value: str | None) -> str:
        if status == "CONFIRMED":
            return confirmed_value or "None specified"
        if status == "UNKNOWN":
            return "Unknown"
        if status == "EXPLICIT_NONE":
            return "None specified"
        return "Not yet provided"

    @staticmethod
    def generate(state: PersonalWishesState) -> str:
        worldwide_assets = DocumentGenerator._display_status(
            state.worldwide_assets_status,
            None
            if state.covers_worldwide_assets is None
            else "Yes"
            if state.covers_worldwide_assets
            else "No",
        )
        children_names = DocumentGenerator._display_status(
            state.children_names_status,
            ", ".join(state.children_names),
        )
        specific_gifts = DocumentGenerator._display_status(
            state.specific_gifts_status,
            state.specific_gifts,
        )
        additional_wishes = DocumentGenerator._display_status(
            state.additional_wishes_status,
            state.additional_wishes,
        )

        lines = [
            "PERSONAL WISHES DOCUMENT",
            "Fictional — Not Legal Advice",
            "",
            "This is a fictional document prepared for demonstration purposes only.",
            "",
            f"Full Name: {state.full_name or 'Not yet provided'}",
            f"Home Address: {state.home_address or 'Not yet provided'}",
            f"Covers Worldwide Assets: {worldwide_assets}",
            f"Has Children: {'Yes' if state.has_children else 'No' if state.has_children is False else 'Not yet provided'}",
            f"Children Names: {children_names}",
            f"Executor: {state.executor.name or 'Not yet provided'}",
            f"Executor Relationship: {state.executor.relationship or 'Not yet provided'}",
            f"Specific Gifts: {specific_gifts}",
            f"Additional Wishes: {additional_wishes}",
            "",
            "This document is fictional and does not constitute legal advice.",
        ]
        return "\n".join(lines)
