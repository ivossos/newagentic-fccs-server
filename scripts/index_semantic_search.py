"""Index semantic search embeddings from local metadata CSVs."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fccs_agent.services.semantic_search import SemanticSearchService, index_from_csvs


def main() -> None:
    db_url = os.environ.get("DATABASE_URL", "sqlite:///./data/fccs_agent_v2.db")
    service = SemanticSearchService(db_url)

    results = index_from_csvs(service)
    total_indexed = sum(results.values())

    for dimension, count in results.items():
        status = "ok" if count else "skip"
        print(f"[{status}] {dimension}: indexed {count} members")

    print(f"Done. Total indexed: {total_indexed}")


if __name__ == "__main__":
    main()
