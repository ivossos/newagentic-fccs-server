"""Data tools - export_data_slice, import_data_slice, smart_retrieve, smart_import, copy_data, clear_data.

Enhanced with:
- DynamicGridBuilder for flexible grid construction
- Semantic member resolution for fuzzy input support
- Pre-validation with correction suggestions
- Data import capabilities (write path)
"""

from typing import Any, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, field

from fccs_agent.client.fccs_client import FccsClient

_client: FccsClient = None
_app_name: str = None

# Lazy import to avoid circular dependencies
_semantic_resolver = None
_discovery_service = None


def _get_resolver():
    """Lazy load semantic resolver."""
    global _semantic_resolver, _discovery_service
    if _semantic_resolver is None:
        try:
            from fccs_agent.intelligence.olap_discovery import (
                get_semantic_resolver,
                get_discovery_service,
            )
            _semantic_resolver = get_semantic_resolver()
            _discovery_service = get_discovery_service()
        except Exception:
            pass
    return _semantic_resolver


def set_client(client: FccsClient):
    global _client
    _client = client


def set_app_name(app_name: str):
    global _app_name
    _app_name = app_name


# ============================================================================
# FCCS Grid Definition Converter - Fixes POV format for Oracle API
# ============================================================================

# FCCS 14-dimension order (required for POV array format)
FCCS_DIMENSION_ORDER = [
    "Years", "Scenario", "View", "Consolidation", "ICP",
    "Data Source", "Movement", "Entity", "Currency",
    "Custom 3", "Region", "Venturi Entity", "Custom 4"
]

# Default values for each dimension
FCCS_DIMENSION_DEFAULTS = {
    "Years": "FY24",
    "Scenario": "Actual",
    "View": "FCCS_Periodic",
    "Consolidation": "FCCS_Entity Input",
    "ICP": "FCCS_No Intercompany",
    "Intercompany": "FCCS_No Intercompany",
    "Data Source": "FCCS_Managed Data",
    "Movement": "FCCS_Mvmts_Subtotal",
    "Entity": "FCCS_Total Geography",
    "Currency": "Entity Currency",
    "Custom 3": "Total Custom 3",
    "Region": "Total Region",
    "Venturi Entity": "Total Venturi Entity",
    "Custom 4": "Total Custom 4",
    "Multi-GAAP": "FCCS_Local GAAP",
    "Period": "Jan",
}

# Dimension name aliases
FCCS_DIMENSION_ALIASES = {
    "Intercompany": "ICP",
    "Multi-GAAP": "View",
}


def _convert_grid_definition(grid_definition: dict) -> dict:
    """
    Convert user-friendly grid_definition to Oracle FCCS API format.
    
    Supports both dictionary-style POV and array format (pass-through).
    """
    if not grid_definition:
        return grid_definition
    
    converted = {"suppressMissingBlocks": grid_definition.get("suppressMissingBlocks", True)}
    
    # ============ Convert POV ============
    pov = grid_definition.get("pov", {})
    
    # Check if already in correct format (array of arrays)
    if isinstance(pov, dict) and "members" in pov:
        converted["pov"] = pov
    elif isinstance(pov, dict):
        # Dictionary format - need to convert to array
        pov_members = []
        for dim_name in FCCS_DIMENSION_ORDER:
            value = pov.get(dim_name)
            # Try aliases
            if value is None:
                for alias, canonical in FCCS_DIMENSION_ALIASES.items():
                    if canonical == dim_name and alias in pov:
                        value = pov[alias]
                        break
            # Use default if not specified
            if value is None:
                value = FCCS_DIMENSION_DEFAULTS.get(dim_name, "")
            # Ensure list format
            pov_members.append([value] if isinstance(value, str) else value)
        converted["pov"] = {"members": pov_members}
    else:
        # Fallback - use all defaults
        pov_members = [[FCCS_DIMENSION_DEFAULTS.get(dim, "")] for dim in FCCS_DIMENSION_ORDER]
        converted["pov"] = {"members": pov_members}
    
    # ============ Convert Columns ============
    columns = grid_definition.get("columns", [])
    if columns:
        converted_cols = []
        for col in columns:
            if isinstance(col, dict):
                members = col.get("members", [])
                if members and isinstance(members[0], str):
                    members = [[m] for m in members]
                converted_cols.append({"members": members})
            else:
                converted_cols.append(col)
        converted["columns"] = converted_cols
    
    # ============ Convert Rows ============
    rows = grid_definition.get("rows", [])
    if rows:
        converted_rows = []
        for row in rows:
            if isinstance(row, dict):
                members = row.get("members", [])
                if members and isinstance(members[0], str):
                    members = [[m] for m in members]
                converted_rows.append({"members": members})
            else:
                converted_rows.append(row)
        converted["rows"] = converted_rows
    
    return converted


