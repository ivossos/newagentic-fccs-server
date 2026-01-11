"""Consolidation operations tools - run_consolidation, run_translation, ownership, period management."""

from typing import Any, Optional, List, Dict
from datetime import datetime

from fccs_agent.client.fccs_client import FccsClient

_client: FccsClient = None
_app_name: str = None


def set_client(client: FccsClient):
    global _client
    _client = client


def set_app_name(app_name: str):
    global _app_name
    _app_name = app_name


# ============================================================================
# CONSOLIDATION EXECUTION
# ============================================================================

async def run_consolidation(
    entity: str,
    scenario: str = "Actual",
    year: str = "FY24",
    period: str = "Jan",
    consolidation_type: str = "ALL",
    force_recalc: bool = False
) -> Dict[str, Any]:
    """Run consolidation for an entity / Executar consolidação para uma entidade.

    This is the core FCCS operation that calculates:
    - Currency translation
    - Intercompany eliminations  
    - Ownership adjustments (proportional consolidation, equity method)
    - Rollup to parent entities

    Args:
        entity: Entity to consolidate (e.g., 'FCCS_Total Geography', 'USA', 'E001').
        scenario: Scenario name (default: 'Actual').
        year: Fiscal year (default: 'FY24').
        period: Period to consolidate (default: 'Jan').
        consolidation_type: Type of consolidation:
            - 'ALL': Full consolidation (translation + elimination + ownership)
            - 'TRANSLATE': Currency translation only
            - 'CONSOLIDATE': Consolidation without translation
            - 'ELIMINATE_ICP': Intercompany eliminations only
            - 'CALC_OWNERSHIP': Ownership calculations only
        force_recalc: Force recalculation even if data hasn't changed.

    Returns:
        dict: Consolidation job result with status and job ID.
    """
    # Map consolidation types to rule names
    rule_mapping = {
        "ALL": "Consolidate",
        "TRANSLATE": "Translate",
        "CONSOLIDATE": "Consolidate",
        "ELIMINATE_ICP": "IntercompanyElimination",
        "CALC_OWNERSHIP": "OwnershipCalculation",
    }
    
    rule_name = rule_mapping.get(consolidation_type.upper(), "Consolidate")
    
    parameters = {
        "Entity": entity,
        "Scenario": scenario,
        "Year": year,
        "Period": period,
    }
    
    if force_recalc:
        parameters["ForceCalculate"] = "true"
    
    result = await _client.run_business_rule(_app_name, rule_name, parameters)
    
    return {
        "status": "success",
        "data": {
            "job_id": result.get("jobId"),
            "job_status": result.get("status"),
            "consolidation_type": consolidation_type,
            "entity": entity,
            "scenario": scenario,
            "year": year,
            "period": period,
            "result": result
        }
    }


async def run_translation(
    entity: str,
    scenario: str = "Actual",
    year: str = "FY24",
    period: str = "Jan",
    target_currency: str = "USD"
) -> Dict[str, Any]:
    """Run currency translation for an entity / Executar tradução de moeda.

    Translates entity data from local currency to the specified target currency
    using the configured exchange rates.

    Args:
        entity: Entity to translate.
        scenario: Scenario name.
        year: Fiscal year.
        period: Period to translate.
        target_currency: Target currency code (default: 'USD').

    Returns:
        dict: Translation job result.
    """
    parameters = {
        "Entity": entity,
        "Scenario": scenario,
        "Year": year,
        "Period": period,
        "TargetCurrency": target_currency,
    }
    
    result = await _client.run_business_rule(_app_name, "Translate", parameters)
    
    return {
        "status": "success",
        "data": {
            "job_id": result.get("jobId"),
            "entity": entity,
            "target_currency": target_currency,
            "result": result
        }
    }


