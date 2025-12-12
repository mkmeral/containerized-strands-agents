"""Tests for Agent Manager."""

import asyncio
import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

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

    def test_list_agents_empty(self, manager):
        """Test listing agents when none exist."""
        agents = manager.list_agents()
        assert agents == []

    @pytest.mark.asyncio
    async def test_get_messages_not_found(self, manager):
        """Test getting messages for non-existent agent."""
        result = await manager.get_messages("nonexistent")
        assert result["status"] == "error"

    def test_extract_text_content_string(self, manager):
        """Test extracting text from string content."""
        result = manager._extract_text_content("hello")
        assert result == "hello"

    def test_extract_text_content_list(self, manager):
        """Test extracting text from list content."""
        content = [{"text": "hello"}, {"text": "world"}]
        result = manager._extract_text_content(content)
        assert result == "hello\nworld"

    def test_format_tool_use_messages(self, manager):
        """Test formatting tool use messages."""
        content = [
            {"text": "I'll run a command"},
            {"type": "tool_use", "name": "shell", "input": {"command": "ls"}}
        ]
        result = manager._format_tool_use_messages(content)
        assert len(result) == 2
        assert result[0]["role"] == "assistant"
        assert result[0]["content"] == "I'll run a command"
        assert result[1]["role"] == "tool_use"
        assert result[1]["tool"] == "shell"
        assert result[1]["input"] == {"command": "ls"}

    def test_format_tool_result_message(self, manager):
        """Test formatting tool result messages."""
        content = [
            {
                "type": "tool_result", 
                "tool_use_id": "123",
                "content": [{"text": "output here"}]
            }
        ]
        result = manager._format_tool_result_message(content)
        assert result is not None
        assert result["role"] == "tool_result"
        assert result["tool"] == "unknown"  # We don't extract tool name yet
        assert result["output"] == "output here"

    def test_format_tool_result_message_none(self, manager):
        """Test tool result message with no tool_result."""
        content = [{"text": "regular message"}]
        result = manager._format_tool_result_message(content)
        assert result is None


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
