# Getting Started with Containerized Strands Agents

Run isolated AI agents in Docker containers with persistent memory, custom tools, and GitHub integration.

## Prerequisites

- Python 3.11+
- Docker (running)
- AWS credentials with Bedrock access (`~/.aws/credentials`)

## Installation

```bash
# Install directly from GitHub (with web UI)
pip install "containerized-strands-agents[webui] @ git+https://github.com/mkmeral/containerized-strands-agents.git"

# Or clone for development
git clone https://github.com/mkmeral/containerized-strands-agents.git
cd containerized-strands-agents
pip install -e ".[webui]"
```

## Quick Start: Web UI

```bash
containerized-strands-agents-webui
```

Open the URL shown (usually http://localhost:8000). Create an agent, give it a name, and start chatting.

## Quick Start: MCP Server (Kiro/Claude Desktop)

Add to `~/.kiro/settings/mcp.json`:

```json
{
  "mcpServers": {
    "containerized-strands-agents": {
      "command": "containerized-strands-agents-server"
    }
  }
}
```

Then in Kiro:
```
Send a message to agent "my-helper" asking it to create a Python script that...
```

## Key Concepts

**Agents are persistent.** Each agent has its own workspace and remembers conversations across restarts.

**Fire-and-forget messaging.** `send_message` returns immediately. Use `get_messages` to check results when needed.

**Snapshots for portability.** Backup and restore agents anywhere:

```bash
# Backup
containerized-strands-agents snapshot --data-dir ./data/agents/my-agent --output backup.zip

# Restore
containerized-strands-agents restore --snapshot backup.zip --data-dir ./new-location
```

## Running Agents in GitHub Actions

1. Copy the workflow template:
   ```bash
   cp templates/gha-agent-workflow.yml .github/workflows/run-agent.yml
   ```

2. Set up AWS secrets in your repo (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)

3. Trigger via workflow_dispatch with a message

4. Pull results locally:
   ```bash
   containerized-strands-agents pull --repo owner/repo --run-id 12345 --data-dir ./my-agent
   ```

## CLI Commands

| Command | Description |
|---------|-------------|
| `snapshot` | Create a backup of an agent |
| `restore` | Restore an agent from backup |
| `run` | Run an agent directly (no Docker) |
| `pull` | Download agent state from GitHub Actions |

## Environment Variables

### Server Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `CONTAINERIZED_STRANDS_DATA_DIR` | `./data` | Base directory for persistence |
| `AGENT_HOST_IDLE_TIMEOUT` | `720` | Minutes before idle container stops (12 hrs) |
| `CONTAINERIZED_AGENTS_SYSTEM_PROMPTS` | - | Comma-separated paths to system prompt files |
| `CONTAINERIZED_AGENTS_TOOLS` | - | Path to global tools directory |
| `CONTAINERIZED_AGENTS_MCP_CONFIG` | - | Path to default mcp.json for all agents |

### Passed to Containers

These are passed through to agents if set:

| Variable | Description |
|----------|-------------|
| `CONTAINERIZED_AGENTS_GITHUB_TOKEN` | GitHub PAT for git clone/push |
| `OPENAI_API_KEY` | OpenAI API key (for OpenAI models) |
| `GOOGLE_API_KEY` | Google/Gemini API key |
| `AWS_BEARER_TOKEN_BEDROCK` | Alternative Bedrock auth (instead of ~/.aws creds) |

### Web UI vs MCP Server

**Web UI** reads env vars from your shell:
```bash
export CONTAINERIZED_AGENTS_GITHUB_TOKEN="github_pat_xxxx"
export AWS_BEARER_TOKEN_BEDROCK="your-token"
containerized-strands-agents-webui
```

**MCP Server** (Kiro/Claude Desktop) needs env vars in `mcp.json`:
```json
{
  "mcpServers": {
    "containerized-strands-agents": {
      "command": "containerized-strands-agents-server",
      "env": {
        "CONTAINERIZED_AGENTS_GITHUB_TOKEN": "github_pat_xxxx",
        "CONTAINERIZED_AGENTS_MCP_CONFIG": "/path/to/mcp.json",
        "AWS_BEARER_TOKEN_BEDROCK": "your-token"
      }
    }
  }
}
```

The `CONTAINERIZED_AGENTS_MCP_CONFIG` points to an mcp.json that all spawned agents will use by default.

The MCP client spawns the server as a subprocess, so it doesn't inherit your shell environment. You'll need to set the same vars in both places if you use both interfaces.

## What Agents Can Do

- Read/write files in their workspace
- Run shell commands
- Execute Python code
- Create GitHub issues and PRs
- Spawn sub-agents
- Load custom tools dynamically
- **Use MCP servers** for external tools (AWS docs, Perplexity, GitHub, etc.)

## MCP Server Support

Give agents access to external tools via MCP (Model Context Protocol). Uses the same config format as Kiro/Claude Desktop.

**Option 1: Global default for all agents**
```bash
export CONTAINERIZED_AGENTS_MCP_CONFIG="~/.kiro/settings/mcp.json"
containerized-strands-agents-webui
```

**Option 2: Per-agent via send_message**
```python
send_message(
    agent_id="researcher",
    message="Search for Lambda documentation",
    mcp_config_file="~/.kiro/settings/mcp.json"
)
```

**Option 3: Inline config**
```python
send_message(
    agent_id="docs-agent",
    message="What is S3?",
    mcp_config={
        "mcpServers": {
            "aws-docs": {
                "command": "uvx",
                "args": ["awslabs.aws-documentation-mcp-server@latest"]
            }
        }
    }
)
```

MCP config is persisted per-agent - set it once and it's remembered.

## Next Steps

- Check [README.md](README.md) for full configuration options
- See [AGENTS.md](AGENTS.md) for architecture details
- Look at `templates/gha-agent-workflow.yml` for CI/CD patterns
