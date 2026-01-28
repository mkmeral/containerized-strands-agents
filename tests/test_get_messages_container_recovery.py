"""Tests for get_messages container recovery and status handling."""

import asyncio
import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from containerized_strands_agents.agent_manager import AgentManager, TaskTracker, AgentInfo


class TestGetMessagesContainerStatus:
    """Tests for get_messages container status reporting."""

    @pytest.fixture
    def mock_docker(self):
        """Mock Docker client."""
        from docker.errors import NotFound
        
        with patch("containerized_strands_agents.agent_manager.docker") as mock:
            mock_client = MagicMock()
            mock.from_env.return_value = mock_client
            
            # Mock network - raise NotFound (the actual docker exception)
            mock_client.networks.get.side_effect = NotFound("Network not found")
            mock_client.networks.create.return_value = MagicMock()
            
            yield mock_client

    @pytest.fixture
    def manager(self, mock_docker, tmp_path):
        """Create AgentManager with mocked dependencies."""
        with patch("containerized_strands_agents.agent_manager.TASKS_FILE", tmp_path / "tasks.json"):
            with patch("containerized_strands_agents.agent_manager.AGENTS_DIR", tmp_path / "agents"):
                with patch("containerized_strands_agents.agent_manager.DATA_DIR", tmp_path):
                    mgr = AgentManager()
                    mgr.tracker = TaskTracker(tmp_path / "tasks.json")
                    yield mgr

    def _create_agent_with_messages(self, manager, agent_id: str, tmp_path: Path) -> AgentInfo:
        """Helper to create an agent with some messages on disk."""
        now = datetime.now(timezone.utc).isoformat()
        agent = AgentInfo(
            agent_id=agent_id,
            container_id="abc123",
            container_name=f"agent-{agent_id}",
            port=9000,
            status="stopped",
            created_at=now,
            last_activity=now,
        )
        manager.tracker.update_agent(agent)
        
        # Create messages directory structure
        agent_dir = manager._get_agent_dir(agent_id)
        messages_dir = agent_dir / ".agent" / "session" / "agents" / "agent_default" / "messages"
        messages_dir.mkdir(parents=True, exist_ok=True)
        
        # Create some message files
        msg1 = {"message": {"role": "user", "content": "Hello"}, "message_id": 0}
        msg2 = {"message": {"role": "assistant", "content": [{"type": "text", "text": "Hi there!"}]}, "message_id": 1}
        
        (messages_dir / "message_0.json").write_text(json.dumps(msg1))
        (messages_dir / "message_1.json").write_text(json.dumps(msg2))
        
        return agent

    @pytest.mark.asyncio
    async def test_get_messages_returns_container_status_running(self, manager, mock_docker, tmp_path):
        """Test that get_messages returns container_status='running' when container is up."""
        agent = self._create_agent_with_messages(manager, "test-running", tmp_path)
        agent.status = "running"
        manager.tracker.update_agent(agent)
        
        # Mock container as running
        mock_container = MagicMock()
        mock_container.status = "running"
        mock_docker.containers.get.return_value = mock_container
        
        # Mock the HTTP calls using patch on the module
        with patch("containerized_strands_agents.agent_manager.httpx.AsyncClient") as mock_client_class:
            # Create mock response for /history endpoint
            mock_history_response = MagicMock()
            mock_history_response.status_code = 200
            mock_history_response.json.return_value = {"messages": [{"role": "user", "content": "test"}]}
            mock_history_response.raise_for_status = MagicMock()
            
            # Create mock response for /health endpoint
            mock_health_response = MagicMock()
            mock_health_response.status_code = 200
            mock_health_response.json.return_value = {"processing": False}
            
            # Create mock async client
            mock_async_client = MagicMock()
            
            # Make get return different responses based on URL
            async def mock_get(url, **kwargs):
                if "health" in url:
                    return mock_health_response
                return mock_history_response
            
            mock_async_client.get = mock_get
            
            # Setup context manager
            async def mock_aenter(*args):
                return mock_async_client
            
            async def mock_aexit(*args):
                return None
            
            mock_client_class.return_value.__aenter__ = mock_aenter
            mock_client_class.return_value.__aexit__ = mock_aexit
            
            result = await manager.get_messages("test-running")
        
        assert result["status"] == "success"
        assert result["container_status"] == "running"
        assert result["source"] == "container"
        assert "restart_hint" not in result

    @pytest.mark.asyncio
    async def test_get_messages_returns_container_status_stopped(self, manager, mock_docker, tmp_path):
        """Test that get_messages returns container_status='stopped' and source='disk' when container is down."""
        agent = self._create_agent_with_messages(manager, "test-stopped", tmp_path)
        
        # Mock container as not running
        mock_container = MagicMock()
        mock_container.status = "exited"
        mock_docker.containers.get.return_value = mock_container
        
        result = await manager.get_messages("test-stopped")
        
        assert result["status"] == "success"
        assert result["container_status"] == "stopped"
        assert result["source"] == "disk"
        assert "restart_hint" in result
        assert "auto_restart=True" in result["restart_hint"]

    @pytest.mark.asyncio
    async def test_get_messages_reads_from_disk_when_stopped(self, manager, mock_docker, tmp_path):
        """Test that messages are correctly read from disk when container is stopped."""
        agent = self._create_agent_with_messages(manager, "test-disk-read", tmp_path)
        
        # Mock container as not running
        mock_container = MagicMock()
        mock_container.status = "exited"
        mock_docker.containers.get.return_value = mock_container
        
        result = await manager.get_messages("test-disk-read", count=10)
        
        assert result["status"] == "success"
        assert result["source"] == "disk"
        assert len(result["messages"]) == 2
        assert result["messages"][0]["role"] == "user"
        assert result["messages"][1]["role"] == "assistant"


