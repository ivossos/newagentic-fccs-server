"""Local cache for dimension members and other metadata."""

import json
import os
from pathlib import Path
from typing import Any, Optional

# Cache directory in project root
CACHE_DIR = Path(__file__).parent.parent.parent / ".cache"
MEMBERS_CACHE_DIR = CACHE_DIR / "members"


def ensure_cache_dir():
    """Ensure cache directories exist."""
    MEMBERS_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_cache_file_path(app_name: str, dimension_name: str) -> Path:
    """Get cache file path for a dimension's members."""
    ensure_cache_dir()
    # Sanitize names for filename
    safe_app = app_name.replace("/", "_").replace("\\", "_")
    safe_dim = dimension_name.replace("/", "_").replace("\\", "_")
    return MEMBERS_CACHE_DIR / f"{safe_app}_{safe_dim}.json"


def load_members_from_cache(app_name: str, dimension_name: str) -> Optional[dict[str, Any]]:
    """Load dimension members from local cache.
    
    First checks JSON cache file, then falls back to CSV file in project root.
    
    Returns:
        Cached members dict or None if not found.
    """
    # First, try JSON cache file
    cache_file = get_cache_file_path(app_name, dimension_name)
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("items"):
                    return data
        except Exception:
            pass
    
    # Fallback: Check for CSV file in project root (for Entity and Account dimensions)
    if app_name == "Consol":
        csv_file = None
        if dimension_name == "Entity":
            csv_file = cache_file.parent.parent.parent / "Ravi_ExportedMetadata_Entity.csv"
        elif dimension_name == "Account":
            csv_file = cache_file.parent.parent.parent / "Ravi_ExportedMetadata_Account.csv"
        
        if csv_file and csv_file.exists():
            try:
                import csv
                members = []
                encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]
                
                for encoding in encodings:
                    try:
                        with open(csv_file, "r", encoding=encoding) as f:
                            reader = csv.DictReader(f)
                            for row in reader:
                                if dimension_name == "Entity":
                                    member_name = row.get("Entity", "").strip()
                                elif dimension_name == "Account":
                                    member_name = row.get("Account", "").strip()
                                else:
                                    continue
                                
                                parent = row.get("Parent", "").strip()
                                alias = row.get("Alias: Default", "").strip()
                                description = row.get("Description", "").strip()
                                
                                if member_name and member_name != dimension_name:
                                    members.append({
                                        "name": member_name,
                                        "parent": parent if parent else "Root",
                                        "description": description or alias or member_name,
                                        "alias": alias if alias else None
                                    })
                        if members:
                            return {"items": members}
                    except Exception:
                        if encoding == encodings[-1]:
                            raise
                        continue
            except Exception:
                pass
    
    return None


def save_members_to_cache(app_name: str, dimension_name: str, members: dict[str, Any]):
    """Save dimension members to local cache."""
    cache_file = get_cache_file_path(app_name, dimension_name)
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(members, f, indent=2, ensure_ascii=False)
    except Exception as e:
        # Don't fail if cache write fails
        print(f"Warning: Could not write to cache: {e}", file=os.sys.stderr)


def clear_members_cache(app_name: Optional[str] = None, dimension_name: Optional[str] = None):
    """Clear cache for members.
    
    Args:
        app_name: If provided, only clear cache for this app
        dimension_name: If provided, only clear cache for this dimension
    """
    if not MEMBERS_CACHE_DIR.exists():
        return
    
    if app_name and dimension_name:
        # Clear specific file
        cache_file = get_cache_file_path(app_name, dimension_name)
        if cache_file.exists():
            cache_file.unlink()
    elif app_name:
        # Clear all files for this app
        safe_app = app_name.replace("/", "_").replace("\\", "_")
        for cache_file in MEMBERS_CACHE_DIR.glob(f"{safe_app}_*.json"):
            cache_file.unlink()
    else:
        # Clear all cache
        for cache_file in MEMBERS_CACHE_DIR.glob("*.json"):
            cache_file.unlink()


def list_cached_dimensions(app_name: Optional[str] = None) -> list[dict[str, str]]:
    """List all cached dimensions.
    
    Returns:
        List of dicts with 'app_name' and 'dimension_name'
    """
    if not MEMBERS_CACHE_DIR.exists():
        return []
    
    cached = []
    for cache_file in MEMBERS_CACHE_DIR.glob("*.json"):
        # Parse filename: {app_name}_{dimension_name}.json
        name = cache_file.stem
        parts = name.split("_", 1)
        if len(parts) == 2:
            cached_app, cached_dim = parts
            if not app_name or cached_app == app_name:
                cached.append({
                    "app_name": cached_app,
                    "dimension_name": cached_dim,
                    "cache_file": str(cache_file)
                })
    
    return cached

