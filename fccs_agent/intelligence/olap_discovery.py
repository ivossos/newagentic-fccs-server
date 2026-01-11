"""OLAP Discovery Service - Intelligent multidimensional data discovery.

This module provides OLAP-aware capabilities:
- Hierarchy indexing and navigation
- Semantic member resolution with fuzzy matching
- Drill-down/roll-up intelligence
- Smart POV management
"""

from __future__ import annotations

import csv
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from difflib import SequenceMatcher
from functools import lru_cache

# Data directory path
DATA_DIR = Path(__file__).parent.parent.parent / "data"


@dataclass
class MemberNode:
    """Single member with full hierarchy context."""
    name: str
    parent: Optional[str] = None
    children: List[str] = field(default_factory=list)
    level: int = 0
    alias: Optional[str] = None
    uda: List[str] = field(default_factory=list)
    data_storage: str = "store"  # store, dynamic_calc, never_share, label_only
    is_calculated: bool = False
    account_type: Optional[str] = None  # asset, liability, equity, revenue, expense
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DimensionInfo:
    """Metadata about a dimension."""
    name: str
    total_members: int = 0
    max_depth: int = 0
    root_members: List[str] = field(default_factory=list)
    storage_types: Dict[str, int] = field(default_factory=dict)
    has_aliases: bool = False
    has_uda: bool = False
    cardinality_class: str = "low"  # low (<100), medium (<1000), high (>=1000)


@dataclass
class HierarchyIndex:
    """Indexed hierarchy for fast traversal."""
    dimension: str
    members: Dict[str, MemberNode] = field(default_factory=dict)
    by_level: Dict[int, List[str]] = field(default_factory=dict)
    by_parent: Dict[str, List[str]] = field(default_factory=dict)
    alias_index: Dict[str, str] = field(default_factory=dict)  # lowercase alias -> member_name
    uda_index: Dict[str, List[str]] = field(default_factory=dict)  # uda -> [member_names]
    info: Optional[DimensionInfo] = None


@dataclass
class MemberMatch:
    """Result of semantic member search."""
    member_name: str
    dimension: str
    match_type: str  # exact, alias, fuzzy, uda
    confidence: float  # 0.0 - 1.0
    matched_term: str  # What was matched against
    node: Optional[MemberNode] = None
    alternatives: List[str] = field(default_factory=list)


@dataclass
class DrillPath:
    """Suggested drill operation."""
    direction: str  # down, up, across
    dimension: str
    from_member: str
    to_members: List[str]
    description: str
    member_count: int = 0
    is_recommended: bool = False


