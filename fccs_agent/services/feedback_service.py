"""Feedback Service - SQLite-based tracking for reinforcement learning."""

import time
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, JSON, Boolean,
    create_engine, func
)
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class ToolExecution(Base):
    """Track tool executions for feedback and RL."""

    __tablename__ = "tool_executions"

    id = Column(Integer, primary_key=True)
    session_id = Column(String, index=True)
    tool_name = Column(String, index=True)
    arguments = Column(JSON)
    result = Column(JSON)
    success = Column(Boolean)
    error_message = Column(String, nullable=True)
    execution_time_ms = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    # User feedback (added later via API)
    user_rating = Column(Integer, nullable=True)  # 1-5 scale
    user_feedback = Column(String, nullable=True)


class ToolMetrics(Base):
    """Aggregated metrics per tool for analysis."""

    __tablename__ = "tool_metrics"

    id = Column(Integer, primary_key=True)
    tool_name = Column(String, unique=True)
    total_calls = Column(Integer, default=0, nullable=False, server_default="0")
    success_count = Column(Integer, default=0, nullable=False, server_default="0")
    failure_count = Column(Integer, default=0, nullable=False, server_default="0")
    avg_execution_time_ms = Column(Float, default=0, nullable=False, server_default="0")
    avg_user_rating = Column(Float, nullable=True)
    last_updated = Column(DateTime, default=datetime.utcnow)


class FeedbackService:
    """Service for tracking tool executions and user feedback."""

    def __init__(self, db_url: str):
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def log_execution(
        self,
        session_id: str,
        tool_name: str,
        arguments: dict,
        result: Any,
        success: bool,
        error_message: Optional[str],
        execution_time_ms: float
    ) -> int:
        """Log a tool execution and return its ID."""
        try:
            with self.Session() as session:
                execution = ToolExecution(
                    session_id=session_id,
                    tool_name=tool_name,
                    arguments=arguments,
                    result=result if success else None,
                    success=success,
                    error_message=error_message,
                    execution_time_ms=execution_time_ms
                )
                session.add(execution)
                session.commit()
                execution_id = execution.id

            # Update aggregated metrics in a separate session to avoid conflicts
            try:
                self._update_metrics_separate_session(tool_name, success, execution_time_ms)
            except Exception:
                # If metrics update fails, just log the execution without metrics
                pass

            return execution_id
        except Exception:
            # If logging fails completely, return -1 to indicate failure
            # but don't raise - we don't want to break tool execution
            return -1

    def add_user_feedback(
        self,
        execution_id: int,
        rating: int,
        feedback: Optional[str] = None
    ):
        """Add user feedback to an execution."""
        with self.Session() as session:
            execution = session.query(ToolExecution).get(execution_id)
            if execution:
                execution.user_rating = rating
                execution.user_feedback = feedback
                session.commit()

                # Update tool's average rating
                self._update_rating_metrics(session, execution.tool_name)

    def get_tool_metrics(self, tool_name: Optional[str] = None) -> list[dict]:
        """Get aggregated metrics for tools."""
        with self.Session() as session:
            query = session.query(ToolMetrics)
            if tool_name:
                query = query.filter(ToolMetrics.tool_name == tool_name)
            return [
                {
                    "tool_name": m.tool_name,
                    "total_calls": m.total_calls,
                    "success_rate": m.success_count / m.total_calls if m.total_calls > 0 else 0,
                    "avg_execution_time_ms": m.avg_execution_time_ms,
                    "avg_user_rating": m.avg_user_rating
                }
                for m in query.all()
            ]

    def get_recent_executions(
        self,
        tool_name: Optional[str] = None,
        limit: int = 50
    ) -> list[dict]:
        """Get recent tool executions."""
        with self.Session() as session:
            query = session.query(ToolExecution).order_by(
                ToolExecution.created_at.desc()
            )
            if tool_name:
                query = query.filter(ToolExecution.tool_name == tool_name)
            query = query.limit(limit)

            return [
                {
                    "id": e.id,
                    "session_id": e.session_id,
                    "tool_name": e.tool_name,
                    "success": e.success,
                    "execution_time_ms": e.execution_time_ms,
                    "user_rating": e.user_rating,
                    "created_at": e.created_at.isoformat() if e.created_at else None
                }
                for e in query.all()
            ]

    def _update_metrics_separate_session(
        self,
        tool_name: str,
        success: bool,
        execution_time_ms: float
    ):
        """Update aggregated metrics for a tool using a separate session."""
        try:
            with self.Session() as session:
                # Use merge to get or create, and ensure we have a clean object
                metrics = session.query(ToolMetrics).filter_by(tool_name=tool_name).first()
                
                if not metrics:
                    # Create new metrics record with explicit defaults
                    metrics = ToolMetrics(
                        tool_name=tool_name,
                        total_calls=0,
                        success_count=0,
                        failure_count=0,
                        avg_execution_time_ms=0.0
                    )
                    session.add(metrics)
                    session.flush()
                
                # Refresh to get latest values from database and handle any NULLs
                session.refresh(metrics)
                
                # Safely read current values, handling None explicitly
                current_total = int(metrics.total_calls) if metrics.total_calls is not None else 0
                current_success = int(metrics.success_count) if metrics.success_count is not None else 0
                current_failure = int(metrics.failure_count) if metrics.failure_count is not None else 0
                current_avg = float(metrics.avg_execution_time_ms) if metrics.avg_execution_time_ms is not None else 0.0

                # Calculate new values
                new_total = current_total + 1
                if success:
                    new_success = current_success + 1
                    new_failure = current_failure
                else:
                    new_success = current_success
                    new_failure = current_failure + 1

                # Calculate new average execution time
                if new_total == 1:
                    new_avg = execution_time_ms
                else:
                    old_total_time = current_avg * current_total
                    new_avg = (old_total_time + execution_time_ms) / new_total

                # Update all values at once using assignment (not +=)
                # This ensures SQLAlchemy doesn't try to do increment operations
                metrics.total_calls = new_total
                metrics.success_count = new_success
                metrics.failure_count = new_failure
                metrics.avg_execution_time_ms = new_avg
                metrics.last_updated = datetime.utcnow()
                
                session.commit()
        except Exception as e:
            # Log error but don't raise - we don't want to break tool execution
            import sys
            print(f"Warning: Failed to update metrics: {e}", file=sys.stderr)
            # Silently fail - metrics are optional

    def _update_rating_metrics(self, session, tool_name: str):
        """Update average rating for a tool."""
        avg_rating = session.query(func.avg(ToolExecution.user_rating)).filter(
            ToolExecution.tool_name == tool_name,
            ToolExecution.user_rating.isnot(None)
        ).scalar()

        metrics = session.query(ToolMetrics).filter_by(tool_name=tool_name).first()
        if metrics:
            metrics.avg_user_rating = avg_rating
            session.commit()