class TestGetMessagesAutoRestart:
    """Tests for get_messages auto_restart functionality."""

    @pytest.fixture
    def mock_docker(self):
        """Mock Docker client."""
        from docker.errors import NotFound
        
        with patch("containerized_strands_agents.agent_manager.docker") as mock:
            mock_client = MagicMock()
            mock.from_env.return_value = mock_client
            
            mock_client.networks.get.side_effect = NotFound("Network not found")
            mock_client.networks.create.return_value = MagicMock()
            
            yield mock_client

    @pytest.fixture
    def manager(self, mock_docker, tmp_path):
        """Create AgentManager with mocked dependencies."""
        with patch("containerized_strands_agents.agent_manager.TASKS_FILE", tmp_path / "tasks.json"):
            with patch("containerized_strands_agents.agent_manager.AGENTS_DIR", tmp_path / "agents"):
                with patch("containerized_strands_agents.agent_manager.DATA_DIR", tmp_path):
                    mgr = AgentManager()
                    mgr.tracker = TaskTracker(tmp_path / "tasks.json")
                    yield mgr

    @pytest.mark.asyncio
    async def test_auto_restart_triggers_container_restart(self, manager, mock_docker, tmp_path):
        """Test that auto_restart=True triggers container restart via _start_container."""
        now = datetime.now(timezone.utc).isoformat()
        agent = AgentInfo(
            agent_id="test-auto-restart",
            container_id="abc123",
            container_name="agent-test-auto-restart",
            port=9000,
            status="stopped",
            created_at=now,
            last_activity=now,
        )
        manager.tracker.update_agent(agent)
        manager._get_agent_dir("test-auto-restart")  # Create directories
        
        # Initially container is stopped
        mock_container = MagicMock()
        mock_container.status = "exited"
        mock_docker.containers.get.return_value = mock_container
        
        # Mock _start_container method
        with patch.object(manager, '_start_container', new_callable=AsyncMock) as mock_start:
            # Make _start_container return a running agent
            restarted_agent = AgentInfo(
                agent_id="test-auto-restart",
                container_id="xyz789",
                container_name="agent-test-auto-restart",
                port=9000,
                status="running",
                created_at=now,
                last_activity=now,
            )
            mock_start.return_value = restarted_agent
            
            # Also mock the container check after restart
            call_count = [0]
            def container_status_side_effect(*args, **kwargs):
                call_count[0] += 1
                container = MagicMock()
                # First call - container is stopped, after restart - running
                container.status = "running" if call_count[0] > 1 else "exited"
                return container
            mock_docker.containers.get.side_effect = container_status_side_effect
            
            # Mock HTTP client for post-restart message fetch
            with patch("containerized_strands_agents.agent_manager.httpx.AsyncClient") as mock_client_class:
                mock_history_response = MagicMock()
                mock_history_response.status_code = 200
                mock_history_response.json.return_value = {"messages": [{"role": "assistant", "content": "Hello"}]}
                mock_history_response.raise_for_status = MagicMock()
                
                mock_health_response = MagicMock()
                mock_health_response.status_code = 200
                mock_health_response.json.return_value = {"processing": False}
                
                mock_async_client = MagicMock()
                
                async def mock_get(url, **kwargs):
                    if "health" in url:
                        return mock_health_response
                    return mock_history_response
                
                mock_async_client.get = mock_get
                
                async def mock_aenter(*args):
                    return mock_async_client
                
                async def mock_aexit(*args):
                    return None
                
                mock_client_class.return_value.__aenter__ = mock_aenter
                mock_client_class.return_value.__aexit__ = mock_aexit
                
                result = await manager.get_messages("test-auto-restart", auto_restart=True)
            
            # Verify _start_container was called with the agent
            mock_start.assert_called_once()

    @pytest.mark.asyncio
    async def test_auto_restart_false_does_not_restart(self, manager, mock_docker, tmp_path):
        """Test that auto_restart=False (default) does not restart container."""
        now = datetime.now(timezone.utc).isoformat()
        agent = AgentInfo(
            agent_id="test-no-restart",
            container_id="abc123",
            container_name="agent-test-no-restart",
            port=9000,
            status="stopped",
            created_at=now,
            last_activity=now,
        )
        manager.tracker.update_agent(agent)
        manager._get_agent_dir("test-no-restart")
        
        # Container is stopped
        mock_container = MagicMock()
        mock_container.status = "exited"
        mock_docker.containers.get.return_value = mock_container
        
        with patch.object(manager, '_start_container', new_callable=AsyncMock) as mock_start:
            result = await manager.get_messages("test-no-restart", auto_restart=False)
            
            # _start_container should NOT be called
            mock_start.assert_not_called()
            
            # Should read from disk instead
            assert result["source"] == "disk"
            assert result["container_status"] == "stopped"


