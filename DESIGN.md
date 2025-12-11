# Agent Host MCP Server - Design Document

## Overview

An MCP server that hosts isolated AI agents in Docker containers. Each agent runs independently, persists conversation history, and can be restored after reboots.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     MCP Server (FastMCP)                        │
│                                                                 │
│  Tools:                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │send_message │  │get_messages │  │list_agents  │              │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘              │
│         │                │                │                     │
│         └────────────────┼────────────────┘                     │
│                          ▼                                      │
│              ┌───────────────────────┐                          │
│              │    Agent Manager      │                          │
│              │  - spawn containers   │                          │
│              │  - idle timeout (30m) │                          │
│              │  - health checks      │                          │
│              └───────────┬───────────┘                          │
│                          ▼                                      │
│              ┌───────────────────────┐                          │
│              │  tasks.json (persist) │                          │
│              │  - agent_id           │                          │
│              │  - container_id       │                          │
│              │  - status             │                          │
│              │  - last_activity      │                          │
│              └───────────────────────┘                          │
└─────────────────────────────────────────────────────────────────┘
                              │ Docker API
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
   │  Container  │     │  Container  │     │  Container  │
   │  agent_001  │     │  agent_002  │     │  agent_N    │
   │             │     │             │     │             │
   │ HTTP API    │     │ HTTP API    │     │ HTTP API    │
   │ :8080       │     │ :8080       │     │ :8080       │
   │             │     │             │     │             │
   │ Strands     │     │ Strands     │     │ Strands     │
   │ Agent +     │     │ Agent +     │     │ Agent +     │
   │ FileSession │     │ FileSession │     │ FileSession │
   │             │     │             │     │             │
   │ /workspace  │     │ /workspace  │     │ /workspace  │
   │ (isolated)  │     │ (isolated)  │     │ (isolated)  │
   └─────────────┘     └─────────────┘     └─────────────┘
        │                   │                   │
        ▼                   ▼                   ▼
   data/agents/        data/agents/        data/agents/
   agent_001/          agent_002/          agent_N/
   ├─session.json      ├─session.json      ├─session.json
   └─workspace/        └─workspace/        └─workspace/
```

## Key Design Decisions

| Aspect | Decision |
|--------|----------|
| Container per agent | Yes, full isolation |
| Session persistence | FileSessionManager in Strands (auto-saves messages) |
| Working directory | Isolated per agent, mounted volume |
| Message format | Full conversation history (user + assistant, no tool calls) |
| Agent lifecycle | Idle timeout (30 min default), auto-stop |
| Communication | HTTP API inside container, MCP server calls via Docker network |

## MCP Tools

### send_message
```python
@mcp.tool
async def send_message(agent_id: str, message: str) -> dict:
    """Send message to agent. Creates new agent if ID doesn't exist.
    Returns immediately (async) - use get_messages to poll response."""
```

### get_messages
```python
@mcp.tool  
async def get_messages(agent_id: str, count: int = 1) -> dict:
    """Get last N messages from agent's conversation history.
    Returns list of {role, content} without tool calls."""
```

### list_agents
```python
@mcp.tool
async def list_agents() -> dict:
    """List all agents with their status (running/idle/stopped)."""
```

## Agent Container Specification

- **Base**: Python 3.11 slim
- **Framework**: Strands SDK + strands-agents-tools
- **Session**: FileSessionManager (persists to mounted volume)
- **Tools**: `file_read`, `file_write`, `editor`, `shell`, `use_agent`, `python_repl`, `load_tool`
- **Model**: Default Bedrock (Claude Sonnet)
- **System Prompt**: Hardcoded general-purpose assistant
- **API**: FastAPI on port 8080 (`/chat`, `/history`, `/health`)
- **Idle Timeout**: 30 minutes, container auto-stops

## Project Structure

```
slack_events/
├── pyproject.toml
├── src/
│   └── agent_host/
│       ├── __init__.py
│       ├── server.py           # FastMCP server + tools
│       ├── agent_manager.py    # Docker lifecycle, idle monitor
│       └── config.py           # Timeouts, system prompt
├── docker/
│   ├── Dockerfile
│   ├── agent_runner.py         # FastAPI + Strands agent
│   └── requirements.txt
└── data/
    ├── tasks.json              # Agent registry (persisted)
    └── agents/{agent_id}/
        ├── session.json        # Conversation history
        └── workspace/          # Agent's isolated files
```

## Communication Flow

1. `send_message("agent_1", "hello")` → MCP server
2. Agent Manager checks tasks.json → agent_1 not found
3. Spawn container, mount `data/agents/agent_1/`, assign port
4. HTTP POST to container `/chat` with message
5. Container loads FileSessionManager (restores history if exists)
6. Strands agent processes, saves session, returns response
7. MCP returns `{status: "success", response: "..."}`
8. Idle monitor stops container after 30min inactivity
9. On next message → container restarts, session restored from file

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| IDLE_TIMEOUT_MINUTES | 30 | Minutes before idle container stops |
| DATA_DIR | ./data | Base directory for persistence |
| DOCKER_NETWORK | agent-host-net | Docker network for containers |
| CONTAINER_PORT | 8080 | Internal port for agent API |
