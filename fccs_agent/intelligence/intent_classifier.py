"""Intent Classification for FCCS queries.

Classifies user queries into actionable intents and extracts
FCCS-specific entities (periods, scenarios, accounts, entities, etc.).

Supports both rule-based and LLM-powered classification.
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import re
from enum import Enum


class IntentType(Enum):
    """FCCS Intent Types."""
    DATA_RETRIEVAL = "data_retrieval"
    DIMENSION_EXPLORATION = "dimension_exploration"
    JOURNAL_MANAGEMENT = "journal_management"
    CONSOLIDATION = "consolidation"
    JOB_MANAGEMENT = "job_management"
    REPORTING = "reporting"
    VARIANCE_ANALYSIS = "variance_analysis"
    PERIOD_CLOSE = "period_close"
    METADATA_VALIDATION = "metadata_validation"
    INTERCOMPANY = "intercompany"
    # OLAP-aware exploration intents
    MEMBER_SEARCH = "member_search"
    HIERARCHY_EXPLORE = "hierarchy_explore"
    DRILL_DOWN = "drill_down"
    CONTRIBUTION_ANALYSIS = "contribution_analysis"
    TREND_ANALYSIS = "trend_analysis"
    UNKNOWN = "unknown"


@dataclass
class Intent:
    """Classified intent with entities and suggested tools."""
    name: str
    intent_type: IntentType
    confidence: float
    entities: Dict[str, str] = field(default_factory=dict)
    suggested_tools: List[str] = field(default_factory=list)
    sub_intent: Optional[str] = None
    reasoning: Optional[str] = None  # For LLM-based classification


@dataclass
class EntityMatch:
    """A matched entity from the query."""
    entity_type: str
    value: str
    start_pos: int
    end_pos: int
    normalized_value: Optional[str] = None


class FCCSIntentClassifier:
    """Classify user queries into FCCS intents and extract entities.
    
    Uses a combination of:
    1. Pattern matching for common query structures
    2. Keyword scoring for intent classification
    3. Regex extraction for FCCS entities
    4. Optional LLM enhancement for complex queries
    """
    
    # Intent configuration with patterns, keywords, and suggested tools
    INTENT_CONFIG = {
        IntentType.DATA_RETRIEVAL: {
            "patterns": [
                r"(?:get|retrieve|export|show|what is|what's|tell me|give me|fetch).{0,30}(?:data|value|balance|amount|number)",
                r"(?:revenue|profit|income|expense|asset|liability|equity|cash)",
                r"(?:net income|total revenue|cash flow|operating|gross margin)",
                r"(?:how much|what are the).{0,20}(?:for|in|at)",
                r"(?:pull|extract).{0,20}(?:data|numbers|figures)",
            ],
            "keywords": ["data", "value", "balance", "amount", "revenue", "profit", "income", 
                        "expense", "retrieve", "get", "show", "export", "pull", "fetch"],
            "negative_keywords": ["journal", "job", "status", "dimension", "member"],
            "tools": ["smart_retrieve", "export_data_slice", "smart_retrieve_consolidation_breakdown"],
            "sub_intents": {
                "single_value": r"(?:what is|what's|show me).{0,20}(?:the|a)?\s*(?:value|balance|amount)",
                "time_series": r"(?:trend|over time|monthly|quarterly|by period)",
                "comparison": r"(?:compare|versus|vs|against|difference)",
            }
        },
        IntentType.DIMENSION_EXPLORATION: {
            "patterns": [
                r"(?:list|show|get|what are).{0,20}(?:dimension|member|hierarchy|entities|accounts)",
                r"(?:what|which|how many).{0,20}(?:entities|accounts|members|dimensions)",
                r"(?:children|descendants|parent|ancestors).{0,20}(?:of|for)",
                r"(?:explore|browse|navigate).{0,20}(?:hierarchy|structure|tree)",
            ],
            "keywords": ["dimension", "member", "hierarchy", "entity", "account", "list", 
                        "children", "parent", "structure", "metadata"],
            "negative_keywords": ["value", "balance", "data", "journal"],
            "tools": ["get_dimensions", "get_members", "get_dimension_hierarchy", "query_local_metadata"],
            "sub_intents": {
                "list_all": r"(?:all|list all|show all|every)",
                "hierarchy": r"(?:hierarchy|children|parent|structure|tree)",
                "search": r"(?:find|search|look for|where is)",
            }
        },
        IntentType.JOURNAL_MANAGEMENT: {
            "patterns": [
                r"(?:journal|entry|adjustment|posting|jv|je)",
                r"(?:post|approve|submit|reject|unpost).{0,20}(?:journal|entry)",
                r"(?:create|make|add).{0,20}(?:journal|adjustment|entry)",
                r"(?:list|show|get).{0,20}(?:journal|posting|adjustment)",
            ],
            "keywords": ["journal", "entry", "posting", "adjustment", "approve", "post", 
                        "submit", "reject", "unpost", "jv", "je"],
            "negative_keywords": ["consolidation rule", "business rule"],
            "tools": ["get_journals", "get_journal_details", "perform_journal_action", 
                     "export_journals", "import_journals"],
            "sub_intents": {
                "list": r"(?:list|show|get|view).{0,20}(?:journal|posting)",
                "action": r"(?:post|approve|submit|reject|unpost)",
                "create": r"(?:create|make|add|new)",
                "details": r"(?:detail|line|item|breakdown)",
            }
        },
        IntentType.CONSOLIDATION: {
            "patterns": [
                r"(?:consolidat|consol|elimination|eliminate|intercompany|icp)",
                r"(?:run|execute|trigger).{0,20}(?:consol|consolidation|rule)",
                r"(?:entity input|entity total|proportion|contribution)",
                r"(?:ownership|investment|equity method)",
            ],
            "keywords": ["consolidation", "consolidate", "elimination", "intercompany", 
                        "ownership", "equity method", "proportion", "contribution"],
            "negative_keywords": [],
            "tools": ["run_business_rule", "generate_consolidation_process_report", 
                     "smart_retrieve_consolidation_breakdown", "export_consolidation_rulesets"],
            "sub_intents": {
                "run": r"(?:run|execute|trigger|start)",
                "status": r"(?:status|progress|check|monitor)",
                "breakdown": r"(?:breakdown|detail|component|entity input|entity total)",
                "report": r"(?:report|overview|summary)",
            }
        },
        IntentType.JOB_MANAGEMENT: {
            "patterns": [
                r"(?:job|task|process|batch).{0,20}(?:status|running|complete|failed)",
                r"(?:check|monitor|track|what happened).{0,20}(?:job|task|process)",
                r"(?:list|show|get).{0,20}(?:job|task|recent job)",
                r"(?:is the|did the).{0,20}(?:job|rule|process).{0,20}(?:finish|complete|fail)",
            ],
            "keywords": ["job", "task", "process", "status", "running", "complete", 
                        "failed", "monitor", "check", "batch"],
            "negative_keywords": ["journal"],
            "tools": ["list_jobs", "get_job_status"],
            "sub_intents": {
                "status": r"(?:status|progress|state|how is)",
                "list": r"(?:list|show|recent|all)",
                "specific": r"(?:job id|specific job|this job)",
            }
        },
        IntentType.REPORTING: {
            "patterns": [
                r"(?:report|generate report|create report|run report)",
                r"(?:task manager|supplemental data|enterprise journal).{0,20}(?:report)",
                r"(?:export|download).{0,20}(?:report|pdf|excel)",
                r"(?:financial report|fccs report|close report)",
            ],
            "keywords": ["report", "generate", "task manager", "supplemental", "export", 
                        "pdf", "excel", "download"],
            "negative_keywords": [],
            "tools": ["generate_report", "get_report_job_status", "generate_report_script",
                     "generate_consolidation_process_report"],
            "sub_intents": {
                "generate": r"(?:generate|create|run|produce)",
                "download": r"(?:download|export|save)",
                "status": r"(?:status|ready|complete)",
            }
        },
        IntentType.VARIANCE_ANALYSIS: {
            "patterns": [
                r"(?:variance|var|difference|delta|change)",
                r"(?:actual|forecast|budget).{0,20}(?:vs|versus|against|compared)",
                r"(?:compare|comparison).{0,20}(?:actual|forecast|budget|prior)",
                r"(?:year over year|yoy|month over month|mom|period over period)",
            ],
            "keywords": ["variance", "compare", "comparison", "versus", "vs", "actual", 
                        "forecast", "budget", "yoy", "mom", "delta", "change"],
            "negative_keywords": [],
            "tools": ["smart_retrieve", "export_data_slice"],
            "sub_intents": {
                "actual_vs_forecast": r"(?:actual).{0,10}(?:vs|versus|forecast)",
                "actual_vs_budget": r"(?:actual).{0,10}(?:vs|versus|budget)",
                "yoy": r"(?:year over year|yoy|prior year|py)",
                "period": r"(?:period|month|quarter)",
            }
        },
        IntentType.PERIOD_CLOSE: {
            "patterns": [
                r"(?:period|month|quarter).{0,20}(?:close|closing|end)",
                r"(?:close|closing).{0,20}(?:status|checklist|process)",
                r"(?:ready to close|close activities|pre-close)",
            ],
            "keywords": ["close", "closing", "period end", "month end", "quarter end", 
                        "checklist", "pre-close"],
            "negative_keywords": [],
            "tools": ["list_jobs", "get_journals", "smart_retrieve", "validate_metadata"],
            "sub_intents": {
                "status": r"(?:status|ready|checklist)",
                "activities": r"(?:activities|tasks|steps)",
            }
        },
        IntentType.METADATA_VALIDATION: {
            "patterns": [
                r"(?:validate|check|verify).{0,20}(?:metadata|dimension|member)",
                r"(?:metadata).{0,20}(?:validation|check|error)",
                r"(?:data integrity|consistency check)",
            ],
            "keywords": ["validate", "validation", "check", "verify", "metadata", 
                        "integrity", "consistency"],
            "negative_keywords": [],
            "tools": ["validate_metadata", "get_dimensions", "get_members"],
            "sub_intents": {
                "validate": r"(?:validate|run validation)",
                "check": r"(?:check|verify|look for errors)",
            }
        },
        IntentType.INTERCOMPANY: {
            "patterns": [
                r"(?:intercompany|icp|ic).{0,20}(?:matching|elimination|balance)",
                r"(?:matching report|icp report|intercompany report)",
                r"(?:eliminate|elimination).{0,20}(?:intercompany|ic|icp)",
            ],
            "keywords": ["intercompany", "icp", "matching", "elimination", "ic balance"],
            "negative_keywords": [],
            "tools": ["generate_intercompany_matching_report", "smart_retrieve", "get_journals"],
            "sub_intents": {
                "matching": r"(?:matching|match|reconcile)",
                "elimination": r"(?:elimination|eliminate)",
                "report": r"(?:report|summary)",
            }
        },
        # OLAP-aware exploration intents
        IntentType.MEMBER_SEARCH: {
            "patterns": [
                r"(?:find|search|look for|locate).{0,20}(?:account|member|entity)",
                r"(?:which|what).{0,20}(?:account|member|entity).{0,20}(?:like|similar|match)",
                r"(?:account|member|entity).{0,20}(?:like|similar|match|contains)",
                r"(?:find|search).{0,20}(?:revenue|expense|asset|liability)",
            ],
            "keywords": ["find", "search", "look for", "locate", "like", "similar",
                        "match", "contains", "fuzzy", "where is"],
            "negative_keywords": ["value", "balance", "data", "get data"],
            "tools": ["search_members", "explore_dimension"],
            "sub_intents": {
                "account_search": r"(?:account|revenue|expense|income)",
                "entity_search": r"(?:entity|company|subsidiary)",
                "general_search": r"(?:member|dimension)",
            }
        },
        IntentType.HIERARCHY_EXPLORE: {
            "patterns": [
                r"(?:show|list|get|what are).{0,20}(?:children|descendants|parent|ancestors)",
                r"(?:children|descendants|parent|ancestors).{0,20}(?:of|for|under)",
                r"(?:explore|navigate|browse).{0,20}(?:hierarchy|tree|structure)",
                r"(?:drill into|expand|collapse).{0,20}(?:account|entity|member)",
                r"(?:what|which).{0,20}(?:under|below|above)",
            ],
            "keywords": ["children", "descendants", "parent", "ancestors", "hierarchy",
                        "explore", "navigate", "tree", "structure", "under", "below", "above"],
            "negative_keywords": ["value", "balance", "data for"],
            "tools": ["explore_dimension", "get_drill_suggestions", "list_available_dimensions"],
            "sub_intents": {
                "children": r"(?:children|descendants|under|below|expand)",
                "parent": r"(?:parent|ancestors|above|roll up)",
                "siblings": r"(?:siblings|peers|same level)",
                "path": r"(?:path|hierarchy|full tree)",
            }
        },
        IntentType.DRILL_DOWN: {
            "patterns": [
                r"(?:drill|drilldown|drill down).{0,20}(?:into|on|to)",
                r"(?:break down|breakdown|decompose).{0,20}(?:by|into)",
                r"(?:show|what).{0,20}(?:makes up|comprises|components of)",
                r"(?:detailed|details|breakdown).{0,20}(?:for|of)",
            ],
            "keywords": ["drill", "drilldown", "drill down", "break down", "breakdown",
                        "decompose", "components", "detailed", "details", "dive into"],
            "negative_keywords": [],
            "tools": ["explore_dimension", "get_drill_suggestions", "smart_retrieve"],
            "sub_intents": {
                "account_drill": r"(?:account|revenue|expense|income)",
                "entity_drill": r"(?:entity|company|geography)",
                "period_drill": r"(?:period|quarter|month)",
            }
        },
        IntentType.CONTRIBUTION_ANALYSIS: {
            "patterns": [
                r"(?:what|which).{0,20}(?:makes up|comprises|contributes to|composition)",
                r"(?:breakdown|break down|contribution).{0,20}(?:of|for|to)",
                r"(?:top|largest|biggest|smallest).{0,20}(?:contributor|component)",
                r"(?:percentage|percent|share).{0,20}(?:of|breakdown|composition)",
            ],
            "keywords": ["contribution", "contributes", "makes up", "comprises",
                        "composition", "percentage", "share", "top", "largest", "breakdown"],
            "negative_keywords": [],
            "tools": ["explore_dimension", "smart_retrieve", "get_drill_suggestions"],
            "sub_intents": {
                "by_entity": r"(?:entity|company|subsidiary|geography)",
                "by_account": r"(?:account|line item|category)",
                "top_n": r"(?:top|largest|biggest|smallest)",
            }
        },
        IntentType.TREND_ANALYSIS: {
            "patterns": [
                r"(?:trend|trending|over time|historical)",
                r"(?:show|get).{0,20}(?:trend|movement|change).{0,20}(?:for|of|in)",
                r"(?:monthly|quarterly|yearly|periodic).{0,20}(?:trend|view|data)",
                r"(?:how|what).{0,20}(?:changed|moved|trended)",
            ],
            "keywords": ["trend", "trending", "over time", "historical", "movement",
                        "change", "monthly", "quarterly", "periodic"],
            "negative_keywords": [],
            "tools": ["smart_retrieve", "smart_retrieve_with_movement"],
            "sub_intents": {
                "ytd": r"(?:ytd|year to date|cumulative)",
                "periodic": r"(?:monthly|quarterly|by period)",
                "movement": r"(?:movement|change|delta)",
            }
        },
    }
    
    # FCCS Entity patterns with normalization
    ENTITY_PATTERNS = {
        "period": {
            "pattern": r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|Q[1-4]|YearTotal|BegBal)\b",
            "normalize": lambda x: x.capitalize() if len(x) == 3 else x
        },
        "year": {
            "pattern": r"\b(FY\d{2}|\d{4})\b",
            "normalize": lambda x: f"FY{x[-2:]}" if x.isdigit() else x.upper()
        },
        "scenario": {
            "pattern": r"\b(Actual|Forecast|Budget|Plan|Working|Final)\b",
            "normalize": lambda x: x.capitalize()
        },
        "account": {
            # Match FCCS account patterns - allow spaces but exclude common prepositions to avoid over-matching
            # Examples: FCCS_Net Income, FCCS_Cash, FCCS_Retained Earnings, 40000, etc
            "pattern": r"\b(FCCS_(?!Total[\s_]Geography|Total[\s_]Company|Entity_)[\w]+(?:\s(?!for|in|at|by|of|with|during|from|the)[\w]+)*|\d{4,6})\b",
            "normalize": lambda x: x.replace("_", " ").strip()
        },
        "entity": {
            # Match FCCS entity patterns - exclude FY\d\d which is a year pattern
            # E001, US01, etc but NOT FY24 (which is a year)
            "pattern": r"\b(FCCS_Total[\s_]Geography|FCCS_Total_Geography|E\d{3,4}|(?!FY\d{2})[A-Z]{2,4}\d{2,4}|Total[\s_](?:Company|Geography|Entity))\b",
            "normalize": lambda x: x.replace("_", " ").upper()
        },
        "consolidation": {
            "pattern": r"\b(FCCS_Entity[\s_](?:Input|Consolidation|Total)|FCCS_(?:Proportion|Elimination|Contribution))\b",
            "normalize": lambda x: x.replace("_", " ")
        },
        "currency": {
            "pattern": r"\b(USD|EUR|GBP|JPY|BRL|Entity[\s_]Currency|Local|Reporting)\b",
            "normalize": lambda x: x.upper() if len(x) == 3 else x
        },
        "view": {
            "pattern": r"\b(FCCS_YTD|FCCS_Periodic|YTD|Periodic)\b",
            "normalize": lambda x: f"FCCS_{x}" if not x.startswith("FCCS") else x
        },
        "movement": {
            "pattern": r"\b(FCCS_Mvmts_[\w]+|FCCS_Mvmts_Total|FCCS_Mvmts_Subtotal)\b",
            "normalize": lambda x: x
        },
        "journal_status": {
            "pattern": r"\b(Working|Submitted|Approved|Rejected|Posted)\b",
            "normalize": lambda x: x.capitalize()
        },
        "job_id": {
            "pattern": r"\b(\d{8,})\b",
            "normalize": lambda x: x
        },
    }
    
    # Common FCCS abbreviations and aliases
    # NOTE: Use underscores in FCCS names for proper extraction
    ALIASES = {
        # Periods
        "january": "Jan", "february": "Feb", "march": "Mar", "april": "Apr",
        "may": "May", "june": "Jun", "july": "Jul", "august": "Aug",
        "september": "Sep", "october": "Oct", "november": "Nov", "december": "Dec",
        "q1": "Q1", "q2": "Q2", "q3": "Q3", "q4": "Q4",
        "year total": "YearTotal", "full year": "YearTotal", "annual": "YearTotal",
        # Scenarios
        "actuals": "Actual", "act": "Actual", "forecast": "Forecast", "fcst": "Forecast",
        "plan": "Plan", "budget": "Budget", "bud": "Budget",
        # Common accounts - USE UNDERSCORES for proper regex matching
        "net income": "FCCS_Net_Income", "ni": "FCCS_Net_Income",
        "income statement": "FCCS_Income_Statement", 
        "total revenue": "FCCS_Total_Revenue", "revenue": "FCCS_Total_Revenue",
        "total assets": "FCCS_Total_Assets", "assets": "FCCS_Total_Assets",
        "total liabilities": "FCCS_Total_Liabilities",
        "cash": "FCCS_Cash", "cash flow": "FCCS_Cash_Flow",
        "investment in sub": "FCCS_Investment_In_Sub",
        "total equity": "FCCS_Total_Equity",
        # Consolidation - keep these for explicit consolidation queries only
        "entity input": "FCCS_Entity_Input",
        "entity total": "FCCS_Entity_Total",
        "eliminations": "FCCS_Elimination", "elim": "FCCS_Elimination",
        "proportion": "FCCS_Proportion", "prop": "FCCS_Proportion",
        "contribution": "FCCS_Contribution", "contrib": "FCCS_Contribution",
    }
    
    def __init__(self, use_llm: bool = False):
        """Initialize classifier.
        
        Args:
            use_llm: Whether to use LLM for complex queries (requires LLMReasoner).
        """
        self.use_llm = use_llm
        self._llm_reasoner = None
        
        # Compile regex patterns for performance
        self._compiled_patterns = {}
        for intent_type, config in self.INTENT_CONFIG.items():
            self._compiled_patterns[intent_type] = [
                re.compile(p, re.IGNORECASE) for p in config["patterns"]
            ]
        
        self._compiled_entity_patterns = {
            entity_type: re.compile(config["pattern"], re.IGNORECASE)
            for entity_type, config in self.ENTITY_PATTERNS.items()
        }
    
    def set_llm_reasoner(self, reasoner):
        """Set LLM reasoner for enhanced classification."""
        self._llm_reasoner = reasoner
        self.use_llm = True
    
    def classify(self, query: str) -> Intent:
        """Classify user query into intent with entities.
        
        Args:
            query: User's natural language query.
            
        Returns:
            Intent object with classification results.
        """
        # Preprocess query
        processed_query = self._preprocess_query(query)
        
        # Extract entities first (they inform intent classification)
        entities = self.extract_entities(processed_query)
        
        # Score each intent type
        intent_scores = self._score_intents(processed_query, entities)
        
        # Get best intent
        best_intent_type, best_score = max(intent_scores.items(), key=lambda x: x[1])
        
        # If confidence is low and LLM is available, use LLM
        if best_score < 0.3 and self.use_llm and self._llm_reasoner:
            return self._classify_with_llm(query, entities)
        
        # Determine sub-intent
        sub_intent = self._detect_sub_intent(processed_query, best_intent_type)
        
        # Get suggested tools
        config = self.INTENT_CONFIG.get(best_intent_type, {})
        suggested_tools = config.get("tools", [])
        
        return Intent(
            name=best_intent_type.value,
            intent_type=best_intent_type,
            confidence=best_score,
            entities=entities,
            suggested_tools=suggested_tools,
            sub_intent=sub_intent,
            reasoning=f"Matched patterns: {best_score:.2f} confidence"
        )
    
    def extract_entities(self, query: str) -> Dict[str, str]:
        """Extract FCCS dimension entities from query.
        
        Args:
            query: User's query (original case).
            
        Returns:
            Dict mapping entity types to extracted values.
        """
        entities = {}
        
        # We need both original and processed for better matching
        processed = self._preprocess_query(query)
        aliased_processed = self._replace_aliases(processed)
        
        # Note: we run regex on aliased_processed but want to potentially 
        # map back to original case if it's a specific member ID like E501
        
        for entity_type, pattern in self._compiled_entity_patterns.items():
            match = pattern.search(aliased_processed)
            if match:
                value = match.group(0)
                
                # If it's a member ID pattern like E\d+, try to find original case in query
                if entity_type == "entity" and re.match(r'e\d+', value):
                    orig_match = re.search(re.escape(value), query, re.IGNORECASE)
                    if orig_match:
                        value = orig_match.group(0)
                
                # Normalize the value
                normalizer = self.ENTITY_PATTERNS[entity_type].get("normalize")
                if normalizer:
                    value = normalizer(value)
                entities[entity_type] = value
        
        return entities
    
    def extract_all_entities(self, query: str) -> List[EntityMatch]:
        """Extract all entity mentions with positions.
        
        Useful for highlighting or detailed analysis.
        
        Args:
            query: User's query.
            
        Returns:
            List of EntityMatch objects.
        """
        matches = []
        processed = self._replace_aliases(query)
        
        for entity_type, pattern in self._compiled_entity_patterns.items():
            for match in pattern.finditer(processed):
                value = match.group(0)
                normalizer = self.ENTITY_PATTERNS[entity_type].get("normalize")
                normalized = normalizer(value) if normalizer else value
                
                matches.append(EntityMatch(
                    entity_type=entity_type,
                    value=value,
                    start_pos=match.start(),
                    end_pos=match.end(),
                    normalized_value=normalized
                ))
        
        return sorted(matches, key=lambda x: x.start_pos)
    
    def _preprocess_query(self, query: str) -> str:
        """Preprocess query for better matching."""
        # Lowercase for matching
        processed = query.lower()
        
        # Normalize whitespace
        processed = re.sub(r'\s+', ' ', processed).strip()
        
        return processed
    
    def _replace_aliases(self, query: str) -> str:
        """Replace known aliases with canonical forms."""
        result = query.lower()
        for alias, canonical in self.ALIASES.items():
            result = re.sub(rf'\b{re.escape(alias)}\b', canonical, result, flags=re.IGNORECASE)
        return result
    
    def _score_intents(
        self,
        query: str,
        entities: Dict[str, str]
    ) -> Dict[IntentType, float]:
        """Score each intent type for the query.
        
        Uses a weighted combination of:
        - Pattern matches (50%)
        - Keyword presence (30%)
        - Entity relevance (20%)
        """
        scores = {}
        
        for intent_type, config in self.INTENT_CONFIG.items():
            # Pattern matching score
            pattern_score = self._calculate_pattern_score(
                query, self._compiled_patterns[intent_type]
            )
            
            # Keyword score
            keyword_score = self._calculate_keyword_score(
                query, 
                config.get("keywords", []),
                config.get("negative_keywords", [])
            )
            
            # Entity relevance score
            entity_score = self._calculate_entity_relevance(entities, intent_type)
            
            # Weighted combination
            total_score = (
                pattern_score * 0.50 +
                keyword_score * 0.30 +
                entity_score * 0.20
            )
            
            scores[intent_type] = total_score
        
        return scores
    
    def _calculate_pattern_score(
        self,
        query: str,
        patterns: List[re.Pattern]
    ) -> float:
        """Calculate pattern match score."""
        if not patterns:
            return 0.0
        
        matches = sum(1 for p in patterns if p.search(query))
        # Use sqrt to reduce impact of many matches
        return min(1.0, (matches / len(patterns)) ** 0.5) if patterns else 0.0
    
    def _calculate_keyword_score(
        self,
        query: str,
        keywords: List[str],
        negative_keywords: List[str]
    ) -> float:
        """Calculate keyword presence score."""
        if not keywords:
            return 0.0
        
        # Positive keywords
        positive_matches = sum(1 for kw in keywords if kw.lower() in query)
        positive_score = min(1.0, positive_matches / len(keywords))
        
        # Negative keywords (penalize)
        negative_matches = sum(1 for kw in negative_keywords if kw.lower() in query)
        negative_penalty = min(0.5, negative_matches * 0.15)
        
        return max(0.0, positive_score - negative_penalty)
    
    def _calculate_entity_relevance(
        self,
        entities: Dict[str, str],
        intent_type: IntentType
    ) -> float:
        """Calculate how relevant extracted entities are to the intent."""
        # Entity type relevance mapping
        relevance_map = {
            IntentType.DATA_RETRIEVAL: ["account", "entity", "period", "year", "scenario"],
            IntentType.DIMENSION_EXPLORATION: ["entity", "account"],
            IntentType.JOURNAL_MANAGEMENT: ["period", "year", "scenario", "journal_status"],
            IntentType.CONSOLIDATION: ["entity", "consolidation", "period", "year"],
            IntentType.JOB_MANAGEMENT: ["job_id"],
            IntentType.REPORTING: ["period", "year", "scenario"],
            IntentType.VARIANCE_ANALYSIS: ["scenario", "period", "year", "account"],
            IntentType.PERIOD_CLOSE: ["period", "year"],
            IntentType.METADATA_VALIDATION: ["entity", "account"],
            IntentType.INTERCOMPANY: ["entity", "period", "year"],
            # OLAP-aware intents
            IntentType.MEMBER_SEARCH: ["account", "entity"],
            IntentType.HIERARCHY_EXPLORE: ["account", "entity"],
            IntentType.DRILL_DOWN: ["account", "entity", "period", "year"],
            IntentType.CONTRIBUTION_ANALYSIS: ["account", "entity", "period", "year"],
            IntentType.TREND_ANALYSIS: ["account", "entity", "period", "year", "movement"],
        }
        
        relevant_types = relevance_map.get(intent_type, [])
        if not relevant_types:
            return 0.0
        
        matches = sum(1 for et in relevant_types if et in entities)
        return matches / len(relevant_types)
    
    def _detect_sub_intent(
        self,
        query: str,
        intent_type: IntentType
    ) -> Optional[str]:
        """Detect sub-intent within the main intent."""
        config = self.INTENT_CONFIG.get(intent_type, {})
        sub_intents = config.get("sub_intents", {})
        
        for sub_name, pattern in sub_intents.items():
            if re.search(pattern, query, re.IGNORECASE):
                return sub_name
        
        return None
    
    def _classify_with_llm(
        self,
        query: str,
        entities: Dict[str, str]
    ) -> Intent:
        """Use LLM for complex query classification."""
        if not self._llm_reasoner:
            return Intent(
                name=IntentType.UNKNOWN.value,
                intent_type=IntentType.UNKNOWN,
                confidence=0.0,
                entities=entities,
                suggested_tools=["get_application_info"],
                reasoning="LLM not available for complex classification"
            )
        
        # LLM classification will be implemented in llm_reasoning.py
        return self._llm_reasoner.classify_intent(query, entities)
    
    def get_intent_examples(self, intent_type: IntentType) -> List[str]:
        """Get example queries for an intent type.
        
        Useful for training or documentation.
        """
        examples = {
            IntentType.DATA_RETRIEVAL: [
                "What is the net income for Jan 2024?",
                "Show me revenue for Entity E001 in Q4",
                "Get the balance for account 40000 in Forecast scenario",
                "Retrieve total assets for FY24",
            ],
            IntentType.DIMENSION_EXPLORATION: [
                "List all entities in the hierarchy",
                "Show children of Total Company",
                "What accounts are under Revenue?",
                "Get dimension members for Entity",
            ],
            IntentType.JOURNAL_MANAGEMENT: [
                "Show me posted journals for January",
                "Approve journal JE-001",
                "List all pending journal entries",
                "What journals need approval?",
            ],
            IntentType.CONSOLIDATION: [
                "Run consolidation for December",
                "Show me the consolidation breakdown for Total Geography",
                "What are the eliminations for Q4?",
                "Generate consolidation process report",
            ],
            IntentType.JOB_MANAGEMENT: [
                "Check job status for 123456789",
                "List recent jobs",
                "Did the consolidation job complete?",
                "Show me running jobs",
            ],
        }
        return examples.get(intent_type, [])