class OLAPDiscoveryService:
    """Core OLAP discovery service with hierarchy management."""

    def __init__(self):
        self._hierarchies: Dict[str, HierarchyIndex] = {}
        self._loaded = False

    def load_all_hierarchies(self) -> None:
        """Load all available dimension hierarchies from CSV files."""
        csv_mappings = {
            "Account": "Ravi_ExportedMetadata_Account.csv",
            "Entity": "Ravi_ExportedMetadata_Entity.csv",
            "Movement": "Ravi_ExportedMetadata_Movement.csv",
            "Data Source": "Ravi_ExportedMetadata_Data Source.csv",
        }

        for dimension, filename in csv_mappings.items():
            filepath = DATA_DIR / filename
            if filepath.exists():
                try:
                    self._hierarchies[dimension] = self._parse_csv_hierarchy(filepath, dimension)
                except Exception as e:
                    print(f"Warning: Failed to load {dimension} hierarchy: {e}", file=sys.stderr)

        self._loaded = True

    def _parse_csv_hierarchy(self, filepath: Path, dimension: str) -> HierarchyIndex:
        """Parse a CSV metadata file into a HierarchyIndex."""
        index = HierarchyIndex(dimension=dimension)

        # Read CSV with BOM handling
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)

            # Clean column names (remove leading/trailing spaces)
            if reader.fieldnames:
                reader.fieldnames = [name.strip() for name in reader.fieldnames]

            for row in reader:
                # Get member name (first column varies by dimension)
                member_name = row.get(dimension, row.get(list(row.keys())[0], '')).strip()
                if not member_name:
                    continue

                # Parse parent
                parent = row.get('Parent', '').strip() or None
                if parent == member_name:
                    parent = None

                # Parse alias
                alias = row.get('Alias: Default', '').strip() or None

                # Parse data storage
                data_storage = row.get('Data Storage', 'store').strip().lower().replace(' ', '_')
                if not data_storage:
                    data_storage = 'store'

                # Parse account type (for Account dimension)
                account_type = row.get('Account Type', '').strip().lower() or None

                # Create member node
                node = MemberNode(
                    name=member_name,
                    parent=parent,
                    alias=alias,
                    data_storage=data_storage,
                    is_calculated=data_storage == 'dynamic_calc',
                    account_type=account_type,
                    properties={k.strip(): v.strip() for k, v in row.items() if v and v.strip()}
                )

                index.members[member_name] = node

                # Build alias index
                if alias:
                    index.alias_index[alias.lower()] = member_name
                    # Also index partial alias (e.g., "10100 - Cash" -> index "cash")
                    if ' - ' in alias:
                        alias_suffix = alias.split(' - ', 1)[1].lower()
                        index.alias_index[alias_suffix] = member_name

        # Build parent-child relationships and levels
        self._build_relationships(index)

        # Build dimension info
        index.info = self._build_dimension_info(index)

        return index

    def _build_relationships(self, index: HierarchyIndex) -> None:
        """Build parent-child relationships and calculate levels."""
        # Find children for each parent
        for name, node in index.members.items():
            if node.parent:
                if node.parent not in index.by_parent:
                    index.by_parent[node.parent] = []
                index.by_parent[node.parent].append(name)

                # Update parent's children list
                if node.parent in index.members:
                    index.members[node.parent].children.append(name)

        # Calculate levels (BFS from roots)
        roots = [name for name, node in index.members.items() if not node.parent or node.parent not in index.members]

        for root in roots:
            self._calculate_levels(index, root, 0)

        # Build by_level index
        for name, node in index.members.items():
            if node.level not in index.by_level:
                index.by_level[node.level] = []
            index.by_level[node.level].append(name)

    def _calculate_levels(self, index: HierarchyIndex, member: str, level: int) -> None:
        """Recursively calculate levels from a member."""
        if member not in index.members:
            return

        index.members[member].level = level

        for child in index.members[member].children:
            self._calculate_levels(index, child, level + 1)

    def _build_dimension_info(self, index: HierarchyIndex) -> DimensionInfo:
        """Build dimension metadata summary."""
        storage_counts: Dict[str, int] = {}
        max_depth = 0
        alias_count = 0

        for node in index.members.values():
            # Count storage types
            storage_counts[node.data_storage] = storage_counts.get(node.data_storage, 0) + 1

            # Track max depth
            if node.level > max_depth:
                max_depth = node.level

            # Count aliases
            if node.alias:
                alias_count += 1

        total = len(index.members)
        cardinality = "low" if total < 100 else ("medium" if total < 1000 else "high")

        roots = [name for name, node in index.members.items() if not node.parent or node.parent not in index.members]

        return DimensionInfo(
            name=index.dimension,
            total_members=total,
            max_depth=max_depth,
            root_members=roots,
            storage_types=storage_counts,
            has_aliases=alias_count > 0,
            has_uda=len(index.uda_index) > 0,
            cardinality_class=cardinality
        )

    def get_hierarchy(self, dimension: str) -> Optional[HierarchyIndex]:
        """Get hierarchy index for a dimension."""
        if not self._loaded:
            self.load_all_hierarchies()
        return self._hierarchies.get(dimension)

    def get_member(self, dimension: str, member_name: str) -> Optional[MemberNode]:
        """Get a specific member node."""
        hierarchy = self.get_hierarchy(dimension)
        if hierarchy:
            return hierarchy.members.get(member_name)
        return None

    def get_children(self, dimension: str, member: str, depth: int = 1) -> List[MemberNode]:
        """Get children of a member up to specified depth."""
        hierarchy = self.get_hierarchy(dimension)
        if not hierarchy or member not in hierarchy.members:
            return []

        result = []
        self._collect_children(hierarchy, member, depth, result)
        return result

    def _collect_children(self, hierarchy: HierarchyIndex, member: str, depth: int, result: List[MemberNode]) -> None:
        """Recursively collect children."""
        if depth <= 0:
            return

        node = hierarchy.members.get(member)
        if not node:
            return

        for child_name in node.children:
            child_node = hierarchy.members.get(child_name)
            if child_node:
                result.append(child_node)
                self._collect_children(hierarchy, child_name, depth - 1, result)

    def get_parent_path(self, dimension: str, member: str) -> List[str]:
        """Get the path from member to root."""
        hierarchy = self.get_hierarchy(dimension)
        if not hierarchy or member not in hierarchy.members:
            return []

        path = []
        current = member
        visited = set()

        while current and current not in visited:
            visited.add(current)
            path.append(current)
            node = hierarchy.members.get(current)
            if node and node.parent and node.parent in hierarchy.members:
                current = node.parent
            else:
                break

        return path

    def get_siblings(self, dimension: str, member: str) -> List[MemberNode]:
        """Get siblings of a member (same parent)."""
        hierarchy = self.get_hierarchy(dimension)
        if not hierarchy or member not in hierarchy.members:
            return []

        node = hierarchy.members.get(member)
        if not node or not node.parent:
            return []

        parent_node = hierarchy.members.get(node.parent)
        if not parent_node:
            return []

        return [
            hierarchy.members[sibling]
            for sibling in parent_node.children
            if sibling != member and sibling in hierarchy.members
        ]

    def get_dimension_info(self, dimension: str) -> Optional[DimensionInfo]:
        """Get dimension metadata."""
        hierarchy = self.get_hierarchy(dimension)
        return hierarchy.info if hierarchy else None

    def list_dimensions(self) -> List[str]:
        """List all loaded dimensions."""
        if not self._loaded:
            self.load_all_hierarchies()
        return list(self._hierarchies.keys())


