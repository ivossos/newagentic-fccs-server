"""Local Data tools - Querying cached metadata and local financial data."""

from typing import Any, Optional
import json
from fccs_agent.services.cache_service import get_cache_service
from sqlalchemy import text

async def query_local_metadata(
    dimension: Optional[str] = None,
    member_filter: Optional[str] = None,
    property_filter: Optional[str] = None
) -> dict[str, Any]:
    """Query the local metadata cache using SQLite.
    
    Args:
        dimension: Optional dimension name to filter by.
        member_filter: SQL LIKE pattern for member name (e.g., 'FCCS_%').
        property_filter: Optional JSON property filter (not implemented in this simplified version).
        
    Returns:
        dict: List of matching members and their properties.
    """
    cache = get_cache_service()
    if not cache:
        return {"status": "error", "error": "Cache service not initialized"}
        
    try:
        results = []
        with cache.Session() as session:
            from fccs_agent.services.cache_service import MetadataCache
            query = session.query(MetadataCache)
            
            if dimension:
                query = query.filter(MetadataCache.dimension == dimension)
            if member_filter:
                query = query.filter(MetadataCache.member.like(member_filter))
                
            items = query.limit(100).all()
            for item in items:
                results.append({
                    "dimension": item.dimension,
                    "member": item.member,
                    "properties": json.loads(item.properties)
                })
                
        return {
            "status": "success",
            "count": len(results),
            "data": results,
            "source": "local_sqlite"
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

TOOL_DEFINITIONS = [
    {
        "name": "query_local_metadata",
        "description": "Query the local metadata cache for dimension members / Consultar cache local de metadados",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dimension": {
                    "type": "string",
                    "description": "Dimension name (e.g., Account, Entity)",
                },
                "member_filter": {
                    "type": "string",
                    "description": "SQL LIKE pattern for member name (e.g., 'FCCS_Net%')",
                },
            },
        },
    },
]

