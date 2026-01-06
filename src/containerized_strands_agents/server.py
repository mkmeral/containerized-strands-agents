"""FastMCP Server for Agent Host."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastmcp import FastMCP

from containerized_strands_agents.agent_manager import AgentManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global agent manager instance
agent_manager: AgentManager | None = None


def _parse_system_prompts_env() -> list[dict[str, str]]:
    """Parse the CONTAINERIZED_AGENTS_SYSTEM_PROMPTS environment variable.
    
    Returns:
        List of dicts with 'name' and 'path' keys for each available system prompt.
    """
    env_var = os.environ.get("CONTAINERIZED_AGENTS_SYSTEM_PROMPTS", "")
    if not env_var:
        return []
    
    prompts = []
    for file_path in env_var.split(","):
        file_path = file_path.strip()
        if not file_path:
            continue
            
        try:
            path_obj = Path(file_path).expanduser().resolve()
            if not path_obj.exists() or not path_obj.is_file():
                logger.warning(f"System prompt file not found or not a file: {file_path}")
                continue
            
            # Try to extract display name from first line
            display_name = None
            try:
                with open(path_obj, 'r', encoding='utf-8') as f:
                    first_line = f.readline().strip()
                    if first_line.startswith('#'):
                        display_name = first_line[1:].strip()
            except Exception as e:
                logger.warning(f"Could not read first line of {file_path}: {e}")
            
            # Fallback to filename if no display name found
            if not display_name:
                display_name = path_obj.stem
            
            prompts.append({
                'name': display_name,
                'path': str(path_obj)
            })
            
        except Exception as e:
            logger.warning(f"Could not process system prompt file {file_path}: {e}")
            continue
    
    return prompts


def _build_send_message_docstring() -> str:
    """Build the docstring for send_message with dynamic system prompt list."""
    base_docstring = """Send a message to an agent (fire-and-forget). Creates the agent if it doesn't exist.

    This returns immediately after dispatching the message. The agent processes
    the message in the background. Use get_messages to check for the response.

    Args:
        agent_id: Unique identifier for the agent. Use descriptive names like 
                  "code-reviewer", "data-analyst", etc.
        message: The message to send to the agent.
        aws_profile: AWS profile name to use (from ~/.aws/credentials). 
                     If not specified, uses default credentials.
        aws_region: AWS region for Bedrock. Defaults to us-east-1.
        system_prompt: Custom system prompt for the agent. If provided on first 
                       message, this will override the default system prompt and 
                       persist across container restarts.
        system_prompt_file: Path to a file on the host machine containing the system 
                            prompt. If both system_prompt and system_prompt_file are 
                            provided, system_prompt_file takes precedence.
        tools: List of paths to .py tool files that only this specific agent gets.
               These tools are loaded in addition to any global tools.
        data_dir: Custom data directory for this agent. If provided, agent data 
                  (workspace, session, tools) will be stored there instead of the 
                  default location. Useful for project-specific agents.
        mcp_config: MCP server configuration dict (same format as Kiro/Claude Desktop).
                    Example: {"mcpServers": {"github": {"command": "uvx", "args": ["mcp-server-github"]}}}
                    Persisted to agent's .agent/mcp.json and used on subsequent messages.
        mcp_config_file: Path to an existing mcp.json file on the host machine.
                         The config is read and persisted to the agent's .agent/mcp.json.
                         Takes precedence over mcp_config if both are provided.
                         Tip: Point to your existing ~/.kiro/settings/mcp.json or similar.
        description: Brief description of the agent's purpose (1-2 sentences).
                     Helps identify agents when using list_agents. Set on first message
                     or updated if provided again."""

    # Get available system prompts
    available_prompts = _parse_system_prompts_env()
    if available_prompts:
        prompt_list = "\n    Available system prompts:\n"
        for prompt in available_prompts:
            prompt_list += f"    - {prompt['name']}: {prompt['path']}\n"
        base_docstring += prompt_list

    base_docstring += """

    Returns:
        dict with status ("dispatched", "queued", or "error") and agent_id."""

    return base_docstring


@asynccontextmanager
async def lifespan(app):
    """Manage agent manager lifecycle."""
    global agent_manager
    agent_manager = AgentManager()
    await agent_manager.start_idle_monitor()
    logger.info("Agent Host MCP Server started")
    yield
    agent_manager.stop_idle_monitor()
    logger.info("Agent Host MCP Server stopped")


mcp = FastMCP(
    name="Agent Host",
    instructions="""This MCP server spawns background worker agents in Docker containers.