@dataclass
class GridDimension:
    """Configuration for a single dimension in the grid."""
    name: str
    member: str
    placement: str = "pov"  # pov, row, column
    validated: bool = False
    original_input: Optional[str] = None
    confidence: float = 1.0
    suggestions: List[str] = field(default_factory=list)


class DynamicGridBuilder:
    """Build FCCS data grids dynamically with member validation.

    Features:
    - Semantic member resolution (fuzzy matching)
    - Pre-validation before API call
    - Correction suggestions for invalid members
    - Flexible dimension placement (POV, rows, columns)
    """

    # Default dimension order for FCCS 14-dimension cube (Consol)
    DEFAULT_DIMENSION_ORDER = [
        "Years", "Scenario", "View", "Consolidation",
        "Intercompany", "Data Source", "Movement", "Entity",
        "Currency", "Custom1", "Custom2", "Custom3", "Custom4"
    ]

    # Default members for each dimension
    DEFAULT_MEMBERS = {
        "Years": "FY24",
        "Scenario": "Actual",
        "View": "FCCS_YTD",
        "Consolidation": "FCCS_Entity Total",
        "Intercompany": "FCCS_Intercompany Top",
        "Data Source": "FCCS_Total Data Source",
        "Movement": "FCCS_Mvmts_Total",
        "Entity": "FCCS_Total Geography",
        "Currency": "Entity Currency",
        "Custom1": "Total Custom 3",
        "Custom2": "Total Region",
        "Custom3": "Total Venturi Entity",
        "Custom4": "Total Custom 4",
        "Account": "FCCS_Net Income",
        "Period": "Jan",
    }

    def __init__(self):
        self.dimensions: Dict[str, GridDimension] = {}
        self.validation_errors: List[str] = []
        self.resolver = _get_resolver()

    def set_dimension(
        self,
        name: str,
        member: str,
        placement: str = "pov",
        validate: bool = True
    ) -> 'DynamicGridBuilder':
        """Set a dimension member.

        Args:
            name: Dimension name (e.g., "Account", "Entity").
            member: Member name (supports fuzzy input).
            placement: Where to place in grid (pov, row, column).
            validate: Whether to validate using semantic resolver.

        Returns:
            Self for method chaining.
        """
        original_input = member
        confidence = 1.0
        suggestions = []
        validated = False

        # Try semantic resolution if available and dimension is Account/Entity
        if validate and self.resolver and name in ["Account", "Entity"]:
            match = self.resolver.resolve(member, dimension=name, limit=1)
            if match and match[0].confidence >= 0.6:
                member = match[0].member_name
                confidence = match[0].confidence
                validated = True
            elif match:
                # Low confidence - include suggestions
                suggestions = [m.member_name for m in self.resolver.resolve(
                    member, dimension=name, limit=5
                )]

        self.dimensions[name] = GridDimension(
            name=name,
            member=member,
            placement=placement,
            validated=validated,
            original_input=original_input,
            confidence=confidence,
            suggestions=suggestions
        )
        return self

    def set_account(self, member: str) -> 'DynamicGridBuilder':
        """Set Account dimension (row by default)."""
        return self.set_dimension("Account", member, "row")

    def set_entity(self, member: str) -> 'DynamicGridBuilder':
        """Set Entity dimension."""
        return self.set_dimension("Entity", member, "pov")

    def set_period(self, member: str) -> 'DynamicGridBuilder':
        """Set Period dimension (column by default)."""
        return self.set_dimension("Period", member, "column", validate=False)

    def set_years(self, member: str) -> 'DynamicGridBuilder':
        """Set Years dimension."""
        return self.set_dimension("Years", member, "pov", validate=False)

    def set_scenario(self, member: str) -> 'DynamicGridBuilder':
        """Set Scenario dimension."""
        return self.set_dimension("Scenario", member, "pov", validate=False)

    def set_consolidation(self, member: str) -> 'DynamicGridBuilder':
        """Set Consolidation dimension."""
        return self.set_dimension("Consolidation", member, "pov", validate=False)

    def set_movement(self, member: str) -> 'DynamicGridBuilder':
        """Set Movement dimension."""
        return self.set_dimension("Movement", member, "pov")

    def get_validation_report(self) -> Dict[str, Any]:
        """Get validation report for all dimensions."""
        report = {
            "valid": True,
            "dimensions": {},
            "warnings": [],
            "suggestions": {}
        }

        for name, dim in self.dimensions.items():
            report["dimensions"][name] = {
                "member": dim.member,
                "original_input": dim.original_input,
                "confidence": dim.confidence,
                "validated": dim.validated
            }

            if dim.confidence < 0.8 and dim.original_input != dim.member:
                report["warnings"].append(
                    f"{name}: '{dim.original_input}' resolved to '{dim.member}' "
                    f"(confidence: {dim.confidence:.0%})"
                )

            if dim.suggestions:
                report["suggestions"][name] = dim.suggestions

            if dim.confidence < 0.6:
                report["valid"] = False

        return report

    def build(self) -> Dict[str, Any]:
        """Build the grid definition.

        Returns:
            Grid definition dict for export_data_slice API.
        """
        # Start with defaults
        pov_members = []
        row_members = []
        column_members = []

        # Build POV in correct dimension order
        for dim_name in self.DEFAULT_DIMENSION_ORDER:
            if dim_name in self.dimensions:
                dim = self.dimensions[dim_name]
                if dim.placement == "pov":
                    pov_members.append([dim.member])
                elif dim.placement == "row":
                    row_members.append([dim.member])
                elif dim.placement == "column":
                    column_members.append([dim.member])
            else:
                # Use default
                default = self.DEFAULT_MEMBERS.get(dim_name)
                if default:
                    pov_members.append([default])

        # Handle Account (typically row)
        if "Account" in self.dimensions:
            dim = self.dimensions["Account"]
            if dim.placement == "row":
                row_members.append([dim.member])
            elif dim.placement == "column":
                column_members.append([dim.member])
            else:
                pov_members.append([dim.member])
        else:
            row_members.append([self.DEFAULT_MEMBERS["Account"]])

        # Handle Period (typically column)
        if "Period" in self.dimensions:
            dim = self.dimensions["Period"]
            if dim.placement == "column":
                column_members.append([dim.member])
            elif dim.placement == "row":
                row_members.append([dim.member])
            else:
                pov_members.append([dim.member])
        else:
            column_members.append([self.DEFAULT_MEMBERS["Period"]])

        grid = {
            "suppressMissingBlocks": True,
            "pov": {"members": pov_members},
            "columns": [{"members": column_members}] if column_members else [],
            "rows": [{"members": row_members}] if row_members else []
        }

        return grid


