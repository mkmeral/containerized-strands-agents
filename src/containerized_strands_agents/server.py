"""FastMCP Server for Agent Host with MCP Tasks support."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastmcp import FastMCP
from mcp.types import (
    ServerTasksCapability,
    TasksListCapability,
    TasksCancelCapability,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TaskStatusNotification,
    TaskStatusNotificationParams,
)

from containerized_strands_agents.agent_manager import AgentManager
from containerized_strands_agents.task_store import TaskStore
from containerized_strands_agents.task_handlers import register_task_handlers

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global instances
agent_manager: AgentManager | None = None
task_store: TaskStore | None = None


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
    base_docstring = """Send a message to an agent and get a task for tracking.

    Creates the agent if it doesn't exist. Returns an MCP Task object that 
    clients can use to track progress via the tasks protocol:
    - tasks/get: Check task status
    - tasks/list: List all tasks
    - tasks/cancel: Cancel a running task
    - tasks/result: Get task output

    The agent processes the message in the background. Task status automatically
    transitions from 'working' → 'completed' or 'failed'.

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
        dict with task info including taskId for tracking, status, and agent_id.
        Use the taskId with tasks/get, tasks/result, or tasks/cancel."""

    return base_docstring


mcp = FastMCP(
    name="Agent Host",
    instructions="""This MCP server spawns background worker agents in Docker containers.

IMPORTANT: These are autonomous background workers, NOT interactive assistants.

How it works:
1. send_message dispatches work to an agent and returns a Task immediately
2. Each Task has a taskId that you can use to track progress
3. Use tasks/get with the taskId to check if the agent is done
4. Use tasks/result with the taskId to get the agent's output
5. Use tasks/cancel with the taskId to stop a running task
6. Use tasks/list to see all tasks and their statuses

Task lifecycle: working → completed (success) or failed (error) or cancelled (stopped)

Typical workflow:
1. send_message("researcher", "Find all open issues") → returns Task with taskId
2. Move on to other work — the agent runs autonomously
3. Check status: tasks/get(taskId) → see if still 'working' or 'completed'
4. Get results: tasks/result(taskId) → see what the agent produced

