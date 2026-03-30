"""Tests for the TaskStore."""

import asyncio
import pytest
from datetime import datetime, timezone

from containerized_strands_agents.task_store import TaskStore, TaskPayload
from mcp.types import (
    TASK_STATUS_WORKING,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_CANCELLED,
)


@pytest.fixture
def task_store():
    """Create a fresh TaskStore for each test."""
    return TaskStore(ttl_ms=3600000, poll_interval_ms=5000)


@pytest.mark.asyncio
async def test_create_task(task_store):
    """Test creating a new task."""
    task = await task_store.create_task("test-agent", "Hello world")
    
    assert task.taskId.startswith("task-")
    assert task.status == TASK_STATUS_WORKING
    assert task.statusMessage == "Agent 'test-agent' is processing the message"
    assert task.ttl == 3600000
    assert task.pollInterval == 5000
    assert task.createdAt is not None
    assert task.lastUpdatedAt is not None
    assert task_store.task_count == 1


@pytest.mark.asyncio
async def test_create_multiple_tasks(task_store):
    """Test creating multiple tasks."""
    task1 = await task_store.create_task("agent-1", "msg 1")
    task2 = await task_store.create_task("agent-2", "msg 2")
    task3 = await task_store.create_task("agent-1", "msg 3")
    
    assert task_store.task_count == 3
    assert task1.taskId != task2.taskId
    assert task1.taskId != task3.taskId


@pytest.mark.asyncio
async def test_get_task(task_store):
    """Test getting a task by ID."""
    task = await task_store.create_task("test-agent", "Hello")
    
    retrieved = await task_store.get_task(task.taskId)
    assert retrieved is not None
    assert retrieved.taskId == task.taskId
    assert retrieved.status == TASK_STATUS_WORKING