def _resolve_member(member: str, dimension: str) -> Tuple[str, float, List[str]]:
    """Resolve a member name using semantic matching.

    Args:
        member: Input member name (may be fuzzy).
        dimension: Dimension name for context.

    Returns:
        Tuple of (resolved_member, confidence, suggestions).
    """
    resolver = _get_resolver()
    if not resolver:
        return member, 1.0, []

    if dimension not in ["Account", "Entity", "Movement", "Data Source"]:
        return member, 1.0, []

    matches = resolver.resolve(member, dimension=dimension, limit=5)
    if matches and matches[0].confidence >= 0.6:
        suggestions = [m.member_name for m in matches[1:4]]
        return matches[0].member_name, matches[0].confidence, suggestions

    # Low confidence - return original with suggestions
    suggestions = [m.member_name for m in matches] if matches else []
    return member, 0.0, suggestions


async def export_data_slice(
    grid_definition: dict[str, Any],
    cube_name: str = "Consol"
) -> dict[str, Any]:
    """Export a specific data slice (grid) from the application / Exportar um slice de dados.

    Supports both dictionary-style and array-style POV definitions.
    
    Dictionary-style (user-friendly):
        {"pov": {"Years": "FY24", "Scenario": "Actual", ...}}
    
    Array-style (Oracle API format):
        {"pov": {"members": [["FY24"], ["Actual"], ...]}}

    Args:
        grid_definition: The data grid definition with pov, columns, and rows.
        cube_name: The name of the cube (default: 'Consol').

    Returns:
        dict: The exported data slice with rows and column values.
    """
    # Convert grid definition to Oracle API format
    converted_grid = _convert_grid_definition(grid_definition)
    
    result = await _client.export_data_slice(_app_name, cube_name, converted_grid)
    return {"status": "success", "data": result}


