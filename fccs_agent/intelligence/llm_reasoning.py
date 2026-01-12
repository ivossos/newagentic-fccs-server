"""LLM-Powered Reasoning for FCCS operations.

Uses Claude API for:
- Complex intent classification
- Query understanding and disambiguation
- Response generation
- Error explanation
- Recommendation synthesis
"""

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import json
import os
import sys
import asyncio
from enum import Enum

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

from fccs_agent.intelligence.intent_classifier import Intent, IntentType


class ReasoningMode(Enum):
    """Reasoning modes for different use cases."""
    INTENT_CLASSIFICATION = "intent_classification"
    QUERY_UNDERSTANDING = "query_understanding"
    ERROR_EXPLANATION = "error_explanation"
    RESPONSE_SYNTHESIS = "response_synthesis"
    RECOMMENDATION = "recommendation"
    DISAMBIGUATION = "disambiguation"


@dataclass
class ReasoningResult:
    """Result from LLM reasoning."""
    success: bool
    content: str
    structured_data: Optional[Dict[str, Any]] = None
    confidence: float = 0.0
    tokens_used: int = 0
    reasoning_mode: ReasoningMode = ReasoningMode.QUERY_UNDERSTANDING


SYSTEM_PROMPTS = {
    ReasoningMode.INTENT_CLASSIFICATION: """You are an expert at understanding Oracle EPM Cloud FCCS queries.

Classify user queries into intents and extract FCCS-specific entities.

Available intents:
- data_retrieval: Retrieving financial data, balances, values
- dimension_exploration: Exploring dimensions, members, hierarchies
- journal_management: Working with journals, entries, approvals
- consolidation: Running or checking consolidation processes
- job_management: Checking job status, running rules
- reporting: Generating reports
- variance_analysis: Comparing actual vs forecast, YoY analysis
- period_close: Period close activities
- metadata_validation: Validating metadata
- intercompany: Intercompany matching and reconciliation

Respond in JSON format only:
{"intent": "intent_name", "confidence": 0.0-1.0, "entities": {}, "suggested_tools": [], "reasoning": "brief"}""",
    
    ReasoningMode.QUERY_UNDERSTANDING: """You are an expert assistant for Oracle EPM Cloud FCCS.
Understand user queries and provide clear, structured responses.
Be concise but thorough. Use FCCS terminology correctly.""",

    ReasoningMode.ERROR_EXPLANATION: """You are an expert at explaining Oracle EPM Cloud FCCS errors.
Identify root cause, explain simply, and suggest resolution steps.""",

    ReasoningMode.RESPONSE_SYNTHESIS: """You are an expert at synthesizing FCCS query results.
Summarize key findings, highlight important values, note anomalies, and suggest follow-up actions.""",

    ReasoningMode.RECOMMENDATION: """You are an expert FCCS advisor providing recommendations.
Consider context, suggest follow-up actions, highlight best practices.""",

    ReasoningMode.DISAMBIGUATION: """You are an expert at clarifying ambiguous FCCS queries.
Identify ambiguity, list interpretations, ask clarifying questions."""
}


TOOL_DESCRIPTIONS = {
    "smart_retrieve": "Retrieve financial data with automatic dimension handling",
    "smart_retrieve_consolidation_breakdown": "Get consolidation breakdown (Input, Total, Elimination)",
    "export_data_slice": "Export data slice with custom grid definition",
    "get_dimensions": "List all dimensions",
    "get_members": "Get members of a dimension",
    "get_journals": "List journals with filters",
    "perform_journal_action": "Submit, approve, reject, post, or unpost a journal",
    "list_jobs": "List recent jobs",
    "run_business_rule": "Execute a business rule",
    "generate_report": "Generate a report",
    "validate_metadata": "Validate application metadata",
}


