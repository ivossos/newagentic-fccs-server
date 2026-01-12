"""Intercompany (ICP) tools - matching, analysis, eliminations."""

import csv
import os
from pathlib import Path
from typing import Any, Optional, List, Dict
from datetime import datetime

from fccs_agent.client.fccs_client import FccsClient

_client: FccsClient = None
_app_name: str = None

# Cache for metadata
_entity_cache: List[Dict] = None
_icp_cache: List[Dict] = None
_account_cache: List[Dict] = None


def set_client(client: FccsClient):
    global _client
    _client = client


def set_app_name(app_name: str):
    global _app_name
    _app_name = app_name


# ============================================================================
# LOCAL METADATA LOADING
# ============================================================================

def _get_metadata_path() -> Path:
    """Get path to metadata CSV files."""
    # Try multiple locations
    possible_paths = [
        Path(__file__).parent.parent.parent / "data",
        Path("C:/Users/ivoss/Downloads/Projetos/agentic/newagentic-fccs-server/data"),
        Path(os.getcwd()) / "data",
    ]
    for path in possible_paths:
        if path.exists():
            return path
    return possible_paths[0]


def _load_csv_metadata(filename: str) -> List[Dict]:
    """Load metadata from CSV file."""
    metadata_path = _get_metadata_path() / filename
    
    if not metadata_path.exists():
        return []
    
    rows = []
    encodings = ["utf-8-sig", "utf-8", "latin-1", "cp1252"]
    
    for encoding in encodings:
        try:
            with open(metadata_path, "r", encoding=encoding) as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                if rows:
                    break
        except Exception:
            continue
    
    return rows


def _get_entities_from_cache() -> List[Dict]:
    """Load entities from local CSV cache."""
    global _entity_cache
    
    if _entity_cache is None:
        rows = _load_csv_metadata("Ravi_ExportedMetadata_Entity.csv")
        _entity_cache = []
        
        for row in rows:
            # Handle different column name formats
            name = (row.get("Entity") or row.get("\ufeffEntity") or "").strip()
            parent = (row.get(" Parent") or row.get("Parent") or "").strip()
            alias = (row.get(" Alias: Default") or row.get("Alias: Default") or "").strip()
            data_storage = (row.get(" Data Storage") or row.get("Data Storage") or "").strip()
            
            if name and name != "Entity":
                _entity_cache.append({
                    "name": name,
                    "parent": parent,
                    "alias": alias,
                    "data_storage": data_storage,
                    "is_leaf": data_storage.lower() in ["store", "shared", "never share"]
                })
    
    return _entity_cache


def _get_icp_members_from_cache() -> List[Dict]:
    """Load ICP members from local CSV cache."""
    global _icp_cache
    
    if _icp_cache is None:
        rows = _load_csv_metadata("Ravi_ExportedMetadata_Intercompany.csv")
        _icp_cache = []
        
        for row in rows:
            name = (row.get("Intercompany") or row.get("\ufeffIntercompany") or "").strip()
            parent = (row.get(" Parent") or row.get("Parent") or "").strip()
            alias = (row.get(" Alias: Default") or row.get("Alias: Default") or "").strip()
            
            if name and name.startswith("ICP_"):
                _icp_cache.append({
                    "name": name,
                    "parent": parent,
                    "alias": alias,
                })
    
    return _icp_cache


def _get_icp_accounts_from_cache() -> List[str]:
    """Load ICP-flagged accounts from local CSV cache."""
    global _account_cache
    
    if _account_cache is None:
        rows = _load_csv_metadata("Ravi_ExportedMetadata_Account.csv")
        _account_cache = []
        
        for row in rows:
            name = (row.get("Account") or row.get("\ufeffAccount") or "").strip()
            icp_flag = (row.get(" Intercompany Account") or row.get("Intercompany Account") or "").strip()
            
            if name and "IC_Acc_Yes" in icp_flag:
                _account_cache.append(name)
    
    return _account_cache