async def smart_retrieve(
    account: str,
    entity: str = "FCCS_Total Geography",
    period: str = "Jan",
    years: str = "FY24",
    scenario: str = "Actual",
    consolidation: str = "FCCS_Entity Total",
    validate_members: bool = True
) -> dict[str, Any]:
    """Smart data retrieval with automatic 14-dimension handling and semantic resolution.

    Supports fuzzy member matching - e.g., "net income" resolves to "FCCS_Net Income".

    Args:
        account: The Account member (e.g., 'FCCS_Net Income', 'net income', '4110').
        entity: The Entity member (default: 'FCCS_Total Geography').
        period: The Period member (default: 'Jan').
        years: The Years member (default: 'FY24').
        scenario: The Scenario member (default: 'Actual').
        consolidation: The Consolidation member (default: 'FCCS_Entity Total').
        validate_members: Whether to validate/resolve members semantically.

    Returns:
        dict: The retrieved data with validation info.
    """
    validation_info = {}
    resolved_account = account
    resolved_entity = entity

    # Semantic resolution for account and entity
    if validate_members:
        acct_resolved, acct_conf, acct_suggestions = _resolve_member(account, "Account")
        resolved_account = acct_resolved
        if acct_conf < 1.0:
            validation_info["account"] = {
                "input": account,
                "resolved": acct_resolved,
                "confidence": acct_conf,
                "suggestions": acct_suggestions
            }

        ent_resolved, ent_conf, ent_suggestions = _resolve_member(entity, "Entity")
        resolved_entity = ent_resolved
        if ent_conf < 1.0:
            validation_info["entity"] = {
                "input": entity,
                "resolved": ent_resolved,
                "confidence": ent_conf,
                "suggestions": ent_suggestions
            }

    # Build grid definition with hardcoded defaults for 14 dimensions
    grid_definition = {
        "suppressMissingBlocks": True,
        "pov": {
            "members": [
                [years], [scenario], ["FCCS_YTD"], [consolidation],
                ["FCCS_Intercompany Top"], ["FCCS_Total Data Source"],
                ["FCCS_Mvmts_Total"], [resolved_entity], ["Entity Currency"],
                ["Total Custom 3"], ["Total Region"], ["Total Venturi Entity"],
                ["Total Custom 4"]
            ]
        },
        "columns": [{"members": [[period]]}],
        "rows": [{"members": [[resolved_account]]}]
    }

    result = await _client.export_data_slice(_app_name, "Consol", grid_definition)

    response = {"status": "success", "data": result}
    if validation_info:
        response["member_resolution"] = validation_info

    return response


async def smart_retrieve_consolidation_breakdown(
    account: str,
    entity: str = "FCCS_Total Geography",
    period: str = "Jan",
    years: str = "FY24",
    scenario: str = "Actual"
) -> dict[str, Any]:
    """Retrieve all Consolidation dimension members for an entity / Recuperar todos os membros da dimensao Consolidation.

    This function retrieves FCCS_Entity Input, FCCS_Entity Consolidation, FCCS_Entity Total,
    FCCS_Proportion, FCCS_Elimination, and FCCS_Contribution for a given entity.

    Args:
        account: The Account member (e.g., 'FCCS_Net Income').
        entity: The Entity member (default: 'FCCS_Total Geography').
        period: The Period member (default: 'Jan').
        years: The Years member (default: 'FY24').
        scenario: The Scenario member (default: 'Actual').

    Returns:
        dict: The retrieved data for all Consolidation members.
    """
    consolidation_members = [
        "FCCS_Entity Input",
        "FCCS_Entity Consolidation",
        "FCCS_Entity Total",
        "FCCS_Proportion",
        "FCCS_Elimination",
        "FCCS_Contribution"
    ]
    
    results = {}
    for consol_member in consolidation_members:
        try:
            grid_definition = {
                "suppressMissingBlocks": True,
                "pov": {
                    "members": [
                        [years], [scenario], ["FCCS_YTD"], [consol_member],
                        ["FCCS_Intercompany Top"], ["FCCS_Total Data Source"],
                        ["FCCS_Mvmts_Total"], [entity], ["Entity Currency"],
                        ["Total Custom 3"], ["Total Region"], ["Total Venturi Entity"],
                        ["Total Custom 4"]
                    ]
                },
                "columns": [{"members": [[period]]}],
                "rows": [{"members": [[account]]}]
            }
            result = await _client.export_data_slice(_app_name, "Consol", grid_definition)
            
            # Extract value from result
            value = 0.0
            if result and "rows" in result and len(result["rows"]) > 0:
                row = result["rows"][0]
                if "data" in row and len(row["data"]) > 0:
                    try:
                        value = float(row["data"][0])
                    except (ValueError, TypeError):
                        value = 0.0
            
            results[consol_member] = value
        except Exception as e:
            results[consol_member] = 0.0
    
    return {
        "status": "success",
        "data": {
            "entity": entity,
            "account": account,
            "period": period,
            "years": years,
            "scenario": scenario,
            "consolidation_breakdown": results,
            "summary": {
                "entity_input": results.get("FCCS_Entity Input", 0.0),
                "entity_consolidation": results.get("FCCS_Entity Consolidation", 0.0),
                "entity_total": results.get("FCCS_Entity Total", 0.0),
                "proportion": results.get("FCCS_Proportion", 0.0),
                "elimination": results.get("FCCS_Elimination", 0.0),
                "contribution": results.get("FCCS_Contribution", 0.0)
            }
        }
    }