class SemanticMemberResolver:
    """Resolve member names with fuzzy matching and alias support."""

    def __init__(self, discovery_service: OLAPDiscoveryService):
        self.discovery = discovery_service

    def resolve(
        self,
        search_term: str,
        dimension: Optional[str] = None,
        match_types: Optional[List[str]] = None,
        limit: int = 10
    ) -> List[MemberMatch]:
        """
        Resolve a search term to member(s).

        Args:
            search_term: User's input (e.g., "net income", "10100", "cash")
            dimension: Optional dimension constraint
            match_types: Enabled match strategies ["exact", "alias", "fuzzy"]
            limit: Maximum results to return

        Returns:
            List of MemberMatch ordered by confidence
        """
        if match_types is None:
            match_types = ["exact", "alias", "fuzzy"]

        results: List[MemberMatch] = []
        search_lower = search_term.lower().strip()
        search_normalized = self._normalize_member_name(search_term)

        dimensions_to_search = [dimension] if dimension else self.discovery.list_dimensions()

        for dim in dimensions_to_search:
            hierarchy = self.discovery.get_hierarchy(dim)
            if not hierarchy:
                continue

            # Exact match
            if "exact" in match_types:
                results.extend(self._exact_match(hierarchy, search_term, search_normalized))

            # Alias match
            if "alias" in match_types:
                results.extend(self._alias_match(hierarchy, search_lower))

            # Fuzzy match
            if "fuzzy" in match_types:
                results.extend(self._fuzzy_match(hierarchy, search_lower, search_normalized))

        # Sort by confidence and deduplicate
        results = self._deduplicate_results(results)
        results.sort(key=lambda x: x.confidence, reverse=True)

        return results[:limit]

    def _normalize_member_name(self, name: str) -> str:
        """Normalize member name for matching (spaces to underscores, FCCS prefix)."""
        normalized = name.strip()
        normalized = re.sub(r'\s+', '_', normalized)
        return normalized

    def _exact_match(self, hierarchy: HierarchyIndex, search: str, normalized: str) -> List[MemberMatch]:
        """Find exact matches."""
        results = []

        # Direct match
        if search in hierarchy.members:
            node = hierarchy.members[search]
            results.append(MemberMatch(
                member_name=search,
                dimension=hierarchy.dimension,
                match_type="exact",
                confidence=1.0,
                matched_term=search,
                node=node
            ))

        # Normalized match
        if normalized in hierarchy.members and normalized != search:
            node = hierarchy.members[normalized]
            results.append(MemberMatch(
                member_name=normalized,
                dimension=hierarchy.dimension,
                match_type="exact",
                confidence=1.0,
                matched_term=normalized,
                node=node
            ))

        # Case-insensitive match
        search_lower = search.lower()
        for name, node in hierarchy.members.items():
            if name.lower() == search_lower and name not in [search, normalized]:
                results.append(MemberMatch(
                    member_name=name,
                    dimension=hierarchy.dimension,
                    match_type="exact",
                    confidence=0.98,
                    matched_term=name,
                    node=node
                ))

        return results

    def _alias_match(self, hierarchy: HierarchyIndex, search_lower: str) -> List[MemberMatch]:
        """Find matches via alias."""
        results = []

        # Direct alias lookup
        if search_lower in hierarchy.alias_index:
            member_name = hierarchy.alias_index[search_lower]
            node = hierarchy.members.get(member_name)
            if node:
                results.append(MemberMatch(
                    member_name=member_name,
                    dimension=hierarchy.dimension,
                    match_type="alias",
                    confidence=0.95,
                    matched_term=node.alias or search_lower,
                    node=node
                ))

        # Partial alias match
        for alias, member_name in hierarchy.alias_index.items():
            if search_lower in alias or alias in search_lower:
                if alias != search_lower:  # Already handled above
                    node = hierarchy.members.get(member_name)
                    if node:
                        # Calculate confidence based on match quality
                        confidence = 0.85 if search_lower in alias else 0.75
                        results.append(MemberMatch(
                            member_name=member_name,
                            dimension=hierarchy.dimension,
                            match_type="alias",
                            confidence=confidence,
                            matched_term=node.alias or alias,
                            node=node
                        ))

        return results

    def _fuzzy_match(self, hierarchy: HierarchyIndex, search_lower: str, normalized: str) -> List[MemberMatch]:
        """Find fuzzy matches using similarity scoring."""
        results = []

        for name, node in hierarchy.members.items():
            name_lower = name.lower()

            # Skip if already matched exactly
            if name_lower == search_lower:
                continue

            # Calculate similarity
            similarity = self._calculate_similarity(search_lower, name_lower)

            # Also check against alias
            alias_similarity = 0.0
            if node.alias:
                alias_similarity = self._calculate_similarity(search_lower, node.alias.lower())

            best_similarity = max(similarity, alias_similarity)

            # Threshold for fuzzy matches
            if best_similarity >= 0.6:
                matched_term = node.alias if alias_similarity > similarity else name
                results.append(MemberMatch(
                    member_name=name,
                    dimension=hierarchy.dimension,
                    match_type="fuzzy",
                    confidence=best_similarity * 0.9,  # Scale down fuzzy confidence
                    matched_term=matched_term,
                    node=node
                ))

        return results

    def _calculate_similarity(self, s1: str, s2: str) -> float:
        """Calculate string similarity using SequenceMatcher."""
        # Direct ratio
        ratio = SequenceMatcher(None, s1, s2).ratio()

        # Boost for prefix match
        if s2.startswith(s1) or s1.startswith(s2):
            ratio = min(1.0, ratio + 0.2)

        # Boost for word containment
        if s1 in s2 or s2 in s1:
            ratio = min(1.0, ratio + 0.15)

        return ratio

    def _deduplicate_results(self, results: List[MemberMatch]) -> List[MemberMatch]:
        """Remove duplicate matches, keeping highest confidence."""
        seen: Dict[Tuple[str, str], MemberMatch] = {}

        for match in results:
            key = (match.dimension, match.member_name)
            if key not in seen or match.confidence > seen[key].confidence:
                seen[key] = match

        return list(seen.values())

    def suggest_corrections(self, invalid_member: str, dimension: str, limit: int = 5) -> List[str]:
        """Suggest corrections for an invalid member name."""
        matches = self.resolve(invalid_member, dimension=dimension, match_types=["fuzzy"], limit=limit)
        return [m.member_name for m in matches]

    def resolve_account(self, term: str) -> Optional[MemberMatch]:
        """Specialized account resolution."""
        matches = self.resolve(term, dimension="Account", limit=1)
        return matches[0] if matches else None

    def resolve_entity(self, term: str) -> Optional[MemberMatch]:
        """Specialized entity resolution."""
        matches = self.resolve(term, dimension="Entity", limit=1)
        return matches[0] if matches else None


# Global singleton instance
_discovery_service: Optional[OLAPDiscoveryService] = None
_resolver: Optional[SemanticMemberResolver] = None


def get_discovery_service() -> OLAPDiscoveryService:
    """Get or create the global OLAP discovery service."""
    global _discovery_service
    if _discovery_service is None:
        _discovery_service = OLAPDiscoveryService()
        _discovery_service.load_all_hierarchies()
    return _discovery_service


def get_semantic_resolver() -> SemanticMemberResolver:
    """Get or create the global semantic resolver."""
    global _resolver
    if _resolver is None:
        _resolver = SemanticMemberResolver(get_discovery_service())
    return _resolver
