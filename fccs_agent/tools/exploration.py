"""Exploration tools - OLAP-aware dimension navigation and semantic search.

This module provides intelligent dimension exploration with:
- Hierarchy navigation (drill-down, roll-up, siblings)
- Semantic member search with fuzzy matching
- Contribution analysis
- Smart POV suggestions
"""

from typing import Any, List, Optional

from fccs_agent.intelligence.olap_discovery import (
    get_discovery_service,
    get_semantic_resolver,
    MemberNode,
    MemberMatch,
    DrillPath,
)


async def explore_dimension(
    dimension: str,
    member: Optional[str] = None,
    operation: str = "children",
    search_term: Optional[str] = None,
    depth: int = 1,
    include_metadata: bool = True
) -> dict[str, Any]:
    """Explore a dimension with OLAP-aware operations.

    Operations:
    - children: Get immediate children of member (drill-down)
    - parent: Get parent member (roll-up)
    - siblings: Get members at same level
    - path: Get full path from member to root
    - search: Fuzzy search across dimension
    - info: Get dimension metadata (cardinality, depth, storage types)

    Args:
        dimension: Dimension name (Account, Entity, Movement, Data Source).
        member: Target member for hierarchy operations.
        operation: Operation type (children, parent, siblings, path, search, info).
        search_term: Search term for search operation.
        depth: Depth for children operation (default: 1, -1 for all).
        include_metadata: Include member metadata (alias, level, data storage).

    Returns:
        dict: Operation results with members and metadata.
    """
    discovery = get_discovery_service()
    resolver = get_semantic_resolver()

    # Resolve member if provided (allows fuzzy input)
    resolved_member = None
    if member:
        match = resolver.resolve(member, dimension=dimension, limit=1)
        if match:
            resolved_member = match[0].member_name
        else:
            # Try exact match as fallback
            node = discovery.get_member(dimension, member)
            if node:
                resolved_member = member
            else:
                return {
                    "status": "error",
                    "error": f"Member '{member}' not found in {dimension}",
                    "suggestions": resolver.suggest_corrections(member, dimension, limit=5)
                }

    if operation == "children":
        if not resolved_member:
            # Return root members
            hierarchy = discovery.get_hierarchy(dimension)
            if not hierarchy or not hierarchy.info:
                return {"status": "error", "error": f"Dimension '{dimension}' not found"}

            root_members = hierarchy.info.root_members
            members_data = [
                _member_to_dict(hierarchy.members[m], include_metadata)
                for m in root_members if m in hierarchy.members
            ]
            return {
                "status": "success",
                "data": {
                    "dimension": dimension,
                    "operation": "children",
                    "parent": None,
                    "members": members_data,
                    "count": len(members_data)
                }
            }

        # Get children with specified depth
        children = discovery.get_children(dimension, resolved_member, depth=depth)
        members_data = [_member_to_dict(c, include_metadata) for c in children]

        return {
            "status": "success",
            "data": {
                "dimension": dimension,
                "operation": "children",
                "parent": resolved_member,
                "depth": depth,
                "members": members_data,
                "count": len(members_data)
            }
        }

    elif operation == "parent":
        if not resolved_member:
            return {"status": "error", "error": "Member required for parent operation"}

        path = discovery.get_parent_path(dimension, resolved_member)
        if len(path) < 2:
            return {
                "status": "success",
                "data": {
                    "dimension": dimension,
                    "operation": "parent",
                    "member": resolved_member,
                    "parent": None,
                    "message": "Member is at root level"
                }
            }

        parent_name = path[1]
        parent_node = discovery.get_member(dimension, parent_name)

        return {
            "status": "success",
            "data": {
                "dimension": dimension,
                "operation": "parent",
                "member": resolved_member,
                "parent": _member_to_dict(parent_node, include_metadata) if parent_node else {"name": parent_name}
            }
        }

    elif operation == "siblings":
        if not resolved_member:
            return {"status": "error", "error": "Member required for siblings operation"}

        siblings = discovery.get_siblings(dimension, resolved_member)
        members_data = [_member_to_dict(s, include_metadata) for s in siblings]

        return {
            "status": "success",
            "data": {
                "dimension": dimension,
                "operation": "siblings",
                "member": resolved_member,
                "siblings": members_data,
                "count": len(members_data)
            }
        }

    elif operation == "path":
        if not resolved_member:
            return {"status": "error", "error": "Member required for path operation"}

        path = discovery.get_parent_path(dimension, resolved_member)
        path_data = []
        for i, member_name in enumerate(path):
            node = discovery.get_member(dimension, member_name)
            if node:
                path_data.append({
                    "name": node.name,
                    "level": node.level,
                    "alias": node.alias,
                    "position": i  # 0 = target, last = root
                })

        return {
            "status": "success",
            "data": {
                "dimension": dimension,
                "operation": "path",
                "member": resolved_member,
                "path_to_root": path_data,
                "depth": len(path_data) - 1
            }
        }

    elif operation == "search":
        if not search_term:
            return {"status": "error", "error": "search_term required for search operation"}

        matches = resolver.resolve(search_term, dimension=dimension, limit=20)
        results = [
            {
                "member_name": m.member_name,
                "match_type": m.match_type,
                "confidence": round(m.confidence, 3),
                "matched_term": m.matched_term,
                "alias": m.node.alias if m.node else None,
                "level": m.node.level if m.node else None,
                "data_storage": m.node.data_storage if m.node else None
            }
            for m in matches
        ]

        return {
            "status": "success",
            "data": {
                "dimension": dimension,
                "operation": "search",
                "search_term": search_term,
                "results": results,
                "count": len(results)
            }
        }

    elif operation == "info":
        info = discovery.get_dimension_info(dimension)
        if not info:
            return {"status": "error", "error": f"Dimension '{dimension}' not found"}

        return {
            "status": "success",
            "data": {
                "dimension": dimension,
                "operation": "info",
                "total_members": info.total_members,
                "max_depth": info.max_depth,
                "root_members": info.root_members[:10],  # First 10 roots
                "storage_types": info.storage_types,
                "has_aliases": info.has_aliases,
                "cardinality_class": info.cardinality_class
            }
        }

    else:
        return {
            "status": "error",
            "error": f"Unknown operation: {operation}",
            "valid_operations": ["children", "parent", "siblings", "path", "search", "info"]
        }


