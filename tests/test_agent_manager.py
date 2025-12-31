"""Tests for Agent Manager."""

import asyncio
import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Import json for test_has_existing_session_with_messages

from containerized_strands_agents.agent_manager import AgentManager, TaskTracker, AgentInfo


class TestTaskTracker:
    """Tests for TaskTracker."""

    def test_load_empty(self, tmp_path):
        """Test loading from non-existent file."""
        tracker = TaskTracker(tmp_path / "tasks.json")
        agents = tracker.load()
        assert agents == {}

    def test_save_and_load(self, tmp_path):
        """Test saving and loading agents."""
        tracker = TaskTracker(tmp_path / "tasks.json")
        
        agent = AgentInfo(
            agent_id="test-1",
            container_name="agent-test-1",
            port=9000,
            status="running",
            created_at="2024-01-01T00:00:00Z",
            last_activity="2024-01-01T00:00:00Z",
        )
        
        tracker.update_agent(agent)
        
        loaded = tracker.load()
        assert "test-1" in loaded
        assert loaded["test-1"].agent_id == "test-1"
        assert loaded["test-1"].port == 9000

    def test_remove_agent(self, tmp_path):
        """Test removing an agent."""
        tracker = TaskTracker(tmp_path / "tasks.json")
        
        agent = AgentInfo(
            agent_id="test-1",
            container_name="agent-test-1",
            port=9000,
            status="running",
            created_at="2024-01-01T00:00:00Z",
            last_activity="2024-01-01T00:00:00Z",
        )
        
        tracker.update_agent(agent)
        tracker.remove_agent("test-1")
        
        loaded = tracker.load()
        assert "test-1" not in loaded


class TestAgentManager:
    """Tests for AgentManager."""

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

    def test_get_next_port(self, manager):
        """Test port allocation."""
        port1 = manager._get_next_port()
        port2 = manager._get_next_port()
        assert port2 > port1

    @pytest.mark.asyncio
    async def test_list_agents_empty(self, manager):
        """Test listing agents when none exist."""
        agents = await manager.list_agents()
        assert agents == []

    @pytest.mark.asyncio
    async def test_get_messages_not_found(self, manager):
        """Test getting messages for non-existent agent."""
        result = await manager.get_messages("nonexistent")
        assert result["status"] == "error"

    def test_get_agent_dir_creates_structure(self, manager, tmp_path):
        """Test that _get_agent_dir creates the proper directory structure."""
        agent_id = "test-agent"
        agent_dir = manager._get_agent_dir(agent_id)
        
        # Check directories were created
        assert agent_dir.exists()
        assert (agent_dir / "workspace").exists()
        assert (agent_dir / ".agent").exists()
        assert (agent_dir / ".agent" / "tools").exists()
        assert (agent_dir / ".agent" / "session").exists()
        assert (agent_dir / ".agent" / "runner").exists()

    def test_save_and_load_system_prompt(self, manager, tmp_path):
        """Test saving and loading system prompt in .agent/ directory."""
        agent_id = "test-agent"
        custom_prompt = "You are a test assistant."
        
        manager._save_system_prompt(agent_id, custom_prompt)
        
        # Check file was created in .agent/ subdirectory
        agent_dir = manager._get_agent_dir(agent_id)
        prompt_file = agent_dir / ".agent" / "system_prompt.txt"
        assert prompt_file.exists()
        assert prompt_file.read_text() == custom_prompt
        
        # Load and verify
        loaded = manager._load_system_prompt(agent_id)
        assert loaded == custom_prompt

    def test_has_existing_session_empty(self, manager):
        """Test _has_existing_session returns False when no session exists."""
        result = manager._has_existing_session("nonexistent-agent")
        assert result == False

    def test_has_existing_session_with_messages(self, manager, tmp_path):
        """Test _has_existing_session returns True when messages exist."""
        agent_id = "test-agent"
        agent_dir = manager._get_agent_dir(agent_id)
        
        # Create FileSessionManager-style message files
        messages_dir = agent_dir / ".agent" / "session" / "agents" / "agent_default" / "messages"
        messages_dir.mkdir(parents=True)
        
        # Create a message file
        msg_data = {"message": {"role": "user", "content": "Hello"}, "message_id": 0}
        (messages_dir / "message_0.json").write_text(json.dumps(msg_data))
        
        result = manager._has_existing_session(agent_id)
        assert result == True


class TestAgentInfo:
    """Tests for AgentInfo model."""

    def test_create_agent_info(self):
        """Test creating AgentInfo."""
        agent = AgentInfo(
            agent_id="test",
            container_name="agent-test",
            port=9000,
            status="running",
            created_at="2024-01-01T00:00:00Z",
            last_activity="2024-01-01T00:00:00Z",
        )
        assert agent.agent_id == "test"
        assert agent.container_id is None

    def test_agent_info_with_container(self):
        """Test AgentInfo with container ID."""
        agent = AgentInfo(
            agent_id="test",
            container_id="abc123",
            container_name="agent-test",
            port=9000,
            status="running",
            created_at="2024-01-01T00:00:00Z",
            last_activity="2024-01-01T00:00:00Z",
        )
        assert agent.container_id == "abc123"
