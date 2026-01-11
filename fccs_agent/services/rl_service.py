"""Reinforcement Learning Service for tool selection and optimization."""

import hashlib
import json
import math
import random
import threading
from collections import deque
from datetime import datetime
from typing import Any, Optional, Dict, List, Tuple, NamedTuple
from collections import defaultdict

import numpy as np
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, create_engine, func, UniqueConstraint
from sqlalchemy.orm import declarative_base, sessionmaker

from fccs_agent.services.feedback_service import FeedbackService, ToolExecution, ToolMetrics

Base = declarative_base()


class Experience(NamedTuple):
    """Single experience tuple for replay buffer."""
    state_hash: str
    action: str  # tool_name
    reward: float
    next_state_hash: Optional[str]
    done: bool  # True if terminal state


class RLPolicy(Base):
    """RL Policy table for storing Q-values and action values."""

    __tablename__ = "rl_policy"

    id = Column(Integer, primary_key=True)
    tool_name = Column(String(255), nullable=False, index=True)
    context_hash = Column(String(64), nullable=False, index=True)
    action_value = Column(Float, default=0.0)  # Q-value or expected reward
    visit_count = Column(Integer, default=0)
    last_updated = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('tool_name', 'context_hash', name='uq_tool_context'),
    )



class RLEpisode(Base):
    """RL Episode table for tracking complete sessions."""

    __tablename__ = "rl_episodes"

    id = Column(Integer, primary_key=True)
    session_id = Column(String(255), nullable=False, index=True)
    episode_reward = Column(Float, default=0.0)
    tool_sequence = Column(JSON)  # List of tool names used in sequence
    outcome = Column(String(50))  # 'success', 'partial', 'failure'
    created_at = Column(DateTime, default=datetime.utcnow)


class RLMetrics(Base):
    """RL Learning metrics for monitoring and debugging."""

    __tablename__ = "rl_metrics"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    metric_name = Column(String(100), nullable=False, index=True)
    metric_value = Column(Float, nullable=False)
    extra_data = Column(JSON)  # Additional context (renamed from 'metadata' which is reserved)


class ToolSequence(Base):
    """N-gram tool sequences for sequence learning."""

    __tablename__ = "rl_tool_sequences"

    id = Column(Integer, primary_key=True)
    sequence_key = Column(String(512), nullable=False, unique=True, index=True)  # e.g., "get_dimensions->get_members"
    count = Column(Integer, default=1)
    avg_reward = Column(Float, default=0.0)
    success_rate = Column(Float, default=0.0)
    last_seen = Column(DateTime, default=datetime.utcnow)


class ExperienceReplayBuffer:
    """Fixed-size buffer for experience replay with prioritization support."""

    def __init__(self, capacity: int = 10000, alpha: float = 0.6):
        """Initialize replay buffer.

        Args:
            capacity: Maximum number of experiences to store.
            alpha: Priority exponent (0 = uniform, 1 = full priority).
        """
        self.capacity = capacity
        self.alpha = alpha
        self.buffer: deque[Experience] = deque(maxlen=capacity)
        self.priorities: deque[float] = deque(maxlen=capacity)
        self._lock = threading.Lock()

    def add(self, experience: Experience, priority: Optional[float] = None):
        """Add experience to buffer with optional priority."""
        with self._lock:
            self.buffer.append(experience)
            # Default priority is max existing priority (or 1.0 for first)
            if priority is None:
                priority = max(self.priorities) if self.priorities else 1.0
            self.priorities.append(priority)

    def sample(self, batch_size: int) -> List[Experience]:
        """Sample a batch of experiences using prioritized sampling."""
        with self._lock:
            if len(self.buffer) < batch_size:
                return list(self.buffer)

            # Calculate sampling probabilities
            priorities = np.array(self.priorities)
            probs = priorities ** self.alpha
            probs /= probs.sum()

            # Sample indices
            indices = np.random.choice(len(self.buffer), size=batch_size, replace=False, p=probs)
            return [self.buffer[i] for i in indices]

    def update_priority(self, idx: int, priority: float):
        """Update priority of experience at index."""
        with self._lock:
            if 0 <= idx < len(self.priorities):
                self.priorities[idx] = priority

    def __len__(self) -> int:
        return len(self.buffer)


class SequenceLearner:
    """Learn and recommend tool sequences using N-gram models."""

    def __init__(self, session_factory, n: int = 3):
        """Initialize sequence learner.

        Args:
            session_factory: SQLAlchemy session factory.
            n: Maximum N-gram length (default 3 for trigrams).
        """
        self.Session = session_factory
        self.n = n
        self._sequence_cache: Dict[str, Dict] = {}
        self._cache_lock = threading.Lock()

    def _create_sequence_key(self, tools: List[str]) -> str:
        """Create a unique key for a tool sequence."""
        return "->".join(tools)

    def record_sequence(self, tool_sequence: List[str], reward: float, success: bool):
        """Record all N-grams from a tool sequence.

        Args:
            tool_sequence: List of tool names in execution order.
            reward: Total reward for the sequence.
            success: Whether the sequence was successful.
        """
        if len(tool_sequence) < 2:
            return

        # Generate all N-grams (bigrams, trigrams, etc.)
        for n in range(2, min(self.n + 1, len(tool_sequence) + 1)):
            for i in range(len(tool_sequence) - n + 1):
                ngram = tool_sequence[i:i + n]
                self._update_sequence(ngram, reward / len(tool_sequence), success)

    def _update_sequence(self, tools: List[str], reward: float, success: bool):
        """Update a single N-gram sequence in database."""
        sequence_key = self._create_sequence_key(tools)

        try:
            with self.Session() as session:
                seq = session.query(ToolSequence).filter_by(sequence_key=sequence_key).first()

                if seq:
                    # Update running averages
                    old_count = seq.count
                    new_count = old_count + 1
                    seq.avg_reward = (seq.avg_reward * old_count + reward) / new_count
                    seq.success_rate = (seq.success_rate * old_count + (1.0 if success else 0.0)) / new_count
                    seq.count = new_count
                    seq.last_seen = datetime.utcnow()
                else:
                    # Create new sequence
                    seq = ToolSequence(
                        sequence_key=sequence_key,
                        count=1,
                        avg_reward=reward,
                        success_rate=1.0 if success else 0.0,
                        last_seen=datetime.utcnow()
                    )
                    session.add(seq)

                session.commit()

                # Update cache
                with self._cache_lock:
                    self._sequence_cache[sequence_key] = {
                        "count": seq.count,
                        "avg_reward": seq.avg_reward,
                        "success_rate": seq.success_rate
                    }
        except Exception:
            pass  # Silently fail - don't break main flow

    def get_next_tool_recommendations(
        self,
        recent_tools: List[str],
        available_tools: List[str],
        top_k: int = 5
    ) -> List[Dict]:
        """Get recommended next tools based on sequence patterns.

        Args:
            recent_tools: Recently executed tools (last N-1 tools).
            available_tools: List of available tool names.
            top_k: Number of recommendations to return.

        Returns:
            List of dicts with tool_name, score, and reason.
        """
        if not recent_tools:
            return []

        recommendations = []

        # Look for matching sequences with each available tool as next
        for tool in available_tools:
            best_score = 0.0
            best_reason = ""

            # Check all N-gram lengths
            for n in range(1, min(self.n, len(recent_tools) + 1)):
                prefix = recent_tools[-n:]
                sequence_key = self._create_sequence_key(prefix + [tool])

                # Check cache first
                seq_data = None
                with self._cache_lock:
                    seq_data = self._sequence_cache.get(sequence_key)

                # If not in cache, try database
                if seq_data is None:
                    try:
                        with self.Session() as session:
                            seq = session.query(ToolSequence).filter_by(sequence_key=sequence_key).first()
                            if seq:
                                seq_data = {
                                    "count": seq.count,
                                    "avg_reward": seq.avg_reward,
                                    "success_rate": seq.success_rate
                                }
                                with self._cache_lock:
                                    self._sequence_cache[sequence_key] = seq_data
                    except Exception:
                        pass

                if seq_data and seq_data["count"] >= 2:  # Minimum 2 occurrences
                    # Score based on reward, success rate, and count
                    score = (
                        seq_data["avg_reward"] * 0.4 +
                        seq_data["success_rate"] * 10 * 0.4 +
                        min(seq_data["count"] / 10, 1.0) * 0.2  # Confidence from count
                    )

                    if score > best_score:
                        best_score = score
                        best_reason = f"Follows {self._create_sequence_key(prefix)} ({seq_data['count']}x, {seq_data['success_rate']*100:.0f}% success)"

            if best_score > 0:
                recommendations.append({
                    "tool_name": tool,
                    "sequence_score": best_score,
                    "reason": best_reason
                })

        # Sort by score and return top_k
        recommendations.sort(key=lambda x: x["sequence_score"], reverse=True)
        return recommendations[:top_k]


