# Project Overview

Containerized Strands Agents is an MCP (Model Context Protocol) server that hosts isolated
Strands AI agents in Docker containers. Each agent runs independently with its own workspace,
persists conversation history across restarts, and supports custom system prompts, per-agent
tools, and GitHub integration. The fire-and-forget architecture enables autonomous background
task execution while the host manages container lifecycle, idle timeouts, and session persistence.

## Repository Structure

- `src/containerized_strands_agents/` — Core MCP server: FastMCP tools, agent manager, Docker
  orchestration, and configuration
- `docker/` — Docker image definition: agent runner FastAPI server, GitHub tools, Strands agent
  setup
- `ui/` — Optional web UI: FastAPI REST wrapper and HTML interface for managing agents
- `scripts/` — Shell scripts for building Docker image and running the server
- `tests/` — Unit, integration, and end-to-end tests using pytest
- `data/` — Runtime persistence directory (gitignored): agent workspaces, sessions, task registry

## Build & Development Commands

```bash
# Install in development mode
pip install -e ".[dev]"

# Install with web UI support
pip install -e ".[webui]"

# Install all features
pip install -e ".[webui,dev]"

# Build Docker image (auto-built on first use, or manually)
./scripts/build_docker.sh

# Run MCP server directly
python -m containerized_strands_agents.server

# Run web UI (finds free port 8000-8100)
containerized-strands-agents-webui
# or
python run_web_ui.py

# Run tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_agent_manager.py -v

# Run integration tests (requires Docker)
python -m pytest tests/test_integration.py -v

# Run end-to-end tests (requires Docker + AWS credentials)
python -m pytest tests/test_e2e.py -v
```

## Code Style & Conventions

- Python 3.11+ required; type hints used throughout
- Formatting: Standard Python conventions; ~100 char line length preferred
- Naming: `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_SNAKE` for
  constants
- Async/await pattern for all I/O operations (Docker, HTTP, file system)
- Pydantic models for data validation (`AgentInfo`, request/response schemas)
- Logging via `logging` module; use `logger.info/warning/error` appropriately
- Environment variables prefixed with `CONTAINERIZED_AGENTS_` or `AGENT_HOST_`
- Docstrings: Google style for public functions and classes

> TODO: Add pre-commit hooks configuration for automated linting

## Architecture Notes

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              MCP Client (Kiro, etc.)                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FastMCP Server (server.py)                          │
│  Tools: send_message, get_messages, list_agents, stop_agent                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AgentManager (agent_manager.py)                      │
│  - Docker container lifecycle (create, start, stop)                         │
│  - TaskTracker: JSON-based agent registry persistence                       │
│  - Idle monitor: auto-stop containers after timeout                         │
│  - System prompt & tool management                                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    ▼                  ▼                  ▼
           ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
           │  Container 1 │   │  Container 2 │   │  Container N │
           │  (agent-foo) │   │  (agent-bar) │   │     ...      │
           │              │   │              │   │              │
           │ FastAPI:8080 │   │ FastAPI:8080 │   │ FastAPI:8080 │
           │ Strands Agent│   │ Strands Agent│   │ Strands Agent│
           └──────────────┘   └──────────────┘   └──────────────┘
                    │                  │                  │
                    ▼                  ▼                  ▼
           ┌──────────────────────────────────────────────────┐
           │              Host File System                    │
           │  data/agents/{agent_id}/                         │
           │    ├── workspace/     (persistent files)         │
           │    ├── session_{id}/  (conversation history)     │
           │    ├── tools/         (per-agent tools)          │
           │    └── system_prompt.txt                         │
           └──────────────────────────────────────────────────┘
```

**Data Flow:**
1. MCP client calls `send_message` with agent_id and message
2. AgentManager creates/restarts Docker container if needed
3. Message dispatched to container's `/chat` endpoint (fire-and-forget)
4. Strands Agent processes message using available tools
5. FileSessionManager persists conversation to mounted volume
6. Client polls `get_messages` to retrieve results when needed

**Key Components:**
- `FastMCP`: MCP protocol implementation exposing tools to clients
- `AgentManager`: Orchestrates Docker containers, manages state via `TaskTracker`
- `agent_runner.py`: FastAPI server inside container running Strands Agent
- `FileSessionManager`: Persists agent conversation history to JSON files
- `SummarizingConversationManager`: Intelligently summarizes old messages to manage context

## Testing Strategy

| Type        | Location                    | Runner                          | Notes                          |
|-------------|-----------------------------|---------------------------------|--------------------------------|
| Unit        | `tests/test_agent_manager.py` | `pytest`                       | Mocked Docker, fast            |
| Unit        | `tests/test_custom_system_prompt*.py` | `pytest`               | System prompt handling         |
| Integration | `tests/test_integration.py` | `pytest` (requires Docker)      | Real containers, short tasks   |
| E2E         | `tests/test_e2e.py`         | `pytest` (requires Docker+AWS)  | Full agent flow with Bedrock   |

```bash
# Run all tests
python -m pytest tests/ -v

