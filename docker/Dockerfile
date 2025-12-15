FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including Node.js
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy agent runner
COPY agent_runner.py .

# Create workspace directory
RUN mkdir -p /data/workspace

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV AGENT_ID=default
ENV IDLE_TIMEOUT_MINUTES=30

# AWS credentials will be passed via environment or mounted ~/.aws
# These can be overridden at runtime
ENV AWS_DEFAULT_REGION=us-east-1

# Expose port
EXPOSE 8080

# Run the agent
CMD ["python", "agent_runner.py"]
