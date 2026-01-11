"""Orchestrator for agentic reasoning and execution."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Awaitable

from fccs_agent.intelligence.context_memory import ContextMemory
from fccs_agent.intelligence.intent_classifier import FCCSIntentClassifier, Intent
from fccs_agent.intelligence.llm_reasoning import LLMReasoner
from fccs_agent.intelligence.planner import FCCSPlanner, ExecutionStep, ExecutionPlan, StepStatus
from fccs_agent.services.rl_service import RLService

# Setup logging
logger = logging.getLogger(__name__)


class ExecutionStatus(Enum):
    """Status of the overall execution."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass
class OrchestratorResponse:
    """Consolidated response from the orchestrator."""
    success: bool
    results: List[Dict[str, Any]] = field(default_factory=list)
    plan: Optional[ExecutionPlan] = None
    intent: Optional[Intent] = None
    context_updates: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    synthesis: Optional[str] = None
    error_explanation: Optional[str] = None
    execution_time_ms: float = 0.0
    tokens_used: int = 0


@dataclass
class OrchestratorConfig:
    """Configuration for the orchestrator."""
    use_llm: bool = True
    use_rl: bool = True
    use_context_memory: bool = True
    enable_parallel_execution: bool = True
    confidence_threshold: float = 0.7
    max_steps: int = 10
    verbose: bool = True