# Global state for tracking
_feedback_service: Optional[FeedbackService] = None
_execution_start_times: dict[str, float] = {}


def init_feedback_service(db_url: str) -> FeedbackService:
    """Initialize the global feedback service."""
    global _feedback_service
    _feedback_service = FeedbackService(db_url)
    return _feedback_service


def get_feedback_service() -> Optional[FeedbackService]:
    """Get the global feedback service instance."""
    return _feedback_service


def before_tool_callback(session_id: str, tool_name: str, args: dict) -> None:
    """Track tool execution start time (call before tool execution)."""
    key = f"{session_id}:{tool_name}:{time.time()}"
    _execution_start_times[session_id] = time.time()


def after_tool_callback(
    session_id: str,
    tool_name: str,
    args: dict,
    result: Any
) -> Optional[int]:
    """Log tool execution result (call after tool execution).
    
    Returns:
        Execution ID if logging was successful, None otherwise.
    """
    start_time = _execution_start_times.pop(session_id, time.time())
    execution_time_ms = (time.time() - start_time) * 1000

    success = isinstance(result, dict) and result.get("status") == "success"
    error_message = result.get("error") if isinstance(result, dict) else None

    if _feedback_service:
        try:
            execution_id = _feedback_service.log_execution(
                session_id=session_id,
                tool_name=tool_name,
                arguments=args,
                result=result,
                success=success,
                error_message=error_message,
                execution_time_ms=execution_time_ms
            )
            
            return execution_id
        except Exception as e:
            # Silently fail feedback logging to not break tool execution
            import sys
            print(f"Warning: Failed to log execution to feedback service: {e}", file=sys.stderr)
            return None
    
    return None