IMPORTANT: These are autonomous background workers, NOT interactive assistants.
- send_message dispatches work to an agent and returns immediately
- Agents work independently in the background (can take minutes to hours)
- Do NOT invoke get_messages multiple times waiting for results. Give time to agents for them to work and complete their task.
- Use get_messages only when a human explicitly asks to check on an agent's progress

Typical workflow:
1. Use send_message to assign a task to an agent
2. Move on to other work - the agent runs autonomously  
3. Check results later via get_messages only if explicitly asked by the user

Use list_agents to see all agents and their status.
Use stop_agent to terminate an agent's container.
""",
)


async def _send_message(
    agent_id: str,
    message: str,
    aws_profile: str | None = None,
    aws_region: str | None = None,
    system_prompt: str | None = None,
    system_prompt_file: str | None = None,
    tools: list[str] | None = None,
    data_dir: str | None = None,
    mcp_config: dict | None = None,
    mcp_config_file: str | None = None,
    description: str | None = None,
) -> dict:
    if not agent_manager:
        return {"status": "error", "error": "Agent manager not initialized"}
    
    logger.info(f"Sending message to agent {agent_id}")
    result = await agent_manager.send_message(
        agent_id, 
        message,
        aws_profile=aws_profile,
        aws_region=aws_region,
        system_prompt=system_prompt,
        system_prompt_file=system_prompt_file,
        tools=tools,
        data_dir=data_dir,
        mcp_config=mcp_config,
        mcp_config_file=mcp_config_file,
        description=description,
    )
    return result

# Dynamically set the docstring and register the tool with explicit name
_send_message.__doc__ = _build_send_message_docstring()
send_message = mcp.tool(name="send_message")(_send_message)


@mcp.tool
async def get_messages(agent_id: str, count: int = 1, include_tool_messages: bool = False) -> dict:
    """Get the latest messages from an agent's conversation history.

    IMPORTANT: Do not poll this endpoint repeatedly. Use it on-demand when you
    need to check an agent's response, not in a loop.

    Args:
        agent_id: The agent to get messages from.
        count: Number of messages to retrieve (default: 1, returns last message).
        include_tool_messages: If True, include tool_use and tool_result messages.
                              Defaults to False to keep responses smaller.

    Returns:
        dict with status, messages, agent's data_dir path, and processing state.
    """
    if not agent_manager:
        return {"status": "error", "error": "Agent manager not initialized"}
    
    return await agent_manager.get_messages(agent_id, count, include_tool_messages)


@mcp.tool
async def list_agents() -> dict:
    """List all agents and their current status.
    
    Returns:
        dict with list of agents including id, status, data_dir, and last activity.
    """
    if not agent_manager:
        return {"status": "error", "error": "Agent manager not initialized"}
    
    agents = await agent_manager.list_agents()
    return {"status": "success", "agents": agents}


@mcp.tool
async def stop_agent(agent_id: str) -> dict:
    """Stop an agent's Docker container immediately.
    
    Args:
        agent_id: The ID of the agent to stop.
    
    Returns:
        dict with status ("success" or "error") and details about the operation.
    """
    if not agent_manager:
        return {"status": "error", "error": "Agent manager not initialized"}
    
    logger.info(f"Stopping agent {agent_id}")
    success = await agent_manager.stop_agent(agent_id)
    
    if success:
        return {
            "status": "success", 
            "message": f"Agent {agent_id} has been stopped successfully"
        }
    else:
        return {
            "status": "error", 
            "error": f"Failed to stop agent {agent_id}. Agent may not exist or container not found."
        }


def main():
    """Run the MCP server."""
    import sys
    
    async def run():
        global agent_manager
        agent_manager = AgentManager()
        await agent_manager.start_idle_monitor()
        try:
            await mcp.run_async()
        finally:
            agent_manager.stop_idle_monitor()
    
    asyncio.run(run())


if __name__ == "__main__":
    main()
