"""Configuration for Containerized Strands Agents MCP Server."""

import os
from pathlib import Path

# Paths - src/containerized_strands_agents/config.py -> ../.. -> project root
BASE_DIR = Path(__file__).parent.parent.parent
DATA_DIR = Path(os.getenv("CONTAINERIZED_STRANDS_DATA_DIR", BASE_DIR / "data"))
TASKS_FILE = DATA_DIR / "tasks.json"
AGENTS_DIR = DATA_DIR / "agents"

# Docker settings
DOCKER_IMAGE_NAME = "agent-host-runner"
DOCKER_NETWORK = "agent-host-net"
CONTAINER_PORT = 8080

# Timeouts
IDLE_TIMEOUT_MINUTES = int(os.getenv("AGENT_HOST_IDLE_TIMEOUT", "720"))  # 12 hours default
HEALTH_CHECK_INTERVAL_SECONDS = 60
CONTAINER_STARTUP_TIMEOUT_SECONDS = 30

# MCP Configuration
# Path to default mcp.json file for all agents (can be overridden per-agent)
MCP_CONFIG_FILE = os.getenv("CONTAINERIZED_AGENTS_MCP_CONFIG", "")

# Agent system prompt
SYSTEM_PROMPT = """You are a helpful AI assistant running in an isolated environment.

You have access to the following tools:
- file_read: Read files from your workspace
- file_write: Write files to your workspace
- editor: Edit files with precision
- shell: Execute shell commands
- python_repl: Run Python code
- use_agent: Spawn sub-agents for complex tasks
- load_tool: Dynamically load additional tools

Your workspace is at /workspace. All file operations should be relative to this directory.

Be helpful, concise, and thorough in completing tasks. If a task requires multiple steps,
break it down and execute each step carefully.
"""
