"""Context Memory for FCCS conversations.

Manages persistent and session-based context including:
- Point of View (POV) state
- Entity focus tracking
- Query history
- Result caching for context enrichment
- Hierarchy-aware navigation tracking
"""

from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import deque
import hashlib
import json
import threading

from sqlalchemy import Column, Integer, String, DateTime, JSON, Float, Text, Index, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


@dataclass
class HierarchyContext:
    """Tracks current position in a dimension hierarchy."""
    dimension: str
    current_member: str
    parent: Optional[str] = None
    children: List[str] = field(default_factory=list)
    siblings: List[str] = field(default_factory=list)
    level: int = 0
    path_to_root: List[str] = field(default_factory=list)
    last_operation: Optional[str] = None  # children, parent, siblings, search
    last_updated: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "dimension": self.dimension,
            "current_member": self.current_member,
            "parent": self.parent,
            "children": self.children[:10],  # Limit for serialization
            "siblings": self.siblings[:10],
            "level": self.level,
            "path_to_root": self.path_to_root,
            "last_operation": self.last_operation,
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'HierarchyContext':
        """Create from dictionary."""
        last_updated = data.get("last_updated")
        if isinstance(last_updated, str):
            last_updated = datetime.fromisoformat(last_updated)
        elif last_updated is None:
            last_updated = datetime.utcnow()

        return cls(
            dimension=data.get("dimension", ""),
            current_member=data.get("current_member", ""),
            parent=data.get("parent"),
            children=data.get("children", []),
            siblings=data.get("siblings", []),
            level=data.get("level", 0),
            path_to_root=data.get("path_to_root", []),
            last_operation=data.get("last_operation"),
            last_updated=last_updated,
        )


@dataclass
class DrillSuggestion:
    """Suggested drill operation based on context."""
    direction: str  # down, up, across
    dimension: str
    from_member: str
    to_members: List[str]
    description: str
    member_count: int = 0
    is_recommended: bool = False
    reason: str = ""


class ConversationContext(Base):
    """Persistent conversation context storage."""
    __tablename__ = "conversation_context"
    
    id = Column(Integer, primary_key=True)
    session_id = Column(String(255), nullable=False, index=True)
    context_type = Column(String(50), nullable=False)  # "pov", "entity_focus", "query_history"
    context_data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = Column(DateTime)
    
    __table_args__ = (
        Index('ix_context_session_type', 'session_id', 'context_type'),
    )


class QueryHistory(Base):
    """Track query history for learning patterns."""
    __tablename__ = "query_history"
    
    id = Column(Integer, primary_key=True)
    session_id = Column(String(255), nullable=False, index=True)
    query_text = Column(Text)
    intent = Column(String(100))
    entities = Column(JSON)
    tools_used = Column(JSON)
    success = Column(Integer)  # 1 = success, 0 = failure
    execution_time_ms = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class ResultCache(Base):
    """Cache recent results for context enrichment."""
    __tablename__ = "result_cache"
    
    id = Column(Integer, primary_key=True)
    session_id = Column(String(255), nullable=False, index=True)
    cache_key = Column(String(255), nullable=False, index=True)  # Hash of tool + params
    tool_name = Column(String(100))
    parameters = Column(JSON)
    result_summary = Column(JSON)  # Summarized result for context
    full_result = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    
    __table_args__ = (
        Index('ix_cache_session_key', 'session_id', 'cache_key'),
    )