class LLMReasoner:
    """LLM-powered reasoning for complex FCCS operations."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-opus-4-5-20251101",
        max_tokens: int = 1024,
        temperature: float = 0.3
    ):
        """Initialize LLM reasoner."""
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        
        if HAS_ANTHROPIC and self.api_key:
            self.client = anthropic.Anthropic(api_key=self.api_key)
            self.async_client = anthropic.AsyncAnthropic(api_key=self.api_key)
            self._available = True
        else:
            self.client = None
            self.async_client = None
            self._available = False
    
    @property
    def is_available(self) -> bool:
        """Check if LLM is available."""
        return self._available
    
    def classify_intent(
        self,
        query: str,
        entities: Dict[str, str],
        context: Optional[Dict[str, Any]] = None
    ) -> Intent:
        """Classify query intent using LLM."""
        if not self._available:
            return self._fallback_classification(query, entities)
        
        try:
            user_prompt = self._build_classification_prompt(query, entities, context)
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=SYSTEM_PROMPTS[ReasoningMode.INTENT_CLASSIFICATION],
                messages=[{"role": "user", "content": user_prompt}]
            )
            
            content = response.content[0].text
            result = self._parse_json_response(content)
            
            if result:
                intent_name = result.get("intent", "unknown")
                intent_type = self._map_intent_type(intent_name)
                
                return Intent(
                    name=intent_name,
                    intent_type=intent_type,
                    confidence=result.get("confidence", 0.8),
                    entities={**entities, **result.get("entities", {})},
                    suggested_tools=result.get("suggested_tools", []),
                    sub_intent=result.get("sub_intent"),
                    reasoning=result.get("reasoning")
                )
            
        except Exception as e:
            print(f"LLM classification error: {e}", file=sys.stderr)

        return self._fallback_classification(query, entities)

    async def classify_intent_async(
        self,
        query: str,
        entities: Dict[str, str],
        context: Optional[Dict[str, Any]] = None
    ) -> Intent:
        """Async version of classify_intent."""
        if not self._available:
            return self._fallback_classification(query, entities)
        
        try:
            user_prompt = self._build_classification_prompt(query, entities, context)
            
            response = await self.async_client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=SYSTEM_PROMPTS[ReasoningMode.INTENT_CLASSIFICATION],
                messages=[{"role": "user", "content": user_prompt}]
            )
            
            content = response.content[0].text
            result = self._parse_json_response(content)
            
            if result:
                intent_name = result.get("intent", "unknown")
                intent_type = self._map_intent_type(intent_name)
                
                return Intent(
                    name=intent_name,
                    intent_type=intent_type,
                    confidence=result.get("confidence", 0.8),
                    entities={**entities, **result.get("entities", {})},
                    suggested_tools=result.get("suggested_tools", []),
                    sub_intent=result.get("sub_intent"),
                    reasoning=result.get("reasoning")
                )
            
        except Exception as e:
            print(f"LLM classification error: {e}", file=sys.stderr)

        return self._fallback_classification(query, entities)

    async def understand_query(
        self,
        query: str,
        context: Dict[str, Any]
    ) -> ReasoningResult:
        """Understand and analyze a user query."""
        if not self._available:
            return ReasoningResult(
                success=False,
                content="LLM not available",
                reasoning_mode=ReasoningMode.QUERY_UNDERSTANDING
            )
        
        try:
            prompt = f"""Analyze this FCCS query:

Query: {query}

Current Context:
{json.dumps(context, indent=2)}

Provide:
1. What the user wants to accomplish
2. Key FCCS dimensions/members involved
3. Recommended approach
4. Any clarifications needed"""

            response = await self.async_client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=SYSTEM_PROMPTS[ReasoningMode.QUERY_UNDERSTANDING],
                messages=[{"role": "user", "content": prompt}]
            )
            
            return ReasoningResult(
                success=True,
                content=response.content[0].text,
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                reasoning_mode=ReasoningMode.QUERY_UNDERSTANDING
            )
            
        except Exception as e:
            return ReasoningResult(
                success=False,
                content=f"Error: {str(e)}",
                reasoning_mode=ReasoningMode.QUERY_UNDERSTANDING
            )
    
    async def explain_error(
        self,
        error_message: str,
        tool_name: str,
        parameters: Dict[str, Any]
    ) -> ReasoningResult:
        """Explain an error in user-friendly terms."""
        if not self._available:
            return ReasoningResult(
                success=False,
                content=f"Error in {tool_name}: {error_message}",
                reasoning_mode=ReasoningMode.ERROR_EXPLANATION
            )
        
        try:
            prompt = f"""Explain this FCCS error:

Tool: {tool_name}
Parameters: {json.dumps(parameters, indent=2)}
Error: {error_message}

