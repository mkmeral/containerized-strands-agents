# Containerized Strands Agents

An MCP server that hosts isolated Strands AI agents in Docker containers. Each agent runs independently with its own workspace, persists conversation history, and can be restored after reboots.

## Features

- **Async/Non-blocking**: `send_message` returns immediately (fire-and-forget), use `get_messages` to poll for responses
- **Isolated Agents**: Each agent runs in its own Docker container
- **Session Persistence**: Conversation history is saved and restored across container restarts
- **Custom System Prompts**: Configure per-agent system prompts via text or file
- **GitHub Integration**: Agents can push to repositories with scoped access tokens
- **AWS Profile Support**: Pass different AWS profiles for different agents
- **Idle Timeout**: Containers automatically stop after 30 minutes of inactivity
- **Full Toolset**: Agents have access to file operations, shell, Python REPL, and more

## Prerequisites

- Python 3.11+
- Docker
- AWS credentials configured in `~/.aws/`

## Installation

```bash
# Basic installation
pip install -e .

# With web UI support
pip install -e ".[webui]"

# With development tools
pip install -e ".[dev]"

# All features
pip install -e ".[webui,dev]"
```

The Docker image will be built automatically on first use.

## Usage

### Web UI

Launch the web interface for easy agent management:

```bash
containerized-strands-agents-webui
# or
python run_web_ui.py
```

Then open http://localhost:8000 in your browser to:
- View all agents with real-time status updates
- Chat with agents through a clean interface
- Create new agents with custom system prompts
- Stop agents on demand

### As an MCP Server

Add to your MCP configuration (e.g., `~/.kiro/settings/mcp.json`):

```json
{
  "mcpServers": {
    "containerized-strands-agents": {
      "command": "containerized-strands-agents",
      "env": {
        "CONTAINERIZED_AGENTS_GITHUB_TOKEN": "github_pat_xxxx",
        "CONTAINERIZED_AGENTS_SYSTEM_PROMPTS": "/path/to/prompt1.txt,/path/to/prompt2.txt"
      }
    }
  }
}
```

### MCP Tools

#### send_message

Send a message to an agent (fire-and-forget). Creates the agent if it doesn't exist.

```python
send_message(
    agent_id="my-agent",                    # Unique agent identifier
    message="Hello, agent!",                # Message to send
    aws_profile="my-profile",               # Optional: AWS profile
    aws_region="us-west-2",                 # Optional: AWS region (default: us-east-1)
    system_prompt="You are a pirate...",    # Optional: Custom system prompt
    system_prompt_file="/path/to/prompt",   # Optional: Load prompt from file (takes precedence)
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
# Returns: {"status": "success", "messages": [...], "processing": true/false}
```

#### list_agents

List all agents and their status.

```python
list_agents()
# Returns: {"status": "success", "agents": [{"agent_id": "...", "status": "running", "processing": false, ...}]}
```

#### stop_agent

Stop an agent's container immediately.

```python
stop_agent(agent_id="my-agent")
# Returns: {"status": "success", "message": "Agent my-agent has been stopped successfully"}
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CONTAINERIZED_STRANDS_DATA_DIR` | `./data` | Base directory for persistence |
| `AGENT_HOST_IDLE_TIMEOUT` | `30` | Minutes before idle container stops |
| `CONTAINERIZED_AGENTS_GITHUB_TOKEN` | - | GitHub PAT for git push access (scoped to specific repos) |
| `CONTAINERIZED_AGENTS_SYSTEM_PROMPTS` | - | Comma-separated paths to system prompt files (shown in tool description) |

### GitHub Token Setup

To enable agents to push to GitHub:

1. Create a [Fine-Grained Personal Access Token](https://github.com/settings/tokens?type=beta)
2. Select "Only select repositories" and choose your sandbox/test repos
3. Grant "Contents: Read and write" permission
4. Set the token:

```bash
export CONTAINERIZED_AGENTS_GITHUB_TOKEN="github_pat_xxxx"
containerized-strands-agents
```

Agents will be able to `git push` only to repositories the token has access to.

### Dynamic System Prompt List

Pre-configure system prompts that appear in the tool description:

```bash
export CONTAINERIZED_AGENTS_SYSTEM_PROMPTS="/path/to/code_reviewer.txt,/path/to/data_analyst.txt"
```

If a prompt file starts with `# Display Name`, that name will be shown in the tool description. Otherwise, the filename is used.

See [DYNAMIC_PROMPT_LIST_FEATURE.md](DYNAMIC_PROMPT_LIST_FEATURE.md) for details.

## Agent Capabilities

Each agent has access to these tools:

- `file_read` - Read files from workspace
- `file_write` - Write files to workspace
- `editor` - Edit files with precision
- `shell` - Execute shell commands
- `python_repl` - Run Python code
- `use_agent` - Spawn sub-agents
- `load_tool` - Dynamically load additional tools

**Important**: Agents should always work in `/data/workspace` - this directory is mounted from the host and persists across container restarts.

## Data Persistence

All data is stored in the `data/` directory:

```
data/
├── tasks.json              # Agent registry
└── agents/{agent_id}/
    ├── session.json        # Conversation history
    ├── system_prompt.txt   # Custom system prompt (if set)
    └── workspace/          # Agent's isolated files
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
python -m pytest tests/ -v

# Rebuild Docker image after changes
docker build -t agent-host-runner docker/
```

## Architecture

See [DESIGN.md](DESIGN.md) for detailed architecture documentation.
