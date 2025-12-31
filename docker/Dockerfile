FROM python:3.11-slim

# App code lives in /app, but we'll set WORKDIR to /data/workspace later
# so agent file operations persist to the mounted volume

# Install system dependencies including Node.js
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy agent code
COPY *.py /app/

# Create tools directory for dynamic tool loading
RUN mkdir -p /app/tools

# Create workspace directory and set as working directory
# This ensures relative paths in file operations persist to the mounted volume
RUN mkdir -p /data/workspace
WORKDIR /data/workspace

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV AGENT_ID=default
ENV IDLE_TIMEOUT_MINUTES=30
ENV BYPASS_TOOL_CONSENT="true"
ENV STRANDS_NON_INTERACTIVE="true"


# AWS credentials will be passed via environment or mounted ~/.aws
# These can be overridden at runtime
ENV AWS_DEFAULT_REGION=us-east-1

# Expose port
EXPOSE 8080

# Run the agent from /app
CMD ["python", "/app/agent_runner.py"]