async def search_members(
    search_term: str,
    dimension: Optional[str] = None,
    match_types: Optional[List[str]] = None,
    limit: int = 10
) -> dict[str, Any]:
    """Search for members across dimensions with semantic matching.

    Supports:
    - Exact match (confidence: 1.0)
    - Alias match (confidence: 0.95)
    - Fuzzy match using string similarity (confidence: 0.6-0.9)

    Args:
        search_term: User's search input (e.g., "net income", "10100", "cash").
        dimension: Optional dimension constraint (Account, Entity, etc.).
        match_types: Enabled match strategies ["exact", "alias", "fuzzy"].
        limit: Maximum results to return.

    Returns:
        dict: Search results with confidence scores.
    """
    resolver = get_semantic_resolver()

    matches = resolver.resolve(
        search_term,
        dimension=dimension,
        match_types=match_types,
        limit=limit
    )

    results = [
        {
            "member_name": m.member_name,
            "dimension": m.dimension,
            "match_type": m.match_type,
            "confidence": round(m.confidence, 3),
            "matched_term": m.matched_term,
            "alias": m.node.alias if m.node else None,
            "level": m.node.level if m.node else None,
            "data_storage": m.node.data_storage if m.node else None,
            "account_type": m.node.account_type if m.node else None
        }
        for m in matches
    ]

    return {
        "status": "success",
        "data": {
            "search_term": search_term,
            "dimension_filter": dimension,
            "results": results,
            "count": len(results),
            "best_match": results[0] if results else None
        }
    }


async def get_drill_suggestions(
    dimension: str,
    member: str
) -> dict[str, Any]:
    """Get intelligent drill-down/up suggestions for a member.

    Analyzes the member's position in hierarchy and suggests:
    - Drill-down paths (children to explore)
    - Roll-up options (parent aggregations)
    - Sibling comparisons

    Args:
        dimension: Dimension name.
        member: Current member position.

    Returns:
        dict: Drill suggestions with descriptions.
    """
    discovery = get_discovery_service()
    resolver = get_semantic_resolver()

    # Resolve member
    match = resolver.resolve(member, dimension=dimension, limit=1)
    if not match:
        return {
            "status": "error",
            "error": f"Member '{member}' not found in {dimension}",
            "suggestions": resolver.suggest_corrections(member, dimension)
        }

    resolved_member = match[0].member_name
    node = discovery.get_member(dimension, resolved_member)
    if not node:
        return {"status": "error", "error": f"Member node not found: {resolved_member}"}

    suggestions: List[dict] = []

    # Drill-down suggestions
    if node.children:
        child_count = len(node.children)
        child_preview = node.children[:5]
        suggestions.append({
            "direction": "down",
            "description": f"Drill down into {resolved_member} ({child_count} children)",
            "target_members": child_preview,
            "member_count": child_count,
            "is_recommended": child_count <= 10  # Recommend if manageable
        })

    # Roll-up suggestion
    if node.parent:
        parent_node = discovery.get_member(dimension, node.parent)
        if parent_node:
            sibling_count = len(parent_node.children)
            suggestions.append({
                "direction": "up",
                "description": f"Roll up to {node.parent} (aggregates {sibling_count} members)",
                "target_members": [node.parent],
                "member_count": sibling_count,
                "is_recommended": False
            })

    # Sibling comparison suggestion
    siblings = discovery.get_siblings(dimension, resolved_member)
    if siblings:
        sibling_names = [s.name for s in siblings[:5]]
        suggestions.append({
            "direction": "across",
            "description": f"Compare with {len(siblings)} siblings under {node.parent}",
            "target_members": sibling_names,
            "member_count": len(siblings),
            "is_recommended": len(siblings) <= 5
        })

    return {
        "status": "success",
        "data": {
            "dimension": dimension,
            "current_member": resolved_member,
            "current_level": node.level,
            "suggestions": suggestions
        }
    }