class TestReadMessagesFromDisk:
    """Tests for the _read_messages_from_disk helper method."""

    @pytest.fixture
    def mock_docker(self):
        """Mock Docker client."""
        from docker.errors import NotFound
        
        with patch("containerized_strands_agents.agent_manager.docker") as mock:
            mock_client = MagicMock()
            mock.from_env.return_value = mock_client
            
            mock_client.networks.get.side_effect = NotFound("Network not found")
            mock_client.networks.create.return_value = MagicMock()
            
            yield mock_client

    @pytest.fixture
    def manager(self, mock_docker, tmp_path):
        """Create AgentManager with mocked dependencies."""
        with patch("containerized_strands_agents.agent_manager.TASKS_FILE", tmp_path / "tasks.json"):
            with patch("containerized_strands_agents.agent_manager.AGENTS_DIR", tmp_path / "agents"):
                with patch("containerized_strands_agents.agent_manager.DATA_DIR", tmp_path):
                    mgr = AgentManager()
                    mgr.tracker = TaskTracker(tmp_path / "tasks.json")
                    yield mgr

    def test_read_messages_empty_directory(self, manager, tmp_path):
        """Test reading from non-existent messages directory."""
        result = manager._read_messages_from_disk("nonexistent", None, 10, False)
        assert result == []

    def test_read_messages_filters_tool_messages(self, manager, tmp_path):
        """Test that tool messages are filtered when include_tool_messages=False."""
        agent_id = "test-filter"
        agent_dir = manager._get_agent_dir(agent_id)
        messages_dir = agent_dir / ".agent" / "session" / "agents" / "agent_default" / "messages"
        messages_dir.mkdir(parents=True, exist_ok=True)
        
        # Create a mix of regular and tool messages
        messages = [
            {"message": {"role": "user", "content": "Hello"}, "message_id": 0},
            {"message": {"role": "assistant", "content": [{"type": "tool_use", "id": "123", "name": "test"}]}, "message_id": 1},
            {"message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "123"}]}, "message_id": 2},
            {"message": {"role": "assistant", "content": [{"type": "text", "text": "Done!"}]}, "message_id": 3},
        ]
        
        for i, msg in enumerate(messages):
            (messages_dir / f"message_{i}.json").write_text(json.dumps(msg))
        
        # Without tool messages
        result = manager._read_messages_from_disk(agent_id, None, 10, include_tool_messages=False)
        assert len(result) == 2  # Only user "Hello" and assistant "Done!"
        
        # With tool messages
        result_all = manager._read_messages_from_disk(agent_id, None, 10, include_tool_messages=True)
        assert len(result_all) == 4

    def test_read_messages_respects_count(self, manager, tmp_path):
        """Test that count parameter limits results."""
        agent_id = "test-count"
        agent_dir = manager._get_agent_dir(agent_id)
        messages_dir = agent_dir / ".agent" / "session" / "agents" / "agent_default" / "messages"
        messages_dir.mkdir(parents=True, exist_ok=True)
        
        # Create 5 messages
        for i in range(5):
            msg = {"message": {"role": "user" if i % 2 == 0 else "assistant", "content": f"Message {i}"}, "message_id": i}
            (messages_dir / f"message_{i}.json").write_text(json.dumps(msg))
        
        # Get last 2 messages
        result = manager._read_messages_from_disk(agent_id, None, 2, include_tool_messages=True)
        assert len(result) == 2
        assert result[0]["content"] == "Message 3"
        assert result[1]["content"] == "Message 4"