Provide:
1. Root cause explanation
2. How to fix it
3. Prevention tips"""

            response = await self.async_client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=SYSTEM_PROMPTS[ReasoningMode.ERROR_EXPLANATION],
                messages=[{"role": "user", "content": prompt}]
            )
            
            return ReasoningResult(
                success=True,
                content=response.content[0].text,
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                reasoning_mode=ReasoningMode.ERROR_EXPLANATION
            )
            
        except Exception as e:
            return ReasoningResult(
                success=False,
                content=f"Error explanation failed: {str(e)}",
                reasoning_mode=ReasoningMode.ERROR_EXPLANATION
            )
    
    async def synthesize_results(
        self,
        results: List[Dict[str, Any]],
        query: str,
        context: Dict[str, Any]
    ) -> ReasoningResult:
        """Synthesize multiple tool results into a coherent response."""
        if not self._available:
            return ReasoningResult(
                success=False,
                content="LLM not available for synthesis",
                reasoning_mode=ReasoningMode.RESPONSE_SYNTHESIS
            )
        
        try:
            prompt = f"""Synthesize these FCCS query results:

Original Query: {query}

Results:
{json.dumps(results, indent=2, default=str)}

Context:
{json.dumps(context, indent=2)}

Provide:
1. Key findings summary
2. Important values/trends
3. Any concerns or anomalies
4. Suggested next steps"""

            response = await self.async_client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=SYSTEM_PROMPTS[ReasoningMode.RESPONSE_SYNTHESIS],
                messages=[{"role": "user", "content": prompt}]
            )
            
            return ReasoningResult(
                success=True,
                content=response.content[0].text,
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                reasoning_mode=ReasoningMode.RESPONSE_SYNTHESIS
            )
            
        except Exception as e:
            return ReasoningResult(
                success=False,
                content=f"Synthesis failed: {str(e)}",
                reasoning_mode=ReasoningMode.RESPONSE_SYNTHESIS
            )
    
    async def generate_recommendations(
        self,
        intent: str,
        results: List[Dict[str, Any]],
        context: Dict[str, Any]
    ) -> List[str]:
        """Generate follow-up recommendations."""
        if not self._available:
            return self._fallback_recommendations(intent, results)
        
        try:
            prompt = f"""Based on this FCCS interaction, suggest follow-up actions:

Intent: {intent}
Results: {json.dumps(results, indent=2, default=str)[:2000]}
Context: {json.dumps(context, indent=2)}

Provide 3-5 specific, actionable recommendations as a JSON array:
["recommendation 1", "recommendation 2", ...]"""

            response = await self.async_client.messages.create(
                model=self.model,
                max_tokens=512,
                temperature=0.5,
                system=SYSTEM_PROMPTS[ReasoningMode.RECOMMENDATION],
                messages=[{"role": "user", "content": prompt}]
            )
            
            content = response.content[0].text
            recommendations = self._parse_json_response(content)
            
            if isinstance(recommendations, list):
                return recommendations[:5]
            
        except Exception as e:
            print(f"Recommendation generation error: {e}", file=sys.stderr)

        return self._fallback_recommendations(intent, results)
    
    async def disambiguate_query(
        self,
        query: str,
        ambiguities: List[str],
        context: Dict[str, Any]
    ) -> ReasoningResult:
        """Help disambiguate an unclear query."""
        if not self._available:
            return ReasoningResult(
                success=False,
                content="Please clarify: " + ", ".join(ambiguities),
                reasoning_mode=ReasoningMode.DISAMBIGUATION
            )
        
        try:
            prompt = f"""Help clarify this FCCS query:

Query: {query}
Potential Ambiguities: {json.dumps(ambiguities)}
Context: {json.dumps(context, indent=2)}