def _get_leaf_entities() -> List[str]:
    """Get leaf entities (store data) from cache."""
    entities = _get_entities_from_cache()
    return [e["name"] for e in entities if e.get("is_leaf")]


def _get_icp_active_entities() -> List[str]:
    """Get entities that are ICP-flagged (more likely to have ICP data)."""
    entities = _get_entities_from_cache()
    # Filter for entities that have ICP flag or are numeric (common pattern for ICP entities)
    icp_entities = []
    for e in entities:
        name = e.get("name", "")
        # Numeric entities like 117, 118 often have ICP data
        if name.isdigit():
            icp_entities.append(name)
        # Entities with ICP naming patterns
        elif "_0" in name or name.startswith("0"):
            icp_entities.append(name)
    return icp_entities


def _get_entity_to_icp_map() -> Dict[str, str]:
    """Map entity names to their ICP member names.
    
    Returns: {"117": "ICP_117", "01_002": "ICP_01_002", ...}
    """
    icp_members = _get_icp_members_from_cache()
    mapping = {}
    for icp in icp_members:
        icp_name = icp.get("name", "")
        if icp_name.startswith("ICP_"):
            entity_name = icp_name[4:]  # Remove "ICP_" prefix
            mapping[entity_name] = icp_name
    return mapping


def _get_icp_to_entity_map() -> Dict[str, str]:
    """Map ICP member names to their entity names.
    
    Returns: {"ICP_117": "117", "ICP_01_002": "01_002", ...}
    """
    icp_members = _get_icp_members_from_cache()
    mapping = {}
    for icp in icp_members:
        icp_name = icp.get("name", "")
        if icp_name.startswith("ICP_"):
            entity_name = icp_name[4:]  # Remove "ICP_" prefix
            mapping[icp_name] = entity_name
    return mapping


# ============================================================================
# ICP ANALYSIS
# ============================================================================

async def get_icp_balances(
    entity: str,
    account: Optional[str] = None,
    scenario: str = "Actual",
    year: str = "FY24",
    period: str = "Dec"
) -> Dict[str, Any]:
    """Get intercompany balances for an entity / Obter saldos intercompanhia.

    Retrieves all ICP balances for an entity, optionally filtered by account.
    Shows both the "sending" (ICP partner) and amounts.

    Args:
        entity: Entity to query.
        account: Specific ICP account (optional - shows all if not specified).
        scenario: Scenario name.
        year: Fiscal year.
        period: Period.

    Returns:
        dict: ICP balances by partner entity.
    """
    # Get ICP dimension members from local cache
    icp_cache = _get_icp_members_from_cache()
    icp_members = [m["name"] for m in icp_cache][:50]  # Limit for performance
    
    # Default to ICP accounts from metadata if not specified
    if account:
        accounts_to_check = [account]
    else:
        icp_accounts = _get_icp_accounts_from_cache()
        accounts_to_check = icp_accounts[:10] if icp_accounts else [
            "10501", "10502", "10503", "10504", "10505", "10506", "10507",
            "20301", "20302", "20303", "20304", "20305", "20306", "20307",
        ]
    
    balances = {}
    
    for icp_partner in icp_members:
        partner_balances = {}
        
        for acct in accounts_to_check:
            try:
                # Build grid to query specific ICP intersection
                grid_definition = {
                    "suppressMissingBlocks": True,
                    "pov": {
                        "members": [
                            [year], [scenario], ["FCCS_YTD"], ["FCCS_Entity Input"],
                            [icp_partner], ["FCCS_Total Data Source"],
                            ["FCCS_Mvmts_Total"], [entity], ["Entity Currency"],
                            ["Total Custom 3"], ["Total Region"], ["Total Venturi Entity"],
                            ["Total Custom 4"]
                        ]
                    },
                    "columns": [{"members": [[period]]}],
                    "rows": [{"members": [[acct]]}]
                }
                
                result = await _client.export_data_slice(_app_name, "Consol", grid_definition)
                
                # Extract value
                value = 0.0
                if result and "rows" in result and len(result["rows"]) > 0:
                    row = result["rows"][0]
                    if "data" in row and len(row["data"]) > 0:
                        try:
                            value = float(row["data"][0])
                        except (ValueError, TypeError):
                            value = 0.0
                
                if value != 0:
                    partner_balances[acct] = value
                    
            except Exception:
                continue
        
        if partner_balances:
            balances[icp_partner] = partner_balances
    
    # Calculate totals
    total_by_account = {}
    for partner, accts in balances.items():
        for acct, value in accts.items():
            if acct not in total_by_account:
                total_by_account[acct] = 0.0
            total_by_account[acct] += value
    
    return {
        "status": "success",
        "data": {
            "entity": entity,
            "scenario": scenario,
            "year": year,
            "period": period,
            "icp_balances": balances,
            "totals": total_by_account,
            "partner_count": len(balances)
        }
    }