async def smart_retrieve_with_movement(
    account: str,
    movement: str,
    entity: str = "FCCS_Total Geography",
    period: str = "Jan",
    years: str = "FY24",
    scenario: str = "Actual",
    consolidation: str = "FCCS_Entity Total"
) -> dict[str, Any]:
    """Smart data retrieval with configurable Movement dimension / Recuperacao inteligente com dimensao Movement customizavel.

    Args:
        account: The Account member (e.g., 'FCCS_Net Income').
        movement: The Movement member (e.g., 'FCCS_Mvmts_Subtotal').
        entity: The Entity member (default: 'FCCS_Total Geography').
        period: The Period member (default: 'Jan').
        years: The Years member (default: 'FY24').
        scenario: The Scenario member (default: 'Actual').
        consolidation: The Consolidation member (default: 'FCCS_Entity Total').

    Returns:
        dict: The retrieved data for the specified dimensions.
    """
    # Build grid definition with hardcoded defaults for 14 dimensions, except Movement
    grid_definition = {
        "suppressMissingBlocks": True,
        "pov": {
            "members": [
                [years], [scenario], ["FCCS_YTD"], [consolidation],
                ["FCCS_Intercompany Top"], ["FCCS_Total Data Source"],
                [movement], [entity], ["Entity Currency"],
                ["Total Custom 3"], ["Total Region"], ["Total Venturi Entity"],
                ["Total Custom 4"]
            ]
        },
        "columns": [{"members": [[period]]}],
        "rows": [{"members": [[account]]}]
    }
    result = await _client.export_data_slice(_app_name, "Consol", grid_definition)
    return {"status": "success", "data": result}


async def copy_data(
    from_scenario: Optional[str] = None,
    to_scenario: Optional[str] = None,
    from_year: Optional[str] = None,
    to_year: Optional[str] = None,
    from_period: Optional[str] = None,
    to_period: Optional[str] = None
) -> dict[str, Any]:
    """Copy data between scenarios, years, or periods / Copiar dados entre cenarios.

    Args:
        from_scenario: Source scenario.
        to_scenario: Target scenario.
        from_year: Source year.
        to_year: Target year.
        from_period: Source period.
        to_period: Target period.

    Returns:
        dict: Job submission result.
    """
    parameters = {}
    if from_scenario:
        parameters["fromScenario"] = from_scenario
    if to_scenario:
        parameters["toScenario"] = to_scenario
    if from_year:
        parameters["fromYear"] = from_year
    if to_year:
        parameters["toYear"] = to_year
    if from_period:
        parameters["fromPeriod"] = from_period
    if to_period:
        parameters["toPeriod"] = to_period

    result = await _client.copy_data(_app_name, parameters)
    return {"status": "success", "data": result}


async def clear_data(
    scenario: Optional[str] = None,
    year: Optional[str] = None,
    period: Optional[str] = None
) -> dict[str, Any]:
    """Clear data for specified scenario, year, and period / Limpar dados.

    Args:
        scenario: Scenario to clear.
        year: Year to clear.
        period: Period to clear.

    Returns:
        dict: Job submission result.
    """
    parameters = {}
    if scenario:
        parameters["scenario"] = scenario
    if year:
        parameters["year"] = year
    if period:
        parameters["period"] = period

    result = await _client.clear_data(_app_name, parameters)
    return {"status": "success", "data": result}


# ============================================================================
# DATA IMPORT FUNCTIONS (NEW - Write Path)
# ============================================================================

async def import_data_slice(
    data_grid: Dict[str, Any],
    cube_name: str = "Consol",
    aggregation_option: str = "REPLACE"
) -> Dict[str, Any]:
    """Import data into a specific slice (grid) of the application / Importar dados para um slice.

    This is the write counterpart to export_data_slice. It allows pushing data
    directly into FCCS cells.

    Args:
        data_grid: The data grid with pov, columns, rows, and cell values.
            Format: {
                "pov": {"members": [["FY24"], ["Actual"], ...]},
                "columns": [{"members": [["Jan"], ["Feb"], ...]}],
                "rows": [{"members": [["Account1"]], "data": [100, 200, ...]}, ...]
            }
        cube_name: The name of the cube (default: 'Consol').
        aggregation_option: How to handle existing data:
            - 'REPLACE': Overwrite existing values (default)
            - 'ADD': Add to existing values
            - 'SUBTRACT': Subtract from existing values

    Returns:
        dict: Import result with status and any validation errors.
    """
    result = await _client.import_data_slice(_app_name, cube_name, data_grid, aggregation_option)
    return {"status": "success", "data": result}