Provide:
1. What needs clarification
2. Possible interpretations
3. Suggested default if user doesn't clarify"""

            response = await self.async_client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=SYSTEM_PROMPTS[ReasoningMode.DISAMBIGUATION],
                messages=[{"role": "user", "content": prompt}]
            )
            
            return ReasoningResult(
                success=True,
                content=response.content[0].text,
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                reasoning_mode=ReasoningMode.DISAMBIGUATION
            )
            
        except Exception as e:
            return ReasoningResult(
                success=False,
                content=f"Disambiguation failed: {str(e)}",
                reasoning_mode=ReasoningMode.DISAMBIGUATION
            )
    
    def _build_classification_prompt(
        self,
        query: str,
        entities: Dict[str, str],
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Build prompt for intent classification."""
        prompt_parts = [
            f"Query: {query}",
            "",
            f"Pre-extracted entities: {json.dumps(entities)}",
        ]
        
        if context:
            pov = context.get("current_pov", {})
            if pov:
                prompt_parts.extend([
                    "",
                    "Current POV context:",
                    f"- Period: {pov.get('period', 'unknown')}",
                    f"- Year: {pov.get('years', 'unknown')}",
                    f"- Scenario: {pov.get('scenario', 'unknown')}",
                    f"- Entity: {pov.get('entity', 'unknown')}",
                ])
            
            recent = context.get("recent_queries", [])
            if recent:
                prompt_parts.extend([
                    "",
                    f"Recent queries: {[q.get('query', '') for q in recent[-3:]]}",
                ])
        
        prompt_parts.extend([
            "",
            "Available tools:",
            *[f"- {name}: {desc}" for name, desc in TOOL_DESCRIPTIONS.items()],
            "",
            "Classify the intent and respond with JSON only.",
        ])
        
        return "\n".join(prompt_parts)
    
    def _parse_json_response(self, content: str) -> Optional[Dict]:
        """Parse JSON from LLM response."""
        try:
            # Try direct parse
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        
        # Try to extract JSON from markdown code blocks
        import re
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Try to find JSON object in content
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        
        # Try to find JSON array in content
        json_match = re.search(r'\[[\s\S]*\]', content)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        
        return None
    
    def _map_intent_type(self, intent_name: str) -> IntentType:
        """Map intent name string to IntentType enum."""
        mapping = {
            "data_retrieval": IntentType.DATA_RETRIEVAL,
            "dimension_exploration": IntentType.DIMENSION_EXPLORATION,
            "journal_management": IntentType.JOURNAL_MANAGEMENT,
            "consolidation": IntentType.CONSOLIDATION,
            "job_management": IntentType.JOB_MANAGEMENT,
            "reporting": IntentType.REPORTING,
            "variance_analysis": IntentType.VARIANCE_ANALYSIS,
            "period_close": IntentType.PERIOD_CLOSE,
            "metadata_validation": IntentType.METADATA_VALIDATION,
            "intercompany": IntentType.INTERCOMPANY,
        }
        return mapping.get(intent_name, IntentType.UNKNOWN)
    
    def _fallback_classification(
        self,
        query: str,
        entities: Dict[str, str]
    ) -> Intent:
        """Fallback classification when LLM is not available."""
        # Simple keyword-based classification
        query_lower = query.lower()
        
        if any(kw in query_lower for kw in ["journal", "entry", "posting"]):
            intent_type = IntentType.JOURNAL_MANAGEMENT
            tools = ["get_journals"]
        elif any(kw in query_lower for kw in ["dimension", "member", "hierarchy"]):
            intent_type = IntentType.DIMENSION_EXPLORATION
            tools = ["get_dimensions", "get_members"]
        elif any(kw in query_lower for kw in ["consolidat", "elimination"]):
            intent_type = IntentType.CONSOLIDATION
            tools = ["smart_retrieve_consolidation_breakdown"]
        elif any(kw in query_lower for kw in ["job", "status", "running"]):
            intent_type = IntentType.JOB_MANAGEMENT
            tools = ["list_jobs"]
        elif any(kw in query_lower for kw in ["variance", "compare", "versus"]):
            intent_type = IntentType.VARIANCE_ANALYSIS
            tools = ["smart_retrieve"]
        else:
            intent_type = IntentType.DATA_RETRIEVAL
            tools = ["smart_retrieve"]
        
        return Intent(
            name=intent_type.value,
            intent_type=intent_type,
            confidence=0.5,
            entities=entities,
            suggested_tools=tools,
            reasoning="Fallback classification (LLM not available)"
        )
    
    def _fallback_recommendations(
        self,
        intent: str,
        results: List[Dict[str, Any]]
    ) -> List[str]:
        """Fallback recommendations when LLM is not available."""
        recommendations = {
            "data_retrieval": [
                "Run variance analysis (Actual vs Forecast)",
                "View consolidation breakdown",
                "Export data to Excel for further analysis",
            ],
            "journal_management": [
                "Check journal approval status",
                "Export journal entries for review",
                "View related consolidation eliminations",
            ],
            "consolidation": [
                "Generate intercompany matching report",
                "Validate metadata before closing",
                "Review elimination journals",
            ],
            "job_management": [
                "Check job details for errors",
                "Re-run failed jobs",
                "Review job parameters",
            ],
        }
        return recommendations.get(intent, ["Get application info", "List recent jobs"])