Use list_agents to see all agents and their container status.
Use get_messages to read raw conversation history from an agent.
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
    if not agent_manager or not task_store:
        return {"status": "error", "error": "Server not initialized"}
    
    logger.info(f"Sending message to agent {agent_id}")
    
    # Create an MCP Task to track this dispatch
    task = await task_store.create_task(agent_id, message)
    
    # Get or create the agent container
    try:
        agent = await agent_manager.get_or_create_agent(
            agent_id,
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
    except Exception as e:
        # Mark task as failed
        await task_store.update_status(
            task.taskId,
            status=TASK_STATUS_FAILED,
            status_message=f"Failed to initialize agent: {e}",
            error=str(e),
        )
        return {
            "status": "error",
            "error": f"Failed to initialize agent: {e}",
            "taskId": task.taskId,
        }
    
    if agent.status != "running":
        await task_store.update_status(
            task.taskId,
            status=TASK_STATUS_FAILED,
            status_message=f"Agent not running: {agent.status}",
            error=f"Agent not running: {agent.status}",
        )
        return {
            "status": "error", 
            "error": f"Agent not running: {agent.status}",
            "taskId": task.taskId,
        }

    # Update agent's last activity
    from datetime import datetime, timezone
    agent.last_activity = datetime.now(timezone.utc).isoformat()
    agent_manager.tracker.update_agent(agent)
    
    # Fire and forget — dispatch message and track completion via task
    asyncio.create_task(
        _dispatch_and_track(agent_id, agent.port, agent.data_dir, message, task.taskId)
    )
    
    return {
        "status": "dispatched",
        "agent_id": agent_id,
        "taskId": task.taskId,
        "taskStatus": task.status,
        "message": (
            f"Task {task.taskId} created. Agent '{agent_id}' is processing. "
            f"Use tasks/get or tasks/result with taskId to check progress."
        ),
    }

# Dynamically set the docstring and register the tool with explicit name
_send_message.__doc__ = _build_send_message_docstring()
send_message = mcp.tool(name="send_message")(_send_message)


async def _dispatch_and_track(
    agent_id: str,
    port: int,
    data_dir: str | None,
    message: str,
    task_id: str,
):
    """Dispatch message to agent container and update task on completion.
    
    This is the bridge between the fire-and-forget dispatch and the MCP Tasks
    protocol. When the agent finishes (or fails), the task is updated.
    """
    import httpx
    
    url = f"http://localhost:{port}/chat"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(3600.0, connect=30.0)) as client:
            resp = await client.post(url, json={"message": message})
            
            if resp.status_code == 200:
                # Agent finished successfully — get the latest messages for the task payload
                output_messages = []
                if agent_manager:
                    try:
                        result = await agent_manager.get_messages(
                            agent_id, count=1, include_tool_messages=False, update_last_read=False
                        )
                        output_messages = result.get("messages", [])
                    except Exception as e:
                        logger.warning(f"Failed to get messages for task {task_id}: {e}")
                
                if task_store:
                    await task_store.update_status(
                        task_id,
                        status=TASK_STATUS_COMPLETED,
                        status_message=f"Agent '{agent_id}' completed successfully",
                        output_messages=output_messages,
                    )
            else:
                if task_store:
                    await task_store.update_status(
                        task_id,
                        status=TASK_STATUS_FAILED,
                        status_message=f"Agent '{agent_id}' returned HTTP {resp.status_code}",
                        error=f"HTTP {resp.status_code}: {resp.text[:500]}",
                    )
                    
    except httpx.TimeoutException:
        if task_store:
            await task_store.update_status(
                task_id,
                status=TASK_STATUS_FAILED,
                status_message=f"Agent '{agent_id}' timed out",
                error="Request timed out after 3600 seconds",
            )
    except Exception as e:
        logger.warning(f"Message dispatch to {agent_id} ended: {e}")
        if task_store:
            # Check if agent is still processing — connection drops don't mean failure
            try:
                agent = agent_manager.tracker.get_agent(agent_id)
                if agent and agent.container_id:
                    is_running = agent_manager._is_container_running(agent.container_id)
                    if is_running:
                        # Agent is still running, check if processing
                        processing = await agent_manager._get_agent_processing_state(agent)
                        if not processing:
                            # Agent finished but we lost the connection — get results
                            result = await agent_manager.get_messages(
                                agent_id, count=1, include_tool_messages=False, update_last_read=False
                            )
                            await task_store.update_status(
                                task_id,
                                status=TASK_STATUS_COMPLETED,
                                status_message=f"Agent '{agent_id}' completed (connection dropped but agent finished)",
                                output_messages=result.get("messages", []),
                            )
                            return
                        # else: still processing, leave task as working
                        return
            except Exception:
                pass
            
            await task_store.update_status(
                task_id,
                status=TASK_STATUS_FAILED,
                status_message=f"Agent '{agent_id}' dispatch failed: {e}",
                error=str(e),
            )


@mcp.tool
async def get_messages(
    agent_id: str, 
    count: int = 1, 
    include_tool_messages: bool = False,
    auto_restart: bool = False,
) -> dict:
    """Get the latest messages from an agent's conversation history.

    NOTE: For task-based tracking, prefer using tasks/get and tasks/result
    with the taskId returned by send_message. This tool provides direct 
    access to the full conversation history.

    Args:
        agent_id: The agent to get messages from.
        count: Number of messages to retrieve (default: 1, returns last message).
        include_tool_messages: If True, include tool_use and tool_result messages.
                              Defaults to False to keep responses smaller.
        auto_restart: If True and the agent's container is stopped, automatically
                     restart it before fetching messages. Defaults to False.

    Returns:
        dict with messages, container status, and processing state.
    """
    if not agent_manager:
        return {"status": "error", "error": "Agent manager not initialized"}
    
    return await agent_manager.get_messages(agent_id, count, include_tool_messages, auto_restart=auto_restart)


