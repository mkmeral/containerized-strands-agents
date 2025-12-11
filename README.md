# Containerized Strands Agents

An MCP server that hosts isolated Strands AI agents in Docker containers. Each agent runs independently with its own workspace, persists conversation history, and can be restored after reboots.

## Features

- **Async/Non-blocking**: `send_message` returns immediately (fire-and-forget), use `get_messages` to poll for responses
- **Isolated Agents**: Each agent runs in its own Docker container
- **Session Persistence**: Conversation history is saved and restored across container restarts
- **AWS Profile Support**: Pass different AWS profiles for different agents
- **Idle Timeout**: Containers automatically stop after 30 minutes of inactivity
- **Full Toolset**: Agents have access to file operations, shell, Python REPL, and more

## Prerequisites

- Python 3.11+
- Docker
- AWS credentials configured in `~/.aws/`

## Installation

```bash
pip install -e .
```

The Docker image will be built automatically on first use.

## Usage

### As an MCP Server

Add to your MCP configuration (e.g., `~/.kiro/settings/mcp.json`):

```json
{
  "mcpServers": {
    "strands-agents": {
      "command": "containerized-strands-agents"
    }
  }
}
```

### MCP Tools

#### send_message

Send a message to an agent (fire-and-forget). Creates the agent if it doesn't exist.

Returns immediately after dispatching - use `get_messages` to poll for the response.

```python
send_message(
    agent_id="my-agent",           # Unique agent identifier
    message="Hello, agent!",       # Message to send
    aws_profile="my-profile",      # Optional: AWS profile from ~/.aws/credentials
    aws_region="us-west-2",        # Optional: AWS region (default: us-east-1)
)
# Returns: {"status": "dispatched", "agent_id": "my-agent", "message": "..."}
```

#### get_messages

Get conversation history from an agent. Use this to check for responses after `send_message`.

```python
get_messages(
    agent_id="my-agent",  # Agent to get messages from
    count=5,              # Number of messages to retrieve (default: 1)
)
# Returns: {"status": "success", "messages": [{"role": "assistant", "content": "..."}]}
```

#### list_agents

List all agents and their status (includes `processing: true/false` to indicate if agent is busy).

```python
list_agents()
# Returns: {"status": "success", "agents": [{"agent_id": "...", "status": "running", "processing": false, ...}]}
```

## Agent Capabilities

Each agent has access to these tools:

- `file_read` - Read files from workspace
- `file_write` - Write files to workspace
- `editor` - Edit files with precision
- `shell` - Execute shell commands
- `python_repl` - Run Python code
- `use_agent` - Spawn sub-agents
- `load_tool` - Dynamically load additional tools

## Data Persistence

All data is stored in the `data/` directory:

```
data/
├── tasks.json              # Agent registry
└── agents/{agent_id}/
    ├── session.json        # Conversation history
    └── workspace/          # Agent's isolated files
```

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `CONTAINERIZED_STRANDS_DATA_DIR` | `./data` | Base directory for persistence |
| `AGENT_HOST_IDLE_TIMEOUT` | `30` | Minutes before idle container stops |

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
python -m pytest tests/ -v

# Run only unit tests (no Docker required)
python -m pytest tests/test_agent_manager.py -v

# Run integration tests (requires Docker)
python -m pytest tests/test_integration.py -v
```

## Architecture

See [DESIGN.md](DESIGN.md) for detailed architecture documentation.
