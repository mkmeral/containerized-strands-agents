# Containerized Strands Agents

An MCP server that hosts isolated Strands AI agents in Docker containers. Each agent runs independently with its own workspace, persists conversation history, and can be restored after reboots.

## Features

- **Async/Non-blocking**: `send_message` returns immediately (fire-and-forget)
- **Isolated Agents**: Each agent runs in its own Docker container
- **Session Persistence**: Conversation history saved and restored across container restarts
- **Custom System Prompts**: Configure per-agent system prompts via text or file
- **MCP Server Support**: Connect agents to external tools via Model Context Protocol
- **GitHub Integration**: Agents can push to repositories with scoped access tokens
- **AWS Profile Support**: Pass different AWS profiles for different agents
- **Retry Logic**: Automatic retry with exponential backoff for transient errors
- **Idle Timeout**: Containers automatically stop after configurable inactivity period
- **Web UI**: Browser-based interface for managing agents and chatting

## Prerequisites

- Python 3.11+
- Docker (running)
- AWS credentials configured in `~/.aws/` with access to Amazon Bedrock (Claude models)

## Quick Start

```bash
# Clone the repository
git clone <repo-url>
cd containerized-strands-agents

# Install with web UI support
pip install -e ".[webui]"

# Start the web UI
containerized-strands-agents-webui
```

