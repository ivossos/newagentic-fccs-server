"""FastMCP stdio server entry point for Claude Desktop integration."""
import os
import sys

# Set environment variables for proper UTF-8 encoding BEFORE any imports
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")

# Configure logging BEFORE any other imports to ensure all output goes to stderr
import logging

# Configure root logger to use stderr only
logging.basicConfig(
    level=logging.WARNING,
    format='%(levelname)-8s %(name)s: %(message)s',
    stream=sys.stderr,
    force=True  # Override any existing configuration
)

# Suppress verbose loggers that might pollute the stream
for logger_name in ['sqlalchemy', 'sqlalchemy.engine', 'httpx', 'httpcore', 'asyncio']:
    logging.getLogger(logger_name).setLevel(logging.WARNING)

from fccs_agent.fastmcp_server import build_fastmcp_server


def main() -> None:
    server = build_fastmcp_server()
    server.run("stdio")


if __name__ == "__main__":
    main()
