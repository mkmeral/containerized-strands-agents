"""Tests for the TaskStore (file-backed persistence)."""

import asyncio
import json
import pytest
from datetime import datetime, timezone
from pathlib import Path

from containerized_strands_agents.task_store import TaskStore, TaskPayload
from mcp.types import (
    TASK_STATUS_WORKING,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_CANCELLED,
)


@pytest.fixture
def tmp_tasks_file(tmp_path):
    """Create a temporary tasks file path for each test."""
    return tmp_path / "mcp_tasks.json"


@pytest.fixture
def task_store(tmp_tasks_file):
    """Create a fresh TaskStore backed by a temp file for each test."""
    return TaskStore(tasks_file=tmp_tasks_file, ttl_ms=3600000, poll_interval_ms=5000)


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
async def test_create_task_persists_to_disk(task_store, tmp_tasks_file):
    """Test that creating a task writes to disk."""
    task = await task_store.create_task("test-agent", "Hello world")
    
    # Verify file exists and contains the task
    assert tmp_tasks_file.exists()
    data = json.loads(tmp_tasks_file.read_text())
    assert task.taskId in data
    assert data[task.taskId]["payload"]["agent_id"] == "test-agent"
    assert data[task.taskId]["payload"]["input_message"] == "Hello world"


@pytest.mark.asyncio
async def test_load_tasks_from_disk(tmp_tasks_file):
    """Test that tasks are loaded from disk on init."""
    # Create a store and add a task
    store1 = TaskStore(tasks_file=tmp_tasks_file, ttl_ms=3600000, poll_interval_ms=5000)
    task = await store1.create_task("test-agent", "Hello world")
    await store1.update_status(task.taskId, status=TASK_STATUS_COMPLETED, status_message="Done")
    
    # Create a new store from the same file — should load the task
    store2 = TaskStore(tasks_file=tmp_tasks_file, ttl_ms=3600000, poll_interval_ms=5000)
    assert store2.task_count == 1
    
    loaded_task = await store2.get_task(task.taskId)
    assert loaded_task is not None
    assert loaded_task.status == TASK_STATUS_COMPLETED
    assert loaded_task.statusMessage == "Done"
    
    loaded_payload = await store2.get_payload(task.taskId)
    assert loaded_payload is not None
    assert loaded_payload.agent_id == "test-agent"
    assert loaded_payload.input_message == "Hello world"


@pytest.mark.asyncio
async def test_load_from_nonexistent_file(tmp_path):
    """Test loading from a file that doesn't exist yet."""
    store = TaskStore(tasks_file=tmp_path / "nonexistent.json")
    assert store.task_count == 0


@pytest.mark.asyncio
async def test_load_from_corrupted_file(tmp_tasks_file):
    """Test loading from a corrupted JSON file."""
    tmp_tasks_file.write_text("not valid json {{{")
    store = TaskStore(tasks_file=tmp_tasks_file)
    assert store.task_count == 0


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
async def test_update_status_persists_to_disk(task_store, tmp_tasks_file):
    """Test that status updates are persisted to disk."""
    task = await task_store.create_task("test-agent", "Hello")
    
    await task_store.update_status(
        task.taskId,
        status=TASK_STATUS_COMPLETED,
        status_message="Done",
    )
    
    # Verify on disk
    data = json.loads(tmp_tasks_file.read_text())
    assert data[task.taskId]["task"]["status"] == TASK_STATUS_COMPLETED


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
async def test_cleanup_expired(tmp_path):
    """Test expired task cleanup."""
    # Create a task store with very short TTL
    tasks_file = tmp_path / "mcp_tasks.json"
    short_ttl_store = TaskStore(tasks_file=tasks_file, ttl_ms=1, poll_interval_ms=100)
    
    await short_ttl_store.create_task("test-agent", "Hello")
    assert short_ttl_store.task_count == 1
    
    # Wait for TTL to expire
    await asyncio.sleep(0.01)
    
    await short_ttl_store.cleanup_expired()
    assert short_ttl_store.task_count == 0
    
    # Verify cleanup persisted to disk
    data = json.loads(tasks_file.read_text())
    assert len(data) == 0


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


@pytest.mark.asyncio
async def test_persistence_survives_restart(tmp_tasks_file):
    """Test full restart scenario: create tasks, 'crash', reload."""
    # Phase 1: Create tasks
    store1 = TaskStore(tasks_file=tmp_tasks_file, ttl_ms=3600000, poll_interval_ms=5000)
    task_a = await store1.create_task("agent-a", "Task A message")
    task_b = await store1.create_task("agent-b", "Task B message")
    
    # Complete task A with output
    output = [{"role": "assistant", "content": [{"type": "text", "text": "Result A"}]}]
    await store1.update_status(task_a.taskId, status=TASK_STATUS_COMPLETED, output_messages=output)
    
    # Task B is still working when "crash" happens
    del store1  # Simulate crash
    
    # Phase 2: Restart — load from disk
    store2 = TaskStore(tasks_file=tmp_tasks_file, ttl_ms=3600000, poll_interval_ms=5000)
    assert store2.task_count == 2
    
    # Task A should be completed with output
    loaded_a = await store2.get_task(task_a.taskId)
    assert loaded_a.status == TASK_STATUS_COMPLETED
    payload_a = await store2.get_payload(task_a.taskId)
    assert payload_a.output_messages == output
    
    # Task B should still be working (reconciliation handles this separately)
    loaded_b = await store2.get_task(task_b.taskId)
    assert loaded_b.status == TASK_STATUS_WORKING
    payload_b = await store2.get_payload(task_b.taskId)
    assert payload_b.agent_id == "agent-b"


@pytest.mark.asyncio
async def test_cancel_persists_to_disk(task_store, tmp_tasks_file):
    """Test that task cancellation persists to disk."""
    task = await task_store.create_task("test-agent", "Hello")
    await task_store.cancel_task(task.taskId)
    
    # Verify on disk
    data = json.loads(tmp_tasks_file.read_text())
    assert data[task.taskId]["task"]["status"] == TASK_STATUS_CANCELLED