@pytest.mark.asyncio
async def test_get_task_not_found(task_store):
    """Test getting a non-existent task."""
    result = await task_store.get_task("task-nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_get_payload(task_store):
    """Test getting a task's payload."""
    task = await task_store.create_task("test-agent", "Hello world")
    
    payload = await task_store.get_payload(task.taskId)
    assert payload is not None
    assert payload.agent_id == "test-agent"
    assert payload.input_message == "Hello world"
    assert payload.output_messages is None
    assert payload.error is None


@pytest.mark.asyncio
async def test_update_status_to_completed(task_store):
    """Test updating a task to completed status."""
    task = await task_store.create_task("test-agent", "Hello")
    
    output = [{"role": "assistant", "content": [{"type": "text", "text": "Done!"}]}]
    updated = await task_store.update_status(
        task.taskId,
        status=TASK_STATUS_COMPLETED,
        status_message="Agent finished",
        output_messages=output,
    )
    
    assert updated is not None
    assert updated.status == TASK_STATUS_COMPLETED
    assert updated.statusMessage == "Agent finished"
    assert updated.lastUpdatedAt > task.createdAt
    
    # Verify payload was updated
    payload = await task_store.get_payload(task.taskId)
    assert payload.output_messages == output


@pytest.mark.asyncio
async def test_update_status_to_failed(task_store):
    """Test updating a task to failed status."""
    task = await task_store.create_task("test-agent", "Hello")
    
    updated = await task_store.update_status(
        task.taskId,
        status=TASK_STATUS_FAILED,
        status_message="Agent crashed",
        error="Container exited with code 1",
    )
    
    assert updated.status == TASK_STATUS_FAILED
    assert updated.statusMessage == "Agent crashed"
    
    payload = await task_store.get_payload(task.taskId)
    assert payload.error == "Container exited with code 1"


@pytest.mark.asyncio
async def test_cannot_update_terminal_task(task_store):
    """Test that terminal tasks cannot be updated."""
    task = await task_store.create_task("test-agent", "Hello")
    
    # Complete it
    await task_store.update_status(task.taskId, status=TASK_STATUS_COMPLETED)
    
    # Try to update again — should return the task but not change status
    result = await task_store.update_status(
        task.taskId,
        status=TASK_STATUS_WORKING,
        status_message="Back to working",
    )
    
    assert result.status == TASK_STATUS_COMPLETED


@pytest.mark.asyncio
async def test_update_nonexistent_task(task_store):
    """Test updating a non-existent task."""
    result = await task_store.update_status("task-nonexistent", status=TASK_STATUS_COMPLETED)
    assert result is None


@pytest.mark.asyncio
async def test_cancel_task(task_store):
    """Test cancelling a task."""
    task = await task_store.create_task("test-agent", "Hello")
    
    cancelled = await task_store.cancel_task(task.taskId)
    assert cancelled.status == TASK_STATUS_CANCELLED
    assert cancelled.statusMessage == "Task cancelled by user"


@pytest.mark.asyncio
async def test_list_tasks(task_store):
    """Test listing all tasks."""
    await task_store.create_task("agent-1", "msg 1")
    await task_store.create_task("agent-2", "msg 2")
    await task_store.create_task("agent-1", "msg 3")
    
    tasks = await task_store.list_tasks()
    assert len(tasks) == 3
    
    # Should be sorted newest first
    assert tasks[0].createdAt >= tasks[1].createdAt


@pytest.mark.asyncio
async def test_list_tasks_by_agent(task_store):
    """Test listing tasks filtered by agent."""
    await task_store.create_task("agent-1", "msg 1")
    await task_store.create_task("agent-2", "msg 2")
    await task_store.create_task("agent-1", "msg 3")
    
    agent_1_tasks = await task_store.list_tasks(agent_id="agent-1")
    assert len(agent_1_tasks) == 2
    
    agent_2_tasks = await task_store.list_tasks(agent_id="agent-2")
    assert len(agent_2_tasks) == 1


@pytest.mark.asyncio
async def test_get_agent_id_for_task(task_store):
    """Test getting agent_id for a task."""
    task = await task_store.create_task("my-agent", "Hello")
    
    agent_id = await task_store.get_agent_id_for_task(task.taskId)
    assert agent_id == "my-agent"


@pytest.mark.asyncio
async def test_get_agent_id_for_nonexistent_task(task_store):
    """Test getting agent_id for non-existent task."""
    agent_id = await task_store.get_agent_id_for_task("task-nonexistent")
    assert agent_id is None


@pytest.mark.asyncio
async def test_get_active_task_for_agent(task_store):
    """Test getting the active task for an agent."""
    task1 = await task_store.create_task("test-agent", "msg 1")
    
    # Complete the first task
    await task_store.update_status(task1.taskId, status=TASK_STATUS_COMPLETED)
    
    # Create a second task
    task2 = await task_store.create_task("test-agent", "msg 2")
    
    active = await task_store.get_active_task_for_agent("test-agent")
    assert active is not None
    assert active.taskId == task2.taskId


@pytest.mark.asyncio
async def test_get_active_task_for_agent_none(task_store):
    """Test getting active task when none exist."""
    task = await task_store.create_task("test-agent", "msg")
    await task_store.update_status(task.taskId, status=TASK_STATUS_COMPLETED)
    
    active = await task_store.get_active_task_for_agent("test-agent")
    assert active is None


@pytest.mark.asyncio
async def test_cleanup_expired(task_store):
    """Test expired task cleanup."""
    # Create a task store with very short TTL
    short_ttl_store = TaskStore(ttl_ms=1, poll_interval_ms=100)
    
    await short_ttl_store.create_task("test-agent", "Hello")
    assert short_ttl_store.task_count == 1
    
    # Wait for TTL to expire
    await asyncio.sleep(0.01)
    
    await short_ttl_store.cleanup_expired()
    assert short_ttl_store.task_count == 0


@pytest.mark.asyncio
async def test_notification_callback(task_store):
    """Test that notification callback is called on status update."""
    notifications = []
    
    async def capture_notification(task_id, task):
        notifications.append((task_id, task.status))
    
    task_store.set_notification_callback(capture_notification)
    
    task = await task_store.create_task("test-agent", "Hello")
    
    # Update should trigger notification
    await task_store.update_status(task.taskId, status=TASK_STATUS_COMPLETED)
    
    assert len(notifications) == 1
    assert notifications[0][0] == task.taskId
    assert notifications[0][1] == TASK_STATUS_COMPLETED


@pytest.mark.asyncio
async def test_notification_callback_error_handled(task_store):
    """Test that notification callback errors are handled gracefully."""
    async def bad_callback(task_id, task):
        raise RuntimeError("Notification failed!")
    
    task_store.set_notification_callback(bad_callback)
    
    task = await task_store.create_task("test-agent", "Hello")
    
    # Should not raise, even though callback fails
    updated = await task_store.update_status(task.taskId, status=TASK_STATUS_COMPLETED)
    assert updated.status == TASK_STATUS_COMPLETED