# Run only unit tests (no Docker required)
python -m pytest tests/test_agent_manager.py tests/test_custom_system_prompt.py -v

# Run integration tests
python -m pytest tests/test_integration.py -v --timeout=120

# Run with coverage (if pytest-cov installed)
python -m pytest tests/ --cov=src/containerized_strands_agents --cov-report=html
```

Tests use `pytest-asyncio` with `asyncio_mode = "auto"` configured in `pyproject.toml`.

## Security & Compliance

**Secrets Handling:**
- AWS credentials: Mounted read-only from `~/.aws/` into containers
- GitHub token: Passed via `CONTAINERIZED_AGENTS_GITHUB_TOKEN` environment variable
- API keys (OpenAI, Google): Passed via environment variables, never logged
- System prompts can contain sensitive instructions; stored in agent data directories

**Container Isolation:**
- Each agent runs in isolated Docker container on `agent-host-net` bridge network
- Workspace mounted read-write; AWS credentials mounted read-only
- Tools directory mounted read-only to prevent agent modification
- `BYPASS_TOOL_CONSENT=true` set for automated operation (agents can execute tools freely)

**Dependency Scanning:**
> TODO: Add dependabot or similar for automated dependency updates

**License:** MIT (see LICENSE file)

## Agent Guardrails

**Files Never Modified by Agents:**
- Host system files outside mounted volumes
- `~/.aws/credentials` (read-only mount)
- Docker configuration and images
- MCP server source code

**Automatic Safeguards:**
- Idle timeout: Containers auto-stop after `AGENT_HOST_IDLE_TIMEOUT` minutes (default: 720/12hrs)
- Container isolation: Agents cannot access host network or other containers directly
- Retry limits: Max 3 retries with exponential backoff for transient errors

**Recommended Reviews:**
- Review agent output before committing to external repositories
- Audit `data/agents/*/workspace/` for unexpected file creation
- Monitor container resource usage for runaway processes

**Rate Limits:**
- Bedrock/Claude API rate limits apply per AWS account
- GitHub API rate limits apply per token (5000 requests/hour for authenticated)

## Extensibility Hooks

**Environment Variables:**
| Variable | Default | Description |
|----------|---------|-------------|
| `CONTAINERIZED_STRANDS_DATA_DIR` | `./data` | Base directory for all persistence |
| `AGENT_HOST_IDLE_TIMEOUT` | `720` | Minutes before idle container stops |
| `CONTAINERIZED_AGENTS_GITHUB_TOKEN` | — | GitHub PAT for git operations |
| `CONTAINERIZED_AGENTS_SYSTEM_PROMPTS` | — | Comma-separated paths to prompt files |
| `CONTAINERIZED_AGENTS_TOOLS` | — | Path to global tools directory |
| `OPENAI_API_KEY` | — | Passed to containers for OpenAI models |
| `GOOGLE_API_KEY` | — | Passed to containers for Gemini models |
| `AWS_BEARER_TOKEN_BEDROCK` | — | Cross-account Bedrock access |

**Per-Agent Customization:**
- `system_prompt`: Custom instructions via text or file path
- `tools`: List of `.py` files to load as additional Strands tools
- `data_dir`: Custom data directory for project-specific agents
- `aws_profile`: Different AWS credentials per agent
- `aws_region`: Different Bedrock region per agent

**Adding New Tools:**
1. Create `.py` file with `@tool` decorated functions (Strands tools format)
2. Place in global tools directory (`CONTAINERIZED_AGENTS_TOOLS`) or pass via `tools` parameter
3. Tools are copied to agent's `/app/tools/` and loaded via `load_tool` at startup

**Web UI Extension:**
- REST API at `ui/api.py` wraps MCP tools for HTTP access
- Extend by adding new FastAPI routes
- Static UI served from `ui/index.html`

## Further Reading

- [README.md](README.md) — Quick start guide and MCP configuration
- [docker/Dockerfile](docker/Dockerfile) — Container image specification
- [docker/agent_runner.py](docker/agent_runner.py) — In-container agent implementation

> TODO: Add docs/ARCHITECTURE.md with detailed design decisions
> TODO: Add docs/TROUBLESHOOTING.md for common issues
> TODO: Add ADR (Architecture Decision Records) directory