async def get_icp_mismatches(
    scenario: str = "Actual",
    year: str = "FY24",
    period: str = "Dec",
    tolerance: float = 0.01,
    entity_pairs: Optional[List[tuple]] = None
) -> Dict[str, Any]:
    """Find ICP mismatches - both unassigned balances and counterparty mismatches.

    Detects TWO types of ICP issues:
    
    TYPE 1 - Unassigned ICP Balances:
        Entity has balance in ICP account but ICP partner not specified.
        Example: Entity 117 has $4M in account 20301 with ICP=FCCS_No Intercompany
        Issue: "I owe someone but didn't say WHO"
        
    TYPE 2 - Counterparty Mismatches:
        Entity A records receivable from B, but B's payable to A doesn't match.
        Example: A says "B owes me $1M", B says "I owe A $800K" = $200K mismatch

    Args:
        scenario: Scenario name.
        year: Fiscal year.
        period: Period to analyze.
        tolerance: Mismatch tolerance amount (default: 0.01).
        entity_pairs: Specific entity pairs to check (optional).

    Returns:
        dict: Both types of mismatches with amounts.
    """
    # Get metadata
    icp_entities = _get_icp_active_entities()
    leaf_entities = _get_leaf_entities()
    all_entities = icp_entities + [e for e in leaf_entities if e not in icp_entities]
    
    if not all_entities:
        return {"status": "error", "error": "No entities found in metadata cache"}
    
    # Get ICP accounts and mappings
    icp_accounts = _get_icp_accounts_from_cache()
    receivable_accounts = [a for a in icp_accounts if a.startswith("10")] or ["10501", "10502", "10503", "10504", "10505", "10506", "10507"]
    payable_accounts = [a for a in icp_accounts if a.startswith("20")] or ["20301", "20302", "20303", "20304", "20305", "20306", "20307"]
    all_icp_accounts = receivable_accounts + payable_accounts
    
    entity_to_icp = _get_entity_to_icp_map()
    icp_to_entity = _get_icp_to_entity_map()
    
    # Limit entities for performance
    sample_entities = all_entities[:50]
    
    # ========================================================================
    # TYPE 1: Unassigned ICP Balances (ICP = FCCS_No Intercompany)
    # ========================================================================
    type1_unassigned = []
    rows_definition = [{"members": [[acct]]} for acct in all_icp_accounts]
    
    for entity in sample_entities:
        try:
            grid_definition = {
                "suppressMissingBlocks": True,
                "pov": {
                    "members": [
                        [year], [scenario], ["FCCS_Periodic"], ["FCCS_Entity Input"],
                        ["FCCS_No Intercompany"], ["FCCS_Managed Data"],
                        ["FCCS_Mvmts_Subtotal"], [entity], ["Entity Currency"],
                        ["Total Custom 3"], ["Total Region"], ["Total Venturi Entity"],
                        ["Total Custom 4"]
                    ]
                },
                "columns": [{"members": [[period]]}],
                "rows": rows_definition
            }
            
            result = await _client.export_data_slice(_app_name, "Consol", grid_definition)
            
            if result and "rows" in result:
                for row in result["rows"]:
                    account = row.get("headers", [""])[0] if row.get("headers") else ""
                    data = row.get("data", [])
                    
                    if data and data[0]:
                        try:
                            value = float(data[0])
                            if abs(value) > tolerance:
                                type1_unassigned.append({
                                    "entity": entity,
                                    "account": account,
                                    "amount": value,
                                    "issue": "ICP balance with no partner assigned"
                                })
                        except (ValueError, TypeError):
                            continue
        except Exception:
            continue
    
    # ========================================================================
    # TYPE 2: Counterparty Mismatches (A's receivable ≠ B's payable)
    # ========================================================================
    type2_mismatches = []
    type2_matched = []
    
    # Get entities that have ICP members
    entities_with_icp = [e for e in sample_entities if e in entity_to_icp]
    
    # Check pairs (limit to first 10 entities, 3 account pairs for performance)
    # 10 entities = 45 pairs × 3 accounts × 2 calls = 270 API calls max
    entities_to_check = entities_with_icp[:10]
    account_pairs = list(zip(receivable_accounts[:3], payable_accounts[:3]))
    
    for i, entity_a in enumerate(entities_to_check):
        icp_a = entity_to_icp.get(entity_a)
        if not icp_a:
            continue
            
        for entity_b in entities_to_check[i+1:]:
            icp_b = entity_to_icp.get(entity_b)
            if not icp_b:
                continue
            
            # Check receivable/payable pairs (limited to 3 for performance)
            for recv_acct, pay_acct in account_pairs:
                try:
                    # A's receivable from B: Entity=A, ICP=ICP_B, Account=recv
                    grid_a = {
                        "suppressMissingBlocks": True,
                        "pov": {
                            "members": [
                                [year], [scenario], ["FCCS_Periodic"], ["FCCS_Entity Input"],
                                [icp_b], ["FCCS_Managed Data"],
                                ["FCCS_Mvmts_Subtotal"], [entity_a], ["Entity Currency"],
                                ["Total Custom 3"], ["Total Region"], ["Total Venturi Entity"],
                                ["Total Custom 4"]
                            ]
                        },
                        "columns": [{"members": [[period]]}],
                        "rows": [{"members": [[recv_acct]]}]
                    }
                    
                    # B's payable to A: Entity=B, ICP=ICP_A, Account=pay
                    grid_b = {
                        "suppressMissingBlocks": True,
                        "pov": {
                            "members": [
                                [year], [scenario], ["FCCS_Periodic"], ["FCCS_Entity Input"],
                                [icp_a], ["FCCS_Managed Data"],
                                ["FCCS_Mvmts_Subtotal"], [entity_b], ["Entity Currency"],
                                ["Total Custom 3"], ["Total Region"], ["Total Venturi Entity"],
                                ["Total Custom 4"]
                            ]
                        },
                        "columns": [{"members": [[period]]}],
                        "rows": [{"members": [[pay_acct]]}]
                    }
                    
                    result_a = await _client.export_data_slice(_app_name, "Consol", grid_a)
                    result_b = await _client.export_data_slice(_app_name, "Consol", grid_b)
                    
                    # Extract values
                    def extract_val(result):
                        try:
                            if result and "rows" in result and result["rows"]:
                                data = result["rows"][0].get("data", [])
                                if data and data[0]:
                                    return float(data[0])
                        except:
                            pass
                        return 0.0
                    
                    val_a = extract_val(result_a)  # A's receivable from B
                    val_b = extract_val(result_b)  # B's payable to A (should be negative)
                    
                    # They should offset: receivable + payable = 0
                    # (A records +1000 receivable, B records -1000 payable)
                    if val_a != 0 or val_b != 0:
                        net = val_a + val_b
                        if abs(net) > tolerance:
                            type2_mismatches.append({
                                "entity_a": entity_a,
                                "entity_b": entity_b,
                                "account_recv": recv_acct,
                                "account_pay": pay_acct,
                                "a_receivable": val_a,
                                "b_payable": val_b,
                                "mismatch": net,
                                "issue": f"{entity_a} records {val_a:,.2f} receivable, {entity_b} records {val_b:,.2f} payable"
                            })
                        elif val_a != 0:  # Matched
                            type2_matched.append({
                                "entity_a": entity_a,
                                "entity_b": entity_b,
                                "amount": abs(val_a)
                            })
                except Exception:
                    continue
    
    # Sort results
    type1_unassigned.sort(key=lambda x: abs(x["amount"]), reverse=True)
    type2_mismatches.sort(key=lambda x: abs(x["mismatch"]), reverse=True)
    
    return {
        "status": "success",
        "data": {
            "scenario": scenario,
            "year": year,
            "period": period,
            "tolerance": tolerance,
            "entities_checked": len(sample_entities),
            
            # Type 1: Unassigned ICP balances
            "type1_unassigned_balances": {
                "description": "ICP account balances with no partner assigned (ICP=FCCS_No Intercompany)",
                "count": len(type1_unassigned),
                "total": sum(abs(x["amount"]) for x in type1_unassigned),
                "items": type1_unassigned[:20]  # Top 20
            },
            
            # Type 2: Counterparty mismatches  
            "type2_counterparty_mismatches": {
                "description": "A's receivable from B does not match B's payable to A",
                "count": len(type2_mismatches),
                "total": sum(abs(x["mismatch"]) for x in type2_mismatches),
                "matched_count": len(type2_matched),
                "items": type2_mismatches[:20]  # Top 20
            }
        }
    }