async def smart_import(
    account: str,
    value: float,
    entity: str = "FCCS_Total Geography",
    period: str = "Jan",
    years: str = "FY24",
    scenario: str = "Actual",
    consolidation: str = "FCCS_Entity Input",
    movement: str = "FCCS_Mvmts_Input",
    data_source: str = "FCCS_Managed Data",
    aggregation_option: str = "REPLACE",
    validate_members: bool = True
) -> Dict[str, Any]:
    """Smart data import with automatic 14-dimension handling and semantic resolution.

    This is the write counterpart to smart_retrieve. Allows pushing a single value
    to a specific intersection with sensible defaults for FCCS.

    Args:
        account: The Account member (supports fuzzy matching).
        value: The numeric value to import.
        entity: The Entity member (default: 'FCCS_Total Geography').
        period: The Period member (default: 'Jan').
        years: The Years member (default: 'FY24').
        scenario: The Scenario member (default: 'Actual').
        consolidation: The Consolidation member (default: 'FCCS_Entity Input').
            Note: For data entry, typically use 'FCCS_Entity Input'.
        movement: The Movement member (default: 'FCCS_Mvmts_Input').
            Note: For data entry, typically use 'FCCS_Mvmts_Input' or specific movement.
        data_source: The Data Source member (default: 'FCCS_Managed Data').
        aggregation_option: 'REPLACE', 'ADD', or 'SUBTRACT' (default: 'REPLACE').
        validate_members: Whether to resolve members semantically (default: True).

    Returns:
        dict: Import result with the imported value and any validation messages.
    """
    validation_info = {}
    resolved_account = account
    resolved_entity = entity

    # Semantic resolution for account and entity
    if validate_members:
        acct_resolved, acct_conf, acct_suggestions = _resolve_member(account, "Account")
        resolved_account = acct_resolved
        if acct_conf < 1.0:
            validation_info["account"] = {
                "input": account,
                "resolved": acct_resolved,
                "confidence": acct_conf,
                "suggestions": acct_suggestions
            }

        ent_resolved, ent_conf, ent_suggestions = _resolve_member(entity, "Entity")
        resolved_entity = ent_resolved
        if ent_conf < 1.0:
            validation_info["entity"] = {
                "input": entity,
                "resolved": ent_resolved,
                "confidence": ent_conf,
                "suggestions": ent_suggestions
            }

    # Build grid definition with entry-appropriate defaults
    data_grid = {
        "pov": {
            "members": [
                [years], [scenario], ["FCCS_YTD"], [consolidation],
                ["FCCS_Intercompany Top"], [data_source],
                [movement], [resolved_entity], ["Entity Currency"],
                ["Total Custom 3"], ["Total Region"], ["Total Venturi Entity"],
                ["Total Custom 4"]
            ]
        },
        "columns": [{"members": [[period]]}],
        "rows": [{"members": [[resolved_account]], "data": [value]}]
    }
    
    result = await _client.import_data_slice(_app_name, "Consol", data_grid, aggregation_option)
    
    response = {
        "status": "success",
        "data": {
            "imported": {
                "account": resolved_account,
                "entity": resolved_entity,
                "period": period,
                "years": years,
                "scenario": scenario,
                "value": value
            },
            "result": result
        }
    }
    
    if validation_info:
        response["member_resolution"] = validation_info
    
    return response


async def smart_import_batch(
    data_rows: List[Dict[str, Any]],
    entity: str = "FCCS_Total Geography",
    years: str = "FY24",
    scenario: str = "Actual",
    consolidation: str = "FCCS_Entity Input",
    movement: str = "FCCS_Mvmts_Input",
    aggregation_option: str = "REPLACE"
) -> Dict[str, Any]:
    """Batch import multiple account/period values / Importacao em lote.

    Efficiently imports multiple data points in a single API call.

    Args:
        data_rows: List of data rows, each with format:
            {"account": "4110", "period": "Jan", "value": 1000.0}
            or for multi-period:
            {"account": "4110", "values": {"Jan": 100, "Feb": 200, "Mar": 300}}
        entity: Entity for all rows (default: 'FCCS_Total Geography').
        years: Year for all rows (default: 'FY24').
        scenario: Scenario for all rows (default: 'Actual').
        consolidation: Consolidation member (default: 'FCCS_Entity Input').
        movement: Movement member (default: 'FCCS_Mvmts_Input').
        aggregation_option: 'REPLACE', 'ADD', or 'SUBTRACT'.

    Returns:
        dict: Batch import result with count of imported rows.
    """
    # Collect all periods and accounts
    all_periods: set = set()
    accounts_data: Dict[str, Dict[str, float]] = {}
    
    for row in data_rows:
        account = row.get("account")
        if not account:
            continue
        
        # Resolve account name
        resolved_account, _, _ = _resolve_member(account, "Account")
            
        if "values" in row:
            # Multi-period format
            for period, value in row["values"].items():
                all_periods.add(period)
                if resolved_account not in accounts_data:
                    accounts_data[resolved_account] = {}
                accounts_data[resolved_account][period] = value
        else:
            # Single period format
            period = row.get("period", "Jan")
            value = row.get("value", 0)
            all_periods.add(period)
            if resolved_account not in accounts_data:
                accounts_data[resolved_account] = {}
            accounts_data[resolved_account][period] = value
    
    # Sort periods for consistent ordering
    period_order = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", 
                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "YearTotal"]
    sorted_periods = sorted(all_periods, key=lambda p: period_order.index(p) if p in period_order else 99)
    
    # Build rows with data aligned to period columns
    rows = []
    for account, period_values in accounts_data.items():
        data = [period_values.get(p, 0) for p in sorted_periods]
        rows.append({"members": [[account]], "data": data})
    
    # Resolve entity
    resolved_entity, _, _ = _resolve_member(entity, "Entity")
    
    # Build grid
    data_grid = {
        "pov": {
            "members": [
                [years], [scenario], ["FCCS_YTD"], [consolidation],
                ["FCCS_Intercompany Top"], ["FCCS_Managed Data"],
                [movement], [resolved_entity], ["Entity Currency"],
                ["Total Custom 3"], ["Total Region"], ["Total Venturi Entity"],
                ["Total Custom 4"]
            ]
        },
        "columns": [{"members": [[p] for p in sorted_periods]}],
        "rows": rows
    }
    
    result = await _client.import_data_slice(_app_name, "Consol", data_grid, aggregation_option)
    
    return {
        "status": "success",
        "data": {
            "rows_imported": len(rows),
            "periods": sorted_periods,
            "accounts": list(accounts_data.keys()),
            "result": result
        }
    }


