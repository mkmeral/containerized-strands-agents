"""File-backed Task Store for MCP Tasks protocol.

Tracks task lifecycle (working → completed/failed/cancelled) for agent dispatches.
Each send_message creates a task. The agent_manager updates tasks as agents complete.

Tasks are persisted to disk (JSON file) on every mutation so they survive
server restarts, process crashes, and laptop sleep/wake cycles.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from mcp.types import (
    Task,
    TaskStatus,
    TASK_STATUS_WORKING,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_CANCELLED,
)
from pydantic import BaseModel

from containerized_strands_agents.config import DATA_DIR

logger = logging.getLogger(__name__)

# Default TTL: 24 hours in milliseconds
DEFAULT_TTL_MS = 24 * 60 * 60 * 1000

# Default poll interval: 5 seconds
DEFAULT_POLL_INTERVAL_MS = 5000

# Default tasks file path
DEFAULT_TASKS_FILE = DATA_DIR / "mcp_tasks.json"


class TaskPayload(BaseModel):
    """Stored payload/result for a task."""
    agent_id: str
    input_message: str
    output_messages: list[dict] | None = None
    error: str | None = None


class TaskStore:
    """File-backed store for MCP Tasks.
    
    Manages the lifecycle of tasks from creation through completion.
    Tasks map 1:1 with agent message dispatches.
    
    All mutations (create, update, cancel, cleanup) persist to disk
    immediately, following the same pattern as TaskTracker in agent_manager.
    On init, tasks are loaded from disk so state survives restarts.
    """

    def __init__(
        self,
        tasks_file: Path | None = None,
        ttl_ms: int = DEFAULT_TTL_MS,
        poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS,
    ):
        self._tasks_file = tasks_file or DEFAULT_TASKS_FILE
        self._tasks: dict[str, Task] = {}
        self._payloads: dict[str, TaskPayload] = {}
        self._lock = asyncio.Lock()
        self._ttl_ms = ttl_ms
        self._poll_interval_ms = poll_interval_ms
        # Callback for sending task status notifications
        self._notification_callback: Optional[callable] = None
        
        # Ensure parent directory exists
        self._tasks_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing tasks from disk
        self._load()

    def _load(self):
        """Load tasks from disk on startup."""
        if not self._tasks_file.exists():
            logger.info(f"No existing tasks file at {self._tasks_file}")
            return
        
        try:
            data = json.loads(self._tasks_file.read_text())
            for task_id, entry in data.items():
                try:
                    task_data = entry.get("task", {})
                    payload_data = entry.get("payload", {})
                    
                    # Reconstruct Task from stored data
                    # Parse datetime strings back to datetime objects
                    if "createdAt" in task_data and isinstance(task_data["createdAt"], str):
                        task_data["createdAt"] = datetime.fromisoformat(task_data["createdAt"])
                    if "lastUpdatedAt" in task_data and isinstance(task_data["lastUpdatedAt"], str):
                        task_data["lastUpdatedAt"] = datetime.fromisoformat(task_data["lastUpdatedAt"])
                    
                    task = Task(**task_data)
                    payload = TaskPayload(**payload_data)
                    
                    self._tasks[task_id] = task
                    self._payloads[task_id] = payload
                except Exception as e:
                    logger.warning(f"Failed to load task {task_id}: {e}")
            
            logger.info(f"Loaded {len(self._tasks)} tasks from {self._tasks_file}")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse tasks file {self._tasks_file}: {e}")
        except Exception as e:
            logger.error(f"Failed to load tasks from {self._tasks_file}: {e}")

    def _save(self):
        """Persist all tasks to disk. Called after every mutation."""
        try:
            data = {}
            for task_id, task in self._tasks.items():
                task_dict = task.model_dump(mode="json")
                payload = self._payloads.get(task_id)
                payload_dict = payload.model_dump() if payload else {}
                data[task_id] = {
                    "task": task_dict,
                    "payload": payload_dict,
                }
            
            self._tasks_file.write_text(json.dumps(data, indent=2, default=str))
        except Exception as e:
            logger.error(f"Failed to save tasks to {self._tasks_file}: {e}")

    def set_notification_callback(self, callback: callable):
        """Set callback for sending task status notifications.
        
        The callback receives (task_id: str, task: Task) and should
        send notifications/tasks/status to connected clients.
        """
        self._notification_callback = callback

    async def create_task(self, agent_id: str, message: str) -> Task:
        """Create a new task for an agent message dispatch.
        
        Args:
            agent_id: The agent this task dispatches to.
            message: The message being sent.
            
        Returns:
            A new Task in 'working' status.
        """
        now = datetime.now(timezone.utc)
        task_id = f"task-{uuid.uuid4().hex[:12]}"

        task = Task(
            taskId=task_id,
            status=TASK_STATUS_WORKING,
            statusMessage=f"Agent '{agent_id}' is processing the message",
            createdAt=now,
            lastUpdatedAt=now,
            ttl=self._ttl_ms,
            pollInterval=self._poll_interval_ms,
        )

        payload = TaskPayload(
            agent_id=agent_id,
            input_message=message,
        )

        async with self._lock:
            self._tasks[task_id] = task
            self._payloads[task_id] = payload
            self._save()

        logger.info(f"Created task {task_id} for agent {agent_id}")
        return task

    async def update_status(
        self,
        task_id: str,
        status: TaskStatus,
        status_message: str | None = None,
        output_messages: list[dict] | None = None,
        error: str | None = None,
    ) -> Task | None:
        """Update a task's status and optionally its payload.
        
        Args:
            task_id: The task to update.
            status: New status (working, completed, failed, cancelled).
            status_message: Optional human-readable status message.
            output_messages: Optional output messages from the agent.
            error: Optional error message if task failed.
            
        Returns:
            Updated Task, or None if task not found.
        """
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                logger.warning(f"Task {task_id} not found for status update")
                return None

            # Don't update terminal tasks
            if task.status in (TASK_STATUS_COMPLETED, TASK_STATUS_FAILED, TASK_STATUS_CANCELLED):
                logger.warning(f"Task {task_id} already in terminal state: {task.status}")
                return task

            now = datetime.now(timezone.utc)
            task.status = status
            task.lastUpdatedAt = now
            if status_message is not None:
                task.statusMessage = status_message

            # Update payload
            payload = self._payloads.get(task_id)
            if payload:
                if output_messages is not None:
                    payload.output_messages = output_messages
                if error is not None:
                    payload.error = error

            self._save()

        logger.info(f"Task {task_id} updated to {status}")

        # Send notification (outside lock to avoid deadlocks)
        if self._notification_callback:
            try:
                await self._notification_callback(task_id, task)
            except Exception as e:
                logger.error(f"Failed to send task notification for {task_id}: {e}")

        return task

    async def get_task(self, task_id: str) -> Task | None:
        """Get a task by ID.
        
        Returns:
            The Task, or None if not found.
        """
        async with self._lock:
            return self._tasks.get(task_id)

    async def get_payload(self, task_id: str) -> TaskPayload | None:
        """Get a task's payload by ID.
        
        Returns:
            The TaskPayload, or None if not found.
        """
        async with self._lock:
            return self._payloads.get(task_id)

    async def list_tasks(self, agent_id: str | None = None) -> list[Task]:
        """List all tasks, optionally filtered by agent_id.
        
        Args:
            agent_id: Optional filter by agent ID.
            
        Returns:
            List of tasks, sorted by creation time (newest first).
        """
        async with self._lock:
            tasks = list(self._tasks.values())
            if agent_id:
                # Filter by agent_id using payloads
                filtered = []
                for task in tasks:
                    payload = self._payloads.get(task.taskId)
                    if payload and payload.agent_id == agent_id:
                        filtered.append(task)
                tasks = filtered

        # Sort newest first
        tasks.sort(key=lambda t: t.createdAt, reverse=True)
        return tasks

    async def cancel_task(self, task_id: str) -> Task | None:
        """Cancel a task.
        
        Returns:
            Updated Task, or None if not found.
        """
        return await self.update_status(
            task_id,
            status=TASK_STATUS_CANCELLED,
            status_message="Task cancelled by user",
        )

    async def get_agent_id_for_task(self, task_id: str) -> str | None:
        """Get the agent_id associated with a task.
        
        Returns:
            Agent ID, or None if task not found.
        """
        async with self._lock:
            payload = self._payloads.get(task_id)
            return payload.agent_id if payload else None

    async def get_active_task_for_agent(self, agent_id: str) -> Task | None:
        """Get the most recent active (working) task for an agent.
        
        Returns:
            The active Task, or None if no active task.
        """
        async with self._lock:
            for task in sorted(self._tasks.values(), key=lambda t: t.createdAt, reverse=True):
                payload = self._payloads.get(task.taskId)
                if payload and payload.agent_id == agent_id and task.status == TASK_STATUS_WORKING:
                    return task
            return None

    async def cleanup_expired(self):
        """Remove expired tasks (past TTL)."""
        now = datetime.now(timezone.utc)
        expired = []
        
        async with self._lock:
            for task_id, task in self._tasks.items():
                if task.ttl is not None:
                    age_ms = (now - task.createdAt).total_seconds() * 1000
                    if age_ms > task.ttl:
                        expired.append(task_id)
            
            for task_id in expired:
                del self._tasks[task_id]
                self._payloads.pop(task_id, None)
            
            if expired:
                self._save()

        if expired:
            logger.info(f"Cleaned up {len(expired)} expired tasks")

    async def reconcile_with_agents(self, agent_manager):
        """Reconcile task states with actual container states after restart.
        
        Tasks that were 'working' when the server stopped may need to be
        updated based on whether their agent containers are still running.
        
        Args:
            agent_manager: The AgentManager to check container states.
        """
        working_tasks = []
        async with self._lock:
            for task_id, task in self._tasks.items():
                if task.status == TASK_STATUS_WORKING:
                    payload = self._payloads.get(task_id)
                    if payload:
                        working_tasks.append((task_id, payload.agent_id))
        
        if not working_tasks:
            return
        
        logger.info(f"Reconciling {len(working_tasks)} working tasks after restart")
        
        for task_id, agent_id in working_tasks:
            try:
                agent = agent_manager.tracker.get_agent(agent_id)
                if not agent or not agent.container_id:
                    # Agent doesn't exist — check disk for results
                    messages = agent_manager._read_messages_from_disk(
                        agent_id, agent.data_dir if agent else None,
                        count=1, include_tool_messages=False
                    )
                    if messages:
                        await self.update_status(
                            task_id,
                            status=TASK_STATUS_COMPLETED,
                            status_message=f"Completed (recovered after restart — agent container not found)",
                            output_messages=messages,
                        )
                    else:
                        await self.update_status(
                            task_id,
                            status=TASK_STATUS_FAILED,
                            status_message="Server restarted, agent container not found and no results on disk",
                        )
                elif not agent_manager._is_container_running(agent.container_id):
                    # Container stopped while server was down — check for results
                    messages = agent_manager._read_messages_from_disk(
                        agent_id, agent.data_dir, count=1, include_tool_messages=False
                    )
                    if messages:
                        await self.update_status(
                            task_id,
                            status=TASK_STATUS_COMPLETED,
                            status_message=f"Completed (recovered after restart — container stopped with results)",
                            output_messages=messages,
                        )
                    else:
                        await self.update_status(
                            task_id,
                            status=TASK_STATUS_FAILED,
                            status_message="Agent container stopped during server downtime, no results found",
                        )
                else:
                    # Container is still running — leave task as working
                    logger.info(f"Task {task_id} agent {agent_id} still running, keeping as working")
            except Exception as e:
                logger.error(f"Failed to reconcile task {task_id}: {e}")

    @property
    def task_count(self) -> int:
        """Number of tracked tasks."""
        return len(self._tasks)
