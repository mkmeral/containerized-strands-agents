# Containerized Strands Agents MCP - Configuration Overview

## MCP Tools (4 total)

| Tool | Description |
|------|-------------|
| `send_message` | Send message to agent (fire-and-forget), creates agent if needed |
| `get_messages` | Get conversation history from an agent |
| `list_agents` | List all agents and their status |
| `stop_agent` | Stop an agent's container |

---

## What You CAN Customize

### Per-Agent (at runtime via `send_message`)

| Parameter | Description |
|-----------|-------------|
| `agent_id` | Unique name for the agent |
| `aws_profile` | AWS profile from `~/.aws/credentials` |
| `aws_region` | AWS region for Bedrock (default: us-east-1) |
| `system_prompt` | Custom system prompt text |
| `system_prompt_file` | Path to file containing system prompt |
| `tools` | List of paths to .py tool files for this agent |
| `data_dir` | Custom data directory for this agent (project-specific) |

### Environment Variables (server-level)

| Env Var | Default | Description |
|---------|---------|-------------|
| `CONTAINERIZED_STRANDS_DATA_DIR` | `./data` | Where agent data is stored |
| `AGENT_HOST_IDLE_TIMEOUT` | `720` (12 hrs) | Minutes before idle agents stop |
| `CONTAINERIZED_AGENTS_GITHUB_TOKEN` | - | GitHub token for git push in containers |
| `CONTAINERIZED_AGENTS_SYSTEM_PROMPTS` | - | Comma-separated list of prompt files to advertise |
| `OPENAI_API_KEY` | - | OpenAI API key (passed to containers) |
| `GOOGLE_API_KEY` | - | Google API key for Gemini (passed to containers) |
| `AWS_BEARER_TOKEN_BEDROCK` | - | AWS bearer token for Bedrock cross-account access |

---

## What You CANNOT Customize (hardcoded)

| Setting | Value | Location |
|---------|-------|----------|
| Docker image | `agent-host-runner` | config.py |
| Container port | `8080` | config.py |
| Docker network | `agent-host-net` | config.py |
| Container startup timeout | `30s` | config.py |
| **Tools in container** | Fixed list | docker/agent_runner.py |
| Model/LLM | Uses default Bedrock | Not configurable per-agent |

---

## Key Limitation

**Tools are baked into the Docker image.** To add/remove tools, you must:

1. Edit `docker/agent_runner.py` 
2. Rebuild the Docker image (`./scripts/build_docker.sh`)

There's no way to specify tools per-agent at runtime currently.

---

## Current Tools in Container

From `docker/agent_runner.py`:

**Core Tools (strands_tools):**
- `file_read` - Read files
- `file_write` - Write files
- `editor` - Edit files with precision
- `shell` - Execute shell commands
- `use_agent` - Spawn sub-agents
- `python_repl` - Run Python code
- `load_tool` - Dynamically load tools

**GitHub Tools (github_tools.py):**
- `create_issue` - Create new issues
- `get_issue` - Get issue details
- `update_issue` - Update issue title/body/state
- `list_issues` - List issues by state
- `get_issue_comments` - Get comments for an issue
- `add_issue_comment` - Add comment to issue/PR
- `create_pull_request` - Create new PR
- `get_pull_request` - Get PR details
- `update_pull_request` - Update PR title/body/base
- `list_pull_requests` - List PRs by state
- `get_pr_review_and_comments` - Get PR review threads
- `reply_to_review_comment` - Reply to PR review comment