@mcp.tool
async def list_agents(unread_only: bool = False) -> dict:
    """List all agents and their current status.
    
    Args:
        unread_only: If True, only return agents with unread messages.
                    Useful for checking which agents have new responses.
    
    Returns:
        dict with list of agents including id, status, data_dir, has_unread, 
        and active task info.
    """
    if not agent_manager or not task_store:
        return {"status": "error", "error": "Server not initialized"}
    
    agents = await agent_manager.list_agents()
    
    # Enrich with active task info
    for agent_data in agents:
        agent_id = agent_data.get("agent_id")
        active_task = await task_store.get_active_task_for_agent(agent_id)
        if active_task:
            agent_data["active_task"] = {
                "taskId": active_task.taskId,
                "status": active_task.status,
                "statusMessage": active_task.statusMessage,
                "createdAt": active_task.createdAt.isoformat(),
            }
        else:
            agent_data["active_task"] = None
    
    if unread_only:
        agents = [a for a in agents if a.get("has_unread", False)]
    
    return {"status": "success", "agents": agents}


@mcp.tool
async def stop_agent(agent_id: str) -> dict:
    """Stop an agent's Docker container immediately.
    
    This also cancels any active tasks for the agent.
    
    Args:
        agent_id: The ID of the agent to stop.
    
    Returns:
        dict with status and details about the operation.
    """
    if not agent_manager or not task_store:
        return {"status": "error", "error": "Server not initialized"}
    
    logger.info(f"Stopping agent {agent_id}")
    
    # Cancel any active tasks for this agent
    active_task = await task_store.get_active_task_for_agent(agent_id)
    if active_task:
        await task_store.cancel_task(active_task.taskId)
        logger.info(f"Cancelled active task {active_task.taskId} for agent {agent_id}")
    
    success = await agent_manager.stop_agent(agent_id)
    
    if success:
        return {
            "status": "success", 
            "message": f"Agent {agent_id} has been stopped successfully",
            "cancelled_task": active_task.taskId if active_task else None,
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
        global agent_manager, task_store
        
        agent_manager = AgentManager()
        task_store = TaskStore()
        
        await agent_manager.start_idle_monitor()
        
        # Reconcile tasks with actual container states after restart
        await task_store.reconcile_with_agents(agent_manager)
        
        # Register MCP task protocol handlers
        register_task_handlers(mcp, task_store, agent_manager)
        
        # Set up task notification callback
        async def send_task_notification(task_id: str, task):
            """Send task status notification to connected clients."""
            try:
                notification = TaskStatusNotification(
                    method="notifications/tasks/status",
                    params=TaskStatusNotificationParams(
                        taskId=task.taskId,
                        status=task.status,
                        statusMessage=task.statusMessage,
                        createdAt=task.createdAt,
                        lastUpdatedAt=task.lastUpdatedAt,
                        ttl=task.ttl,
                        pollInterval=task.pollInterval,
                    ),
                )
                # Send via the underlying MCP server session if available
                if hasattr(mcp, '_mcp_server') and mcp._mcp_server:
                    server = mcp._mcp_server
                    if hasattr(server, 'request_context') and server.request_context:
                        session = server.request_context.session
                        if session:
                            await session.send_notification(notification)
                            logger.debug(f"Sent task status notification for {task_id}")
            except Exception as e:
                logger.debug(f"Could not send task notification for {task_id}: {e}")
        
        task_store.set_notification_callback(send_task_notification)
        
        logger.info("Agent Host MCP Server started with Tasks support (file-backed persistence)")
        
        try:
            await mcp.run_async()
        finally:
            agent_manager.stop_idle_monitor()
    
    asyncio.run(run())


if __name__ == "__main__":
    main()
