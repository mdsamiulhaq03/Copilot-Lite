# MCP server image. Runs on its own, as its own Compose service (the guide requires this).
FROM python:3.12-slim

# No .pyc files, print logs straight away, keep pip quiet and the image small
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 1. Install libraries first. Docker caches this step, so changing our code
#    later does not reinstall everything.
COPY requirements.txt .
RUN pip install -r requirements.txt

# 2. Copy our code (only the server; try_client.py is a laptop test tool)
COPY server.py .

# 3. Where the Dummy API is: in compose, services reach each other by name
ENV DUMMY_API_URL=http://dummy-api:8001 \
    MCP_PORT=8002

# 4. Run as a normal user, not root
RUN useradd --create-home appuser
USER appuser

# 8002 is this service's port everywhere. The MCP address is http://mcp-server:8002/mcp
EXPOSE 8002

# Docker marks the container "healthy" once /health answers
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8002/health', timeout=2)"

CMD ["python", "server.py"]
