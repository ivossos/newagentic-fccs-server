"""Valid Intersections Cache - Pre-computed POV combinations for reliable queries.

Caches discovered valid POV intersections from smart_infer operations to:
- Avoid repeated probing for the same combinations
- Provide fast lookups for common entity/account/cost center combinations
- Track which intersections have data vs. are blocked/empty
- Learn from user queries which POVs are commonly accessed

The cache operates at two levels:
- L1: In-memory LRU cache for fastest access
- L2: SQLite persistent storage for durability
"""

import hashlib
import json
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional, List, Dict

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Text, Boolean, Index,
    create_engine, func
)
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class IntersectionStatus(str, Enum):
    """Status of a POV intersection."""
    VALID = "valid"
    EMPTY = "empty"
    BLOCKED = "blocked"
    INVALID = "invalid"
    UNKNOWN = "unknown"


@dataclass
class POVIntersection:
    """Represents a Point of View intersection."""
    entity: str
    scenario: str = "Actual"
    year: str = "FY24"
    period: str = "Jan"
    account: Optional[str] = None
    consolidation: Optional[str] = None
    currency: Optional[str] = None
    movement: Optional[str] = None
    view: Optional[str] = None
    custom_dims: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "entity": self.entity,
            "scenario": self.scenario,
            "year": self.year,
            "period": self.period,
        }
        if self.account:
            result["account"] = self.account
        if self.consolidation:
            result["consolidation"] = self.consolidation
        if self.currency:
            result["currency"] = self.currency
        if self.movement:
            result["movement"] = self.movement
        if self.view:
            result["view"] = self.view
        if self.custom_dims:
            result.update(self.custom_dims)
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'POVIntersection':
        known_keys = {"entity", "scenario", "year", "period", "account",
                      "consolidation", "currency", "movement", "view"}
        custom_dims = {k: v for k, v in data.items() if k not in known_keys}
        return cls(
            entity=data.get("entity", ""),
            scenario=data.get("scenario", "Actual"),
            year=data.get("year", "FY24"),
            period=data.get("period", "Jan"),
            account=data.get("account"),
            consolidation=data.get("consolidation"),
            currency=data.get("currency"),
            movement=data.get("movement"),
            view=data.get("view"),
            custom_dims=custom_dims
        )

    def hash_key(self) -> str:
        content = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:32]


class ValidIntersection(Base):
    """Persistent storage for valid POV intersections."""
    __tablename__ = "valid_intersections"

    id = Column(Integer, primary_key=True)
    pov_hash = Column(String(32), nullable=False, unique=True, index=True)
    pov_json = Column(Text, nullable=False)
    entity = Column(String(255), nullable=False, index=True)
    scenario = Column(String(100), index=True)
    year = Column(String(20), index=True)
    account = Column(String(255), index=True)
    status = Column(String(20), default="valid")
    has_data = Column(Boolean, default=True)
    last_value = Column(Float)
    access_count = Column(Integer, default=1)
    last_accessed = Column(DateTime, default=datetime.utcnow)
    discovered_by = Column(String(50))
    discovered_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('ix_valid_entity_account', 'entity', 'account'),
        Index('ix_valid_entity_scenario_year', 'entity', 'scenario', 'year'),
    )


class IntersectionAccessLog(Base):
    """Log of intersection access for pattern analysis."""
    __tablename__ = "intersection_access_log"

    id = Column(Integer, primary_key=True)
    pov_hash = Column(String(32), nullable=False, index=True)
    session_id = Column(String(255), index=True)
    tool_name = Column(String(100))
    success = Column(Boolean)
    latency_ms = Column(Float)
    accessed_at = Column(DateTime, default=datetime.utcnow, index=True)


class LRUCache:
    """Thread-safe LRU cache for in-memory intersection lookups."""

    def __init__(self, capacity: int = 1000):
        self.capacity = capacity
        self.cache: OrderedDict[str, Dict] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Dict]:
        with self._lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
            return None

    def put(self, key: str, value: Dict):
        with self._lock:
            if key in self.cache:
                self.cache.move_to_end(key)
            self.cache[key] = value
            if len(self.cache) > self.capacity:
                self.cache.popitem(last=False)

    def remove(self, key: str):
        with self._lock:
            self.cache.pop(key, None)

    def clear(self):
        with self._lock:
            self.cache.clear()

    def __len__(self) -> int:
        return len(self.cache)


