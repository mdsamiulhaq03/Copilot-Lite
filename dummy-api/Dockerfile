# Dummy Error Log API image. Runs on its own, as its own Compose service.
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

# 2. Copy our code
COPY main.py .

# 3. The logs are not copied in: they are mounted from the project's
#    mock-logs/ folder at run time, so editing a log needs no rebuild.
ENV LOGS_DIR=/mock-logs

# 4. Run as a normal user, not root
RUN useradd --create-home appuser
USER appuser

# 8001 is this service's port everywhere: here, in compose, and in the MCP server
EXPOSE 8001

# Docker marks the container "healthy" once /health answers
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health', timeout=2)"

# 0.0.0.0 so the API can be reached from outside the container
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