Open the URL shown in the terminal (usually http://localhost:8000) to create and chat with agents.

## Installation

```bash
# Basic installation (MCP server only)
pip install -e .

# With web UI support
pip install -e ".[webui]"

# All features including dev tools
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

The server finds an available port (starting at 8000) and displays the URL. Use the web interface to:
- Create new agents with custom system prompts
- Chat with existing agents
- View agent status and conversation history
- Stop idle agents

### As an MCP Server (Kiro, Claude Desktop, etc.)

Add to your MCP configuration (e.g., `~/.kiro/settings/mcp.json`):

```json
{
  "mcpServers": {
    "containerized-strands-agents": {
      "command": "containerized-strands-agents-server",
      "env": {
        "CONTAINERIZED_AGENTS_GITHUB_TOKEN": "github_pat_xxxx",
        "CONTAINERIZED_AGENTS_MCP_CONFIG": "/path/to/mcp.json",
        "AWS_BEARER_TOKEN_BEDROCK": "optional-bearer-token"
      }
    }
  }
}
```

The `CONTAINERIZED_AGENTS_MCP_CONFIG` env var sets a default mcp.json for all agents spawned by this server. You can point it to your existing Kiro config or a separate one.

### MCP Tools

| Tool | Description |
|------|-------------|
| `send_message` | Send message to agent (fire-and-forget), creates agent if needed |
| `get_messages` | Get conversation history (use on-demand, not for polling) |
| `list_agents` | List all agents and their status |
| `stop_agent` | Stop an agent's container |

#### send_message Parameters

```python
send_message(
    agent_id="my-agent",
    message="Hello!",
    aws_profile="my-profile",               # Optional: AWS profile for Bedrock
    aws_region="us-west-2",                 # Optional (default: us-east-1)
    system_prompt="You are a pirate...",    # Optional: custom instructions
    system_prompt_file="/path/to/prompt",   # Optional (takes precedence over system_prompt)
    tools=["/path/to/tool.py"],             # Optional: per-agent tools
    data_dir="/path/to/project",            # Optional: custom data directory
    mcp_config_file="~/.kiro/settings/mcp.json",  # Optional: path to MCP config
    mcp_config={"mcpServers": {...}},       # Optional: inline MCP config
)
```

### CLI Commands for Snapshot/Restore

The CLI provides commands to create and restore agent snapshots (backups):

#### Create a Snapshot

```bash
containerized-strands-agents snapshot --data-dir ./my-agent --output snapshot.zip
```

Creates a zip archive of an agent's entire data directory, including:
- Workspace files
- Session history
- System prompts
- Tools
- Runner files

#### Restore from Snapshot

```bash
containerized-strands-agents restore --snapshot snapshot.zip --data-dir ./restored-agent
```

Extracts a snapshot to a new (or existing) directory. The restored agent is immediately ready to run.

**Examples:**

```bash
# Backup an agent
containerized-strands-agents snapshot \
  --data-dir ./data/agents/my-project \
  --output backups/my-project-2024-01-01.zip

# Restore to a new location
containerized-strands-agents restore \
  --snapshot backups/my-project-2024-01-01.zip \
  --data-dir ./data/agents/my-project-restored

# Use with custom data directories
containerized-strands-agents snapshot \
  --data-dir ~/projects/agent-workspace \
  --output ~/backups/agent-snapshot.zip
```

**Notes:**
- Snapshots work with both default data directories (`./data/agents/{id}`) and custom ones
- The CLI validates the directory structure before creating snapshots
- Restoring to an existing directory will prompt for confirmation
- Restored agents can be started immediately using the MCP server or Web UI

#### Pull from GitHub Actions

```bash
containerized-strands-agents pull --repo owner/repo --run-id 12345 --data-dir ./my-agent
```

Downloads agent state from a GitHub Actions artifact. Useful for continuing work started in CI.

**Options:**
- `--repo` (required): Repository in `owner/repo` format
- `--run-id`: Download artifacts from a specific workflow run
- `--artifact`: Download a specific artifact by name
- `--data-dir`: Target directory (default: `./agent-data`)
- `--token`: GitHub token (uses `GITHUB_TOKEN` env var if not provided)

**Examples:**

```bash
# Pull from a specific run
containerized-strands-agents pull \
  --repo myorg/my-repo \
  --run-id 12345678 \
  --data-dir ./data/agents/from-gha

# Pull a specific artifact by name
containerized-strands-agents pull \
  --repo myorg/my-repo \
  --artifact agent-data-default-agent-42 \
  --data-dir ./restored-agent

# Uses gh CLI if available, otherwise GitHub API with token
export GITHUB_TOKEN="ghp_xxxx"
containerized-strands-agents pull --repo myorg/my-repo --run-id 12345
```

### GitHub Actions Workflow

A workflow template is provided at `templates/gha-agent-workflow.yml` for running agents in GitHub Actions:

```bash
# Copy to your repo
cp templates/gha-agent-workflow.yml .github/workflows/run-agent.yml
```

The workflow:
1. Restores agent state from a previous artifact (optional)
2. Runs the agent with your message
3. Uploads updated state as an artifact

Trigger via `workflow_dispatch` with a message input. See the template for required secrets (AWS credentials).

## Configuration

### Environment Variables

These variables configure the MCP server. Set them either in your `mcp.json` (under `env`) or export them in your shell before running the web UI.

**Server Configuration:**

| Variable | Default | Description |
|----------|---------|-------------|
| `CONTAINERIZED_STRANDS_DATA_DIR` | `./data` | Base directory for persistence |
| `AGENT_HOST_IDLE_TIMEOUT` | `720` | Minutes before idle container stops (12 hrs) |
| `CONTAINERIZED_AGENTS_SYSTEM_PROMPTS` | - | Comma-separated paths to prompt files |
| `CONTAINERIZED_AGENTS_TOOLS` | - | Path to global tools directory |
| `CONTAINERIZED_AGENTS_MCP_CONFIG` | - | Path to default mcp.json for all agents |

**Passed to Containers** (agents can use these):

| Variable | Description |
|----------|-------------|
| `CONTAINERIZED_AGENTS_GITHUB_TOKEN` | GitHub PAT for git push access |
| `OPENAI_API_KEY` | OpenAI API key (for OpenAI models) |
| `GOOGLE_API_KEY` | Google/Gemini API key |
| `AWS_BEARER_TOKEN_BEDROCK` | AWS bearer token for Bedrock authentication |

Example for web UI:
```bash
export CONTAINERIZED_AGENTS_GITHUB_TOKEN="github_pat_xxxx"
export AWS_BEARER_TOKEN_BEDROCK="your-token"  # Optional: alternative Bedrock auth
containerized-strands-agents-webui
```

### AWS Setup

Agents use **Amazon Bedrock** with Claude models by default. You have two options:

**Option 1: AWS Credentials (default)**

Your `~/.aws/credentials` are mounted read-only into containers. Ensure your profile has Bedrock access.

```bash
# Verify AWS credentials
aws sts get-caller-identity

# Check Bedrock model access (us-east-1)
aws bedrock list-foundation-models --region us-east-1 --query "modelSummaries[?contains(modelId, 'claude')]"
```

**Option 2: Bearer Token**

Set `AWS_BEARER_TOKEN_BEDROCK` as an alternative authentication method for Bedrock.

### GitHub Token Setup (Optional)

For agents that need to push to GitHub repositories:

1. Create a [Fine-Grained Personal Access Token](https://github.com/settings/tokens?type=beta)
2. Select "Only select repositories" and choose your repos
3. Grant "Contents: Read and write" permission
4. Set `CONTAINERIZED_AGENTS_GITHUB_TOKEN` environment variable

## Agent Capabilities

Each agent has access to:

- `file_read`, `file_write`, `editor` - File operations
- `shell` - Execute shell commands
- `python_repl` - Run Python code
- `use_agent` - Spawn sub-agents
- `load_tool` - Dynamically load additional tools
- GitHub tools - Create/update issues and PRs
- **MCP tools** - Any tools from configured MCP servers

**Important**: Agents work in `/data/workspace` inside the container. This directory persists across container restarts.

## MCP Server Support

Agents can connect to external MCP (Model Context Protocol) servers for additional tools. This uses the same config format as Kiro/Claude Desktop.

### Quick Setup: Use Your Existing Config

Point agents to your existing Kiro mcp.json:

```bash
# Set as default for all agents
export CONTAINERIZED_AGENTS_MCP_CONFIG="~/.kiro/settings/mcp.json"
containerized-strands-agents-webui
```

Or per-agent via MCP tool:
```python
send_message(
    agent_id="researcher",
    message="Search AWS docs for Lambda limits",
    mcp_config_file="~/.kiro/settings/mcp.json"
)
```

### Inline MCP Config

```python
send_message(
    agent_id="docs-agent",
    message="What is Amazon S3?",
    mcp_config={
        "mcpServers": {
            "aws-docs": {
                "command": "uvx",
                "args": ["awslabs.aws-documentation-mcp-server@latest"]
            },
            "perplexity": {
                "command": "npx",
                "args": ["-y", "@anthropic-ai/mcp-server-perplexity"],
                "env": {"PERPLEXITY_API_KEY": "pplx-xxx"}
            }
        }
    }
)
```

### Config Format

Same as Kiro/Claude Desktop:

```json
{
  "mcpServers": {
    "server-name": {
      "command": "uvx",
      "args": ["package-name@latest"],
      "env": {"API_KEY": "..."},
      "disabled": false
    }
  }
}
```

### Configuration Precedence

1. `mcp_config_file` param (path to mcp.json)
2. `mcp_config` param (inline dict)  
3. Agent's persisted config (`.agent/mcp.json`)
4. `CONTAINERIZED_AGENTS_MCP_CONFIG` env var (global default)

MCP config is persisted per-agent, so you only need to set it once. Subsequent messages to the same agent will use the saved config.

### Supported Transports

- **stdio** (default): Local command-line MCP servers via `uvx` or `npx`
- **SSE**: Remote HTTP-based MCP servers

### Notes

- `uvx` and `npx` are pre-installed in containers - no need to install individual MCP servers
- Environment variables in config (like `${GITHUB_TOKEN}`) are expanded at runtime
- Disabled servers (`"disabled": true`) are skipped
- **Fails open**: If an MCP server fails to connect, the agent still starts with other tools. Check container logs for connection errors.

## Data Persistence

```
data/
├── tasks.json              # Agent registry
└── agents/{agent_id}/
    ├── workspace/          # Agent's persistent files
    └── .agent/
        ├── session/        # Conversation history (FileSessionManager)
        ├── system_prompt.txt   # Custom system prompt
        ├── tools/          # Per-agent tools
        └── runner/         # Agent code for standalone execution
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
python -m pytest tests/ -v

# Run only unit tests (no Docker required)
python -m pytest tests/test_agent_manager.py -v

# Rebuild Docker image after changes
./scripts/build_docker.sh
```

## Troubleshooting

**Docker image not found**: Run `./scripts/build_docker.sh` manually

**Bedrock access denied**: Ensure your AWS credentials have Bedrock permissions and the model is enabled in your region

**Agent stuck processing**: Check container logs with `docker logs agent-<agent-id>`

**Port already in use**: The web UI automatically finds an available port; check the terminal output for the actual URL

## License

MIT