async def create_icp_elimination_journal(
    entity_a: str,
    entity_b: str,
    account_debit: str,
    account_credit: str,
    amount: float,
    scenario: str = "Actual",
    year: str = "FY24",
    period: str = "Dec",
    description: Optional[str] = None
) -> Dict[str, Any]:
    """Create an ICP elimination journal entry / Criar lançamento de eliminação ICP.

    Creates a journal entry to eliminate intercompany balances
    between two entities.

    Args:
        entity_a: First entity (debit side).
        entity_b: Second entity (credit side).
        account_debit: Account to debit.
        account_credit: Account to credit.
        amount: Elimination amount (positive).
        scenario: Scenario name.
        year: Fiscal year.
        period: Period.
        description: Journal description.

    Returns:
        dict: Created journal details.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    journal_label = f"ICP_ELIM_{entity_a}_{entity_b}_{timestamp}"
    
    if description is None:
        description = f"ICP elimination between {entity_a} and {entity_b}"
    
    journal_data = {
        "label": journal_label,
        "description": description,
        "scenario": scenario,
        "year": year,
        "period": period,
        "journalType": "Regular",
        "status": "Working",
        "lineItems": [
            {
                "entity": entity_a,
                "account": account_debit,
                "icp": f"ICP_{entity_b}",
                "amount": amount,
            },
            {
                "entity": entity_b,
                "account": account_credit,
                "icp": f"ICP_{entity_a}",
                "amount": -amount,
            }
        ]
    }
    
    return {
        "status": "success",
        "data": {
            "journal_label": journal_label,
            "journal_data": journal_data,
            "action_required": "Use import_journals to create this journal in FCCS",
            "note": "Review line items before importing"
        }
    }


async def get_icp_elimination_summary(
    scenario: str = "Actual",
    year: str = "FY24",
    period: str = "Dec"
) -> Dict[str, Any]:
    """Get summary of ICP eliminations / Obter resumo de eliminações ICP.

    Shows the total eliminations that occurred during consolidation,
    broken down by account type.

    Args:
        scenario: Scenario name.
        year: Fiscal year.
        period: Period.

    Returns:
        dict: Elimination summary by account.
    """
    from fccs_agent.tools.data import smart_retrieve
    
    elimination_accounts = [
        "FCCS_Intercompany Receivables",
        "FCCS_Intercompany Payables",
        "FCCS_Intercompany Revenue",
        "FCCS_Intercompany Expense",
        "FCCS_Intercompany Investment",
        "FCCS_Intercompany Dividend",
    ]
    
    eliminations = {}
    
    for account in elimination_accounts:
        try:
            result = await smart_retrieve(
                account=account,
                entity="FCCS_Total Geography",
                period=period,
                years=year,
                scenario=scenario,
                consolidation="FCCS_Elimination"
            )
            
            # Extract value
            value = 0.0
            data = result.get("data", {})
            if "rows" in data and len(data["rows"]) > 0:
                row = data["rows"][0]
                if "data" in row and len(row["data"]) > 0:
                    try:
                        value = float(row["data"][0])
                    except (ValueError, TypeError):
                        value = 0.0
            
            if value != 0:
                eliminations[account] = value
                
        except Exception:
            continue
    
    return {
        "status": "success",
        "data": {
            "scenario": scenario,
            "year": year,
            "period": period,
            "entity": "FCCS_Total Geography",
            "eliminations": eliminations,
            "total_eliminations": sum(eliminations.values()),
            "account_count": len(eliminations)
        }
    }


# ============================================================================
# TOOL DEFINITIONS
# ============================================================================

TOOL_DEFINITIONS = [
    {
        "name": "get_icp_balances",
        "description": "Get intercompany balances for an entity by partner / Obter saldos intercompanhia",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity": {
                    "type": "string",
                    "description": "Entity to query ICP balances for",
                },
                "account": {
                    "type": "string",
                    "description": "Specific ICP account (optional - shows all if not specified)",
                },
                "scenario": {"type": "string", "description": "Scenario name (default: 'Actual')"},
                "year": {"type": "string", "description": "Fiscal year (default: 'FY24')"},
                "period": {"type": "string", "description": "Period (default: 'Dec')"},
            },
            "required": ["entity"],
        },
    },
    {
        "name": "get_icp_mismatches",
        "description": "Find ICP mismatches between entity pairs - critical for clean consolidation / Encontrar divergências ICP",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scenario": {"type": "string", "description": "Scenario name"},
                "year": {"type": "string", "description": "Fiscal year"},
                "period": {"type": "string", "description": "Period to analyze"},
                "tolerance": {
                    "type": "number",
                    "description": "Mismatch tolerance amount (default: 0.01)",
                },
                "entity_pairs": {
                    "type": "array",
                    "description": "Specific entity pairs to check (optional)",
                    "items": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 2,
                        "maxItems": 2,
                    },
                },
            },
        },
    },
    {
        "name": "create_icp_elimination_journal",
        "description": "Create an ICP elimination journal entry structure / Criar lançamento de eliminação ICP",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_a": {"type": "string", "description": "First entity (debit side)"},
                "entity_b": {"type": "string", "description": "Second entity (credit side)"},
                "account_debit": {"type": "string", "description": "Account to debit"},
                "account_credit": {"type": "string", "description": "Account to credit"},
                "amount": {"type": "number", "description": "Elimination amount (positive)"},
                "scenario": {"type": "string", "description": "Scenario name"},
                "year": {"type": "string", "description": "Fiscal year"},
                "period": {"type": "string", "description": "Period"},
                "description": {"type": "string", "description": "Journal description"},
            },
            "required": ["entity_a", "entity_b", "account_debit", "account_credit", "amount"],
        },
    },
    {
        "name": "get_icp_elimination_summary",
        "description": "Get summary of ICP eliminations from consolidation / Obter resumo de eliminações ICP",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scenario": {"type": "string", "description": "Scenario name"},
                "year": {"type": "string", "description": "Fiscal year"},
                "period": {"type": "string", "description": "Period"},
            },
        },
    },
]
