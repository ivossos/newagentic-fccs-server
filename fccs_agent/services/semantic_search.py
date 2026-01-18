"""Semantic Search Service - Embedding-based member resolution for EPM dimensions.

Enables natural language queries like "show revenue" to resolve to correct account members
by using vector embeddings and cosine similarity search.

Supports:
- Local embeddings via sentence-transformers (default, no API costs)
- Optional OpenAI embeddings for higher quality
- SQLite-based vector storage (no external dependencies)
- Batch embedding generation for dimension metadata
"""

import csv
import hashlib
import json
import math
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional, List, Dict, Tuple

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Text, Index,
    create_engine, func
)
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


@dataclass
class SearchResult:
    """Result from semantic search."""
    dimension: str
    member_name: str
    alias: str
    score: float
    properties: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dimension": self.dimension,
            "member_name": self.member_name,
            "alias": self.alias,
            "score": round(self.score, 4),
            "properties": self.properties
        }


class MemberEmbedding(Base):
    """Stores embeddings for dimension members."""
    __tablename__ = "member_embeddings"

    id = Column(Integer, primary_key=True)
    dimension = Column(String(100), nullable=False, index=True)
    member_name = Column(String(255), nullable=False, index=True)
    alias = Column(String(255))
    search_text = Column(Text)  # Combined text used for embedding
    embedding = Column(Text)  # JSON array of floats
    embedding_model = Column(String(50))  # Model used for embedding
    properties = Column(Text)  # JSON of additional member properties
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('ix_member_dim_name', 'dimension', 'member_name', unique=True),
    )


class SemanticSearchConfig(Base):
    """Stores configuration for semantic search."""
    __tablename__ = "semantic_search_config"

    key = Column(String(100), primary_key=True)
    value = Column(Text)
    updated_at = Column(DateTime, default=datetime.utcnow)


class LocalEmbedder:
    """Local embedding generator using sentence-transformers.

    Falls back to simple TF-IDF-like approach if sentence-transformers unavailable.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.model = None
        self._initialized = False
        self._use_simple = False
        self._vocab: Dict[str, int] = {}

    def _initialize(self):
        """Lazy initialization of the embedding model."""
        if self._initialized:
            return

        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(self.model_name)
            self._use_simple = False
        except ImportError:
            # Fallback to simple word-based embeddings
            self._use_simple = True

        self._initialized = True

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts."""
        self._initialize()

        if self._use_simple:
            return self._simple_embed(texts)

        embeddings = self.model.encode(texts, convert_to_numpy=True)
        return [emb.tolist() for emb in embeddings]

    def _simple_embed(self, texts: List[str], dim: int = 128) -> List[List[float]]:
        """Simple hash-based embedding when sentence-transformers unavailable.

        Uses character n-grams and hashing to create consistent embeddings.
        Not as good as neural embeddings but works without dependencies.
        """
        embeddings = []

        for text in texts:
            text_lower = text.lower()
            embedding = [0.0] * dim

            # Character trigrams
            for i in range(len(text_lower) - 2):
                trigram = text_lower[i:i+3]
                h = int(hashlib.md5(trigram.encode()).hexdigest(), 16)
                idx = h % dim
                embedding[idx] += 1.0

            # Word unigrams
            words = text_lower.split()
            for word in words:
                h = int(hashlib.md5(word.encode()).hexdigest(), 16)
                idx = h % dim
                embedding[idx] += 2.0  # Words weighted more

            # Normalize
            magnitude = math.sqrt(sum(x*x for x in embedding))
            if magnitude > 0:
                embedding = [x / magnitude for x in embedding]

            embeddings.append(embedding)

        return embeddings

    @property
    def dimension(self) -> int:
        """Return embedding dimension."""
        self._initialize()
        if self._use_simple:
            return 128
        return self.model.get_sentence_embedding_dimension()


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    if len(a) != len(b):
        return 0.0

    dot_product = sum(x * y for x, y in zip(a, b))
    magnitude_a = math.sqrt(sum(x * x for x in a))
    magnitude_b = math.sqrt(sum(x * x for x in b))

    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0

    return dot_product / (magnitude_a * magnitude_b)


