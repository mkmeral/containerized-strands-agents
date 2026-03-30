"""Tests for MCP Task Protocol Handlers."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from mcp.shared.exceptions import McpError
from containerized_strands_agents.task_store import TaskStore
from containerized_strands_agents.task_handlers import register_task_handlers
from mcp.types import (
    CancelTaskRequest,
    CancelTaskRequestParams,
    GetTaskPayloadRequest,
    GetTaskPayloadRequestParams,
    GetTaskRequest,
    GetTaskRequestParams,
    ListTasksRequest,
    TASK_STATUS_WORKING,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_CANCELLED,
)


@pytest.fixture
def task_store():
    return TaskStore()


@pytest.fixture
def mock_agent_manager():
    manager = AsyncMock()
    manager.stop_agent = AsyncMock(return_value=True)
    return manager


@pytest.fixture
def mock_mcp_server():
    """Create a mock FastMCP server with _mcp_server attribute."""
    mcp = MagicMock()
    mcp._mcp_server = MagicMock()
    mcp._mcp_server.request_handlers = {}
    return mcp


@pytest.fixture
def registered_handlers(mock_mcp_server, task_store, mock_agent_manager):
    """Register handlers and return the handlers dict."""
    register_task_handlers(mock_mcp_server, task_store, mock_agent_manager)
    return mock_mcp_server._mcp_server.request_handlers


@pytest.mark.asyncio
async def test_handlers_registered(registered_handlers):
    """Test that all task handlers are registered."""
    assert GetTaskRequest in registered_handlers
    assert ListTasksRequest in registered_handlers
    assert CancelTaskRequest in registered_handlers
    assert GetTaskPayloadRequest in registered_handlers


@pytest.mark.asyncio
async def test_get_task_handler(registered_handlers, task_store):
    """Test tasks/get handler returns task info."""
    task = await task_store.create_task("test-agent", "Hello")
    
    req = GetTaskRequest(
        method="tasks/get",
        params=GetTaskRequestParams(taskId=task.taskId),
    )
    
    handler = registered_handlers[GetTaskRequest]
    result = await handler(req)
    
    # GetTaskResult extends Task - check task fields are present
    assert result.root is not None
    assert result.root.taskId == task.taskId
    assert result.root.status == TASK_STATUS_WORKING


@pytest.mark.asyncio
async def test_get_task_handler_not_found(registered_handlers):
    """Test tasks/get handler raises McpError for non-existent task."""
    req = GetTaskRequest(
        method="tasks/get",
        params=GetTaskRequestParams(taskId="task-nonexistent"),
    )
    
    handler = registered_handlers[GetTaskRequest]
    
    with pytest.raises(McpError) as exc_info:
        await handler(req)
    
    assert exc_info.value.error.code == -32001
    assert "not found" in exc_info.value.error.message


@pytest.mark.asyncio
async def test_list_tasks_handler(registered_handlers, task_store):
    """Test tasks/list handler returns all tasks."""
    await task_store.create_task("agent-1", "msg 1")
    await task_store.create_task("agent-2", "msg 2")
    
    req = ListTasksRequest(method="tasks/list")
    
    handler = registered_handlers[ListTasksRequest]
    result = await handler(req)
    
    assert result.root is not None
    assert hasattr(result.root, 'tasks')
    assert len(result.root.tasks) == 2


@pytest.mark.asyncio
async def test_list_tasks_handler_empty(registered_handlers, task_store):
    """Test tasks/list handler returns empty list when no tasks."""
    req = ListTasksRequest(method="tasks/list")
    
    handler = registered_handlers[ListTasksRequest]
    result = await handler(req)
    
    assert result.root is not None
    assert result.root.tasks == []


@pytest.mark.asyncio
async def test_cancel_task_handler(registered_handlers, task_store, mock_agent_manager):
    """Test tasks/cancel handler cancels task and stops agent."""
    task = await task_store.create_task("test-agent", "Hello")
    
    req = CancelTaskRequest(
        method="tasks/cancel",
        params=CancelTaskRequestParams(taskId=task.taskId),
    )
    
    handler = registered_handlers[CancelTaskRequest]
    result = await handler(req)
    
    # CancelTaskResult extends Task - check task is cancelled
    assert result.root is not None
    assert result.root.taskId == task.taskId
    assert result.root.status == TASK_STATUS_CANCELLED
    
    # Should have called stop_agent
    mock_agent_manager.stop_agent.assert_called_once_with("test-agent")


@pytest.mark.asyncio
async def test_cancel_task_handler_not_found(registered_handlers):
    """Test tasks/cancel handler raises McpError for non-existent task."""
    req = CancelTaskRequest(
        method="tasks/cancel",
        params=CancelTaskRequestParams(taskId="task-nonexistent"),
    )
    
    handler = registered_handlers[CancelTaskRequest]
    
    with pytest.raises(McpError) as exc_info:
        await handler(req)
    
    assert exc_info.value.error.code == -32001


@pytest.mark.asyncio
async def test_get_task_result_handler_no_results(registered_handlers, task_store):
    """Test tasks/result handler when task has no results yet."""
    task = await task_store.create_task("test-agent", "Hello")
    
    req = GetTaskPayloadRequest(
        method="tasks/result",
        params=GetTaskPayloadRequestParams(taskId=task.taskId),
    )
    
    handler = registered_handlers[GetTaskPayloadRequest]
    result = await handler(req)
    
    assert result.root is not None
    assert hasattr(result.root, 'content')
    assert len(result.root.content) == 1
    assert "no results yet" in result.root.content[0]["text"]


@pytest.mark.asyncio
async def test_get_task_result_handler_with_output(registered_handlers, task_store):
    """Test tasks/result handler when task has output messages."""
    task = await task_store.create_task("test-agent", "Hello")
    
    # Complete the task with output
    output = [{"role": "assistant", "content": [{"type": "text", "text": "Here are the results!"}]}]
    await task_store.update_status(
        task.taskId,
        status=TASK_STATUS_COMPLETED,
        output_messages=output,
    )
    
    req = GetTaskPayloadRequest(
        method="tasks/result",
        params=GetTaskPayloadRequestParams(taskId=task.taskId),
    )
    
    handler = registered_handlers[GetTaskPayloadRequest]
    result = await handler(req)
    
    assert result.root is not None
    assert hasattr(result.root, 'content')
    assert len(result.root.content) >= 1
    assert "Here are the results!" in result.root.content[0]["text"]


@pytest.mark.asyncio
async def test_get_task_result_handler_with_string_content(registered_handlers, task_store):
    """Test tasks/result handler when output has string content."""
    task = await task_store.create_task("test-agent", "Hello")
    
    output = [{"role": "assistant", "content": "Simple string response"}]
    await task_store.update_status(
        task.taskId,
        status=TASK_STATUS_COMPLETED,
        output_messages=output,
    )
    
    req = GetTaskPayloadRequest(
        method="tasks/result",
        params=GetTaskPayloadRequestParams(taskId=task.taskId),
    )
    
    handler = registered_handlers[GetTaskPayloadRequest]
    result = await handler(req)
    
    assert result.root is not None
    assert len(result.root.content) >= 1
    assert "Simple string response" in result.root.content[0]["text"]


@pytest.mark.asyncio
async def test_get_task_result_handler_with_error(registered_handlers, task_store):
    """Test tasks/result handler when task has an error."""
    task = await task_store.create_task("test-agent", "Hello")
    
    await task_store.update_status(
        task.taskId,
        status="failed",
        error="Container crashed",
    )
    
    req = GetTaskPayloadRequest(
        method="tasks/result",
        params=GetTaskPayloadRequestParams(taskId=task.taskId),
    )
    
    handler = registered_handlers[GetTaskPayloadRequest]
    result = await handler(req)
    
    assert result.root is not None
    assert hasattr(result.root, 'content')
    # Should contain the error message
    error_content = [c for c in result.root.content if "error" in c.get("text", "").lower()]
    assert len(error_content) >= 1
    assert "Container crashed" in error_content[0]["text"]


@pytest.mark.asyncio
async def test_get_task_result_handler_not_found(registered_handlers):
    """Test tasks/result handler raises McpError for non-existent task."""
    req = GetTaskPayloadRequest(
        method="tasks/result",
        params=GetTaskPayloadRequestParams(taskId="task-nonexistent"),
    )
    
    handler = registered_handlers[GetTaskPayloadRequest]
    
    with pytest.raises(McpError) as exc_info:
        await handler(req)
    
    assert exc_info.value.error.code == -32001