TOOL_DEFINITIONS = [
    {
        "name": "export_data_slice",
        "description": "Export a specific data slice (grid) from the application / Exportar um slice de dados",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cube_name": {
                    "type": "string",
                    "description": "The name of the cube (default: 'Consol')",
                },
                "grid_definition": {
                    "type": "object",
                    "description": "The data grid definition with pov, columns, and rows",
                },
            },
            "required": ["grid_definition"],
        },
    },
    {
        "name": "smart_retrieve",
        "description": "Smart data retrieval with semantic member resolution. Supports fuzzy matching (e.g., 'net income' -> 'FCCS_Net Income', 'revenue' -> 'FCCS_Total Revenue'). Auto-handles 14-dimension FCCS cube.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account": {
                    "type": "string",
                    "description": "Account member - supports fuzzy matching (e.g., 'net income', 'revenue', '4110', 'FCCS_Net Income')",
                },
                "entity": {
                    "type": "string",
                    "description": "Entity member (default: 'FCCS_Total Geography') - supports fuzzy matching",
                },
                "period": {
                    "type": "string",
                    "description": "Period member (default: 'Jan')",
                },
                "years": {
                    "type": "string",
                    "description": "Years member (default: 'FY24')",
                },
                "scenario": {
                    "type": "string",
                    "description": "Scenario member (default: 'Actual')",
                },
                "consolidation": {
                    "type": "string",
                    "description": "Consolidation member (default: 'FCCS_Entity Total'). Valid: 'FCCS_Entity Input', 'FCCS_Entity Consolidation', 'FCCS_Entity Total', 'FCCS_Proportion', 'FCCS_Elimination', 'FCCS_Contribution'.",
                },
                "validate_members": {
                    "type": "boolean",
                    "description": "Enable semantic member resolution (default: true)",
                    "default": True
                },
            },
            "required": ["account"],
        },
    },
    {
        "name": "smart_retrieve_consolidation_breakdown",
        "description": "Retrieve all Consolidation dimension members (Entity Input, Entity Consolidation, Entity Total, Proportion, Elimination, Contribution) for an entity / Recuperar todos os membros da dimensao Consolidation para uma entidade",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account": {
                    "type": "string",
                    "description": "The Account member (e.g., 'FCCS_Net Income')",
                },
                "entity": {
                    "type": "string",
                    "description": "The Entity member (default: 'FCCS_Total Geography')",
                },
                "period": {
                    "type": "string",
                    "description": "The Period member (default: 'Jan')",
                },
                "years": {
                    "type": "string",
                    "description": "The Years member (default: 'FY24')",
                },
                "scenario": {
                    "type": "string",
                    "description": "The Scenario member (default: 'Actual')",
                },
            },
            "required": ["account"],
        },
    },
    {
        "name": "smart_retrieve_with_movement",
        "description": "Smart data retrieval with configurable Movement dimension / Recuperacao inteligente com dimensao Movement customizavel",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account": {
                    "type": "string",
                    "description": "The Account member (e.g., 'FCCS_Net Income')",
                },
                "movement": {
                    "type": "string",
                    "description": "The Movement member (e.g., 'FCCS_Mvmts_Subtotal')",
                },
                "entity": {
                    "type": "string",
                    "description": "The Entity member (default: 'FCCS_Total Geography')",
                },
                "period": {
                    "type": "string",
                    "description": "The Period member (default: 'Jan')",
                },
                "years": {
                    "type": "string",
                    "description": "The Years member (default: 'FY24')",
                },
                "scenario": {
                    "type": "string",
                    "description": "The Scenario member (default: 'Actual')",
                },
                "consolidation": {
                    "type": "string",
                    "description": "The Consolidation member (default: 'FCCS_Entity Total')",
                },
            },
            "required": ["account", "movement"],
        },
    },
    {
        "name": "copy_data",
        "description": "Copy data between scenarios, years, or periods / Copiar dados",
        "inputSchema": {
            "type": "object",
            "properties": {
                "from_scenario": {"type": "string", "description": "Source scenario"},
                "to_scenario": {"type": "string", "description": "Target scenario"},
                "from_year": {"type": "string", "description": "Source year"},
                "to_year": {"type": "string", "description": "Target year"},
                "from_period": {"type": "string", "description": "Source period"},
                "to_period": {"type": "string", "description": "Target period"},
            },
        },
    },
    {
        "name": "clear_data",
        "description": "Clear data for specified scenario, year, and period / Limpar dados",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scenario": {"type": "string", "description": "Scenario to clear"},
                "year": {"type": "string", "description": "Year to clear"},
                "period": {"type": "string", "description": "Period to clear"},
            },
        },
    },
    {
        "name": "import_data_slice",
        "description": "Import data into a specific slice (grid) of the application - the write counterpart to export_data_slice / Importar dados para um slice",
        "inputSchema": {
            "type": "object",
            "properties": {
                "data_grid": {
                    "type": "object",
                    "description": "The data grid with pov, columns, rows, and cell values. Rows must include 'data' array with values.",
                },
                "cube_name": {
                    "type": "string",
                    "description": "The name of the cube (default: 'Consol')",
                },
                "aggregation_option": {
                    "type": "string",
                    "enum": ["REPLACE", "ADD", "SUBTRACT"],
                    "description": "How to handle existing data: REPLACE (overwrite), ADD, or SUBTRACT",
                },
            },
            "required": ["data_grid"],
        },
    },
    {
        "name": "smart_import",
        "description": "Smart data import with automatic 14-dimension handling and semantic resolution - write counterpart to smart_retrieve / Importacao inteligente de dados",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account": {
                    "type": "string",
                    "description": "The Account member (supports fuzzy matching like smart_retrieve)",
                },
                "value": {
                    "type": "number",
                    "description": "The numeric value to import",
                },
                "entity": {
                    "type": "string",
                    "description": "The Entity member (default: 'FCCS_Total Geography')",
                },
                "period": {
                    "type": "string",
                    "description": "The Period member (default: 'Jan')",
                },
                "years": {
                    "type": "string",
                    "description": "The Years member (default: 'FY24')",
                },
                "scenario": {
                    "type": "string",
                    "description": "The Scenario member (default: 'Actual')",
                },
                "consolidation": {
                    "type": "string",
                    "description": "The Consolidation member (default: 'FCCS_Entity Input' for data entry)",
                },
                "movement": {
                    "type": "string",
                    "description": "The Movement member (default: 'FCCS_Mvmts_Input')",
                },
                "data_source": {
                    "type": "string",
                    "description": "The Data Source member (default: 'FCCS_Managed Data')",
                },
                "aggregation_option": {
                    "type": "string",
                    "enum": ["REPLACE", "ADD", "SUBTRACT"],
                    "description": "How to handle existing data (default: 'REPLACE')",
                },
                "validate_members": {
                    "type": "boolean",
                    "description": "Enable semantic member resolution (default: true)",
                },
            },
            "required": ["account", "value"],
        },
    },
    {
        "name": "smart_import_batch",
        "description": "Batch import multiple account/period values in a single API call / Importacao em lote",
        "inputSchema": {
            "type": "object",
            "properties": {
                "data_rows": {
                    "type": "array",
                    "description": "List of data rows: [{account, period, value}] or [{account, values: {Jan: 100, Feb: 200}}]",
                    "items": {
                        "type": "object",
                        "properties": {
                            "account": {"type": "string"},
                            "period": {"type": "string"},
                            "value": {"type": "number"},
                            "values": {"type": "object"},
                        },
                        "required": ["account"],
                    },
                },
                "entity": {
                    "type": "string",
                    "description": "Entity for all rows (default: 'FCCS_Total Geography')",
                },
                "years": {
                    "type": "string",
                    "description": "Year for all rows (default: 'FY24')",
                },
                "scenario": {
                    "type": "string",
                    "description": "Scenario for all rows (default: 'Actual')",
                },
                "consolidation": {
                    "type": "string",
                    "description": "Consolidation member (default: 'FCCS_Entity Input')",
                },
                "movement": {
                    "type": "string",
                    "description": "Movement member (default: 'FCCS_Mvmts_Input')",
                },
                "aggregation_option": {
                    "type": "string",
                    "enum": ["REPLACE", "ADD", "SUBTRACT"],
                    "description": "How to handle existing data (default: 'REPLACE')",
                },
            },
            "required": ["data_rows"],
        },
    },
]
