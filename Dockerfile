FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml ./
COPY fccs_agent/ ./fccs_agent/
COPY cli/ ./cli/
COPY web/ ./web/

# Create data directory for SQLite and dummy README
RUN mkdir -p ./data && touch README.md

# Install Python dependencies
RUN pip install --no-cache-dir .

# Cloud Run sets PORT env var
ENV FASTMCP_HOST=0.0.0.0
ENV FASTMCP_PORT=8080

EXPOSE 8080

# Run the REST API server (ChatGPT compatible)
CMD ["uvicorn", "web.rest_api:app", "--host", "0.0.0.0", "--port", "8080"]
