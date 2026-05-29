FROM python:3.11-slim

WORKDIR /app

# Copy project files
COPY . /app

# Install the agent-sudo package locally
RUN pip install --no-cache-dir .

# Standard MCP servers communicate via stdio, no ports need exposing by default, but we'll expose a default port for general use cases.
EXPOSE 8000

# Default entrypoint to start the MCP server
ENTRYPOINT ["agent-sudo-mcp"]
