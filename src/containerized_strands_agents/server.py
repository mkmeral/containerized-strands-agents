"""FastMCP Server for Agent Host."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastmcp import FastMCP

from containerized_strands_agents.agent_manager import AgentManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global agent manager instance
agent_manager: AgentManager | None = None


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
    instructions="""
    This MCP server hosts isolated AI agents in Docker containers.
    
    Use send_message to communicate with agents. If an agent doesn't exist,
    it will be created automatically. Each agent has its own isolated workspace
    and persists conversation history across restarts.
    
    Use get_messages to retrieve conversation history from an agent.
    Use list_agents to see all available agents and their status.
    """,
)


@mcp.tool
async def send_message(
    agent_id: str,
    message: str,
    aws_profile: str | None = None,
    aws_region: str | None = None,
) -> dict:
    """Send a message to an agent. Creates the agent if it doesn't exist.
    
    Args:
        agent_id: Unique identifier for the agent. Use descriptive names like 
                  "code-reviewer", "data-analyst", etc.
        message: The message to send to the agent.
        aws_profile: AWS profile name to use (from ~/.aws/credentials). 
                     If not specified, uses default credentials.
        aws_region: AWS region for Bedrock. Defaults to us-east-1.
    
    Returns:
        dict with status and response from the agent.
    """
    if not agent_manager:
        return {"status": "error", "error": "Agent manager not initialized"}
    
    logger.info(f"Sending message to agent {agent_id}")
    result = await agent_manager.send_message(
        agent_id, 
        message,
        aws_profile=aws_profile,
        aws_region=aws_region,
    )
    return result


@mcp.tool
async def get_messages(agent_id: str, count: int = 1) -> dict:
    """Get the latest messages from an agent's conversation history.
    
    Args:
        agent_id: The agent to get messages from.
        count: Number of messages to retrieve (default: 1, returns last message).
    
    Returns:
        dict with status and list of messages (role + content).
    """
    if not agent_manager:
        return {"status": "error", "error": "Agent manager not initialized"}
    
    return await agent_manager.get_messages(agent_id, count)


@mcp.tool
async def list_agents() -> dict:
    """List all agents and their current status.
    
    Returns:
        dict with list of agents including id, status, and last activity.
    """
    if not agent_manager:
        return {"status": "error", "error": "Agent manager not initialized"}
    
    agents = agent_manager.list_agents()
    return {"status": "success", "agents": agents}


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