class LearningMetricsTracker:
    """Track and store RL learning metrics for monitoring."""

    def __init__(self, session_factory):
        self.Session = session_factory
        self._metrics_buffer: List[Tuple[str, float, Optional[dict]]] = []
        self._buffer_lock = threading.Lock()
        self._flush_threshold = 100  # Flush after 100 metrics

    def record(self, metric_name: str, value: float, metadata: Optional[dict] = None):
        """Record a metric value."""
        with self._buffer_lock:
            self._metrics_buffer.append((metric_name, value, metadata))
            if len(self._metrics_buffer) >= self._flush_threshold:
                self._flush_buffer()

    def _flush_buffer(self):
        """Flush buffered metrics to database."""
        if not self._metrics_buffer:
            return

        try:
            with self.Session() as session:
                for metric_name, value, extra_data in self._metrics_buffer:
                    metric = RLMetrics(
                        metric_name=metric_name,
                        metric_value=value,
                        extra_data=extra_data,
                        timestamp=datetime.utcnow()
                    )
                    session.add(metric)
                session.commit()
            self._metrics_buffer.clear()
        except Exception:
            pass  # Don't break main flow

    def flush(self):
        """Manually flush buffered metrics."""
        with self._buffer_lock:
            self._flush_buffer()

    def get_recent_metrics(
        self,
        metric_name: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """Get recent metrics from database."""
        try:
            with self.Session() as session:
                query = session.query(RLMetrics)
                if metric_name:
                    query = query.filter_by(metric_name=metric_name)
                query = query.order_by(RLMetrics.timestamp.desc()).limit(limit)

                return [
                    {
                        "timestamp": m.timestamp.isoformat() if m.timestamp else None,
                        "metric_name": m.metric_name,
                        "value": m.metric_value,
                        "extra_data": m.extra_data
                    }
                    for m in query.all()
                ]
        except Exception:
            return []

    def get_metric_summary(self, metric_name: str, window_size: int = 100) -> Dict:
        """Get summary statistics for a metric."""
        metrics = self.get_recent_metrics(metric_name, limit=window_size)
        if not metrics:
            return {"count": 0}

        values = [m["value"] for m in metrics]
        return {
            "count": len(values),
            "mean": float(np.mean(values)),
            "std": float(np.std(values)),
            "min": float(np.min(values)),
            "max": float(np.max(values)),
            "latest": values[0] if values else None
        }


class RewardCalculator:
    """Calculate rewards from tool execution results with enhanced multi-component shaping."""

    # Per-tool expected durations (ms) - tools have different performance expectations
    TOOL_BASELINES: Dict[str, Dict[str, Any]] = {
        # Fast retrieval tools (< 2s expected)
        "get_dimensions": {"expected_ms": 1000, "category": "retrieval", "value": 0.5},
        "get_members": {"expected_ms": 1500, "category": "retrieval", "value": 0.5},
        "get_application_info": {"expected_ms": 500, "category": "retrieval", "value": 0.3},
        "get_pov": {"expected_ms": 800, "category": "retrieval", "value": 0.4},
        "list_journals": {"expected_ms": 2000, "category": "retrieval", "value": 0.5},
        "get_journal": {"expected_ms": 1500, "category": "retrieval", "value": 0.5},

        # Medium operations (2-10s expected)
        "retrieve_data": {"expected_ms": 5000, "category": "data", "value": 0.7},
        "export_data": {"expected_ms": 8000, "category": "data", "value": 0.7},
        "get_report": {"expected_ms": 5000, "category": "report", "value": 0.6},
        "run_report": {"expected_ms": 10000, "category": "report", "value": 0.7},

        # Slow operations (10-60s expected) - consolidation, jobs
        "run_consolidation": {"expected_ms": 30000, "category": "consolidation", "value": 1.0},
        "run_job": {"expected_ms": 20000, "category": "job", "value": 0.9},
        "submit_journal": {"expected_ms": 5000, "category": "journal", "value": 0.8},
        "post_journal": {"expected_ms": 10000, "category": "journal", "value": 0.9},
        "approve_journal": {"expected_ms": 3000, "category": "journal", "value": 0.8},

        # Write operations
        "import_data": {"expected_ms": 15000, "category": "data", "value": 0.8},
        "update_member": {"expected_ms": 3000, "category": "write", "value": 0.7},
        "create_member": {"expected_ms": 3000, "category": "write", "value": 0.7},
    }

    # Default baseline for unknown tools
    DEFAULT_BASELINE = {"expected_ms": 5000, "category": "unknown", "value": 0.5}

    # Error type penalties (more specific = less penalty)
    ERROR_PENALTIES: Dict[str, float] = {
        "timeout": -0.3,          # Network/server issues, not user's fault
        "rate_limit": -0.2,       # Temporary, will resolve
        "not_found": -0.5,        # User error - wrong resource
        "permission": -0.6,       # Access issue - needs investigation
        "validation": -0.7,       # Bad input - user should fix
        "server_error": -0.4,     # Server-side issue
        "connection": -0.3,       # Network issues
        "unknown": -0.8,          # Unexpected errors - worst case
    }

    # Reward component weights (sum to 1.0)
    WEIGHTS = {
        "task_completion": 0.35,   # Did the tool succeed?
        "efficiency": 0.20,        # How fast relative to baseline?
        "error_avoidance": 0.25,   # What type of error (if any)?
        "user_satisfaction": 0.15, # User rating
        "response_quality": 0.05,  # Did it return useful data?
    }

    @classmethod
    def get_tool_baseline(cls, tool_name: str) -> Dict[str, Any]:
        """Get baseline configuration for a tool."""
        return cls.TOOL_BASELINES.get(tool_name, cls.DEFAULT_BASELINE)

    @classmethod
    def classify_error(cls, error_message: Optional[str]) -> str:
        """Classify error type from error message."""
        if not error_message:
            return "unknown"

        error_lower = error_message.lower()

        if any(kw in error_lower for kw in ["timeout", "timed out", "deadline"]):
            return "timeout"
        if any(kw in error_lower for kw in ["rate limit", "too many requests", "429"]):
            return "rate_limit"
        if any(kw in error_lower for kw in ["not found", "404", "does not exist", "no such"]):
            return "not_found"
        if any(kw in error_lower for kw in ["permission", "forbidden", "403", "unauthorized", "401", "access denied"]):
            return "permission"
        if any(kw in error_lower for kw in ["invalid", "validation", "bad request", "400", "missing required"]):
            return "validation"
        if any(kw in error_lower for kw in ["500", "502", "503", "504", "server error", "internal error"]):
            return "server_error"
        if any(kw in error_lower for kw in ["connection", "network", "unreachable", "dns"]):
            return "connection"

        return "unknown"

    @classmethod
    def calculate_reward(
        cls,
        execution: ToolExecution,
        avg_execution_time: Optional[float] = None,
        tool_metrics: Optional[Dict] = None
    ) -> float:
        """Calculate multi-component reward for a tool execution.

        Components (weighted):
        - task_completion (35%): Success + tool value weighting
        - efficiency (20%): Performance vs tool-specific baseline
        - error_avoidance (25%): Error type discrimination
        - user_satisfaction (15%): User rating normalized
        - response_quality (5%): Data usefulness heuristic

        Returns:
            float: Total reward normalized to [-1, 1] range
        """
        components = {}
        baseline = cls.get_tool_baseline(execution.tool_name)

        # 1. Task Completion Component [-1, 1]
        if execution.success:
            # Scale by tool value (high-value tools get more reward)
            tool_value = baseline.get("value", 0.5)
            components["task_completion"] = 0.5 + (tool_value * 0.5)  # [0.5, 1.0]
        else:
            components["task_completion"] = -0.5

        # 2. Efficiency Component [-1, 1]
        if execution.execution_time_ms and execution.execution_time_ms > 0:
            expected_ms = baseline.get("expected_ms", 5000)

            # Calculate efficiency ratio (< 1 = faster than expected)
            ratio = execution.execution_time_ms / expected_ms

            if ratio <= 0.5:
                # Very fast - excellent
                components["efficiency"] = 1.0
            elif ratio <= 1.0:
                # Faster than expected - good
                components["efficiency"] = 1.0 - (ratio * 0.5)  # [0.5, 1.0]
            elif ratio <= 2.0:
                # Slower but acceptable
                components["efficiency"] = 0.5 - ((ratio - 1.0) * 0.5)  # [0.0, 0.5]
            elif ratio <= 5.0:
                # Slow - penalize
                components["efficiency"] = -((ratio - 2.0) / 6.0)  # [-0.5, 0.0]
            else:
                # Very slow - heavy penalty
                components["efficiency"] = -0.5 - min(0.5, (ratio - 5.0) / 10.0)  # [-1.0, -0.5]
        else:
            components["efficiency"] = 0.0  # No timing data

        # 3. Error Avoidance Component [-1, 1]
        if execution.success:
            components["error_avoidance"] = 1.0
        else:
            # Classify error and apply appropriate penalty
            error_type = cls.classify_error(execution.error_message if hasattr(execution, 'error_message') else None)
            penalty = cls.ERROR_PENALTIES.get(error_type, -0.8)
            components["error_avoidance"] = penalty

        # 4. User Satisfaction Component [-1, 1]
        if execution.user_rating is not None:
            # Normalize 1-5 rating to [-1, 1]
            # 1 -> -1, 3 -> 0, 5 -> 1
            components["user_satisfaction"] = (execution.user_rating - 3) / 2.0
        else:
            # No rating - use success as proxy (slight positive bias)
            components["user_satisfaction"] = 0.2 if execution.success else -0.2

        # 5. Response Quality Component [-1, 1]
        # Heuristic based on result content
        components["response_quality"] = cls._calculate_response_quality(execution)

        # Calculate weighted sum
        total_reward = sum(
            components[key] * cls.WEIGHTS[key]
            for key in cls.WEIGHTS
        )

        # Clamp to [-1, 1]
        total_reward = max(-1.0, min(1.0, total_reward))

        return total_reward

    @classmethod
    def _calculate_response_quality(cls, execution: ToolExecution) -> float:
        """Calculate response quality score based on result content."""
        if not execution.success:
            return -0.5

        # Check if result exists and has content
        result = getattr(execution, 'result', None)
        if result is None:
            return 0.0

        # If result is a string, check length
        if isinstance(result, str):
            if len(result) == 0:
                return -0.2  # Empty response
            elif len(result) < 50:
                return 0.3   # Short but present
            else:
                return 0.7   # Substantial content

        # If result is a dict/list, check structure
        if isinstance(result, dict):
            if len(result) == 0:
                return -0.2
            elif "error" in result or "message" in result:
                return 0.2   # Might be error wrapper
            else:
                return 0.8   # Structured data

        if isinstance(result, list):
            if len(result) == 0:
                return 0.0   # Empty list (might be valid)
            else:
                return 0.8   # Has items

        return 0.5  # Default for other types

    @classmethod
    def get_reward_breakdown(
        cls,
        execution: ToolExecution,
        avg_execution_time: Optional[float] = None
    ) -> Dict[str, Any]:
        """Get detailed breakdown of reward calculation for debugging."""
        baseline = cls.get_tool_baseline(execution.tool_name)

        # Calculate all components
        components = {}

        # Task completion
        if execution.success:
            tool_value = baseline.get("value", 0.5)
            components["task_completion"] = 0.5 + (tool_value * 0.5)
        else:
            components["task_completion"] = -0.5

        # Efficiency
        if execution.execution_time_ms and execution.execution_time_ms > 0:
            expected_ms = baseline.get("expected_ms", 5000)
            ratio = execution.execution_time_ms / expected_ms

            if ratio <= 0.5:
                components["efficiency"] = 1.0
            elif ratio <= 1.0:
                components["efficiency"] = 1.0 - (ratio * 0.5)
            elif ratio <= 2.0:
                components["efficiency"] = 0.5 - ((ratio - 1.0) * 0.5)
            elif ratio <= 5.0:
                components["efficiency"] = -((ratio - 2.0) / 6.0)
            else:
                components["efficiency"] = -0.5 - min(0.5, (ratio - 5.0) / 10.0)

            efficiency_ratio = ratio
        else:
            components["efficiency"] = 0.0
            efficiency_ratio = None

        # Error avoidance
        error_type = None
        if execution.success:
            components["error_avoidance"] = 1.0
        else:
            error_type = cls.classify_error(getattr(execution, 'error_message', None))
            components["error_avoidance"] = cls.ERROR_PENALTIES.get(error_type, -0.8)

        # User satisfaction
        if execution.user_rating is not None:
            components["user_satisfaction"] = (execution.user_rating - 3) / 2.0
        else:
            components["user_satisfaction"] = 0.2 if execution.success else -0.2

        # Response quality
        components["response_quality"] = cls._calculate_response_quality(execution)

        # Calculate weighted contributions
        weighted = {
            key: components[key] * cls.WEIGHTS[key]
            for key in cls.WEIGHTS
        }

        total = sum(weighted.values())

        return {
            "tool_name": execution.tool_name,
            "success": execution.success,
            "baseline": baseline,
            "execution_time_ms": execution.execution_time_ms,
            "efficiency_ratio": efficiency_ratio,
            "error_type": error_type,
            "user_rating": execution.user_rating,
            "components": components,
            "weights": cls.WEIGHTS,
            "weighted_contributions": weighted,
            "total_reward": max(-1.0, min(1.0, total)),
        }


class AdaptiveExploration:
    """Adaptive epsilon decay based on learning confidence and environment stability."""

    def __init__(
        self,
        initial_rate: float = 0.1,
        min_rate: float = 0.01,
        max_rate: float = 0.5,
        window_size: int = 50,
        stability_threshold: float = 0.1,
        change_detection_threshold: float = 0.3,
        fast_decay: float = 0.98,
        slow_decay: float = 0.999,
        recovery_boost: float = 1.5
    ):
        """Initialize adaptive exploration.

        Args:
            initial_rate: Starting exploration rate.
            min_rate: Minimum exploration rate floor.
            max_rate: Maximum exploration rate ceiling.
            window_size: Number of recent rewards to track.
            stability_threshold: Std dev threshold for "stable" learning.
            change_detection_threshold: Mean drop threshold to detect change.
            fast_decay: Decay rate when learning is stable.
            slow_decay: Decay rate when learning is unstable.
            recovery_boost: Multiplier when environment change detected.
        """
        self.initial_rate = initial_rate
        self.min_rate = min_rate
        self.max_rate = max_rate
        self.window_size = window_size
        self.stability_threshold = stability_threshold
        self.change_detection_threshold = change_detection_threshold
        self.fast_decay = fast_decay
        self.slow_decay = slow_decay
        self.recovery_boost = recovery_boost

        # Current state
        self.current_rate = initial_rate
        self._reward_history: deque = deque(maxlen=window_size)
        self._recent_mean: Optional[float] = None
        self._exploration_count = 0
        self._exploitation_count = 0
        self._change_detected_count = 0
        self._last_stability_check = 0

    def record_reward(self, reward: float):
        """Record a reward observation for stability tracking."""
        self._reward_history.append(reward)

    def get_confidence(self) -> float:
        """Calculate learning confidence based on reward stability.

        Returns:
            Confidence score in [0, 1]. Higher = more stable learning.
        """
        if len(self._reward_history) < 5:
            return 0.0  # Not enough data

        rewards = list(self._reward_history)
        mean = sum(rewards) / len(rewards)
        variance = sum((r - mean) ** 2 for r in rewards) / len(rewards)
        std_dev = math.sqrt(variance)

        # Normalize: low std dev = high confidence
        # std_dev of 0.1 or less = confidence 1.0
        # std_dev of 0.5 or more = confidence 0.0
        confidence = max(0.0, 1.0 - (std_dev / 0.5))
        return confidence

    def detect_environment_change(self) -> bool:
        """Detect if the environment has changed (reward distribution shift).

        Returns:
            True if a significant change is detected.
        """
        if len(self._reward_history) < self.window_size // 2:
            return False

        rewards = list(self._reward_history)
        mid = len(rewards) // 2

        # Compare first half vs second half
        first_half_mean = sum(rewards[:mid]) / mid if mid > 0 else 0
        second_half_mean = sum(rewards[mid:]) / (len(rewards) - mid) if len(rewards) > mid else 0

        # Track the historical mean for comparison
        if self._recent_mean is None:
            self._recent_mean = second_half_mean
            return False

        # Detect significant drop in performance
        if self._recent_mean > 0 and second_half_mean < self._recent_mean * (1 - self.change_detection_threshold):
            self._change_detected_count += 1
            self._recent_mean = second_half_mean
            return True

        # Update running mean
        self._recent_mean = 0.9 * self._recent_mean + 0.1 * second_half_mean
        return False

    def update(self, was_exploration: bool = False) -> float:
        """Update exploration rate adaptively.

        Args:
            was_exploration: Whether the last action was exploratory.

        Returns:
            Updated exploration rate.
        """
        # Track exploration vs exploitation
        if was_exploration:
            self._exploration_count += 1
        else:
            self._exploitation_count += 1

        # Check for environment change
        if self.detect_environment_change():
            # Boost exploration when change detected
            self.current_rate = min(
                self.max_rate,
                self.current_rate * self.recovery_boost
            )
            return self.current_rate

        # Get learning confidence
        confidence = self.get_confidence()

        # Adaptive decay based on confidence
        if confidence > 0.7:
            # High confidence = fast decay (exploit more)
            decay = self.fast_decay
        elif confidence > 0.3:
            # Medium confidence = moderate decay
            decay = (self.fast_decay + self.slow_decay) / 2
        else:
            # Low confidence = slow decay (keep exploring)
            decay = self.slow_decay

        # Apply decay
        self.current_rate = max(
            self.min_rate,
            self.current_rate * decay
        )

        return self.current_rate

    def reset(self, partial: bool = False):
        """Reset exploration rate.

        Args:
            partial: If True, only boost to halfway between current and initial.
        """
        if partial:
            self.current_rate = (self.current_rate + self.initial_rate) / 2
        else:
            self.current_rate = self.initial_rate

    def get_stats(self) -> Dict[str, Any]:
        """Get exploration statistics."""
        total = self._exploration_count + self._exploitation_count
        return {
            "current_rate": round(self.current_rate, 4),
            "confidence": round(self.get_confidence(), 3),
            "exploration_count": self._exploration_count,
            "exploitation_count": self._exploitation_count,
            "exploration_ratio": round(self._exploration_count / total, 3) if total > 0 else 0,
            "change_detected_count": self._change_detected_count,
            "reward_history_size": len(self._reward_history),
            "recent_mean": round(self._recent_mean, 3) if self._recent_mean else None
        }


class ToolSelector:
    """Intelligent tool selection based on RL policy and context."""

    def __init__(
        self,
        feedback_service: FeedbackService,
        exploration_rate: float = 0.1,
        min_samples: int = 5,
        exploration_decay: float = 0.995,
        min_exploration_rate: float = 0.01,
        ucb_c: float = 2.0,
        adaptive_exploration: bool = True
    ):
        self.feedback_service = feedback_service
        self.exploration_rate = exploration_rate
        self.initial_exploration_rate = exploration_rate
        self.min_samples = min_samples
        self.exploration_decay = exploration_decay
        self.min_exploration_rate = min_exploration_rate
        self.ucb_c = ucb_c  # UCB exploration constant
        self._tool_metadata_cache: Optional[dict] = None
        self._total_selections = 0
        self._tool_selection_counts: Dict[str, int] = defaultdict(int)

        # Adaptive exploration
        self._adaptive_enabled = adaptive_exploration
        self._adaptive = AdaptiveExploration(
            initial_rate=exploration_rate,
            min_rate=min_exploration_rate,
            max_rate=0.5
        ) if adaptive_exploration else None

    def create_context_hash(
        self,
        user_query: str = "",
        previous_tool: Optional[str] = None,
        session_length: int = 0
    ) -> str:
        """Create a hash representing the current state/context.
        
        Args:
            user_query: User's query or intent
            previous_tool: Previously executed tool name
            session_length: Number of tools executed in this session
            
        Returns:
            str: SHA256 hash of the context
        """
        # Extract keywords from query (simple approach)
        keywords = self._extract_keywords(user_query)
        
        context = {
            "keywords": sorted(keywords),
            "previous_tool": previous_tool or "",
            "session_length": session_length
        }
        
        context_str = json.dumps(context, sort_keys=True)
        return hashlib.sha256(context_str.encode()).hexdigest()

    def _extract_keywords(self, query: str) -> list[str]:
        """Extract relevant keywords from user query."""
        if not query:
            return []
        
        # Common FCCS-related keywords
        fccs_keywords = [
            "dimension", "member", "account", "entity", "period", "scenario",
            "journal", "consolidation", "report", "data", "retrieve", "export",
            "import", "rule", "job", "status", "hierarchy", "balance", "currency"
        ]
        
        query_lower = query.lower()
        found_keywords = [kw for kw in fccs_keywords if kw in query_lower]
        
        # Also include first few words as keywords
        words = query_lower.split()[:5]
        found_keywords.extend(words)
        
        return list(set(found_keywords))  # Remove duplicates

    def get_tool_recommendations(
        self,
        context_hash: str,
        available_tools: list[str],
        rl_policy: Optional[dict] = None
    ) -> list[dict]:
        """Get ranked list of recommended tools with confidence scores.
        
        Args:
            context_hash: Current context hash
            available_tools: List of available tool names
            rl_policy: Optional dict mapping (tool_name, context_hash) -> action_value
            
        Returns:
            List of dicts with tool_name, confidence, and reason
        """
        recommendations = []
        
        # Get tool metrics from feedback service
        all_metrics = self.feedback_service.get_tool_metrics()
        metrics_dict = {m["tool_name"]: m for m in all_metrics}
        
        for tool_name in available_tools:
            confidence = 0.5  # Default confidence
            reason = "Baseline recommendation"
            
            # Get metrics for this tool
            tool_metrics = metrics_dict.get(tool_name, {})
            
            # Calculate confidence based on multiple factors
            factors = []
            
            # Factor 1: Success rate
            success_rate = tool_metrics.get("success_rate", 0.5)
            if success_rate > 0.8:
                confidence += 0.2
                factors.append("high success rate")
            elif success_rate < 0.5:
                confidence -= 0.2
                factors.append("low success rate")
            
            # Factor 2: User ratings
            avg_rating = tool_metrics.get("avg_user_rating")
            if avg_rating:
                if avg_rating >= 4.0:
                    confidence += 0.15
                    factors.append("high user rating")
                elif avg_rating < 3.0:
                    confidence -= 0.15
                    factors.append("low user rating")
            
            # Factor 3: Execution time (faster is better)
            avg_time = tool_metrics.get("avg_execution_time_ms", 0)
            if avg_time > 0 and avg_time < 1000:  # Less than 1 second
                confidence += 0.1
                factors.append("fast execution")
            
            # Factor 4: RL policy value (if available)
            if rl_policy:
                policy_key = f"{tool_name}:{context_hash}"
                action_value = rl_policy.get(policy_key, 0.0)
                if action_value > 0:
                    confidence += min(0.2, action_value / 10.0)  # Normalize
                    factors.append("RL policy favor")
            
            # Factor 5: Sample size (more samples = more reliable)
            total_calls = tool_metrics.get("total_calls", 0)
            if total_calls >= self.min_samples:
                confidence += 0.05
                factors.append("sufficient samples")
            
            # Clamp confidence to [0, 1]
            confidence = max(0.0, min(1.0, confidence))
            
            if factors:
                reason = ", ".join(factors)
            
            recommendations.append({
                "tool_name": tool_name,
                "confidence": round(confidence, 3),
                "reason": reason,
                "metrics": {
                    "success_rate": success_rate,
                    "avg_rating": avg_rating,
                    "total_calls": total_calls
                }
            })
        
        # Sort by confidence (descending)
        recommendations.sort(key=lambda x: x["confidence"], reverse=True)
        
        return recommendations

    def record_reward(self, reward: float):
        """Record a reward for adaptive exploration tracking."""
        if self._adaptive_enabled and self._adaptive:
            self._adaptive.record_reward(reward)

    def decay_exploration(self, was_exploration: bool = False):
        """Apply exploration rate decay after each selection.

        Args:
            was_exploration: Whether the last selection was exploratory.
        """
        if self._adaptive_enabled and self._adaptive:
            # Use adaptive decay
            self.exploration_rate = self._adaptive.update(was_exploration)
        else:
            # Simple multiplicative decay
            self.exploration_rate = max(
                self.min_exploration_rate,
                self.exploration_rate * self.exploration_decay
            )

    def reset_exploration(self, partial: bool = False):
        """Reset exploration rate.

        Args:
            partial: If True and adaptive, only partial reset.
        """
        if self._adaptive_enabled and self._adaptive:
            self._adaptive.reset(partial=partial)
            self.exploration_rate = self._adaptive.current_rate
        else:
            self.exploration_rate = self.initial_exploration_rate

    def _calculate_ucb_score(
        self,
        tool_name: str,
        context_hash: str,
        rl_policy: Optional[dict] = None
    ) -> float:
        """Calculate UCB score for a tool.

        UCB1: Q(a) + c * sqrt(ln(N) / n(a))

        Args:
            tool_name: Tool to calculate score for.
            context_hash: Current context hash.
            rl_policy: Policy dictionary.

        Returns:
            UCB score (exploitation + exploration bonus).
        """
        # Exploitation term: Q-value from policy
        q_value = 0.0
        if rl_policy:
            policy_key = f"{tool_name}:{context_hash}"
            q_value = rl_policy.get(policy_key, 0.0)
            # Normalize to [0, 1] range
            q_value = 1.0 / (1.0 + math.exp(-q_value / 5.0))

        # Exploration term: UCB bonus for less-tried tools
        n_total = max(1, self._total_selections)
        n_tool = max(1, self._tool_selection_counts.get(tool_name, 1))
        exploration_bonus = self.ucb_c * math.sqrt(math.log(n_total) / n_tool)

        return q_value + exploration_bonus

    def select_tool(
        self,
        context_hash: str,
        available_tools: list[str],
        rl_policy: Optional[dict] = None,
        use_ucb: bool = True
    ) -> tuple[str, bool]:
        """Select a tool using UCB or epsilon-greedy strategy.

        Args:
            context_hash: Current context hash.
            available_tools: List of available tool names.
            rl_policy: Optional dict mapping (tool_name, context_hash) -> action_value.
            use_ucb: Whether to use UCB exploration (default True).

        Returns:
            Tuple of (selected_tool_name, was_exploration).
        """
        if not available_tools:
            raise ValueError("No available tools provided")

        self._total_selections += 1
        was_exploration = False

        # Epsilon-greedy check first (adds randomness even with UCB)
        if random.random() < self.exploration_rate:
            selected = random.choice(available_tools)
            was_exploration = True
        elif use_ucb and self._total_selections > len(available_tools):
            # UCB selection after initial exploration of all tools
            ucb_scores = {
                tool: self._calculate_ucb_score(tool, context_hash, rl_policy)
                for tool in available_tools
            }
            selected = max(ucb_scores, key=ucb_scores.get)
            # If UCB selected a rarely-used tool, count as exploration
            if self._tool_selection_counts.get(selected, 0) < self.min_samples:
                was_exploration = True
        else:
            # Exploitation: select best tool based on recommendations
            recommendations = self.get_tool_recommendations(
                context_hash, available_tools, rl_policy
            )
            if recommendations:
                selected = recommendations[0]["tool_name"]
            else:
                selected = random.choice(available_tools)
                was_exploration = True

        # Update selection counts
        self._tool_selection_counts[selected] += 1

        # Apply exploration decay (pass exploration flag for adaptive)
        self.decay_exploration(was_exploration)

        return selected, was_exploration

    def get_exploration_stats(self) -> Dict:
        """Get exploration statistics for monitoring."""
        stats = {
            "current_exploration_rate": self.exploration_rate,
            "initial_exploration_rate": self.initial_exploration_rate,
            "total_selections": self._total_selections,
            "tool_selection_counts": dict(self._tool_selection_counts),
            "adaptive_enabled": self._adaptive_enabled
        }

        # Add adaptive exploration stats if enabled
        if self._adaptive_enabled and self._adaptive:
            adaptive_stats = self._adaptive.get_stats()
            stats["adaptive"] = adaptive_stats
            stats["learning_confidence"] = adaptive_stats["confidence"]
            stats["environment_changes_detected"] = adaptive_stats["change_detected_count"]

        return stats


class ParameterOptimizer:
    """Learn optimal parameter patterns from successful executions."""

    def __init__(self, feedback_service: FeedbackService):
        self.feedback_service = feedback_service

    def suggest_parameters(
        self,
        tool_name: str,
        partial_args: dict,
        limit: int = 10
    ) -> dict:
        """Suggest optimal parameters based on historical successful executions.
        
        Args:
            tool_name: Name of the tool
            partial_args: Partial arguments provided by user
            limit: Number of historical executions to analyze
            
        Returns:
            Dict with suggested parameters and confidence
        """
        # Get recent successful executions for this tool
        recent_executions = self.feedback_service.get_recent_executions(
            tool_name=tool_name,
            limit=limit * 2  # Get more to filter for success
        )
        
        # Filter for successful executions with high ratings
        successful = [
            e for e in recent_executions
            if e.get("success") and (e.get("user_rating") or 0) >= 4
        ][:limit]
        
        if not successful:
            return {
                "suggested_params": partial_args,
                "confidence": 0.0,
                "reason": "No successful historical data"
            }
        
        # Get full execution details to extract arguments
        # Note: This would require extending feedback_service to return full execution details
        # For now, return partial args with confidence based on success rate
        success_rate = len(successful) / len(recent_executions) if recent_executions else 0
        
        return {
            "suggested_params": partial_args,
            "confidence": min(1.0, success_rate),
            "reason": f"Based on {len(successful)} successful executions",
            "sample_size": len(successful)
        }


class RLService:
    """Main RL service coordinating all RL components."""

    def __init__(
        self,
        feedback_service: FeedbackService,
        db_url: str,
        exploration_rate: float = 0.1,
        learning_rate: float = 0.1,
        discount_factor: float = 0.9,
        min_samples: int = 5,
        replay_buffer_size: int = 10000,
        batch_size: int = 32,
        exploration_decay: float = 0.995,
        min_exploration_rate: float = 0.01,
        ucb_c: float = 2.0
    ):
        self.feedback_service = feedback_service
        self.exploration_rate = exploration_rate
        self.learning_rate = learning_rate
        self.discount_factor = discount_factor
        self.min_samples = min_samples
        self.batch_size = batch_size

        # Initialize database for RL tables
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

        # Initialize core components
        self.reward_calculator = RewardCalculator()
        self.tool_selector = ToolSelector(
            feedback_service,
            exploration_rate=exploration_rate,
            min_samples=min_samples,
            exploration_decay=exploration_decay,
            min_exploration_rate=min_exploration_rate,
            ucb_c=ucb_c,
            adaptive_exploration=True  # Enable adaptive epsilon decay
        )
        self.parameter_optimizer = ParameterOptimizer(feedback_service)

        # Initialize new components
        self.replay_buffer = ExperienceReplayBuffer(capacity=replay_buffer_size)
        self.sequence_learner = SequenceLearner(self.Session, n=3)
        self.metrics_tracker = LearningMetricsTracker(self.Session)

        # Cache for policy values (in-memory for performance)
        # Thread-safe cache with lock
        self._policy_cache: dict[str, float] = {}
        self._cache_updated = False
        self._cache_lock = threading.RLock()  # Reentrant lock for nested calls

        # Track learning progress
        self._update_count = 0

    def calculate_reward(self, execution: ToolExecution) -> float:
        """Calculate reward for a tool execution using enhanced multi-component shaping.

        The reward considers:
        - Task completion (35%): Success + tool value weighting
        - Efficiency (20%): Performance vs tool-specific baseline
        - Error avoidance (25%): Error type discrimination
        - User satisfaction (15%): User rating normalized
        - Response quality (5%): Data usefulness heuristic

        Returns:
            float: Total reward normalized to [-1, 1] range
        """
        # Get tool metrics for context
        metrics = self.feedback_service.get_tool_metrics(execution.tool_name)
        tool_metrics = metrics[0] if metrics else None
        avg_time = tool_metrics.get("avg_execution_time_ms") if tool_metrics else None

        return RewardCalculator.calculate_reward(execution, avg_time, tool_metrics)

    def get_reward_breakdown(self, execution: ToolExecution) -> Dict:
        """Get detailed breakdown of reward calculation for debugging/analysis.

        Useful for understanding why a particular reward was assigned.

        Returns:
            Dict with component scores, weights, and weighted contributions.
        """
        metrics = self.feedback_service.get_tool_metrics(execution.tool_name)
        avg_time = metrics[0].get("avg_execution_time_ms") if metrics else None

        return RewardCalculator.get_reward_breakdown(execution, avg_time)

    def get_tool_recommendations(
        self,
        user_query: str = "",
        previous_tool: Optional[str] = None,
        session_length: int = 0,
        available_tools: Optional[list[str]] = None
    ) -> list[dict]:
        """Get tool recommendations for current context.
        
        Args:
            user_query: User's query or intent
            previous_tool: Previously executed tool
            session_length: Number of tools in current session
            available_tools: Optional list of available tools (if None, uses all)
            
        Returns:
            List of recommended tools with confidence scores
        """
        # Create context hash
        context_hash = self.tool_selector.create_context_hash(
            user_query, previous_tool, session_length
        )
        
        # Get available tools
        if available_tools is None:
            # Get all tools from feedback service metrics
            all_metrics = self.feedback_service.get_tool_metrics()
            available_tools = [m["tool_name"] for m in all_metrics]
        
        # Get RL policy
        rl_policy = self._get_policy_dict()
        
        return self.tool_selector.get_tool_recommendations(
            context_hash, available_tools, rl_policy
        )

    def optimize_parameters(
        self,
        tool_name: str,
        context: dict,
        partial_args: dict
    ) -> dict:
        """Optimize parameters for a tool based on context."""
        return self.parameter_optimizer.suggest_parameters(
            tool_name, partial_args
        )

    def update_policy(
        self,
        session_id: str,
        tool_name: str,
        context_hash: str,
        reward: float,
        next_context_hash: Optional[str] = None,
        available_tools: Optional[list[str]] = None,
        is_terminal: bool = False
    ):
        """Update RL policy using Q-learning update rule.

        Q(s,a) = Q(s,a) + alpha * [reward + gamma * max(Q(s',a')) - Q(s,a)]

        Args:
            session_id: Current session identifier
            tool_name: The tool/action that was taken
            context_hash: Hash of the state before action (s)
            reward: Immediate reward received
            next_context_hash: Hash of the state after action (s')
                              If None, treats as terminal state (no future value)
            available_tools: List of available tools for computing max Q(s',a')
                            If None, uses all known tools from policy cache
            is_terminal: Whether this is a terminal state
        """
        # Store experience in replay buffer
        experience = Experience(
            state_hash=context_hash,
            action=tool_name,
            reward=reward,
            next_state_hash=next_context_hash,
            done=is_terminal
        )
        self.replay_buffer.add(experience, priority=abs(reward) + 1.0)

        # Record reward for adaptive exploration
        self.tool_selector.record_reward(reward)

        # Perform single update
        td_error = self._update_single_policy(
            tool_name, context_hash, reward, next_context_hash, available_tools
        )

        # Track metrics
        self._update_count += 1
        self.metrics_tracker.record("reward", reward, {"tool": tool_name})
        self.metrics_tracker.record("td_error", abs(td_error), {"tool": tool_name})
        self.metrics_tracker.record("exploration_rate", self.tool_selector.exploration_rate)

        # Track adaptive exploration metrics
        if self.tool_selector._adaptive_enabled:
            stats = self.tool_selector.get_exploration_stats()
            self.metrics_tracker.record("learning_confidence", stats.get("learning_confidence", 0))

        # Periodically do batch update from replay buffer
        if self._update_count % 10 == 0 and len(self.replay_buffer) >= self.batch_size:
            self.batch_update_from_replay(available_tools)

    def _update_single_policy(
        self,
        tool_name: str,
        context_hash: str,
        reward: float,
        next_context_hash: Optional[str] = None,
        available_tools: Optional[list[str]] = None
    ) -> float:
        """Perform a single Q-learning update. Returns TD error."""
        # Compute max future Q-value if next state is provided
        max_future_q = 0.0
        if next_context_hash is not None:
            policy_dict = self._get_policy_dict()

            # Get available tools for next state
            if available_tools is None:
                # Extract unique tool names from existing policies
                available_tools = list(set(
                    key.split(":")[0] for key in policy_dict.keys()
                ))

            # Find max Q(s', a') across all available actions in next state
            if available_tools:
                future_q_values = [
                    policy_dict.get(f"{tool}:{next_context_hash}", 0.0)
                    for tool in available_tools
                ]
                max_future_q = max(future_q_values) if future_q_values else 0.0

        td_error = 0.0
        with self.Session() as session:
            # Get or create policy entry
            policy = session.query(RLPolicy).filter_by(
                tool_name=tool_name,
                context_hash=context_hash
            ).first()

            if not policy:
                policy = RLPolicy(
                    tool_name=tool_name,
                    context_hash=context_hash,
                    action_value=0.0,
                    visit_count=0
                )
                session.add(policy)
                session.flush()

            # Full Q-learning update: Q(s,a) = Q(s,a) + alpha * [R + gamma * max(Q(s',a')) - Q(s,a)]
            old_value = policy.action_value
            td_target = reward + self.discount_factor * max_future_q
            td_error = td_target - old_value
            new_value = old_value + self.learning_rate * td_error

            policy.action_value = new_value
            policy.visit_count += 1
            policy.last_updated = datetime.utcnow()

            session.commit()

            # Update cache with thread safety
            cache_key = f"{tool_name}:{context_hash}"
            with self._cache_lock:
                self._policy_cache[cache_key] = new_value
                self._cache_updated = True

        return td_error

    def batch_update_from_replay(
        self,
        available_tools: Optional[list[str]] = None
    ):
        """Perform batch updates from replay buffer for stable learning."""
        if len(self.replay_buffer) < self.batch_size:
            return

        batch = self.replay_buffer.sample(self.batch_size)
        total_td_error = 0.0

        for exp in batch:
            td_error = self._update_single_policy(
                exp.action,
                exp.state_hash,
                exp.reward,
                exp.next_state_hash if not exp.done else None,
                available_tools
            )
            total_td_error += abs(td_error)

        # Track batch metrics
        avg_td_error = total_td_error / len(batch)
        self.metrics_tracker.record("batch_avg_td_error", avg_td_error)

    def _get_policy_dict(self) -> dict[str, float]:
        """Get policy as dictionary for fast lookup.

        Returns a copy of the cache to prevent external modification.
        Thread-safe implementation using lock.
        """
        with self._cache_lock:
            if not self._cache_updated:
                # Load from database
                with self.Session() as session:
                    policies = session.query(RLPolicy).all()
                    for policy in policies:
                        key = f"{policy.tool_name}:{policy.context_hash}"
                        self._policy_cache[key] = policy.action_value
                    self._cache_updated = True

            # Return a copy to prevent external modification
            return self._policy_cache.copy()

    def get_tool_confidence(
        self,
        tool_name: str,
        context_hash: str
    ) -> float:
        """Get confidence score for a tool in given context.

        Maps Q-values (which converge to [-1, 1] with enhanced reward shaping)
        to a [0, 1] confidence score using sigmoid normalization.
        """
        policy_dict = self._get_policy_dict()
        key = f"{tool_name}:{context_hash}"
        action_value = policy_dict.get(key, 0.0)

        # Normalize to [0, 1] range (rewards are now in [-1, 1] range)
        # Use scaling factor of 0.5 for good discrimination:
        # Q = -1.0 -> confidence ~0.12
        # Q =  0.0 -> confidence  0.50
        # Q = +1.0 -> confidence ~0.88
        confidence = 1.0 / (1.0 + np.exp(-action_value / 0.5))
        return float(confidence)

    def log_episode(
        self,
        session_id: str,
        tool_sequence: list[str],
        episode_reward: float,
        outcome: str = "success"
    ):
        """Log a complete episode (session) for sequence learning."""
        with self.Session() as session:
            episode = RLEpisode(
                session_id=session_id,
                episode_reward=episode_reward,
                tool_sequence=tool_sequence,
                outcome=outcome,
                created_at=datetime.utcnow()
            )
            session.add(episode)
            session.commit()

        # Learn N-gram sequences from this episode
        success = outcome == "success"
        self.sequence_learner.record_sequence(tool_sequence, episode_reward, success)

        # Track episode metrics
        self.metrics_tracker.record("episode_reward", episode_reward, {"outcome": outcome})
        self.metrics_tracker.record("episode_length", len(tool_sequence), {"outcome": outcome})

    def get_sequence_recommendations(
        self,
        recent_tools: List[str],
        available_tools: List[str],
        top_k: int = 5
    ) -> List[Dict]:
        """Get tool recommendations based on sequence patterns.

        Args:
            recent_tools: Recently executed tools.
            available_tools: List of available tool names.
            top_k: Number of recommendations.

        Returns:
            List of recommended tools with sequence scores.
        """
        return self.sequence_learner.get_next_tool_recommendations(
            recent_tools, available_tools, top_k
        )

    def get_learning_stats(self) -> Dict:
        """Get comprehensive learning statistics."""
        stats = {
            "update_count": self._update_count,
            "replay_buffer_size": len(self.replay_buffer),
            "exploration_stats": self.tool_selector.get_exploration_stats(),
        }

        # Get metric summaries
        for metric_name in ["reward", "td_error", "episode_reward", "exploration_rate"]:
            summary = self.metrics_tracker.get_metric_summary(metric_name, window_size=100)
            if summary.get("count", 0) > 0:
                stats[f"{metric_name}_stats"] = summary

        return stats

    def get_successful_sequences(
        self,
        tool_name: Optional[str] = None,
        limit: int = 10
    ) -> list[dict]:
        """Get successful tool sequences for pattern learning."""
        try:
            with self.Session() as session:
                query = session.query(RLEpisode).filter_by(outcome="success")
                
                # Fetch all successful episodes first
                episodes = query.order_by(
                    RLEpisode.episode_reward.desc()
                ).limit(limit * 2 if tool_name else limit).all()  # Fetch more if filtering
                
                # Filter by tool_name in Python (more reliable for JSON arrays)
                if tool_name:
                    episodes = [
                        e for e in episodes 
                        if e.tool_sequence and isinstance(e.tool_sequence, list) and tool_name in e.tool_sequence
                    ][:limit]  # Apply limit after filtering
                
                return [
                    {
                        "session_id": e.session_id,
                        "tool_sequence": e.tool_sequence,
                        "episode_reward": e.episode_reward,
                        "created_at": e.created_at.isoformat() if e.created_at else None
                    }
                    for e in episodes
                ]
        except Exception as e:
            # Log error but don't crash - return empty list
            import sys
            print(f"Warning: Failed to get successful sequences: {e}", file=sys.stderr)
            return []


# Global RL service instance with thread-safe initialization
_rl_service: Optional[RLService] = None
_rl_service_lock = threading.Lock()


def init_rl_service(
    feedback_service: FeedbackService,
    db_url: str,
    exploration_rate: float = 0.1,
    learning_rate: float = 0.1,
    discount_factor: float = 0.9,
    min_samples: int = 5,
    replay_buffer_size: int = 10000,
    batch_size: int = 32,
    exploration_decay: float = 0.995,
    min_exploration_rate: float = 0.01,
    ucb_c: float = 2.0
) -> RLService:
    """Initialize the global RL service.

    Thread-safe initialization using double-checked locking pattern.

    Args:
        feedback_service: Feedback service for tool metrics.
        db_url: Database URL for RL tables.
        exploration_rate: Initial exploration rate (epsilon).
        learning_rate: Q-learning alpha parameter.
        discount_factor: Q-learning gamma parameter.
        min_samples: Minimum samples before using RL recommendations.
        replay_buffer_size: Size of experience replay buffer.
        batch_size: Batch size for replay updates.
        exploration_decay: Decay rate for exploration (per selection).
        min_exploration_rate: Minimum exploration rate after decay.
        ucb_c: UCB exploration constant.

    Returns:
        Initialized RLService instance.
    """
    global _rl_service
    if _rl_service is None:
        with _rl_service_lock:
            # Double-check after acquiring lock
            if _rl_service is None:
                _rl_service = RLService(
                    feedback_service,
                    db_url,
                    exploration_rate=exploration_rate,
                    learning_rate=learning_rate,
                    discount_factor=discount_factor,
                    min_samples=min_samples,
                    replay_buffer_size=replay_buffer_size,
                    batch_size=batch_size,
                    exploration_decay=exploration_decay,
                    min_exploration_rate=min_exploration_rate,
                    ucb_c=ucb_c
                )
    return _rl_service


def get_rl_service() -> Optional[RLService]:
    """Get the global RL service instance.

    Thread-safe access to global instance.
    """
    return _rl_service