@dataclass
class POVState:
    """Point of View state for FCCS queries."""
    years: str = "FY24"
    period: str = "Jan"
    scenario: str = "Actual"
    entity: str = "FCCS_Total Geography"
    consolidation: str = "FCCS_Entity Total"
    account: Optional[str] = None
    currency: str = "Entity Currency"
    view: str = "FCCS_YTD"
    movement: str = "FCCS_Mvmts_Total"
    intercompany: str = "FCCS_Intercompany Top"
    data_source: str = "FCCS_Total Data Source"
    
    # Custom dimensions (application-specific)
    custom1: str = "Total Custom 3"
    custom2: str = "Total Region"
    custom3: str = "Total Venturi Entity"
    custom4: str = "Total Custom 4"
    
    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary."""
        return {
            "years": self.years,
            "period": self.period,
            "scenario": self.scenario,
            "entity": self.entity,
            "consolidation": self.consolidation,
            "account": self.account,
            "currency": self.currency,
            "view": self.view,
            "movement": self.movement,
            "intercompany": self.intercompany,
            "data_source": self.data_source,
            "custom1": self.custom1,
            "custom2": self.custom2,
            "custom3": self.custom3,
            "custom4": self.custom4,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> 'POVState':
        """Create from dictionary."""
        return cls(
            years=data.get("years", "FY24"),
            period=data.get("period", "Jan"),
            scenario=data.get("scenario", "Actual"),
            entity=data.get("entity", "FCCS_Total Geography"),
            consolidation=data.get("consolidation", "FCCS_Entity Total"),
            account=data.get("account"),
            currency=data.get("currency", "Entity Currency"),
            view=data.get("view", "FCCS_YTD"),
            movement=data.get("movement", "FCCS_Mvmts_Total"),
            intercompany=data.get("intercompany", "FCCS_Intercompany Top"),
            data_source=data.get("data_source", "FCCS_Total Data Source"),
            custom1=data.get("custom1", "Total Custom 3"),
            custom2=data.get("custom2", "Total Region"),
            custom3=data.get("custom3", "Total Venturi Entity"),
            custom4=data.get("custom4", "Total Custom 4"),
        )
    
    def update(self, **kwargs) -> 'POVState':
        """Create updated copy with new values."""
        data = self.to_dict()
        data.update(kwargs)
        return POVState.from_dict(data)


@dataclass
class ConversationMemory:
    """In-memory conversation state."""
    pov: POVState = field(default_factory=POVState)
    recent_queries: deque = field(default_factory=lambda: deque(maxlen=10))
    recent_results: deque = field(default_factory=lambda: deque(maxlen=5))
    entity_focus: Optional[str] = None
    account_focus: Optional[str] = None
    last_tool_used: Optional[str] = None
    last_activity: datetime = field(default_factory=datetime.utcnow)

    # Hierarchy-aware tracking (per dimension)
    hierarchy_contexts: Dict[str, HierarchyContext] = field(default_factory=dict)
    drill_history: deque = field(default_factory=lambda: deque(maxlen=20))

    def add_query(self, query: str, intent: str, entities: Dict[str, str]):
        """Add a query to history."""
        self.recent_queries.append({
            "query": query,
            "intent": intent,
            "entities": entities,
            "timestamp": datetime.utcnow().isoformat()
        })
        self.last_activity = datetime.utcnow()

    def add_result(self, tool_name: str, params: Dict, result_summary: Dict):
        """Add a result to history."""
        self.recent_results.append({
            "tool_name": tool_name,
            "params": params,
            "summary": result_summary,
            "timestamp": datetime.utcnow().isoformat()
        })
        self.last_tool_used = tool_name
        self.last_activity = datetime.utcnow()

    def update_hierarchy_context(
        self,
        dimension: str,
        member: str,
        operation: str,
        parent: Optional[str] = None,
        children: Optional[List[str]] = None,
        siblings: Optional[List[str]] = None,
        level: int = 0,
        path_to_root: Optional[List[str]] = None
    ):
        """Update hierarchy context for a dimension."""
        ctx = HierarchyContext(
            dimension=dimension,
            current_member=member,
            parent=parent,
            children=children or [],
            siblings=siblings or [],
            level=level,
            path_to_root=path_to_root or [member],
            last_operation=operation,
            last_updated=datetime.utcnow()
        )
        self.hierarchy_contexts[dimension] = ctx

        # Track drill history
        self.drill_history.append({
            "dimension": dimension,
            "member": member,
            "operation": operation,
            "timestamp": datetime.utcnow().isoformat()
        })
        self.last_activity = datetime.utcnow()

    def get_hierarchy_context(self, dimension: str) -> Optional[HierarchyContext]:
        """Get current hierarchy context for a dimension."""
        return self.hierarchy_contexts.get(dimension)


class ContextMemory:
    """Manage conversation context for intelligent FCCS operations.
    
    Features:
    - Persistent POV state across sessions
    - Query history for pattern learning
    - Result caching for context enrichment
    - Entity/account focus tracking
    - Automatic context expiration
    """
    
    # Default TTL for different context types (seconds)
    TTL_CONFIG = {
        "pov": 86400,           # 24 hours
        "entity_focus": 3600,   # 1 hour
        "query_history": 604800, # 7 days
        "result_cache": 1800,    # 30 minutes
    }
    
    def __init__(
        self,
        db_url: str,
        default_ttl: int = 3600,
        enable_persistence: bool = True
    ):
        """Initialize context memory.
        
        Args:
            db_url: Database URL for persistence.
            default_ttl: Default TTL in seconds.
            enable_persistence: Whether to persist to database.
        """
        self.db_url = db_url
        self.default_ttl = default_ttl
        self.enable_persistence = enable_persistence
        
        # In-memory working context
        self._sessions: Dict[str, ConversationMemory] = {}
        self._lock = threading.RLock()
        
        # Initialize database if persistence enabled
        if enable_persistence:
            self.engine = create_engine(db_url)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
        else:
            self.Session = None
    
    def get_or_create_session(self, session_id: str) -> ConversationMemory:
        """Get or create session memory."""
        with self._lock:
            if session_id not in self._sessions:
                # Try to load from database
                pov = self._load_pov(session_id)
                memory = ConversationMemory(pov=pov)
                self._sessions[session_id] = memory
            return self._sessions[session_id]
    
    def set_pov(self, session_id: str, **kwargs):
        """Update POV state for a session.
        
        Args:
            session_id: Session identifier.
            **kwargs: POV fields to update (years, period, scenario, etc.)
        """
        memory = self.get_or_create_session(session_id)
        memory.pov = memory.pov.update(**kwargs)
        
        # Persist to database
        self._save_context(session_id, "pov", memory.pov.to_dict())
    
    def get_pov(self, session_id: str) -> POVState:
        """Get current POV state for a session."""
        memory = self.get_or_create_session(session_id)
        return memory.pov
    
    def get_pov_dict(self, session_id: str) -> Dict[str, str]:
        """Get POV as dictionary with only non-None values."""
        pov = self.get_pov(session_id)
        return {k: v for k, v in pov.to_dict().items() if v is not None}
    
    def update_from_entities(self, session_id: str, entities: Dict[str, str]):
        """Update POV from extracted entities.
        
        Maps entity types to POV fields and updates.
        
        Args:
            session_id: Session identifier.
            entities: Extracted entities from intent classification.
        """
        # Map entity types to POV fields
        entity_to_pov = {
            "period": "period",
            "year": "years",
            "scenario": "scenario",
            "entity": "entity",
            "account": "account",
            "consolidation": "consolidation",
            "currency": "currency",
            "view": "view",
            "movement": "movement",
        }
        
        pov_updates = {}
        for entity_type, value in entities.items():
            if entity_type in entity_to_pov:
                pov_field = entity_to_pov[entity_type]
                pov_updates[pov_field] = value
        
        if pov_updates:
            self.set_pov(session_id, **pov_updates)
    
    def update_from_result(self, session_id: str, tool_name: str, result: Dict[str, Any]):
        """Update context based on tool execution result.
        
        Extracts relevant entities and values from results to maintain context.
        
        Args:
            session_id: Session identifier.
            tool_name: Name of the executed tool.
            result: Tool execution result.
        """
        memory = self.get_or_create_session(session_id)
        
        # Extract data from result
        data = result.get("data", {})
        
        pov_updates = {}
        
        if isinstance(data, dict):
            # Update POV from result data
            for key in ["entity", "account", "period", "years", "scenario"]:
                if key in data:
                    pov_updates[key] = data[key]
            
            # Update focus
            if "entity" in data:
                memory.entity_focus = data["entity"]
            if "account" in data:
                memory.account_focus = data["account"]
        elif isinstance(data, list) and len(data) > 0:
            # Handle list of results (e.g. from query_local_metadata)
            first_item = data[0]
            if isinstance(first_item, dict):
                dim = first_item.get("dimension", "").lower()
                member = first_item.get("member")
                
                if dim == "entity" and member:
                    pov_updates["entity"] = member
                    memory.entity_focus = member
                elif dim == "account" and member:
                    pov_updates["account"] = member
                    memory.account_focus = member
        
        if pov_updates:
            self.set_pov(session_id, **pov_updates)
        
        # Cache result summary
        params = result.get("parameters", {})
        summary = self._summarize_result(result)
        memory.add_result(tool_name, params, summary)
        
        # Persist to cache
        cache_key = self._create_cache_key(tool_name, params)
        self._cache_result(session_id, cache_key, tool_name, params, summary, result)
    
    def get_suggested_params(
        self,
        session_id: str,
        tool_name: str
    ) -> Dict[str, Any]:
        """Get suggested parameters based on current context.
        
        Args:
            session_id: Session identifier.
            tool_name: Target tool name.
            
        Returns:
            Dict of suggested parameter values.
        """
        pov = self.get_pov(session_id)
        pov_dict = pov.to_dict()
        
        # Parameter mapping for each tool
        tool_params = {
            "smart_retrieve": ["account", "entity", "period", "years", "scenario", "consolidation"],
            "smart_retrieve_consolidation_breakdown": ["account", "entity", "period", "years", "scenario"],
            "smart_retrieve_with_movement": ["account", "entity", "period", "years", "scenario", "consolidation", "movement"],
            "export_data_slice": [],  # Uses full grid definition
            "get_journals": ["period", "scenario"],  # Note: 'year' not 'years' for journals
            "get_journal_details": ["period", "scenario"],
            "perform_journal_action": ["period", "scenario"],
            "generate_consolidation_process_report": ["account", "entity", "period", "scenario"],
        }
        
        relevant_params = tool_params.get(tool_name, [])
        
        # Build suggested params
        suggested = {}
        for param in relevant_params:
            if param in pov_dict and pov_dict[param]:
                suggested[param] = pov_dict[param]
        
        # Special handling for journals (year vs years)
        if tool_name in ["get_journals", "get_journal_details", "perform_journal_action"]:
            if "years" in pov_dict:
                suggested["year"] = pov_dict["years"]
        
        return suggested
    
    def get_recent_context(self, session_id: str) -> Dict[str, Any]:
        """Get recent context for prompt enrichment.
        
        Returns summary of recent activity for LLM context.
        """
        memory = self.get_or_create_session(session_id)
        
        return {
            "current_pov": memory.pov.to_dict(),
            "entity_focus": memory.entity_focus,
            "account_focus": memory.account_focus,
            "last_tool_used": memory.last_tool_used,
            "recent_queries": list(memory.recent_queries)[-3:],
            "recent_results": list(memory.recent_results)[-2:],
        }
    
    def record_query(
        self,
        session_id: str,
        query: str,
        intent: str,
        entities: Dict[str, str],
        tools_used: List[str],
        success: bool,
        execution_time_ms: float
    ):
        """Record a query for history and learning.
        
        Args:
            session_id: Session identifier.
            query: Original user query.
            intent: Classified intent.
            entities: Extracted entities.
            tools_used: List of tools that were executed.
            success: Whether the query was successful.
            execution_time_ms: Total execution time.
        """
        memory = self.get_or_create_session(session_id)
        memory.add_query(query, intent, entities)
        
        # Persist to database
        if self.enable_persistence and self.Session:
            try:
                with self.Session() as session:
                    history = QueryHistory(
                        session_id=session_id,
                        query_text=query,
                        intent=intent,
                        entities=entities,
                        tools_used=tools_used,
                        success=1 if success else 0,
                        execution_time_ms=execution_time_ms,
                    )
                    session.add(history)
                    session.commit()
            except Exception:
                pass  # Don't fail on history logging
    
    def get_cached_result(
        self,
        session_id: str,
        tool_name: str,
        params: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Get cached result if available and not expired.
        
        Args:
            session_id: Session identifier.
            tool_name: Tool name.
            params: Tool parameters.
            
        Returns:
            Cached result or None.
        """
        cache_key = self._create_cache_key(tool_name, params)
        
        if not self.enable_persistence or not self.Session:
            return None
        
        try:
            with self.Session() as session:
                cache = session.query(ResultCache).filter_by(
                    session_id=session_id,
                    cache_key=cache_key
                ).filter(
                    ResultCache.expires_at > datetime.utcnow()
                ).first()
                
                if cache:
                    return cache.full_result
        except Exception:
            pass
        
        return None
    
    def clear_session(self, session_id: str):
        """Clear all context for a session."""
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
        
        # Clear from database
        if self.enable_persistence and self.Session:
            try:
                with self.Session() as session:
                    session.query(ConversationContext).filter_by(
                        session_id=session_id
                    ).delete()
                    session.query(ResultCache).filter_by(
                        session_id=session_id
                    ).delete()
                    session.commit()
            except Exception:
                pass
    
    def _load_pov(self, session_id: str) -> POVState:
        """Load POV from database."""
        if not self.enable_persistence or not self.Session:
            return POVState()
        
        try:
            with self.Session() as session:
                ctx = session.query(ConversationContext).filter_by(
                    session_id=session_id,
                    context_type="pov"
                ).filter(
                    ConversationContext.expires_at > datetime.utcnow()
                ).first()
                
                if ctx and ctx.context_data:
                    return POVState.from_dict(ctx.context_data)
        except Exception:
            pass
        
        return POVState()
    
    def _save_context(self, session_id: str, context_type: str, data: Dict):
        """Save context to database."""
        if not self.enable_persistence or not self.Session:
            return
        
        ttl = self.TTL_CONFIG.get(context_type, self.default_ttl)
        expires_at = datetime.utcnow() + timedelta(seconds=ttl)
        
        try:
            with self.Session() as session:
                ctx = session.query(ConversationContext).filter_by(
                    session_id=session_id,
                    context_type=context_type
                ).first()
                
                if ctx:
                    ctx.context_data = data
                    ctx.updated_at = datetime.utcnow()
                    ctx.expires_at = expires_at
                else:
                    ctx = ConversationContext(
                        session_id=session_id,
                        context_type=context_type,
                        context_data=data,
                        expires_at=expires_at
                    )
                    session.add(ctx)
                
                session.commit()
        except Exception:
            pass
    
    def _cache_result(
        self,
        session_id: str,
        cache_key: str,
        tool_name: str,
        params: Dict,
        summary: Dict,
        full_result: Dict
    ):
        """Cache a result."""
        if not self.enable_persistence or not self.Session:
            return
        
        ttl = self.TTL_CONFIG.get("result_cache", 1800)
        expires_at = datetime.utcnow() + timedelta(seconds=ttl)
        
        try:
            with self.Session() as session:
                # Remove old cache entry
                session.query(ResultCache).filter_by(
                    session_id=session_id,
                    cache_key=cache_key
                ).delete()
                
                # Add new cache entry
                cache = ResultCache(
                    session_id=session_id,
                    cache_key=cache_key,
                    tool_name=tool_name,
                    parameters=params,
                    result_summary=summary,
                    full_result=full_result,
                    expires_at=expires_at
                )
                session.add(cache)
                session.commit()
        except Exception:
            pass
    
    def _create_cache_key(self, tool_name: str, params: Dict) -> str:
        """Create cache key from tool and params."""
        content = json.dumps({"tool": tool_name, "params": params}, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:32]
    
    def _summarize_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Create a summary of a result for context."""
        summary = {
            "status": result.get("status"),
            "has_data": "data" in result,
        }
        
        data = result.get("data", {})
        if isinstance(data, dict):
            # Extract key metrics
            if "rows" in data:
                summary["row_count"] = len(data["rows"])
            if "consolidation_breakdown" in data:
                summary["has_consolidation"] = True
            
            # Copy key identifiers
            for key in ["entity", "account", "period", "years", "scenario"]:
                if key in data:
                    summary[key] = data[key]
        
        return summary
    
    def get_query_patterns(
        self,
        session_id: str,
        intent: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict]:
        """Get query patterns for learning.
        
        Args:
            session_id: Session identifier.
            intent: Optional intent filter.
            limit: Maximum results.
            
        Returns:
            List of query patterns with success rates.
        """
        if not self.enable_persistence or not self.Session:
            return []
        
        try:
            with self.Session() as session:
                query = session.query(QueryHistory).filter_by(session_id=session_id)
                
                if intent:
                    query = query.filter_by(intent=intent)
                
                query = query.order_by(QueryHistory.created_at.desc()).limit(limit)
                
                return [
                    {
                        "query": h.query_text,
                        "intent": h.intent,
                        "entities": h.entities,
                        "tools_used": h.tools_used,
                        "success": h.success == 1,
                        "execution_time_ms": h.execution_time_ms,
                        "created_at": h.created_at.isoformat() if h.created_at else None,
                    }
                    for h in query.all()
                ]
        except Exception:
            return []
    
    def cleanup_expired(self):
        """Clean up expired context and cache entries."""
        if not self.enable_persistence or not self.Session:
            return

        try:
            with self.Session() as session:
                now = datetime.utcnow()

                # Clean expired context
                session.query(ConversationContext).filter(
                    ConversationContext.expires_at < now
                ).delete()

                # Clean expired cache
                session.query(ResultCache).filter(
                    ResultCache.expires_at < now
                ).delete()

                session.commit()
        except Exception:
            pass

    # ========================================================================
    # Hierarchy-aware methods
    # ========================================================================

    def track_hierarchy_position(
        self,
        session_id: str,
        dimension: str,
        member: str,
        operation: str,
        parent: Optional[str] = None,
        children: Optional[List[str]] = None,
        siblings: Optional[List[str]] = None,
        level: int = 0,
        path_to_root: Optional[List[str]] = None
    ):
        """Track navigation position in a dimension hierarchy.

        Called after explore_dimension operations to maintain context.

        Args:
            session_id: Session identifier.
            dimension: Dimension name (Account, Entity, etc.).
            member: Current member being navigated.
            operation: Operation performed (children, parent, siblings, search).
            parent: Parent member if known.
            children: Child members if retrieved.
            siblings: Sibling members if retrieved.
            level: Hierarchy level (0 = root).
            path_to_root: Full path from member to root.
        """
        memory = self.get_or_create_session(session_id)
        memory.update_hierarchy_context(
            dimension=dimension,
            member=member,
            operation=operation,
            parent=parent,
            children=children,
            siblings=siblings,
            level=level,
            path_to_root=path_to_root
        )

        # Also update POV if relevant dimension
        if dimension == "Account" and member:
            memory.account_focus = member
            self.set_pov(session_id, account=member)
        elif dimension == "Entity" and member:
            memory.entity_focus = member
            self.set_pov(session_id, entity=member)

        # Persist hierarchy context
        self._save_context(
            session_id,
            f"hierarchy_{dimension}",
            memory.hierarchy_contexts[dimension].to_dict()
        )

    def get_hierarchy_position(
        self,
        session_id: str,
        dimension: str
    ) -> Optional[HierarchyContext]:
        """Get current hierarchy position for a dimension.

        Args:
            session_id: Session identifier.
            dimension: Dimension name.

        Returns:
            HierarchyContext or None if not tracked.
        """
        memory = self.get_or_create_session(session_id)
        return memory.get_hierarchy_context(dimension)

    def get_drill_suggestions(
        self,
        session_id: str,
        dimension: Optional[str] = None
    ) -> List[DrillSuggestion]:
        """Get intelligent drill suggestions based on current context.

        Analyzes current hierarchy positions and recent activity to suggest
        meaningful drill operations.

        Args:
            session_id: Session identifier.
            dimension: Optional dimension to get suggestions for (all if None).

        Returns:
            List of DrillSuggestion objects.
        """
        memory = self.get_or_create_session(session_id)
        suggestions: List[DrillSuggestion] = []

        dimensions = [dimension] if dimension else list(memory.hierarchy_contexts.keys())

        for dim in dimensions:
            ctx = memory.hierarchy_contexts.get(dim)
            if not ctx:
                continue

            # Suggest drill-down if we have children
            if ctx.children:
                suggestions.append(DrillSuggestion(
                    direction="down",
                    dimension=dim,
                    from_member=ctx.current_member,
                    to_members=ctx.children[:5],
                    description=f"Drill into {ctx.current_member} to see {len(ctx.children)} children",
                    member_count=len(ctx.children),
                    is_recommended=len(ctx.children) <= 10,
                    reason="Children available for drill-down"
                ))

            # Suggest roll-up if we have a parent
            if ctx.parent:
                suggestions.append(DrillSuggestion(
                    direction="up",
                    dimension=dim,
                    from_member=ctx.current_member,
                    to_members=[ctx.parent],
                    description=f"Roll up from {ctx.current_member} to {ctx.parent}",
                    member_count=1,
                    is_recommended=ctx.level > 2,  # Recommend if deep in hierarchy
                    reason="Parent available for aggregation"
                ))

            # Suggest sibling comparison if we have siblings
            if ctx.siblings:
                suggestions.append(DrillSuggestion(
                    direction="across",
                    dimension=dim,
                    from_member=ctx.current_member,
                    to_members=ctx.siblings[:5],
                    description=f"Compare {ctx.current_member} with {len(ctx.siblings)} siblings",
                    member_count=len(ctx.siblings),
                    is_recommended=len(ctx.siblings) <= 5,
                    reason="Siblings available for comparison"
                ))

        # Analyze drill history for patterns
        recent_drills = list(memory.drill_history)[-5:]
        if recent_drills:
            # If user has been drilling down, suggest continuing
            down_count = sum(1 for d in recent_drills if d.get("operation") == "children")
            if down_count >= 2:
                for s in suggestions:
                    if s.direction == "down":
                        s.is_recommended = True
                        s.reason = "Continuing drill-down pattern"

        return suggestions

    def get_smart_defaults(
        self,
        session_id: str,
        tool_name: str
    ) -> Dict[str, Any]:
        """Get smart default parameters based on context and hierarchy positions.

        Enhanced version that considers:
        - Current POV state
        - Hierarchy positions
        - Recent drill operations
        - Focus members

        Args:
            session_id: Session identifier.
            tool_name: Target tool name.

        Returns:
            Dict of suggested parameter values.
        """
        memory = self.get_or_create_session(session_id)
        pov = memory.pov
        defaults = self.get_suggested_params(session_id, tool_name)

        # Enhance with hierarchy context for exploration tools
        if tool_name == "explore_dimension":
            # Use most recent hierarchy context as default
            if memory.hierarchy_contexts:
                # Get most recently updated dimension
                most_recent = max(
                    memory.hierarchy_contexts.items(),
                    key=lambda x: x[1].last_updated
                )
                defaults["dimension"] = most_recent[0]
                defaults["member"] = most_recent[1].current_member

        elif tool_name == "search_members":
            # Default to Account dimension for searches
            if not defaults.get("dimension"):
                defaults["dimension"] = "Account"

        elif tool_name == "get_drill_suggestions":
            # Use focused dimension
            if memory.account_focus:
                defaults["dimension"] = "Account"
                defaults["member"] = memory.account_focus
            elif memory.entity_focus:
                defaults["dimension"] = "Entity"
                defaults["member"] = memory.entity_focus

        # For data retrieval tools, use hierarchy-aware member names
        if tool_name in ["smart_retrieve", "smart_retrieve_with_movement"]:
            # Use account from hierarchy context if available
            account_ctx = memory.hierarchy_contexts.get("Account")
            if account_ctx and account_ctx.current_member:
                defaults["account"] = account_ctx.current_member

            # Use entity from hierarchy context if available
            entity_ctx = memory.hierarchy_contexts.get("Entity")
            if entity_ctx and entity_ctx.current_member:
                defaults["entity"] = entity_ctx.current_member

        return defaults

    def get_navigation_context(self, session_id: str) -> Dict[str, Any]:
        """Get full navigation context for prompt enrichment.

        Returns comprehensive context including:
        - Current POV
        - Hierarchy positions for all tracked dimensions
        - Recent drill operations
        - Drill suggestions

        Args:
            session_id: Session identifier.

        Returns:
            Dict with navigation context.
        """
        memory = self.get_or_create_session(session_id)

        hierarchy_summary = {}
        for dim, ctx in memory.hierarchy_contexts.items():
            hierarchy_summary[dim] = {
                "current_member": ctx.current_member,
                "level": ctx.level,
                "parent": ctx.parent,
                "has_children": len(ctx.children) > 0,
                "children_count": len(ctx.children),
                "last_operation": ctx.last_operation,
            }

        return {
            "current_pov": memory.pov.to_dict(),
            "entity_focus": memory.entity_focus,
            "account_focus": memory.account_focus,
            "hierarchy_positions": hierarchy_summary,
            "drill_history": list(memory.drill_history)[-5:],
            "suggestions": [
                {
                    "direction": s.direction,
                    "dimension": s.dimension,
                    "description": s.description,
                    "is_recommended": s.is_recommended,
                }
                for s in self.get_drill_suggestions(session_id)[:3]
            ]
        }