async def list_available_dimensions() -> dict[str, Any]:
    """List all available dimensions with their metadata.

    Returns:
        dict: List of dimensions with cardinality and depth info.
    """
    discovery = get_discovery_service()
    dimensions = discovery.list_dimensions()

    dimension_data = []
    for dim in dimensions:
        info = discovery.get_dimension_info(dim)
        if info:
            dimension_data.append({
                "name": dim,
                "total_members": info.total_members,
                "max_depth": info.max_depth,
                "cardinality_class": info.cardinality_class,
                "has_aliases": info.has_aliases,
                "root_count": len(info.root_members)
            })

    return {
        "status": "success",
        "data": {
            "dimensions": dimension_data,
            "count": len(dimension_data)
        }
    }


def _member_to_dict(node: MemberNode, include_metadata: bool = True) -> dict:
    """Convert MemberNode to dictionary."""
    result = {"name": node.name}

    if include_metadata:
        result.update({
            "alias": node.alias,
            "level": node.level,
            "data_storage": node.data_storage,
            "is_calculated": node.is_calculated,
            "children_count": len(node.children),
            "has_children": len(node.children) > 0
        })
        if node.account_type:
            result["account_type"] = node.account_type

    return result


# Tool definitions for MCP
TOOL_DEFINITIONS = [
    {
        "name": "explore_dimension",
        "description": "Explore FCCS dimensions with OLAP-aware operations: drill-down (children), roll-up (parent), siblings, path-to-root, fuzzy search, or dimension info. Supports semantic member matching.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dimension": {
                    "type": "string",
                    "description": "Dimension name: Account, Entity, Movement, or Data Source",
                    "enum": ["Account", "Entity", "Movement", "Data Source"]
                },
                "member": {
                    "type": "string",
                    "description": "Target member (supports fuzzy matching, e.g., 'net income' finds 'FCCS_Net Income')"
                },
                "operation": {
                    "type": "string",
                    "description": "Operation: children (drill-down), parent (roll-up), siblings, path (to root), search, info",
                    "enum": ["children", "parent", "siblings", "path", "search", "info"],
                    "default": "children"
                },
                "search_term": {
                    "type": "string",
                    "description": "Search term for search operation (fuzzy matching supported)"
                },
                "depth": {
                    "type": "integer",
                    "description": "Depth for children operation (default: 1, -1 for all descendants)",
                    "default": 1
                },
                "include_metadata": {
                    "type": "boolean",
                    "description": "Include member metadata (alias, level, data storage)",
                    "default": True
                }
            },
            "required": ["dimension"]
        }
    },
    {
        "name": "search_members",
        "description": "Search for members across dimensions with semantic/fuzzy matching. Finds members by name, alias, or partial match. Returns confidence scores.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "search_term": {
                    "type": "string",
                    "description": "Search input (e.g., 'revenue', 'net income', '4110', 'cash')"
                },
                "dimension": {
                    "type": "string",
                    "description": "Optional dimension filter",
                    "enum": ["Account", "Entity", "Movement", "Data Source"]
                },
                "match_types": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["exact", "alias", "fuzzy"]},
                    "description": "Enabled match strategies (default: all)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results (default: 10)",
                    "default": 10
                }
            },
            "required": ["search_term"]
        }
    },
    {
        "name": "get_drill_suggestions",
        "description": "Get intelligent drill-down/roll-up suggestions for a member. Suggests children to explore, parent aggregations, and sibling comparisons.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dimension": {
                    "type": "string",
                    "description": "Dimension name",
                    "enum": ["Account", "Entity", "Movement", "Data Source"]
                },
                "member": {
                    "type": "string",
                    "description": "Current member position (supports fuzzy matching)"
                }
            },
            "required": ["dimension", "member"]
        }
    },
    {
        "name": "list_available_dimensions",
        "description": "List all available dimensions with metadata (member count, depth, cardinality).",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]