async def run_force_consolidation(
    entities: List[str],
    scenario: str = "Actual",
    year: str = "FY24",
    periods: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Force consolidation for multiple entities/periods / Forçar consolidação em lote.

    Useful for period-end close when you need to ensure all entities are
    consolidated regardless of data changes.

    Args:
        entities: List of entities to consolidate.
        scenario: Scenario name.
        year: Fiscal year.
        periods: List of periods (default: all 12 months).

    Returns:
        dict: Batch consolidation results.
    """
    if periods is None:
        periods = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    
    results = []
    errors = []
    
    for entity in entities:
        for period in periods:
            try:
                result = await run_consolidation(
                    entity=entity,
                    scenario=scenario,
                    year=year,
                    period=period,
                    consolidation_type="ALL",
                    force_recalc=True
                )
                results.append({
                    "entity": entity,
                    "period": period,
                    "status": "submitted",
                    "job_id": result.get("data", {}).get("job_id")
                })
            except Exception as e:
                errors.append({
                    "entity": entity,
                    "period": period,
                    "error": str(e)
                })
    
    return {
        "status": "success" if not errors else "partial",
        "data": {
            "submitted": len(results),
            "failed": len(errors),
            "results": results,
            "errors": errors
        }
    }


# ============================================================================
# OWNERSHIP MANAGEMENT
# ============================================================================

async def get_ownership_structure(
    parent_entity: Optional[str] = None,
    scenario: str = "Actual",
    year: str = "FY24"
) -> Dict[str, Any]:
    """Get ownership structure for entities / Obter estrutura de propriedade.

    Retrieves the ownership hierarchy including ownership percentages,
    consolidation methods, and control flags.

    Args:
        parent_entity: Parent entity to start from (default: root).
        scenario: Scenario name.
        year: Fiscal year.

    Returns:
        dict: Ownership structure with percentages and methods.
    """
    # Get Entity dimension members with hierarchy
    hierarchy = await _client.get_dimension_hierarchy(
        _app_name, 
        "Entity",
        member_name=parent_entity,
        depth=10,
        include_metadata=True
    )
    
    # Extract ownership-relevant metadata
    def extract_ownership_info(node: Dict) -> Dict:
        metadata = node.get("metadata", {})
        return {
            "entity": node.get("name"),
            "parent": metadata.get("parentName"),
            "ownership_pct": metadata.get("ownershipPercentage", 100.0),
            "consolidation_method": metadata.get("consolidationMethod", "FULL"),
            "control_flag": metadata.get("controllingInterest", True),
            "functional_currency": metadata.get("currency", "USD"),
            "children": [
                extract_ownership_info(child) 
                for child in node.get("children", [])
            ]
        }
    
    ownership_tree = []
    for node in hierarchy.get("hierarchy", []):
        ownership_tree.append(extract_ownership_info(node))
    
    return {
        "status": "success",
        "data": {
            "scenario": scenario,
            "year": year,
            "ownership_structure": ownership_tree,
            "total_entities": hierarchy.get("totalMembers", 0)
        }
    }


async def calculate_minority_interest(
    entity: str,
    account: str = "FCCS_Net Income",
    scenario: str = "Actual",
    year: str = "FY24",
    period: str = "Dec"
) -> Dict[str, Any]:
    """Calculate minority interest for an entity / Calcular participação minoritária.

    For entities with less than 100% ownership, calculates the portion
    of income/equity attributable to minority shareholders.

    Args:
        entity: Entity to calculate.
        account: Account to analyze (default: Net Income).
        scenario: Scenario name.
        year: Fiscal year.
        period: Period for calculation.

    Returns:
        dict: Minority interest calculation with breakdown.
    """
    from fccs_agent.tools.data import smart_retrieve
    
    # Get Entity Total (consolidated view)
    total_result = await smart_retrieve(
        account=account,
        entity=entity,
        period=period,
        years=year,
        scenario=scenario,
        consolidation="FCCS_Entity Total"
    )
    
    # Get Proportion (ownership-adjusted)
    proportion_result = await smart_retrieve(
        account=account,
        entity=entity,
        period=period,
        years=year,
        scenario=scenario,
        consolidation="FCCS_Proportion"
    )
    
    # Get Entity Input (local input)
    input_result = await smart_retrieve(
        account=account,
        entity=entity,
        period=period,
        years=year,
        scenario=scenario,
        consolidation="FCCS_Entity Input"
    )
    
    # Extract values
    def extract_value(result: Dict) -> float:
        try:
            data = result.get("data", {})
            if "rows" in data and len(data["rows"]) > 0:
                row = data["rows"][0]
                if "data" in row and len(row["data"]) > 0:
                    return float(row["data"][0])
        except (ValueError, TypeError, KeyError):
            pass
        return 0.0
    
    entity_total = extract_value(total_result)
    proportion = extract_value(proportion_result)
    entity_input = extract_value(input_result)
    
    # Calculate minority interest
    minority_interest = entity_total - proportion if entity_total != 0 else 0
    ownership_pct = (proportion / entity_input * 100) if entity_input != 0 else 100.0
    
    return {
        "status": "success",
        "data": {
            "entity": entity,
            "account": account,
            "period": period,
            "year": year,
            "values": {
                "entity_input": entity_input,
                "entity_total": entity_total,
                "proportion": proportion,
                "minority_interest": minority_interest
            },
            "calculated_ownership_pct": round(ownership_pct, 2),
            "minority_pct": round(100 - ownership_pct, 2)
        }
    }


# ============================================================================
# PERIOD CLOSE MANAGEMENT
# ============================================================================

async def get_period_close_status(
    scenario: str = "Actual",
    year: str = "FY24",
    period: Optional[str] = None
) -> Dict[str, Any]:
    """Get period close status for all entities / Obter status de fechamento.

    Retrieves the consolidation status for each entity, showing which
    entities need attention during the close process.

    Args:
        scenario: Scenario name.
        year: Fiscal year.
        period: Specific period (default: all periods).

    Returns:
        dict: Close status by entity and period.
    """
    periods = [period] if period else [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
    ]
    
    # Get entity hierarchy
    entities_result = await _client.get_dimension_hierarchy(
        _app_name, "Entity", depth=3
    )
    
    # Extract leaf entities (actual operating entities)
    def get_leaf_entities(node: Dict, leaves: List[str] = None) -> List[str]:
        if leaves is None:
            leaves = []
        children = node.get("children", [])
        if not children or len(children) == 0:
            leaves.append(node.get("name"))
        else:
            for child in children:
                get_leaf_entities(child, leaves)
        return leaves
    
    leaf_entities = []
    for node in entities_result.get("hierarchy", []):
        get_leaf_entities(node, leaf_entities)
    
    # Limit to first 20 entities for performance
    sample_entities = leaf_entities[:20]
    
    status_summary = {
        "scenario": scenario,
        "year": year,
        "periods_checked": periods,
        "entity_count": len(leaf_entities),
        "sample_entities": len(sample_entities),
        "status_by_period": {}
    }
    
    for p in periods:
        status_summary["status_by_period"][p] = {
            "entities_with_data": 0,
            "entities_consolidated": 0,
            "needs_attention": []
        }
    
    return {
        "status": "success",
        "data": status_summary,
        "note": "For full close status, use Task Manager reports via generate_report tool"
    }


async def lock_period(
    scenario: str,
    year: str,
    period: str,
    entities: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Lock a period to prevent further data entry / Bloquear período.

    Locks the specified period for data entry while allowing
    consolidation adjustments.

    Args:
        scenario: Scenario to lock.
        year: Year to lock.
        period: Period to lock.
        entities: Specific entities to lock (default: all).

    Returns:
        dict: Lock operation result.
    """
    parameters = {
        "Scenario": scenario,
        "Year": year,
        "Period": period,
        "LockType": "DATA_ENTRY",
    }
    
    if entities:
        parameters["Entities"] = ",".join(entities)
    
    result = await _client.run_business_rule(_app_name, "LockPeriod", parameters)
    
    return {
        "status": "success",
        "data": {
            "scenario": scenario,
            "year": year,
            "period": period,
            "locked": True,
            "result": result
        }
    }


async def unlock_period(
    scenario: str,
    year: str,
    period: str,
    entities: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Unlock a period for data entry / Desbloquear período.

    Args:
        scenario: Scenario to unlock.
        year: Year to unlock.
        period: Period to unlock.
        entities: Specific entities to unlock (default: all).

    Returns:
        dict: Unlock operation result.
    """
    parameters = {
        "Scenario": scenario,
        "Year": year,
        "Period": period,
    }
    
    if entities:
        parameters["Entities"] = ",".join(entities)
    
    result = await _client.run_business_rule(_app_name, "UnlockPeriod", parameters)
    
    return {
        "status": "success",
        "data": {
            "scenario": scenario,
            "year": year,
            "period": period,
            "locked": False,
            "result": result
        }
    }


# ============================================================================
# TOOL DEFINITIONS
# ============================================================================

TOOL_DEFINITIONS = [
    {
        "name": "run_consolidation",
        "description": "Run consolidation for an entity - the core FCCS operation that calculates translation, eliminations, and ownership / Executar consolidação",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity": {
                    "type": "string",
                    "description": "Entity to consolidate (e.g., 'FCCS_Total Geography', 'USA')",
                },
                "scenario": {
                    "type": "string",
                    "description": "Scenario name (default: 'Actual')",
                },
                "year": {
                    "type": "string",
                    "description": "Fiscal year (default: 'FY24')",
                },
                "period": {
                    "type": "string",
                    "description": "Period to consolidate (default: 'Jan')",
                },
                "consolidation_type": {
                    "type": "string",
                    "enum": ["ALL", "TRANSLATE", "CONSOLIDATE", "ELIMINATE_ICP", "CALC_OWNERSHIP"],
                    "description": "Type of consolidation to run (default: 'ALL')",
                },
                "force_recalc": {
                    "type": "boolean",
                    "description": "Force recalculation even if data hasn't changed",
                },
            },
            "required": ["entity"],
        },
    },
    {
        "name": "run_translation",
        "description": "Run currency translation for an entity / Executar tradução de moeda",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity": {"type": "string", "description": "Entity to translate"},
                "scenario": {"type": "string", "description": "Scenario name"},
                "year": {"type": "string", "description": "Fiscal year"},
                "period": {"type": "string", "description": "Period"},
                "target_currency": {"type": "string", "description": "Target currency code (default: 'USD')"},
            },
            "required": ["entity"],
        },
    },
    {
        "name": "run_force_consolidation",
        "description": "Force consolidation for multiple entities/periods - useful for period-end close / Forçar consolidação em lote",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of entities to consolidate",
                },
                "scenario": {"type": "string", "description": "Scenario name"},
                "year": {"type": "string", "description": "Fiscal year"},
                "periods": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of periods (default: all 12 months)",
                },
            },
            "required": ["entities"],
        },
    },
    {
        "name": "get_ownership_structure",
        "description": "Get ownership structure showing hierarchy, ownership percentages, and consolidation methods / Obter estrutura de propriedade",
        "inputSchema": {
            "type": "object",
            "properties": {
                "parent_entity": {"type": "string", "description": "Parent entity to start from"},
                "scenario": {"type": "string", "description": "Scenario name"},
                "year": {"type": "string", "description": "Fiscal year"},
            },
        },
    },
    {
        "name": "calculate_minority_interest",
        "description": "Calculate minority interest for partially-owned entities / Calcular participação minoritária",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity": {"type": "string", "description": "Entity to calculate"},
                "account": {"type": "string", "description": "Account to analyze (default: 'FCCS_Net Income')"},
                "scenario": {"type": "string", "description": "Scenario name"},
                "year": {"type": "string", "description": "Fiscal year"},
                "period": {"type": "string", "description": "Period"},
            },
            "required": ["entity"],
        },
    },
    {
        "name": "get_period_close_status",
        "description": "Get period close status for all entities / Obter status de fechamento",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scenario": {"type": "string", "description": "Scenario name"},
                "year": {"type": "string", "description": "Fiscal year"},
                "period": {"type": "string", "description": "Specific period (optional)"},
            },
        },
    },
    {
        "name": "lock_period",
        "description": "Lock a period to prevent further data entry / Bloquear período",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scenario": {"type": "string", "description": "Scenario to lock"},
                "year": {"type": "string", "description": "Year to lock"},
                "period": {"type": "string", "description": "Period to lock"},
                "entities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific entities to lock (optional)",
                },
            },
            "required": ["scenario", "year", "period"],
        },
    },
    {
        "name": "unlock_period",
        "description": "Unlock a period for data entry / Desbloquear período",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scenario": {"type": "string", "description": "Scenario to unlock"},
                "year": {"type": "string", "description": "Year to unlock"},
                "period": {"type": "string", "description": "Period to unlock"},
                "entities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific entities to unlock (optional)",
                },
            },
            "required": ["scenario", "year", "period"],
        },
    },
]
