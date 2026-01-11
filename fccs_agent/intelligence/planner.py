"""Multi-step Planning for FCCS operations.

Decomposes complex user queries into executable steps,
handles dependencies, and provides parallel execution strategies.
"""

from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
import copy


class StepStatus(Enum):
    """Execution step status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ExecutionStep:
    """A single step in an execution plan."""
    id: int
    tool_name: str
    parameters: Dict[str, Any]
    depends_on: List[int] = field(default_factory=list)  # Step IDs this depends on
    description: str = ""
    status: StepStatus = StepStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    parallel_group: int = 0  # Steps in same group can run in parallel
    optional: bool = False  # If True, failure doesn't stop the plan
    retry_count: int = 0
    max_retries: int = 2
    
    def can_execute(self, completed_steps: Set[int]) -> bool:
        """Check if all dependencies are satisfied."""
        return all(dep_id in completed_steps for dep_id in self.depends_on)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "tool_name": self.tool_name,
            "parameters": self.parameters,
            "depends_on": self.depends_on,
            "description": self.description,
            "status": self.status.value,
            "parallel_group": self.parallel_group,
            "optional": self.optional,
        }


@dataclass
class ExecutionPlan:
    """A complete execution plan with multiple steps."""
    steps: List[ExecutionStep]
    name: str = "Unnamed Plan"
    description: str = ""
    estimated_duration_seconds: float = 0.0
    
    def get_ready_steps(self, completed_steps: Set[int]) -> List[ExecutionStep]:
        """Get steps that are ready to execute."""
        return [
            step for step in self.steps
            if step.status == StepStatus.PENDING and step.can_execute(completed_steps)
        ]
    
    def get_parallel_groups(self) -> Dict[int, List[ExecutionStep]]:
        """Group steps by parallel execution group."""
        groups = {}
        for step in self.steps:
            if step.parallel_group not in groups:
                groups[step.parallel_group] = []
            groups[step.parallel_group].append(step)
        return groups
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "estimated_duration_seconds": self.estimated_duration_seconds,
        }


class FCCSPlanner:
    """Plan multi-step tool executions for complex FCCS queries.
    
    Supports:
    - Pattern-based planning for common operations
    - Dynamic planning for custom queries
    - Dependency resolution
    - Parallel execution grouping
    - Parameter inheritance between steps
    """
    
    # Pre-defined execution patterns for common FCCS operations
    PATTERNS = {
        # IMPORTANT: simple_data_retrieval should match first for basic queries
        "simple_data_retrieval": {
            "name": "Standard Data Retrieval",
            "description": "Follow standard flow: Check members -> Cache lookup -> Build query -> Execute",
            "steps": [
                {
                    "tool": "query_local_metadata",
                    "params_template": {},
                    "desc": "Check local metadata cache for members",
                    "parallel_group": 0,
                    "optional": True
                },
                {
                    "tool": "smart_retrieve",
                    "params_template": {},
                    "desc": "Execute smart_retrieve (builds query and runs export_data_slice)",
                    "parallel_group": 1
                },
            ],
            # High-priority triggers for simple data queries
            "triggers": ["show me", "get the", "what is", "retrieve", "pull", "fetch",
                         "balance", "value", "amount", "data for"],
            "estimated_duration": 7.0,
            "priority": 10  # Higher priority than other patterns
        },
        "variance_analysis": {
            "name": "Variance Analysis",
            "description": "Compare data across scenarios or periods",
            "steps": [
                {
                    "tool": "smart_retrieve",
                    "params_template": {"scenario": "Actual"},
                    "desc": "Retrieve actual data",
                    "parallel_group": 0
                },
                {
                    "tool": "smart_retrieve",
                    "params_template": {"scenario": "Forecast"},
                    "desc": "Retrieve forecast data",
                    "parallel_group": 0  # Can run in parallel with above
                },
            ],
            "triggers": ["variance", "compare", "actual vs forecast", "actual vs budget", "versus", "vs"],
            "estimated_duration": 10.0,
            "priority": 5
        },
        "consolidation_audit": {
            "name": "Consolidation Audit",
            "description": "Audit consolidation process for an entity",
            "steps": [
                {
                    "tool": "smart_retrieve",
                    "params_template": {},
                    "desc": "Get total value",
                    "parallel_group": 0
                },
                {
                    "tool": "smart_retrieve_consolidation_breakdown",
                    "params_template": {},
                    "desc": "Get consolidation breakdown",
                    "parallel_group": 1
                },
                {
                    "tool": "smart_retrieve_with_movement",
                    "params_template": {"movement": "FCCS_Mvmts_Subtotal"},
                    "desc": "Get movement breakdown",
                    "parallel_group": 1
                },
            ],
            # More specific triggers - require explicit consolidation keywords
            "triggers": ["consolidation audit", "consolidation breakdown", "audit consolidation",
                         "consol breakdown", "elimination breakdown", "breakdown by movement", "movement breakdown"],
            "estimated_duration": 15.0,
            "priority": 3
        },
        "period_close_status": {
            "name": "Period Close Status",
            "description": "Check status of period close activities",
            "steps": [
                {
                    "tool": "list_jobs",
                    "params_template": {},
                    "desc": "Check recent jobs",
                    "parallel_group": 0
                },
                {
                    "tool": "get_journals",
                    "params_template": {"status": "Posted"},
                    "desc": "Check posted journals",
                    "parallel_group": 0
                },
                {
                    "tool": "validate_metadata",
                    "params_template": {},
                    "desc": "Validate metadata",
                    "parallel_group": 1,
                    "optional": True
                },
            ],
            "triggers": ["period close", "month end close", "close status", "ready to close"],
            "estimated_duration": 20.0,
            "priority": 4
        },
        "intercompany_reconciliation": {
            "name": "Intercompany Reconciliation",
            "description": "Check intercompany balances and matching",
            "steps": [
                {
                    "tool": "smart_retrieve",
                    "params_template": {"consolidation": "FCCS_Entity_Input"},
                    "desc": "Get entity input data",
                    "parallel_group": 0
                },
                {
                    "tool": "generate_intercompany_matching_report",
                    "params_template": {},
                    "desc": "Generate ICP matching report",
                    "parallel_group": 1
                },
            ],
            "triggers": ["intercompany reconciliation", "icp matching", "intercompany matching", "icp report"],
            "estimated_duration": 25.0,
            "priority": 4
        },
        "journal_workflow": {
            "name": "Journal Workflow",
            "description": "List and process journals",
            "steps": [
                {
                    "tool": "get_journals",
                    "params_template": {},
                    "desc": "List journals",
                    "parallel_group": 0
                },
            ],
            "triggers": ["list journals", "show journals", "journal entries", "pending journals", "posted journals"],
            "estimated_duration": 5.0,
            "priority": 6
        },
        "run_consolidation": {
            "name": "Run Consolidation",
            "description": "Execute consolidation business rule",
            "steps": [
                {
                    "tool": "run_business_rule",
                    "params_template": {"rule_name": "FCCS_Consolidate All With Data"},
                    "desc": "Run consolidation rule",
                    "parallel_group": 0
                },
            ],
            "triggers": ["run consolidate", "execute consolidate", "consolidate rule", "run consolidation", 
                         "execute consolidation", "perform consolidation", "consolidate"],
            "estimated_duration": 30.0,
            "priority": 8
        },
        "unlock_entity": {
            "name": "Unlock Entity",
            "description": "Unlock entity for data entry or consolidation",
            "steps": [
                {
                    "tool": "run_business_rule",
                    "params_template": {"rule_name": "FCCS_Unlock Impacted Entities"},
                    "desc": "Unlock entity",
                    "parallel_group": 0
                },
            ],
            "triggers": ["unlock entity", "unlock", "run unlock", "execute unlock"],
            "estimated_duration": 10.0,
            "priority": 9
        },
        "lock_entity": {
            "name": "Lock Entity",
            "description": "Lock entity after consolidation",
            "steps": [
                {
                    "tool": "run_business_rule",
                    "params_template": {"rule_name": "FCCS_Lock Entities"},
                    "desc": "Lock entity",
                    "parallel_group": 0
                },
            ],
            "triggers": ["lock entity", "lock", "run lock", "execute lock"],
            "estimated_duration": 10.0,
            "priority": 9
        },
        "translate_entity": {
            "name": "Translate Entity",
            "description": "Run currency translation",
            "steps": [
                {
                    "tool": "run_business_rule",
                    "params_template": {"rule_name": "FCCS_Translate"},
                    "desc": "Run translation rule",
                    "parallel_group": 0
                },
            ],
            "triggers": ["translate", "run translate", "currency translation", "execute translate"],
            "estimated_duration": 20.0,
            "priority": 8
        },
        "unlock_and_consolidate": {
            "name": "Unlock and Consolidate",
            "description": "Unlock entity then run consolidation",
            "steps": [
                {
                    "tool": "run_business_rule",
                    "params_template": {"rule_name": "Unlock"},
                    "desc": "Unlock entity first",
                    "parallel_group": 0
                },
                {
                    "tool": "run_business_rule",
                    "params_template": {"rule_name": "Consolidate"},
                    "desc": "Run consolidation",
                    "parallel_group": 1
                },
            ],
            "triggers": ["unlock then consolidate", "unlock and consolidate", "unlock then run consolidate"],
            "estimated_duration": 40.0,
            "priority": 10
        },
        "data_export_full": {
            "name": "Full Data Export",
            "description": "Export comprehensive data for analysis",
            "steps": [
                {
                    "tool": "get_dimensions",
                    "params_template": {},
                    "desc": "Get dimension list",
                    "parallel_group": 0,
                    "optional": True
                },
                {
                    "tool": "export_data_slice",
                    "params_template": {},
                    "desc": "Export data slice",
                    "parallel_group": 1
                },
            ],
            "triggers": ["export data", "download data", "extract to excel", "data export"],
            "estimated_duration": 30.0,
            "priority": 4
        },
        "yoy_analysis": {
            "name": "Year-over-Year Analysis",
            "description": "Compare current year to prior year",
            "steps": [
                {
                    "tool": "smart_retrieve",
                    "params_template": {"years": "FY24"},
                    "desc": "Get current year data",
                    "parallel_group": 0
                },
                {
                    "tool": "smart_retrieve",
                    "params_template": {"years": "FY23"},
                    "desc": "Get prior year data",
                    "parallel_group": 0
                },
            ],
            "triggers": ["yoy", "year over year", "prior year comparison", "py comparison"],
            "estimated_duration": 10.0,
            "priority": 5
        },
        "entity_analysis": {
            "name": "Entity Analysis",
            "description": "Comprehensive analysis of an entity",
            "steps": [
                {
                    "tool": "get_member",
                    "params_template": {"dimension_name": "Entity", "expansion": "children"},
                    "desc": "Get entity details and children",
                    "parallel_group": 0
                },
                {
                    "tool": "smart_retrieve",
                    "params_template": {"account": "FCCS_Net_Income"},
                    "desc": "Get net income",
                    "parallel_group": 1
                },
            ],
            "triggers": ["entity analysis", "analyze entity", "entity deep dive", "entity breakdown"],
            "estimated_duration": 15.0,
            "priority": 4
        },
        # OLAP-aware exploration patterns
        "member_search": {
            "name": "Member Search",
            "description": "Search for members across dimensions with fuzzy matching",
            "steps": [
                {
                    "tool": "search_members",
                    "params_template": {},
                    "desc": "Search for matching members",
                    "parallel_group": 0
                },
            ],
            "triggers": ["find account", "search member", "look for", "locate", "which account",
                        "find revenue", "find expense", "similar to", "like"],
            "estimated_duration": 2.0,
            "priority": 8
        },
        "hierarchy_drill_down": {
            "name": "Hierarchy Drill-Down",
            "description": "Navigate dimension hierarchy - show children or descendants",
            "steps": [
                {
                    "tool": "explore_dimension",
                    "params_template": {"operation": "children"},
                    "desc": "Get children of member",
                    "parallel_group": 0
                },
                {
                    "tool": "get_drill_suggestions",
                    "params_template": {},
                    "desc": "Get drill suggestions for next steps",
                    "parallel_group": 1,
                    "optional": True
                },
            ],
            "triggers": ["show children", "children of", "drill down", "drill into", "expand",
                        "descendants of", "under", "below", "what's under"],
            "estimated_duration": 3.0,
            "priority": 9
        },
        "hierarchy_roll_up": {
            "name": "Hierarchy Roll-Up",
            "description": "Navigate dimension hierarchy - show parent or path to root",
            "steps": [
                {
                    "tool": "explore_dimension",
                    "params_template": {"operation": "parent"},
                    "desc": "Get parent of member",
                    "parallel_group": 0
                },
            ],
            "triggers": ["parent of", "roll up", "above", "aggregate to", "what contains"],
            "estimated_duration": 2.0,
            "priority": 9
        },
        "hierarchy_path": {
            "name": "Hierarchy Path",
            "description": "Show full path from member to root",
            "steps": [
                {
                    "tool": "explore_dimension",
                    "params_template": {"operation": "path"},
                    "desc": "Get full path to root",
                    "parallel_group": 0
                },
            ],
            "triggers": ["path to root", "full hierarchy", "hierarchy path", "where is", "location of"],
            "estimated_duration": 2.0,
            "priority": 7
        },
        "contribution_analysis": {
            "name": "Contribution Analysis",
            "description": "Analyze what makes up a total - show children with data",
            "steps": [
                {
                    "tool": "explore_dimension",
                    "params_template": {"operation": "children", "depth": 1},
                    "desc": "Get child members",
                    "parallel_group": 0
                },
                {
                    "tool": "smart_retrieve",
                    "params_template": {},
                    "desc": "Get total value",
                    "parallel_group": 0
                },
            ],
            "triggers": ["what makes up", "contribution", "comprises", "composition",
                        "breakdown of", "components of", "top contributors"],
            "estimated_duration": 5.0,
            "priority": 7
        },
        "trend_analysis": {
            "name": "Trend Analysis",
            "description": "Analyze trends over time using movement dimension",
            "steps": [
                {
                    "tool": "smart_retrieve_with_movement",
                    "params_template": {"movement": "FCCS_Mvmts_Subtotal"},
                    "desc": "Get movement breakdown",
                    "parallel_group": 0
                },
            ],
            "triggers": ["trend", "over time", "movement", "how changed", "historical",
                        "periodic trend", "monthly trend"],
            "estimated_duration": 4.0,
            "priority": 6
        },
        "dimension_info": {
            "name": "Dimension Information",
            "description": "Get information about available dimensions",
            "steps": [
                {
                    "tool": "list_available_dimensions",
                    "params_template": {},
                    "desc": "List all dimensions with metadata",
                    "parallel_group": 0
                },
            ],
            "triggers": ["list dimensions", "available dimensions", "what dimensions",
                        "dimension info", "dimension metadata"],
            "estimated_duration": 2.0,
            "priority": 6
        },
    }
    
    # Tool categories for dynamic planning
    TOOL_CATEGORIES = {
        "retrieval": ["smart_retrieve", "export_data_slice", "smart_retrieve_consolidation_breakdown",
                      "smart_retrieve_with_movement"],
        "dimension": ["get_dimensions", "get_members", "get_dimension_hierarchy", "get_member"],
        "exploration": ["explore_dimension", "search_members", "get_drill_suggestions",
                       "list_available_dimensions"],
        "journal": ["get_journals", "get_journal_details", "perform_journal_action"],
        "job": ["list_jobs", "get_job_status", "run_business_rule", "run_data_rule"],
        "report": ["generate_report", "generate_consolidation_process_report",
                   "generate_intercompany_matching_report"],
        "validation": ["validate_metadata"],
        "info": ["get_application_info", "get_rest_api_version"],
    }
    
    # Tool estimated durations (seconds)
    TOOL_DURATIONS = {
        "smart_retrieve": 3.0,
        "export_data_slice": 5.0,
        "get_dimensions": 2.0,
        "get_members": 3.0,
        "get_journals": 4.0,
        "list_jobs": 2.0,
        "generate_report": 15.0,
        "run_business_rule": 30.0,
        "validate_metadata": 10.0,
        # Exploration tools (local operations, very fast)
        "explore_dimension": 0.5,
        "search_members": 0.3,
        "get_drill_suggestions": 0.2,
        "list_available_dimensions": 0.2,
    }
    
    def __init__(self):
        """Initialize planner."""
        self._step_counter = 0
    
    def create_plan(
        self,
        intent: str,
        entities: Dict[str, str],
        available_tools: List[str],
        sub_intent: Optional[str] = None,
        suggested_tools: Optional[List[str]] = None,
        user_query: Optional[str] = None
    ) -> ExecutionPlan:
        """Create execution plan for intent.

        Args:
            intent: The classified intent name.
            entities: Extracted FCCS entities.
            available_tools: List of available tool names.
            sub_intent: Optional sub-intent for more specific planning.
            suggested_tools: Optional list of suggested tools from intent classification.
            user_query: Original user query for better pattern matching.

        Returns:
            ExecutionPlan with steps to execute.
        """
        self._step_counter = 0

        # Try pattern-based planning first (include user query for trigger matching)
        pattern = self._match_pattern(intent, entities, sub_intent, user_query)
        if pattern:
            return self._build_from_pattern(pattern, entities, available_tools)

        # Fall back to dynamic planning
        return self._dynamic_plan(intent, entities, available_tools, suggested_tools)
    
    def _match_pattern(
        self,
        intent: str,
        entities: Dict[str, str],
        sub_intent: Optional[str] = None,
        user_query: Optional[str] = None
    ) -> Optional[Dict]:
        """Match intent to a predefined execution pattern.

        Uses a scoring system that considers:
        - Number of trigger matches (in user query AND intent context)
        - Pattern priority (higher = more preferred)
        - Trigger specificity (longer triggers = more specific)
        """
        # Include user query for trigger matching - this is critical!
        query_text = user_query.lower() if user_query else ""
        entity_context = f"{intent} {sub_intent or ''} {' '.join(entities.values())}".lower()
        combined_context = f"{query_text} {entity_context}"

        best_match = None
        best_score = 0

        for pattern_name, pattern in self.PATTERNS.items():
            triggers = pattern.get("triggers", [])
            priority = pattern.get("priority", 1)

            # Count matches and consider trigger length (specificity)
            matches = 0
            specificity_bonus = 0
            for t in triggers:
                if t.lower() in combined_context:
                    matches += 1
                    # Longer triggers are more specific, give bonus
                    specificity_bonus += len(t) / 20.0

            if matches > 0:
                # Score = matches + priority bonus + specificity
                score = matches + (priority * 0.5) + specificity_bonus

                if score > best_score:
                    best_score = score
                    best_match = pattern

        # Require at least one trigger match
        return best_match if best_score >= 1 else None
    
    def _build_from_pattern(
        self,
        pattern: Dict,
        entities: Dict[str, str],
        available_tools: List[str]
    ) -> ExecutionPlan:
        """Build execution plan from a pattern template."""
        steps = []
        
        for step_template in pattern["steps"]:
            tool_name = step_template["tool"]
            
            # Skip tools not available
            if tool_name not in available_tools:
                continue
            
            # Start with template params (includes rule_name for business rules)
            template_params = copy.deepcopy(step_template.get("params_template", {}))
            
            # Get filtered entity params
            entity_params = self._filter_params_for_tool(tool_name, entities)
            
            # Merge: entity params first, then ensure template params are preserved
            params = {}
            params.update(entity_params)
            
            # Ensure critical template params (like rule_name) are preserved
            for key, value in template_params.items():
                if key not in params:
                    params[key] = value
            
            step = ExecutionStep(
                id=self._next_step_id(),
                tool_name=tool_name,
                parameters=params,
                depends_on=self._calculate_dependencies(steps, step_template),
                description=step_template.get("desc", f"Execute {tool_name}"),
                parallel_group=step_template.get("parallel_group", 0),
                optional=step_template.get("optional", False),
            )
            steps.append(step)
        
        # If no steps, add a default
        if not steps:
            steps = self._create_fallback_steps(entities, available_tools)
        
        return ExecutionPlan(
            steps=steps,
            name=pattern.get("name", "Execution Plan"),
            description=pattern.get("description", ""),
            estimated_duration_seconds=pattern.get("estimated_duration", 10.0)
        )
    
    def _dynamic_plan(
        self,
        intent: str,
        entities: Dict[str, str],
        available_tools: List[str],
        suggested_tools: Optional[List[str]] = None
    ) -> ExecutionPlan:
        """Create dynamic plan when no pattern matches."""
        steps = []
        
        # Use suggested tools if available
        tools_to_use = suggested_tools or []
        
        # If no suggestions, infer from intent
        if not tools_to_use:
            tools_to_use = self._infer_tools_from_intent(intent, available_tools)
        
        # Filter to available tools
        tools_to_use = [t for t in tools_to_use if t in available_tools]
        
        # Create steps
        for i, tool_name in enumerate(tools_to_use[:3]):  # Limit to 3 tools
            params = self._filter_params_for_tool(tool_name, entities)
            
            step = ExecutionStep(
                id=self._next_step_id(),
                tool_name=tool_name,
                parameters=params,
                depends_on=[steps[-1].id] if steps else [],  # Sequential by default
                description=f"Execute {tool_name}",
                parallel_group=i,
            )
            steps.append(step)
        
        # Fallback if no steps
        if not steps:
            steps = self._create_fallback_steps(entities, available_tools)
        
        estimated_duration = sum(
            self.TOOL_DURATIONS.get(s.tool_name, 5.0) for s in steps
        )
        
        return ExecutionPlan(
            steps=steps,
            name="Dynamic Execution Plan",
            description=f"Generated plan for intent: {intent}",
            estimated_duration_seconds=estimated_duration
        )
    
    def _infer_tools_from_intent(
        self,
        intent: str,
        available_tools: List[str]
    ) -> List[str]:
        """Infer tools from intent name."""
        intent_tool_map = {
            "data_retrieval": ["smart_retrieve"],
            "dimension_exploration": ["get_dimensions", "get_members"],
            "journal_management": ["get_journals"],
            "consolidation": ["smart_retrieve_consolidation_breakdown", "generate_consolidation_process_report"],
            "job_management": ["list_jobs"],
            "reporting": ["generate_report"],
            "variance_analysis": ["smart_retrieve"],
            "period_close": ["list_jobs", "get_journals"],
            "metadata_validation": ["validate_metadata"],
            "intercompany": ["generate_intercompany_matching_report"],
            # OLAP-aware intents
            "member_search": ["search_members", "explore_dimension"],
            "hierarchy_explore": ["explore_dimension", "get_drill_suggestions"],
            "drill_down": ["explore_dimension", "smart_retrieve"],
            "contribution_analysis": ["explore_dimension", "smart_retrieve"],
            "trend_analysis": ["smart_retrieve_with_movement"],
        }

        return intent_tool_map.get(intent, ["get_application_info"])
    
    def _filter_params_for_tool(
        self,
        tool_name: str,
        entities: Dict[str, str],
        template_params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Filter entities to valid parameters for a tool.
        
        Args:
            tool_name: Name of the tool.
            entities: Extracted entities from user query.
            template_params: Optional template parameters to preserve (e.g., rule_name).
            
        Returns:
            Filtered parameters for the tool.
        """
        # Parameter mapping for each tool
        tool_params = {
            "smart_retrieve": ["account", "entity", "period", "years", "scenario", "consolidation"],
            "smart_retrieve_consolidation_breakdown": ["account", "entity", "period", "years", "scenario"],
            "smart_retrieve_with_movement": ["account", "entity", "period", "years", "scenario", "consolidation", "movement"],
            "export_data_slice": ["cube_name", "grid_definition"],
            "get_members": ["dimension_name"],
            "get_member": ["dimension_name", "member_name", "expansion"],
            "get_dimension_hierarchy": ["dimension_name", "member_name", "depth", "include_metadata"],
            "get_journals": ["period", "year", "scenario", "status", "consolidation", "view"],
            "get_journal_details": ["journal_label", "period", "scenario", "year"],
            "perform_journal_action": ["journal_label", "action", "period", "scenario", "year"],
            "run_business_rule": ["rule_name", "parameters"],
            "run_data_rule": ["rule_name", "start_period", "end_period", "import_mode", "export_mode"],
            "generate_report": ["report_name", "group_name", "module", "format"],
            "generate_consolidation_process_report": ["account", "entity", "period", "year", "scenario"],
            "generate_intercompany_matching_report": ["parameters"],
            "list_jobs": [],
            "get_job_status": ["job_id"],
            "get_dimensions": [],
            "validate_metadata": ["log_file_name"],
            # OLAP exploration tools
            "explore_dimension": ["dimension", "member", "operation", "search_term", "depth", "include_metadata"],
            "search_members": ["search_term", "dimension", "match_types", "limit"],
            "get_drill_suggestions": ["dimension", "member"],
            "list_available_dimensions": [],
        }
        
        valid_params = tool_params.get(tool_name, [])
        
        # Map entity types to parameter names
        entity_to_param = {
            "period": "period",
            "year": "years",  # Note: different naming
            "scenario": "scenario",
            "account": "account",
            "entity": "entity",
            "consolidation": "consolidation",
            "currency": "currency",
            "movement": "movement",
            "journal_status": "status",
            "job_id": "job_id",
        }
        
        filtered = {}
        for entity_type, value in entities.items():
            param_name = entity_to_param.get(entity_type, entity_type)
            if param_name in valid_params:
                filtered[param_name] = value

        # Special handling for year -> years mapping (most tools use "years")
        if "year" in entities and "years" in valid_params:
            filtered["years"] = entities["year"]

        # Special handling for year -> year mapping (some tools use "year" not "years")
        if "year" in entities and "year" in valid_params and "years" not in valid_params:
            filtered["year"] = entities["year"]

        # Ensure account is passed through if extracted
        if "account" in entities and "account" in valid_params:
            filtered["account"] = entities["account"]
        elif "account" in valid_params and "account" not in filtered:
            # Fallback for common data retrieval tools if account is missing
            if tool_name in ["smart_retrieve", "smart_retrieve_consolidation_breakdown", "smart_retrieve_with_movement"]:
                # Try to find something that looks like an account in the query context
                # or use a default if it's a general analysis query
                filtered["account"] = "FCCS_Net Income"  # Default to Net Income for analysis

        # Ensure entity is passed through if extracted
        if "entity" in entities and "entity" in valid_params and "entity" not in filtered:
            filtered["entity"] = entities["entity"]

        # Special handling for query_local_metadata - map account/entity to dimension/filter
        if tool_name == "query_local_metadata":
            if "account" in entities:
                filtered["dimension"] = "Account"
                filtered["member_filter"] = f"%{entities['account']}%"
            elif "entity" in entities:
                filtered["dimension"] = "Entity"
                filtered["member_filter"] = f"%{entities['entity']}%"

        # Special handling for run_business_rule - build parameters dict
        if tool_name == "run_business_rule":
            rule_params = {}
            param_mapping = {
                "year": "Year",
                "period": "Period",
                "scenario": "Scenario",
                "entity": "Entity",
            }
            for entity_key, param_key in param_mapping.items():
                if entity_key in entities:
                    rule_params[param_key] = entities[entity_key]
            if rule_params:
                filtered["parameters"] = rule_params

        # Special handling for OLAP exploration tools
        if tool_name == "explore_dimension":
            # Map account/entity to dimension/member params
            if "account" in entities:
                filtered["dimension"] = "Account"
                filtered["member"] = entities["account"]
            elif "entity" in entities:
                filtered["dimension"] = "Entity"
                filtered["member"] = entities["entity"]
            # Default operation if not specified
            if "operation" not in filtered:
                filtered["operation"] = "children"

        if tool_name == "search_members":
            # Use account or entity as search term
            if "account" in entities:
                filtered["search_term"] = entities["account"]
                filtered["dimension"] = "Account"
            elif "entity" in entities:
                filtered["search_term"] = entities["entity"]
                filtered["dimension"] = "Entity"

        if tool_name == "get_drill_suggestions":
            # Map account/entity to dimension/member params
            if "account" in entities:
                filtered["dimension"] = "Account"
                filtered["member"] = entities["account"]
            elif "entity" in entities:
                filtered["dimension"] = "Entity"
                filtered["member"] = entities["entity"]

        return filtered
    
    def _calculate_dependencies(
        self,
        existing_steps: List[ExecutionStep],
        step_template: Dict
    ) -> List[int]:
        """Calculate step dependencies based on parallel groups."""
        parallel_group = step_template.get("parallel_group", 0)
        
        if parallel_group == 0:
            return []  # First group has no dependencies
        
        # Depend on all steps in previous group
        prev_group = parallel_group - 1
        deps = [s.id for s in existing_steps if s.parallel_group == prev_group]
        
        return deps
    
    def _create_fallback_steps(
        self,
        entities: Dict[str, str],
        available_tools: List[str]
    ) -> List[ExecutionStep]:
        """Create fallback steps when no plan can be generated."""
        # Default to application info
        default_tool = "get_application_info"
        if default_tool not in available_tools:
            default_tool = available_tools[0] if available_tools else "get_application_info"
        
        return [ExecutionStep(
            id=self._next_step_id(),
            tool_name=default_tool,
            parameters={},
            description=f"Execute {default_tool}",
        )]
    
    def _next_step_id(self) -> int:
        """Get next step ID."""
        self._step_counter += 1
        return self._step_counter
    
    def optimize_plan(self, plan: ExecutionPlan) -> ExecutionPlan:
        """Optimize an execution plan.
        
        Optimizations:
        - Reorder steps to maximize parallelism
        - Remove redundant steps
        - Merge similar tool calls
        """
        # Find steps that can be parallelized
        optimized_steps = self._maximize_parallelism(plan.steps)
        
        # Remove redundant steps
        optimized_steps = self._remove_redundant_steps(optimized_steps)
        
        # Recalculate estimated duration (accounting for parallelism)
        estimated_duration = self._calculate_parallel_duration(optimized_steps)
        
        return ExecutionPlan(
            steps=optimized_steps,
            name=f"{plan.name} (Optimized)",
            description=plan.description,
            estimated_duration_seconds=estimated_duration
        )
    
    def _maximize_parallelism(self, steps: List[ExecutionStep]) -> List[ExecutionStep]:
        """Reorder steps to maximize parallel execution."""
        # Group by actual dependencies, not arbitrary parallel groups
        # Steps without dependencies on each other can be parallel
        
        # For now, keep original ordering
        # TODO: Implement dependency graph analysis
        return steps
    
    def _remove_redundant_steps(self, steps: List[ExecutionStep]) -> List[ExecutionStep]:
        """Remove redundant steps (same tool with same params)."""
        seen = set()
        unique_steps = []
        
        for step in steps:
            key = (step.tool_name, frozenset(step.parameters.items()))
            if key not in seen:
                seen.add(key)
                unique_steps.append(step)
        
        return unique_steps
    
    def _calculate_parallel_duration(self, steps: List[ExecutionStep]) -> float:
        """Calculate duration accounting for parallel execution."""
        groups = {}
        for step in steps:
            if step.parallel_group not in groups:
                groups[step.parallel_group] = []
            groups[step.parallel_group].append(step)
        
        total_duration = 0.0
        for group_steps in groups.values():
            # Duration is the max of parallel steps
            group_duration = max(
                self.TOOL_DURATIONS.get(s.tool_name, 5.0) for s in group_steps
            )
            total_duration += group_duration
        
        return total_duration
    
    def explain_plan(self, plan: ExecutionPlan) -> str:
        """Generate human-readable explanation of the plan."""
        lines = [
            f"## {plan.name}",
            f"_{plan.description}_",
            f"",
            f"**Estimated Duration:** {plan.estimated_duration_seconds:.1f} seconds",
            f"**Steps:** {len(plan.steps)}",
            f"",
            "### Execution Steps:",
            ""
        ]
        
        groups = plan.get_parallel_groups()
        for group_id in sorted(groups.keys()):
            group_steps = groups[group_id]
            if len(group_steps) > 1:
                lines.append(f"**Parallel Group {group_id + 1}:**")
                for step in group_steps:
                    lines.append(f"  - {step.description} (`{step.tool_name}`)")
            else:
                step = group_steps[0]
                lines.append(f"**Step {step.id}:** {step.description} (`{step.tool_name}`)")
        
        return "\n".join(lines)
