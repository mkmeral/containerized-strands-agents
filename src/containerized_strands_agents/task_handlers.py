"""MCP Task Protocol Handlers.

Registers tasks/get, tasks/list, tasks/cancel, and tasks/result handlers
with the FastMCP server to support the MCP Tasks protocol.

These handlers allow MCP clients to:
- Get task status (tasks/get)
- List all tasks (tasks/list)  
- Cancel running tasks (tasks/cancel)
- Get task results (tasks/result)
"""

import logging
from typing import TYPE_CHECKING

from mcp.shared.exceptions import McpError
from mcp.types import (
    CancelTaskRequest,
    CancelTaskResult,
    GetTaskPayloadRequest,
    GetTaskPayloadResult,
    GetTaskRequest,
    GetTaskResult,
    ListTasksRequest,
    ListTasksResult,
    ServerResult,
    ErrorData,
    TASK_STATUS_CANCELLED,
)

if TYPE_CHECKING:
    from containerized_strands_agents.task_store import TaskStore
    from containerized_strands_agents.agent_manager import AgentManager

logger = logging.getLogger(__name__)

# Error codes
TASK_NOT_FOUND = -32001
TASK_CANCEL_FAILED = -32002


def _task_to_result_kwargs(task) -> dict:
    """Extract Task fields as kwargs for result construction.
    
    GetTaskResult and CancelTaskResult extend both Result and Task,
    so they need the Task fields directly (not nested under a 'task' key).
    """
    return {
        "taskId": task.taskId,
        "status": task.status,
        "statusMessage": task.statusMessage,
        "createdAt": task.createdAt,
        "lastUpdatedAt": task.lastUpdatedAt,
        "ttl": task.ttl,
        "pollInterval": task.pollInterval,
    }


def register_task_handlers(
    mcp_server,
    task_store: "TaskStore",
    agent_manager: "AgentManager",
):
    """Register MCP task protocol handlers with the FastMCP server.
    
    This registers handlers for:
    - tasks/get: Get task status by ID
    - tasks/list: List all tasks  
    - tasks/cancel: Cancel a running task (stops the agent)
    - tasks/result: Get task payload/results
    
    Args:
        mcp_server: The FastMCP server instance.
        task_store: The TaskStore for task state.
        agent_manager: The AgentManager for agent operations (cancel → stop agent).
    """
    # Access the underlying MCP server's request handlers
    sdk_server = mcp_server._mcp_server

    async def handle_get_task(req: GetTaskRequest) -> ServerResult:
        """Handle tasks/get - return task status."""
        task_id = req.params.taskId
        task = await task_store.get_task(task_id)
        
        if not task:
            raise McpError(ErrorData(
                code=TASK_NOT_FOUND,
                message=f"Task {task_id} not found",
            ))
        
        return ServerResult(root=GetTaskResult(**_task_to_result_kwargs(task)))

    async def handle_list_tasks(req: ListTasksRequest) -> ServerResult:
        """Handle tasks/list - return all tasks."""
        tasks = await task_store.list_tasks()
        return ServerResult(root=ListTasksResult(tasks=tasks))

    async def handle_cancel_task(req: CancelTaskRequest) -> ServerResult:
        """Handle tasks/cancel - cancel a task and stop its agent."""
        task_id = req.params.taskId
        
        # Get the agent_id for this task
        agent_id = await task_store.get_agent_id_for_task(task_id)
        if not agent_id:
            raise McpError(ErrorData(
                code=TASK_NOT_FOUND,
                message=f"Task {task_id} not found",
            ))
        
        # Stop the agent container
        await agent_manager.stop_agent(agent_id)
        
        # Update task status to cancelled
        task = await task_store.cancel_task(task_id)
        
        if task:
            return ServerResult(root=CancelTaskResult(**_task_to_result_kwargs(task)))
        else:
            raise McpError(ErrorData(
                code=TASK_CANCEL_FAILED,
                message=f"Failed to cancel task {task_id}",
            ))

    async def handle_get_task_result(req: GetTaskPayloadRequest) -> ServerResult:
        """Handle tasks/result - return task payload (input/output)."""
        task_id = req.params.taskId
        
        task = await task_store.get_task(task_id)
        if not task:
            raise McpError(ErrorData(
                code=TASK_NOT_FOUND,
                message=f"Task {task_id} not found",
            ))
        
        payload = await task_store.get_payload(task_id)
        
        # Build content from payload
        content = []
        if payload:
            if payload.output_messages:
                # Extract text content from agent messages
                for msg in payload.output_messages:
                    role = msg.get("role", "")
                    msg_content = msg.get("content", [])
                    if isinstance(msg_content, list):
                        for item in msg_content:
                            if isinstance(item, dict) and item.get("type") == "text":
                                text = item.get("text", "")
                                if text.strip():
                                    content.append({
                                        "type": "text",
                                        "text": f"[{role}] {text}",
                                    })
                    elif isinstance(msg_content, str) and msg_content.strip():
                        content.append({
                            "type": "text",
                            "text": f"[{role}] {msg_content}",
                        })
            
            if payload.error:
                content.append({
                    "type": "text",
                    "text": f"[error] {payload.error}",
                })
        
        if not content:
            content.append({
                "type": "text",
                "text": f"Task {task_id} has no results yet (status: {task.status})",
            })
        
        return ServerResult(root=GetTaskPayloadResult(content=content))

    # Register handlers with the SDK server
    sdk_server.request_handlers[GetTaskRequest] = handle_get_task
    sdk_server.request_handlers[ListTasksRequest] = handle_list_tasks
    sdk_server.request_handlers[CancelTaskRequest] = handle_cancel_task
    sdk_server.request_handlers[GetTaskPayloadRequest] = handle_get_task_result

    logger.info("Registered MCP task protocol handlers (get, list, cancel, result)")
