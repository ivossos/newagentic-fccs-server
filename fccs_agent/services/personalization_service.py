"""Personalization tracker for onboarding and preferences."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


DEFAULT_CHECKLIST: List[Dict[str, Any]] = [
    {
        "key": "app_name",
        "label": "Confirm FCCS application name",
        "status": "pending",
    },
    {
        "key": "cube",
        "label": "Confirm cube/plan type",
        "status": "pending",
    },
    {
        "key": "pov_defaults",
        "label": "Confirm default POV settings",
        "status": "pending",
    },
    {
        "key": "dimensions",
        "label": "Confirm key dimensions (Account/Entity)",
        "status": "pending",
    },
    {
        "key": "language",
        "label": "Confirm preferred language",
        "status": "pending",
    },
    {
        "key": "reporting",
        "label": "Confirm reporting output and format",
        "status": "pending",
    },
]


class PersonalizationChecklist(Base):
    """Persistent checklist state for onboarding and preferences."""

    __tablename__ = "personalization_checklist"

    id = Column(Integer, primary_key=True)
    session_id = Column(String(255), nullable=False, index=True)
    org_id = Column(String(255), index=True)
    checklist_json = Column(Text, nullable=False)
    preferences_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


@dataclass
class ChecklistStatus:
    """Checklist status summary."""

    session_id: str
    org_id: Optional[str]
    items: List[Dict[str, Any]]
    preferences: Dict[str, Any]

    @property
    def completed(self) -> int:
        return sum(1 for item in self.items if item.get("status") == "done")

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def progress(self) -> float:
        return self.completed / self.total if self.total else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "org_id": self.org_id,
            "items": self.items,
            "preferences": self.preferences,
            "completed": self.completed,
            "total": self.total,
            "progress": round(self.progress, 3),
        }


class PersonalizationService:
    """Service for managing personalization checklists and preferences."""

    def __init__(self, db_url: str):
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def ensure_checklist(self, session_id: str, org_id: Optional[str] = None) -> ChecklistStatus:
        """Create checklist if missing and return status."""
        with self.Session() as session:
            entry = session.query(PersonalizationChecklist).filter_by(
                session_id=session_id,
                org_id=org_id
            ).first()

            if not entry:
                entry = PersonalizationChecklist(
                    session_id=session_id,
                    org_id=org_id,
                    checklist_json=json.dumps(DEFAULT_CHECKLIST),
                    preferences_json=json.dumps({})
                )
                session.add(entry)
                session.commit()

            return self._entry_to_status(entry)

    def get_status(self, session_id: str, org_id: Optional[str] = None) -> Optional[ChecklistStatus]:
        """Get checklist status for a session."""
        with self.Session() as session:
            entry = session.query(PersonalizationChecklist).filter_by(
                session_id=session_id,
                org_id=org_id
            ).first()
            if not entry:
                return None
            return self._entry_to_status(entry)

    def update_item(
        self,
        session_id: str,
        key: str,
        status: str = "done",
        value: Optional[str] = None,
        note: Optional[str] = None,
        org_id: Optional[str] = None
    ) -> Optional[ChecklistStatus]:
        """Update a checklist item status and optional value."""
        with self.Session() as session:
            entry = session.query(PersonalizationChecklist).filter_by(
                session_id=session_id,
                org_id=org_id
            ).first()

            if not entry:
                entry = PersonalizationChecklist(
                    session_id=session_id,
                    org_id=org_id,
                    checklist_json=json.dumps(DEFAULT_CHECKLIST),
                    preferences_json=json.dumps({})
                )
                session.add(entry)
                session.commit()

            items = json.loads(entry.checklist_json)
            updated = False
            for item in items:
                if item.get("key") == key:
                    item["status"] = status
                    if value is not None:
                        item["value"] = value
                    if note is not None:
                        item["note"] = note
                    updated = True
                    break

            if not updated:
                items.append({
                    "key": key,
                    "label": key.replace("_", " ").title(),
                    "status": status,
                    **({"value": value} if value is not None else {}),
                    **({"note": note} if note is not None else {}),
                })

            entry.checklist_json = json.dumps(items)
            entry.updated_at = datetime.utcnow()
            session.commit()

            return self._entry_to_status(entry)

    def set_preference(
        self,
        session_id: str,
        key: str,
        value: Any,
        org_id: Optional[str] = None
    ) -> Optional[ChecklistStatus]:
        """Set a personalization preference value."""
        with self.Session() as session:
            entry = session.query(PersonalizationChecklist).filter_by(
                session_id=session_id,
                org_id=org_id
            ).first()
            if not entry:
                entry = PersonalizationChecklist(
                    session_id=session_id,
                    org_id=org_id,
                    checklist_json=json.dumps(DEFAULT_CHECKLIST),
                    preferences_json=json.dumps({})
                )
                session.add(entry)
                session.commit()

            preferences = json.loads(entry.preferences_json or "{}")
            preferences[key] = value
            entry.preferences_json = json.dumps(preferences)
            entry.updated_at = datetime.utcnow()
            session.commit()

            return self._entry_to_status(entry)

    def get_all_preferences(
        self,
        session_id: str,
        org_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get all preferences for a session.

        Args:
            session_id: Session identifier
            org_id: Optional organization identifier

        Returns:
            Dictionary of all preferences
        """
        with self.Session() as session:
            entry = session.query(PersonalizationChecklist).filter_by(
                session_id=session_id,
                org_id=org_id
            ).first()

            if not entry:
                return {}

            return json.loads(entry.preferences_json or "{}")

    def _entry_to_status(self, entry: PersonalizationChecklist) -> ChecklistStatus:
        items = json.loads(entry.checklist_json or "[]")
        preferences = json.loads(entry.preferences_json or "{}")
        return ChecklistStatus(
            session_id=entry.session_id,
            org_id=entry.org_id,
            items=items,
            preferences=preferences
        )


_personalization_service: Optional[PersonalizationService] = None
_service_lock = threading.Lock()


def init_personalization_service(db_url: str) -> PersonalizationService:
    """Initialize personalization service singleton."""
    global _personalization_service
    with _service_lock:
        if _personalization_service is None:
            _personalization_service = PersonalizationService(db_url)
    return _personalization_service


def get_personalization_service() -> Optional[PersonalizationService]:
    """Get personalization service singleton."""
    return _personalization_service
