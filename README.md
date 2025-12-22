# Containerized Strands Agents

An MCP server that hosts isolated Strands AI agents in Docker containers. Each agent runs independently with its own workspace, persists conversation history, and can be restored after reboots.

## Features

- **Async/Non-blocking**: `send_message` returns immediately (fire-and-forget)
- **Isolated Agents**: Each agent runs in its own Docker container
- **Session Persistence**: Conversation history saved and restored across container restarts
- **Custom System Prompts**: Configure per-agent system prompts via text or file
- **GitHub Integration**: Agents can push to repositories with scoped access tokens
- **AWS Profile Support**: Pass different AWS profiles for different agents
- **Retry Logic**: Automatic retry with exponential backoff for transient errors
- **Idle Timeout**: Containers automatically stop after configurable inactivity period

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

# All features
pip install -e ".[webui,dev]"
```

The Docker image will be built automatically on first use.

## Usage

### Web UI

```bash
containerized-strands-agents-webui
# or
python run_web_ui.py
```

Open http://localhost:8000 to view agents, chat, and manage containers.

### As an MCP Server

Add to your MCP configuration (e.g., `~/.kiro/settings/mcp.json`):

```json
{
  "mcpServers": {
    "containerized-strands-agents": {
      "command": "containerized-strands-agents",
      "env": {
        "CONTAINERIZED_AGENTS_GITHUB_TOKEN": "github_pat_xxxx"
      }
    }
  }
}
```

### MCP Tools

| Tool | Description |
|------|-------------|
| `send_message` | Send message to agent (fire-and-forget), creates agent if needed |
| `get_messages` | Get conversation history (use on-demand, not for polling) |
| `list_agents` | List all agents and their status |
| `stop_agent` | Stop an agent's container |

#### send_message

```python
send_message(
    agent_id="my-agent",
    message="Hello!",
    aws_profile="my-profile",               # Optional
    aws_region="us-west-2",                 # Optional (default: us-east-1)
    system_prompt="You are a pirate...",    # Optional
    system_prompt_file="/path/to/prompt",   # Optional (takes precedence)
    tools=["/path/to/tool.py"],             # Optional: per-agent tools
    data_dir="/path/to/project",            # Optional: custom data directory
)
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CONTAINERIZED_STRANDS_DATA_DIR` | `./data` | Base directory for persistence |
| `AGENT_HOST_IDLE_TIMEOUT` | `720` | Minutes before idle container stops (12 hrs) |
| `CONTAINERIZED_AGENTS_GITHUB_TOKEN` | - | GitHub PAT for git push access |
| `CONTAINERIZED_AGENTS_SYSTEM_PROMPTS` | - | Comma-separated paths to prompt files |
| `OPENAI_API_KEY` | - | OpenAI API key (passed to containers) |
| `GOOGLE_API_KEY` | - | Google/Gemini API key (passed to containers) |
| `AWS_BEARER_TOKEN_BEDROCK` | - | AWS bearer token for Bedrock cross-account |

### GitHub Token Setup

1. Create a [Fine-Grained Personal Access Token](https://github.com/settings/tokens?type=beta)
2. Select "Only select repositories" and choose your repos
3. Grant "Contents: Read and write" permission
4. Set `CONTAINERIZED_AGENTS_GITHUB_TOKEN`

## Agent Capabilities

Each agent has access to:

- `file_read`, `file_write`, `editor` - File operations
- `shell` - Execute shell commands
- `python_repl` - Run Python code
- `use_agent` - Spawn sub-agents
- `load_tool` - Dynamically load additional tools
- GitHub tools - Create/update issues and PRs

**Important**: Agents work in `/data/workspace` - this directory persists across container restarts.

## Data Persistence

```
data/
├── tasks.json              # Agent registry
└── agents/{agent_id}/
    ├── session_{id}/       # Conversation history
    ├── system_prompt.txt   # Custom system prompt
    ├── tools/              # Per-agent tools
    └── workspace/          # Agent's files
```

## Development

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v

# Rebuild Docker image after changes
./scripts/build_docker.sh
```

## License

MIT