class SemanticSearchService:
    """Service for semantic search over dimension members.

    Features:
    - Embedding generation and storage
    - Semantic similarity search
    - Batch member indexing
    - Alias and property support
    - Common term mappings (revenue -> account patterns)
    """

    # Common financial term mappings for EPM
    TERM_MAPPINGS = {
        # Revenue terms
        "revenue": ["revenue", "sales", "income", "receita", "vendas", "4"],
        "sales": ["sales", "revenue", "vendas", "receita"],
        "receita": ["receita", "revenue", "sales", "vendas"],

        # Expense terms
        "expense": ["expense", "cost", "despesa", "custo", "5", "6"],
        "cost": ["cost", "expense", "custo", "despesa"],
        "despesa": ["despesa", "expense", "cost"],

        # Profit terms
        "profit": ["profit", "income", "lucro", "resultado", "net income"],
        "income": ["income", "profit", "lucro", "receita"],
        "lucro": ["lucro", "profit", "income"],

        # Balance sheet
        "assets": ["assets", "ativo", "asset"],
        "liabilities": ["liabilities", "passivo", "liability"],
        "equity": ["equity", "patrimonio", "shareholders"],

        # Cash flow
        "cash": ["cash", "caixa", "cash flow"],
        "operating": ["operating", "operacional", "operations"],

        # Common abbreviations
        "pl": ["p&l", "profit loss", "income statement", "dre"],
        "bs": ["balance sheet", "balanco", "bp"],
        "cf": ["cash flow", "fluxo de caixa", "dfc"],
    }

    def __init__(
        self,
        db_url: str,
        embedder: Optional[LocalEmbedder] = None,
        similarity_threshold: float = 0.3
    ):
        """Initialize semantic search service.

        Args:
            db_url: Database URL for embedding storage.
            embedder: Optional custom embedder (defaults to LocalEmbedder).
            similarity_threshold: Minimum similarity score for results.
        """
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

        self.embedder = embedder or LocalEmbedder()
        self.similarity_threshold = similarity_threshold

        self._embedding_cache: Dict[str, List[float]] = {}
        self._cache_lock = threading.Lock()

    def index_member(
        self,
        dimension: str,
        member_name: str,
        alias: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Index a single dimension member for semantic search.

        Args:
            dimension: Dimension name (Account, Entity, etc.).
            member_name: Member name.
            alias: Optional alias/description.
            properties: Optional additional properties.

        Returns:
            True if indexed successfully.
        """
        # Create searchable text
        search_parts = [dimension, member_name]
        if alias:
            search_parts.append(alias)
        if properties:
            # Add relevant property values
            for key in ["description", "label", "formula"]:
                if key in properties:
                    search_parts.append(str(properties[key]))

        search_text = " ".join(search_parts)

        # Generate embedding
        embeddings = self.embedder.embed([search_text])
        embedding = embeddings[0]

        # Store in database
        try:
            with self.Session() as session:
                existing = session.query(MemberEmbedding).filter_by(
                    dimension=dimension,
                    member_name=member_name
                ).first()

                if existing:
                    existing.alias = alias
                    existing.search_text = search_text
                    existing.embedding = json.dumps(embedding)
                    existing.embedding_model = self.embedder.model_name
                    existing.properties = json.dumps(properties) if properties else None
                    existing.updated_at = datetime.utcnow()
                else:
                    entry = MemberEmbedding(
                        dimension=dimension,
                        member_name=member_name,
                        alias=alias,
                        search_text=search_text,
                        embedding=json.dumps(embedding),
                        embedding_model=self.embedder.model_name,
                        properties=json.dumps(properties) if properties else None
                    )
                    session.add(entry)

                session.commit()
                return True
        except Exception as e:
            print(f"Error indexing member: {e}")
            return False

    def index_members_batch(
        self,
        members: List[Dict[str, Any]],
        dimension: str
    ) -> int:
        """Index multiple members in batch for efficiency.

        Args:
            members: List of member dicts with 'name', 'alias', 'properties'.
            dimension: Dimension name.

        Returns:
            Number of members indexed.
        """
        if not members:
            return 0

        # Prepare search texts
        search_texts = []
        for m in members:
            parts = [dimension, m.get("name", "")]
            if m.get("alias"):
                parts.append(m["alias"])
            if m.get("properties"):
                for key in ["description", "label"]:
                    if key in m["properties"]:
                        parts.append(str(m["properties"][key]))
            search_texts.append(" ".join(parts))

        # Generate embeddings in batch
        embeddings = self.embedder.embed(search_texts)

        # Store in database
        indexed = 0
        try:
            with self.Session() as session:
                for i, m in enumerate(members):
                    member_name = m.get("name", "")
                    if not member_name:
                        continue

                    existing = session.query(MemberEmbedding).filter_by(
                        dimension=dimension,
                        member_name=member_name
                    ).first()

                    if existing:
                        existing.alias = m.get("alias")
                        existing.search_text = search_texts[i]
                        existing.embedding = json.dumps(embeddings[i])
                        existing.embedding_model = self.embedder.model_name
                        existing.properties = json.dumps(m.get("properties")) if m.get("properties") else None
                        existing.updated_at = datetime.utcnow()
                    else:
                        entry = MemberEmbedding(
                            dimension=dimension,
                            member_name=member_name,
                            alias=m.get("alias"),
                            search_text=search_texts[i],
                            embedding=json.dumps(embeddings[i]),
                            embedding_model=self.embedder.model_name,
                            properties=json.dumps(m.get("properties")) if m.get("properties") else None
                        )
                        session.add(entry)

                    indexed += 1

                session.commit()
        except Exception as e:
            print(f"Error batch indexing: {e}")

        return indexed

    def search(
        self,
        query: str,
        dimension: Optional[str] = None,
        top_k: int = 5,
        include_mappings: bool = True
    ) -> List[SearchResult]:
        """Search for members matching a natural language query.

        Args:
            query: Natural language search query.
            dimension: Optional dimension filter.
            top_k: Maximum number of results.
            include_mappings: Whether to expand query with term mappings.

        Returns:
            List of SearchResult objects sorted by relevance.
        """
        # Expand query with term mappings
        expanded_query = query
        if include_mappings:
            expanded_query = self._expand_query(query)

        # Generate query embedding
        query_embedding = self.embedder.embed([expanded_query])[0]

        # Load all embeddings for the dimension(s)
        results = []
        try:
            with self.Session() as session:
                query_obj = session.query(MemberEmbedding)
                if dimension:
                    query_obj = query_obj.filter_by(dimension=dimension)

                for entry in query_obj.all():
                    entry_embedding = json.loads(entry.embedding)
                    score = cosine_similarity(query_embedding, entry_embedding)

                    if score >= self.similarity_threshold:
                        properties = json.loads(entry.properties) if entry.properties else None
                        results.append(SearchResult(
                            dimension=entry.dimension,
                            member_name=entry.member_name,
                            alias=entry.alias or entry.member_name,
                            score=score,
                            properties=properties
                        ))
        except Exception as e:
            print(f"Error searching: {e}")

        # Sort by score descending
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]

    def search_by_dimension(
        self,
        query: str,
        dimensions: List[str],
        top_k_per_dimension: int = 3
    ) -> Dict[str, List[SearchResult]]:
        """Search across multiple dimensions and group results.

        Args:
            query: Natural language search query.
            dimensions: List of dimensions to search.
            top_k_per_dimension: Max results per dimension.

        Returns:
            Dict mapping dimension name to results.
        """
        results = {}
        for dim in dimensions:
            dim_results = self.search(query, dimension=dim, top_k=top_k_per_dimension)
            if dim_results:
                results[dim] = dim_results
        return results

    def resolve_member(
        self,
        query: str,
        dimension: str,
        min_confidence: float = 0.5
    ) -> Optional[SearchResult]:
        """Resolve a query to a single best-matching member.

        Use this when you need to map user input to a specific member.

        Args:
            query: User input to resolve.
            dimension: Target dimension.
            min_confidence: Minimum score to accept.

        Returns:
            Best matching SearchResult or None.
        """
        results = self.search(query, dimension=dimension, top_k=1)
        if results and results[0].score >= min_confidence:
            return results[0]
        return None

    def _expand_query(self, query: str) -> str:
        """Expand query with synonyms and term mappings."""
        query_lower = query.lower()
        expansions = [query]

        for term, synonyms in self.TERM_MAPPINGS.items():
            if term in query_lower:
                for syn in synonyms:
                    if syn not in query_lower:
                        expansions.append(syn)

        return " ".join(expansions)

    def get_indexed_dimensions(self) -> List[Dict[str, Any]]:
        """Get statistics about indexed dimensions."""
        try:
            with self.Session() as session:
                stats = session.query(
                    MemberEmbedding.dimension,
                    func.count(MemberEmbedding.id).label("count"),
                    func.max(MemberEmbedding.updated_at).label("last_updated")
                ).group_by(MemberEmbedding.dimension).all()

                return [
                    {
                        "dimension": s[0],
                        "member_count": s[1],
                        "last_updated": s[2].isoformat() if s[2] else None
                    }
                    for s in stats
                ]
        except Exception:
            return []

    def clear_dimension(self, dimension: str) -> int:
        """Clear all embeddings for a dimension.

        Returns:
            Number of entries deleted.
        """
        try:
            with self.Session() as session:
                count = session.query(MemberEmbedding).filter_by(
                    dimension=dimension
                ).delete()
                session.commit()
                return count
        except Exception:
            return 0


# Global service instance
_semantic_search_service: Optional[SemanticSearchService] = None
_service_lock = threading.Lock()


def init_semantic_search(
    db_url: str,
    similarity_threshold: float = 0.3
) -> SemanticSearchService:
    """Initialize the global semantic search service."""
    global _semantic_search_service
    with _service_lock:
        if _semantic_search_service is None:
            _semantic_search_service = SemanticSearchService(
                db_url=db_url,
                similarity_threshold=similarity_threshold
            )
    return _semantic_search_service


def get_semantic_search() -> Optional[SemanticSearchService]:
    """Get the global semantic search service instance."""
    return _semantic_search_service


def index_from_csvs(
    service: SemanticSearchService,
    data_dir: Optional[Path] = None,
    csv_mappings: Optional[Dict[str, str]] = None
) -> Dict[str, int]:
    """Index embeddings from local metadata CSVs."""
    base_dir = data_dir or (Path(__file__).resolve().parents[2] / "data")
    mappings = csv_mappings or {
        "Account": "Ravi_ExportedMetadata_Account.csv",
        "Entity": "Ravi_ExportedMetadata_Entity.csv",
        "Movement": "Ravi_ExportedMetadata_Movement.csv",
        "Data Source": "Ravi_ExportedMetadata_Data Source.csv",
    }

    results: Dict[str, int] = {}
    for dimension, filename in mappings.items():
        filepath = base_dir / filename
        if not filepath.exists():
            results[dimension] = 0
            continue

        members: List[Dict[str, Any]] = []
        with open(filepath, "r", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames:
                reader.fieldnames = [name.strip() for name in reader.fieldnames]

            for row in reader:
                name = row.get(dimension) or row.get(list(row.keys())[0], "")
                name = name.strip() if isinstance(name, str) else ""
                if not name:
                    continue

                alias = row.get("Alias: Default") or row.get("Alias") or ""
                alias = alias.strip() if isinstance(alias, str) else None

                properties = {
                    key.strip(): value.strip()
                    for key, value in row.items()
                    if isinstance(value, str) and value.strip()
                }

                members.append({
                    "name": name,
                    "alias": alias,
                    "properties": properties
                })

        results[dimension] = service.index_members_batch(members, dimension=dimension)

    return results