class FCCSOrchestrator:
    """Central orchestrator for the FCCS Agent reasoning pipeline.
    
    Coordinates intent classification, planning, execution, 
    context management, and results synthesis.
    """

    def __init__(
        self,
        client: Any = None,
        config: Optional[OrchestratorConfig] = None,
        db_url: str = None,
        anthropic_api_key: str = None,
        app_name: str = "Consol"
    ):
        """Initialize the orchestrator."""
        self.client = client
        self.config = config or OrchestratorConfig()
        self.app_name = app_name
        
        # Initialize components
        self.intent_classifier = FCCSIntentClassifier()
        self.planner = FCCSPlanner()
        
        if self.config.use_context_memory and db_url:
            self.context_memory = ContextMemory(db_url)
        else:
            self.context_memory = None
            
        if self.config.use_llm and anthropic_api_key:
            self.llm_reasoner = LLMReasoner(api_key=anthropic_api_key)
        else:
            self.llm_reasoner = None
            
        self.rl_service: Optional[RLService] = None
        self._tool_handlers: Dict[str, Callable[..., Awaitable[Dict[str, Any]]]] = {}
        self._available_tools: List[str] = []

    def set_tool_handlers(self, handlers: Dict[str, Callable]):
        """Register tool handlers."""
        self._tool_handlers = handlers
        self._available_tools = list(handlers.keys())

    def set_rl_service(self, rl_service: RLService):
        """Register RL service."""
        self.rl_service = rl_service

    async def process(
        self,
        user_query: str,
        session_id: str = "default"
    ) -> OrchestratorResponse:
        """Process a user query through the full reasoning pipeline."""
        start_time = time.time()
        results = []
        tokens_used = 0
        
        try:
            # 1. Classify intent
            # if self.config.verbose:
            #    print(f"[Orchestrator] Classifying intent for: {user_query[:50]}...", file=sys.stderr)
            
            intent = await self._classify_intent(user_query, session_id)
            
            # 2. Enrich context from memory
            enriched_entities = intent.entities.copy()
            if self.context_memory:
                self.context_memory.update_from_entities(session_id, intent.entities)
                
                # Get suggested params based on context
                suggested = self.context_memory.get_suggested_params(
                    session_id, 
                    intent.suggested_tools[0] if intent.suggested_tools else ""
                )
                
                # Merge suggested into enriched (entities from query take precedence)
                for k, v in suggested.items():
                    if k not in enriched_entities or not enriched_entities[k]:
                        enriched_entities[k] = v
            
            # 3. Generate plan
            plan = self.planner.create_plan(
                intent=intent.name,
                entities=enriched_entities,
                available_tools=self._available_tools,
                sub_intent=intent.sub_intent,
                suggested_tools=intent.suggested_tools,
                user_query=user_query
            )
            
            if not plan.steps:
                return OrchestratorResponse(
                    success=False,
                    intent=intent,
                    error_explanation="I'm sorry, I couldn't determine which tools to use for your request."
                )
            
            # 4. Execute plan
            results = await self._execute_plan(plan, session_id, user_query)
            
            # 5. Synthesize results
            synthesis = None
            if self.llm_reasoner and self.llm_reasoner.is_available:
                try:
                    context = self.context_memory.get_recent_context(session_id) if self.context_memory else {}
                    synthesis_result = await self.llm_reasoner.synthesize_results(
                        query=user_query,
                        results=results,
                        context=context
                    )
                    synthesis = synthesis_result.content
                    tokens_used += synthesis_result.tokens_used
                except Exception as e:
                    print(f"Warning: Synthesis failed: {e}", file=sys.stderr)
            
            # 6. Generate recommendations
            recommendations = []
            if self.rl_service:
                try:
                    last_tool = results[-1].get("tool_name") if results else None
                    recommendations = self.rl_service.get_tool_recommendations(
                        user_query=user_query,
                        previous_tool=last_tool,
                        session_length=len(results),
                        available_tools=self._available_tools
                    )
                except Exception:
                    pass
            
            # If no RL recommendations, try LLM recommendations
            if not recommendations and self.llm_reasoner and self.llm_reasoner.is_available:
                try:
                    rec_result = await self.llm_reasoner.generate_recommendations(
                        intent=intent.name,
                        results=results,
                        context=context
                    )
                    recommendations = rec_result # It returns List[str] already
                except Exception:
                    pass

            execution_time = (time.time() - start_time) * 1000
            
            return OrchestratorResponse(
                success=all(r.get("status") == "success" for r in results),
                results=results,
                plan=plan,
                intent=intent,
                synthesis=synthesis,
                recommendations=recommendations,
                execution_time_ms=execution_time,
                tokens_used=tokens_used
            )

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            logger.exception("Orchestrator error")
            return OrchestratorResponse(
                success=False,
                error_explanation=str(e),
                execution_time_ms=execution_time
            )

    async def _classify_intent(self, query: str, session_id: str) -> Intent:
        """Classify intent using rules and LLM if needed."""
        # Rule-based classification first
        intent = self.intent_classifier.classify(query)
        
        # If confidence is low and LLM is available, use LLM
        if intent.confidence < self.config.confidence_threshold:
            if self.llm_reasoner and self.llm_reasoner.is_available:
                try:
                    context = self.context_memory.get_recent_context(session_id) if self.context_memory else {}
                    llm_intent_data = await self.llm_reasoner.classify_intent_async(query, context)
                    
                    # Merge LLM intent if it has higher confidence
                    if llm_intent_data.confidence > intent.confidence:
                        intent.name = llm_intent_data.name
                        intent.confidence = llm_intent_data.confidence
                        intent.entities.update(llm_intent_data.entities)
                        intent.suggested_tools = llm_intent_data.suggested_tools
                except Exception as e:
                    print(f"Warning: LLM classification failed: {e}", file=sys.stderr)
                    
        return intent

    async def _execute_plan(
        self,
        plan: ExecutionPlan,
        session_id: str,
        user_query: str
    ) -> List[Dict[str, Any]]:
        """Execute all steps in a plan."""
        results = []
        
        # Group steps by parallel group
        groups: Dict[int, List[Any]] = {}
        for step in plan.steps:
            groups.setdefault(step.parallel_group, []).append(step)
            
        # Execute groups sequentially
        for group_id in sorted(groups.keys()):
            group_steps = groups[group_id]
            
            # Execute steps in group
            if self.config.enable_parallel_execution and len(group_steps) > 1:
                # Parallel execution within group
                tasks = [
                    self._execute_step(step, session_id, user_query)
                    for step in group_steps
                ]
                group_results = await asyncio.gather(*tasks)
                results.extend(group_results)
            else:
                # Sequential execution within group
                for step in group_steps:
                    result = await self._execute_step(step, session_id, user_query)
                    results.append(result)
                    
                    # Stop if mandatory step failed
                    if result.get("status") == "error" and not step.optional:
                        break
                        
            # Check if we should stop execution
            if results and results[-1].get("status") == "error" and not groups[group_id][-1].optional:
                break
                
        return results

    async def _execute_step(
        self,
        step: Any,
        session_id: str,
        user_query: str
    ) -> Dict[str, Any]:
        """Execute a single plan step."""
        tool_name = step.tool_name
        params = step.parameters.copy() # Use a copy to avoid modifying plan
        
        # 1. Update params from context if context memory is available
        # This allows results from earlier steps (like query_local_metadata)
        # to influence later steps (like smart_retrieve)
        if self.context_memory:
            suggested = self.context_memory.get_suggested_params(session_id, tool_name)
            # Default values to avoid overwriting explicitly provided values with defaults
            defaults = {"entity": "FCCS_Total Geography", "consolidation": "FCCS_Entity Total"}
            
            # Merge context into params: 
            # 1. If param is missing or placeholder, always use context
            # 2. For account and entity, prefer context if it's not a default value
            for k, v in suggested.items():
                is_placeholder = k in params and str(params[k]).startswith("%")
                is_missing = k not in params or not params[k]
                is_default = k in defaults and v == defaults[k]
                
                if is_missing or is_placeholder or (k in ["account", "entity"] and not is_default):
                    params[k] = v
        
        handler = self._tool_handlers.get(tool_name)
        if not handler:
            return {
                "status": "error",
                "error": f"Tool handler not found: {tool_name}",
                "tool_name": tool_name
            }
            
        step.status = StepStatus.RUNNING
        
        try:
            # Note: we use the handler directly, but the actual tool execution
            # is wrapped by execute_tool in agent.py which handles RL and feedback.
            # Here we are calling the handler which might be the real tool or a mock.
            
            # If running via orchestrator, we want to use the enhanced execution
            from fccs_agent.agent import execute_tool
            result = await execute_tool(
                tool_name=tool_name,
                arguments=params,
                session_id=session_id,
                user_query=user_query
            )
            
            step.status = StepStatus.COMPLETED if result.get("status") == "success" else StepStatus.FAILED
            
            # Update context if successful
            if step.status == StepStatus.COMPLETED and self.context_memory:
                self.context_memory.update_from_result(session_id, tool_name, result)
                
            return {
                "tool_name": tool_name,
                "parameters": params,
                **result
            }
            
        except Exception as e:
            step.status = StepStatus.FAILED
            return {
                "status": "error",
                "error": str(e),
                "tool_name": tool_name,
                "parameters": params
            }
