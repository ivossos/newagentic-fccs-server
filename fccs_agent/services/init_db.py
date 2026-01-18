"""Database initialization script for FCCS Agent.

This script initializes all database tables for the FCCS Agent services:
- Feedback Service: ToolExecution, ToolMetrics
- Cache Service: CacheEntry, MetadataCache
- RL Service: RLPolicy, RLEpisode, RLMetrics, ToolSequence
- Semantic Search: MemberEmbedding, SemanticSearchConfig
- Valid Intersections: ValidIntersection, IntersectionAccessLog
- Personalization: PersonalizationChecklist

Usage:
    python -m fccs_agent.services.init_db

Or import and call init_database() from code.
"""

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect


def get_database_url() -> str:
    """Get database URL from environment or default."""
    return os.environ.get("DATABASE_URL", "sqlite:///./data/fccs_agent.db")


def init_database(db_url: str | None = None, echo: bool = False) -> None:
    """Initialize all database tables.

    Args:
        db_url: Database URL. If None, uses DATABASE_URL env var or default.
        echo: If True, print SQL statements to stdout.
    """
    if db_url is None:
        db_url = get_database_url()

    # Ensure data directory exists for SQLite
    if db_url.startswith("sqlite:///"):
        db_path = db_url.replace("sqlite:///", "")
        if db_path.startswith("./"):
            db_path = db_path[2:]
        db_dir = Path(db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

    engine = create_engine(db_url, echo=echo)

    # Import all models to register them with their Base classes
    from fccs_agent.services.feedback_service import Base as FeedbackBase
    from fccs_agent.services.feedback_service import ToolExecution, ToolMetrics

    from fccs_agent.services.cache_service import Base as CacheBase
    from fccs_agent.services.cache_service import CacheEntry, MetadataCache

    from fccs_agent.services.rl_service import Base as RLBase
    from fccs_agent.services.rl_service import RLPolicy, RLEpisode, RLMetrics, ToolSequence

    from fccs_agent.services.semantic_search import Base as SemanticBase
    from fccs_agent.services.semantic_search import MemberEmbedding, SemanticSearchConfig

    from fccs_agent.services.valid_intersections import Base as IntersectionBase
    from fccs_agent.services.valid_intersections import ValidIntersection, IntersectionAccessLog

    from fccs_agent.services.personalization_service import Base as PersonalizationBase
    from fccs_agent.services.personalization_service import PersonalizationChecklist

    # Create all tables
    print(f"Initializing database: {db_url}")

    FeedbackBase.metadata.create_all(engine)
    print("  Created feedback tables: tool_executions, tool_metrics")

    CacheBase.metadata.create_all(engine)
    print("  Created cache tables: api_cache, metadata_cache")

    RLBase.metadata.create_all(engine)
    print("  Created RL tables: rl_policy, rl_episodes, rl_metrics, rl_tool_sequences")

    SemanticBase.metadata.create_all(engine)
    print("  Created semantic search tables: member_embeddings, semantic_search_config")

    IntersectionBase.metadata.create_all(engine)
    print("  Created valid intersections tables: valid_intersections, intersection_access_log")

    PersonalizationBase.metadata.create_all(engine)
    print("  Created personalization tables: personalization_checklist")

    # Verify tables exist
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"\nDatabase initialized with {len(tables)} tables: {', '.join(tables)}")

    return engine


def reset_database(db_url: str | None = None, confirm: bool = False) -> None:
    """Drop and recreate all database tables.

    WARNING: This will delete all data!

    Args:
        db_url: Database URL. If None, uses DATABASE_URL env var or default.
        confirm: Must be True to proceed with reset.
    """
    if not confirm:
        print("ERROR: Must pass confirm=True to reset database.")
        print("This operation will DELETE ALL DATA.")
        return

    if db_url is None:
        db_url = get_database_url()

    engine = create_engine(db_url)

    # Import all Base classes
    from fccs_agent.services.feedback_service import Base as FeedbackBase
    from fccs_agent.services.cache_service import Base as CacheBase
    from fccs_agent.services.rl_service import Base as RLBase
    from fccs_agent.services.semantic_search import Base as SemanticBase
    from fccs_agent.services.valid_intersections import Base as IntersectionBase
    from fccs_agent.services.personalization_service import Base as PersonalizationBase

    # Drop all tables
    print(f"Dropping all tables from: {db_url}")
    FeedbackBase.metadata.drop_all(engine)
    CacheBase.metadata.drop_all(engine)
    RLBase.metadata.drop_all(engine)
    SemanticBase.metadata.drop_all(engine)
    IntersectionBase.metadata.drop_all(engine)
    PersonalizationBase.metadata.drop_all(engine)
    print("  All tables dropped.")

    # Recreate
    init_database(db_url)


def check_database(db_url: str | None = None) -> dict:
    """Check database status and return table info.

    Args:
        db_url: Database URL. If None, uses DATABASE_URL env var or default.

    Returns:
        Dict with database status and table information.
    """
    if db_url is None:
        db_url = get_database_url()

    engine = create_engine(db_url)
    inspector = inspect(engine)

    tables = inspector.get_table_names()

    result = {
        "database_url": db_url,
        "tables": {},
        "status": "ok" if tables else "empty"
    }

    for table in tables:
        columns = inspector.get_columns(table)
        result["tables"][table] = {
            "columns": [col["name"] for col in columns],
            "column_count": len(columns)
        }

    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="FCCS Agent Database Initialization")
    parser.add_argument(
        "--db-url",
        help="Database URL (default: from DATABASE_URL env or sqlite:///./data/fccs_agent.db)"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop and recreate all tables (WARNING: deletes data)"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check database status"
    )
    parser.add_argument(
        "--echo",
        action="store_true",
        help="Print SQL statements"
    )

    args = parser.parse_args()

    if args.check:
        status = check_database(args.db_url)
        print(f"Database: {status['database_url']}")
        print(f"Status: {status['status']}")
        print(f"Tables ({len(status['tables'])}):")
        for table, info in status["tables"].items():
            print(f"  - {table}: {info['column_count']} columns")
            print(f"    Columns: {', '.join(info['columns'])}")
    elif args.reset:
        response = input("WARNING: This will DELETE ALL DATA. Type 'yes' to confirm: ")
        if response.lower() == "yes":
            reset_database(args.db_url, confirm=True)
        else:
            print("Reset cancelled.")
    else:
        init_database(args.db_url, echo=args.echo)