class ValidIntersectionsService:
    """Service for managing valid POV intersection cache."""

    DEFAULT_TTL_HOURS = 168  # 7 days

    def __init__(self, db_url: str, l1_capacity: int = 1000, ttl_hours: int = 168):
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.l1_cache = LRUCache(capacity=l1_capacity)
        self.ttl = timedelta(hours=ttl_hours)

    def is_valid(self, pov: POVIntersection, check_freshness: bool = True) -> Optional[IntersectionStatus]:
        """Check if a POV intersection is valid."""
        pov_hash = pov.hash_key()

        cached = self.l1_cache.get(pov_hash)
        if cached:
            if check_freshness:
                cached_at = datetime.fromisoformat(cached["cached_at"])
                if datetime.utcnow() - cached_at > self.ttl:
                    self.l1_cache.remove(pov_hash)
                    return None
            return IntersectionStatus(cached["status"])

        try:
            with self.Session() as session:
                entry = session.query(ValidIntersection).filter_by(pov_hash=pov_hash).first()
                if entry:
                    if check_freshness and entry.last_accessed:
                        if datetime.utcnow() - entry.last_accessed > self.ttl:
                            return None

                    self.l1_cache.put(pov_hash, {
                        "status": entry.status,
                        "has_data": entry.has_data,
                        "cached_at": datetime.utcnow().isoformat()
                    })
                    entry.access_count += 1
                    entry.last_accessed = datetime.utcnow()
                    session.commit()
                    return IntersectionStatus(entry.status)
        except Exception as e:
            print(f"Error checking intersection: {e}")
        return None

    def record_intersection(
        self,
        pov: POVIntersection,
        status: IntersectionStatus,
        has_data: bool = True,
        last_value: Optional[float] = None,
        discovered_by: str = "smart_infer"
    ) -> bool:
        """Record a discovered POV intersection."""
        pov_hash = pov.hash_key()
        pov_dict = pov.to_dict()

        try:
            with self.Session() as session:
                existing = session.query(ValidIntersection).filter_by(pov_hash=pov_hash).first()
                if existing:
                    existing.status = status.value
                    existing.has_data = has_data
                    if last_value is not None:
                        existing.last_value = last_value
                    existing.access_count += 1
                    existing.last_accessed = datetime.utcnow()
                else:
                    entry = ValidIntersection(
                        pov_hash=pov_hash,
                        pov_json=json.dumps(pov_dict),
                        entity=pov.entity,
                        scenario=pov.scenario,
                        year=pov.year,
                        account=pov.account,
                        status=status.value,
                        has_data=has_data,
                        last_value=last_value,
                        discovered_by=discovered_by
                    )
                    session.add(entry)
                session.commit()

            self.l1_cache.put(pov_hash, {
                "status": status.value,
                "has_data": has_data,
                "cached_at": datetime.utcnow().isoformat()
            })
            return True
        except Exception as e:
            print(f"Error recording intersection: {e}")
            return False

    def record_batch(self, intersections: List[Dict[str, Any]], discovered_by: str = "smart_infer") -> int:
        """Record multiple intersections from smart_infer results."""
        recorded = 0
        try:
            with self.Session() as session:
                for item in intersections:
                    pov_data = item.get("pov", item)
                    status = item.get("status", "valid")
                    has_data = item.get("has_data", True)

                    pov = POVIntersection.from_dict(pov_data)
                    pov_hash = pov.hash_key()

                    existing = session.query(ValidIntersection).filter_by(pov_hash=pov_hash).first()
                    if existing:
                        existing.status = status
                        existing.has_data = has_data
                        existing.access_count += 1
                        existing.last_accessed = datetime.utcnow()
                    else:
                        entry = ValidIntersection(
                            pov_hash=pov_hash,
                            pov_json=json.dumps(pov_data),
                            entity=pov.entity,
                            scenario=pov.scenario,
                            year=pov.year,
                            account=pov.account,
                            status=status,
                            has_data=has_data,
                            discovered_by=discovered_by
                        )
                        session.add(entry)

                    self.l1_cache.put(pov_hash, {
                        "status": status,
                        "has_data": has_data,
                        "cached_at": datetime.utcnow().isoformat()
                    })
                    recorded += 1
                session.commit()
        except Exception as e:
            print(f"Error batch recording: {e}")
        return recorded

    def get_valid_for_entity(self, entity: str, scenario: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Get all valid intersections for an entity."""
        try:
            with self.Session() as session:
                query = session.query(ValidIntersection).filter(
                    ValidIntersection.entity == entity,
                    ValidIntersection.status == "valid"
                )
                if scenario:
                    query = query.filter(ValidIntersection.scenario == scenario)
                query = query.order_by(ValidIntersection.access_count.desc()).limit(limit)

                return [
                    {
                        "pov": json.loads(entry.pov_json),
                        "access_count": entry.access_count,
                        "last_accessed": entry.last_accessed.isoformat() if entry.last_accessed else None
                    }
                    for entry in query.all()
                ]
        except Exception:
            return []

    def get_valid_accounts_for_entity(self, entity: str, scenario: str = "Actual", year: str = "FY24") -> List[str]:
        """Get list of accounts with valid data for an entity."""
        try:
            with self.Session() as session:
                accounts = session.query(ValidIntersection.account).filter(
                    ValidIntersection.entity == entity,
                    ValidIntersection.scenario == scenario,
                    ValidIntersection.year == year,
                    ValidIntersection.status == "valid",
                    ValidIntersection.account.isnot(None)
                ).distinct().all()
                return [a[0] for a in accounts if a[0]]
        except Exception:
            return []

    def suggest_pov(self, partial_pov: Dict[str, str], top_k: int = 5) -> List[Dict[str, Any]]:
        """Suggest complete POVs based on partial input."""
        suggestions = []
        try:
            with self.Session() as session:
                query = session.query(ValidIntersection).filter(ValidIntersection.status == "valid")
                if "entity" in partial_pov:
                    query = query.filter(ValidIntersection.entity == partial_pov["entity"])
                if "scenario" in partial_pov:
                    query = query.filter(ValidIntersection.scenario == partial_pov["scenario"])
                if "year" in partial_pov:
                    query = query.filter(ValidIntersection.year == partial_pov["year"])
                if "account" in partial_pov:
                    query = query.filter(ValidIntersection.account == partial_pov["account"])

                query = query.order_by(ValidIntersection.access_count.desc()).limit(top_k)
                for entry in query.all():
                    suggestions.append({
                        "pov": json.loads(entry.pov_json),
                        "score": entry.access_count,
                        "reason": f"Used {entry.access_count} times"
                    })
        except Exception:
            pass
        return suggestions

    def log_access(self, pov: POVIntersection, session_id: str, tool_name: str, success: bool, latency_ms: float):
        """Log an intersection access for pattern analysis."""
        try:
            with self.Session() as session:
                log = IntersectionAccessLog(
                    pov_hash=pov.hash_key(),
                    session_id=session_id,
                    tool_name=tool_name,
                    success=success,
                    latency_ms=latency_ms
                )
                session.add(log)
                session.commit()
        except Exception:
            pass

    def get_statistics(self) -> Dict[str, Any]:
        """Get cache statistics."""
        try:
            with self.Session() as session:
                total = session.query(func.count(ValidIntersection.id)).scalar()
                valid = session.query(func.count(ValidIntersection.id)).filter(
                    ValidIntersection.status == "valid"
                ).scalar()
                entities = session.query(func.count(func.distinct(ValidIntersection.entity))).scalar()
                accounts = session.query(func.count(func.distinct(ValidIntersection.account))).scalar()

                return {
                    "total_cached": total,
                    "valid_count": valid,
                    "unique_entities": entities,
                    "unique_accounts": accounts,
                    "l1_cache_size": len(self.l1_cache),
                    "l1_capacity": self.l1_cache.capacity
                }
        except Exception:
            return {}

    def clear_stale(self, older_than_days: int = 30) -> int:
        """Clear stale cache entries."""
        cutoff = datetime.utcnow() - timedelta(days=older_than_days)
        try:
            with self.Session() as session:
                count = session.query(ValidIntersection).filter(
                    ValidIntersection.last_accessed < cutoff
                ).delete()
                session.commit()
                self.l1_cache.clear()
                return count
        except Exception:
            return 0


# Global service instance
_valid_intersections_service: Optional[ValidIntersectionsService] = None
_service_lock = threading.Lock()


def init_valid_intersections(db_url: str, l1_capacity: int = 1000, ttl_hours: int = 168) -> ValidIntersectionsService:
    """Initialize the global valid intersections service."""
    global _valid_intersections_service
    with _service_lock:
        if _valid_intersections_service is None:
            _valid_intersections_service = ValidIntersectionsService(
                db_url=db_url,
                l1_capacity=l1_capacity,
                ttl_hours=ttl_hours
            )
    return _valid_intersections_service


def get_valid_intersections() -> Optional[ValidIntersectionsService]:
    """Get the global valid intersections service instance."""
    return _valid_intersections_service
