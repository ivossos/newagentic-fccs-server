from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PlanStep:
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""


@dataclass
class Plan:
    query: str
    steps: list[PlanStep]
    notes: str = ""


@dataclass
class ToolExecutionResult:
    tool_name: str
    arguments: dict[str, Any]
    result: dict[str, Any]


@dataclass
class PipelineResult:
    status: str
    plan: Plan
    results: list[ToolExecutionResult]
    error: str | None = None
