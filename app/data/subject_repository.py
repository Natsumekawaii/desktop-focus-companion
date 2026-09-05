"""Compatibility adapter for the V1 subject repository API."""

from __future__ import annotations

from app.data.database import Database
from app.data.focus_item_repository import (
    DEFAULT_FOCUS_ITEMS,
    DuplicateFocusItemError,
    FocusItemError,
    FocusItemNotFoundError,
    FocusItemRepository,
    InvalidFocusItemError,
)
from app.data.models import FocusItem, Subject

DEFAULT_SUBJECT_NAMES = tuple(name for name, _color in DEFAULT_FOCUS_ITEMS)
SubjectError = FocusItemError
InvalidSubjectNameError = InvalidFocusItemError
DuplicateSubjectError = DuplicateFocusItemError
SubjectNotFoundError = FocusItemNotFoundError


class SubjectRepository:
    """V1-shaped adapter; new runtime code uses FocusItemRepository directly."""

    def __init__(self, database: Database) -> None:
        self._focus_items = FocusItemRepository(database)

    def ensure_defaults(self) -> None:
        self._focus_items.ensure_defaults()

    def create(self, name: str) -> Subject:
        return _as_subject(self._focus_items.create(name))

    def list_active(self) -> list[Subject]:
        return [_as_subject(item) for item in self._focus_items.list_active()]

    def list_all(self) -> list[Subject]:
        return [_as_subject(item) for item in self._focus_items.list_all()]

    def get(self, subject_id: int, include_archived: bool = True) -> Subject:
        return _as_subject(self._focus_items.get(subject_id, include_archived))

    def rename(self, subject_id: int, new_name: str) -> Subject:
        return _as_subject(self._focus_items.rename(subject_id, new_name))

    def archive(self, subject_id: int) -> None:
        self._focus_items.archive(subject_id)


def _as_subject(item: FocusItem) -> Subject:
    return Subject(
        id=item.id,
        name=item.name,
        is_archived=item.is_archived,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


__all__ = [
    "DEFAULT_SUBJECT_NAMES",
    "DuplicateSubjectError",
    "InvalidSubjectNameError",
    "SubjectError",
    "SubjectNotFoundError",
    "SubjectRepository",
]
