"""Cache Service - SQLite-based caching for FCCS API responses and metadata."""

import json
import time
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import (
    Column, String, Text, DateTime,
    create_engine
)
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

class CacheEntry(Base):
    """Generic cache entry for API responses."""
    __tablename__ = "api_cache"

    key = Column(String, primary_key=True)
    value = Column(Text)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

class MetadataCache(Base):
    """Cache for dimension members and properties."""
    __tablename__ = "metadata_cache"

    dimension = Column(String, primary_key=True)
    member = Column(String, primary_key=True)
    properties = Column(Text)  # JSON string of properties
    last_updated = Column(DateTime, default=datetime.utcnow)

class CacheService:
    """Service for managing local cache in SQLite."""

    def __init__(self, db_url: str):
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def get(self, key: str) -> Optional[Any]:
        """Get a value from cache if not expired."""
        with self.Session() as session:
            entry = session.query(CacheEntry).filter(
                CacheEntry.key == key,
                CacheEntry.expires_at > datetime.utcnow()
            ).first()
            
            if entry:
                return json.loads(entry.value)
        return None

    def set(self, key: str, value: Any, ttl_seconds: int = 3600):
        """Set a value in cache with a TTL."""
        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        json_value = json.dumps(value)
        
        with self.Session() as session:
            # Upsert logic
            entry = session.query(CacheEntry).filter(CacheEntry.key == key).first()
            if entry:
                entry.value = json_value
                entry.expires_at = expires_at
                entry.created_at = datetime.utcnow()
            else:
                entry = CacheEntry(key=key, value=json_value, expires_at=expires_at)
                session.add(entry)
            session.commit()

    def get_member(self, dimension: str, member: str) -> Optional[dict]:
        """Get member properties from metadata cache."""
        with self.Session() as session:
            entry = session.query(MetadataCache).filter(
                MetadataCache.dimension == dimension,
                MetadataCache.member == member
            ).first()
            if entry:
                return json.loads(entry.properties)
        return None

    def update_member(self, dimension: str, member: str, properties: dict):
        """Update member properties in metadata cache."""
        json_props = json.dumps(properties)
        with self.Session() as session:
            entry = session.query(MetadataCache).filter(
                MetadataCache.dimension == dimension,
                MetadataCache.member == member
            ).first()
            if entry:
                entry.properties = json_props
                entry.last_updated = datetime.utcnow()
            else:
                entry = MetadataCache(
                    dimension=dimension,
                    member=member,
                    properties=json_props
                )
                session.add(entry)
            session.commit()

    def clear_expired(self):
        """Clear expired cache entries."""
        with self.Session() as session:
            session.query(CacheEntry).filter(
                CacheEntry.expires_at <= datetime.utcnow()
            ).delete()
            session.commit()

# Global cache instance
_cache_service: Optional[CacheService] = None

def init_cache_service(db_url: str) -> CacheService:
    global _cache_service
    _cache_service = CacheService(db_url)
    return _cache_service

def get_cache_service() -> Optional[CacheService]:
    return _cache_service

