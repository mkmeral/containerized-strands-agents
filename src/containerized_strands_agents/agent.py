"""Shared agent logic for creating and running Strands agents."""

import json
import logging
import os
from pathlib import Path
from typing import Optional

from strands import Agent
from strands.agent.conversation_manager import SummarizingConversationManager
from strands.session.file_session_manager import FileSessionManager
from strands_tools import (
    file_read,
    file_write,
    editor,
    shell,
    use_agent,
    python_repl,
    load_tool,
)

# GitHub tools are only available in Docker container
try:
    from github_tools import (
        create_issue,
        get_issue,
        update_issue,
        list_issues,
        get_issue_comments,
        add_issue_comment,
        create_pull_request,
        get_pull_request,
        update_pull_request,
        list_pull_requests,
        get_pr_review_and_comments,
        reply_to_review_comment,
    )
    GITHUB_TOOLS = [
        create_issue, get_issue, update_issue, list_issues, get_issue_comments, add_issue_comment,
        create_pull_request, get_pull_request, update_pull_request, list_pull_requests,
        get_pr_review_and_comments, reply_to_review_comment,
    ]
except ImportError:
    GITHUB_TOOLS = []

logger = logging.getLogger(__name__)


def get_env_capabilities() -> str:
    """Get available capabilities from environment metadata."""
    metadata_str = os.getenv("AGENT_ENV_METADATA", "{}")
    try:
        metadata = json.loads(metadata_str)
        caps = [v["capability"] for v in metadata.values() if v.get("available")]
        return "\n".join(f"- {c}" for c in caps) if caps else ""
    except Exception:
        return ""


def load_system_prompt(data_dir: Path, custom_system_prompt: Optional[str] = None) -> str:
    """Load system prompt, preferring custom if available.
    
    Args:
        data_dir: Path to the agent data directory
        custom_system_prompt: Optional custom system prompt to use directly
        
    Returns:
        The system prompt to use for the agent
    """
    # If custom prompt is provided directly, use it
    if custom_system_prompt:
        return custom_system_prompt
    
    # Try to load from file if enabled
    custom_prompt_file = data_dir / ".agent" / "system_prompt.txt"
    if os.getenv("CUSTOM_SYSTEM_PROMPT") == "true" and custom_prompt_file.exists():
        try:
            base_prompt = custom_prompt_file.read_text()
            logger.info("Using custom system prompt from file")
        except Exception as e:
            logger.error(f"Failed to load custom system prompt: {e}")
            logger.info("Falling back to default system prompt")
            base_prompt = None
    else:
        base_prompt = None
    
    if not base_prompt:
        # Detect if running in Docker (data_dir starts with /data)
        is_docker = str(data_dir).startswith("/data")
        workspace_path = str(data_dir / "workspace") if is_docker else str(data_dir / "workspace")
        
        base_prompt = f"""You are a helpful AI assistant{"" if not is_docker else " running in an isolated Docker container"}.

IMPORTANT: Your persistent workspace is {workspace_path}. ALWAYS work in this directory.
- Clone repos here: cd {workspace_path} && git clone ...
- Create files here: {workspace_path}/myproject/...
- This directory {"is mounted from the host and " if is_docker else ""}persists across {"container restarts" if is_docker else "sessions"}.
- Do NOT use /tmp or other directories - they will be lost.

Available tools:
- file_read, file_write, editor: File operations (use paths relative to {workspace_path})
- shell: Execute shell commands (always cd to {workspace_path} first)
- python_repl: Run Python code
- use_agent: Spawn sub-agents for complex tasks
- load_tool: Dynamically load additional tools

When given a task:
1. Work in {workspace_path}
2. Be thorough but concise
3. Test your work before committing
4. Commit with clear messages
"""
    
    # Append environment capabilities if any
    capabilities = get_env_capabilities()
    if capabilities:
        base_prompt += f"\n\nEnvironment capabilities:\n{capabilities}"
    
    return base_prompt


def load_dynamic_tools(agent: Agent, tools_dir: Optional[Path] = None):
    """Load tools dynamically from a directory.
    
    Args:
        agent: The agent to load tools into
        tools_dir: Optional directory containing tool files. If None, no dynamic loading occurs.
    """
    if not tools_dir:
        return
    
    if not tools_dir.exists():
        logger.info(f"Tools directory not found: {tools_dir}")
        return
    
    # Find all .py files in the tools directory
    tool_files = list(tools_dir.glob("*.py"))
    if not tool_files:
        logger.info(f"No .py files found in {tools_dir}")
        return
    
    logger.info(f"Loading {len(tool_files)} dynamic tools from {tools_dir}")
    
    for tool_file in tool_files:
        try:
            # Extract tool name from filename (without .py extension)
            tool_name = tool_file.stem
            
            # Use the load_tool function to dynamically load the tool
            agent.tool.load_tool(path=str(tool_file), name=tool_name)
            logger.info(f"Successfully loaded dynamic tool: {tool_name}")
        except Exception as e:
            logger.error(f"Failed to load tool {tool_file}: {e}")


def create_agent(
    data_dir: Path,
    system_prompt: Optional[str] = None,
    tools_dir: Optional[Path] = None,
    agent_id: str = "agent",
) -> Agent:
    """Create a configured Strands Agent.
    
    Args:
        data_dir: Path to the agent data directory (will be created if it doesn't exist)
        system_prompt: Optional custom system prompt. If None, loads from file or uses default
        tools_dir: Optional directory containing custom tools to load
        agent_id: Agent ID for session management (default: "agent")
        
    Returns:
        Configured Strands Agent instance
    """
    # Ensure data directory structure exists
    data_dir = Path(data_dir).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    
    workspace_dir = data_dir / "workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    
    session_dir = data_dir / ".agent" / "session"
    session_dir.mkdir(parents=True, exist_ok=True)
    
    # Load system prompt
    prompt = load_system_prompt(data_dir, system_prompt)
    
    # Create session manager
    session_manager = FileSessionManager(
        session_id=agent_id,
        storage_dir=str(session_dir)
    )
    
    # Create agent with session manager and summarizing conversation manager
    base_tools = [file_read, file_write, editor, shell, use_agent, python_repl, load_tool]
    agent = Agent(
        system_prompt=prompt,
        tools=base_tools + GITHUB_TOOLS,
        session_manager=session_manager,
        conversation_manager=SummarizingConversationManager(
            summary_ratio=0.3,  # Summarize 30% of messages when context reduction needed
            preserve_recent_messages=10,  # Always keep 10 most recent messages
        ),
        model="global.anthropic.claude-sonnet-4-5-20250929-v1:0",
    )
    logger.info(f"Agent initialized with session at {session_dir}")
    
    # Load dynamic tools if tools directory is provided
    load_dynamic_tools(agent, tools_dir)
    
    return agent


def run_agent(agent: Agent, message: str) -> str:
    """Run agent with a message and return the response.
    
    Args:
        agent: The configured agent instance
        message: The message to send to the agent
        
    Returns:
        The agent's response as a string
    """
    result = agent(message)
    return str(result)
