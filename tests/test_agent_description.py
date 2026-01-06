"""Tests for agent description field."""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from docker.errors import NotFound

from containerized_strands_agents.agent_manager import AgentManager, AgentInfo


class TestAgentDescription:
    """Tests for agent description handling."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def agent_manager(self, temp_dir):
        """Create an AgentManager with mocked Docker client."""
        with patch("containerized_strands_agents.agent_manager.docker") as mock_docker:
            mock_client = MagicMock()
            mock_docker.from_env.return_value = mock_client
            mock_client.networks.get.side_effect = NotFound("Not found")
            mock_client.images.get.return_value = MagicMock()
            
            with patch("containerized_strands_agents.agent_manager.AGENTS_DIR", temp_dir / "agents"):
                with patch("containerized_strands_agents.agent_manager.TASKS_FILE", temp_dir / "tasks.json"):
                    manager = AgentManager()
                    yield manager

    def test_agent_info_with_description(self):
        """Test AgentInfo model includes description field."""
        agent = AgentInfo(
            agent_id="test-agent",
            container_name="agent-test-agent",
            port=9000,
            status="running",
            created_at="2024-01-01T00:00:00Z",
            last_activity="2024-01-01T00:00:00Z",
            description="A test agent for unit testing"
        )
        
        assert agent.description == "A test agent for unit testing"
        
        # Verify it serializes correctly
        data = agent.model_dump()
        assert data["description"] == "A test agent for unit testing"

    def test_agent_info_without_description(self):
        """Test AgentInfo model works without description (backward compatible)."""
        agent = AgentInfo(
            agent_id="test-agent",
            container_name="agent-test-agent",
            port=9000,
            status="running",
            created_at="2024-01-01T00:00:00Z",
            last_activity="2024-01-01T00:00:00Z",
        )
        
        assert agent.description is None

    def test_agent_info_from_dict_without_description(self):
        """Test AgentInfo can be loaded from dict without description (migration)."""
        # Simulates loading old data that doesn't have description field
        data = {
            "agent_id": "old-agent",
            "container_name": "agent-old-agent",
            "port": 9000,
            "status": "stopped",
            "created_at": "2024-01-01T00:00:00Z",
            "last_activity": "2024-01-01T00:00:00Z",
        }
        
        agent = AgentInfo(**data)
        assert agent.description is None

    @pytest.mark.asyncio
    async def test_create_agent_with_description(self, agent_manager, temp_dir):
        """Test creating a new agent with description."""
        with patch("containerized_strands_agents.agent_manager.AGENTS_DIR", temp_dir / "agents"):
            with patch.object(agent_manager, "_start_container", new_callable=AsyncMock) as mock_start:
                mock_start.return_value = AgentInfo(
                    agent_id="test-agent",
                    container_id="abc123",
                    container_name="agent-test-agent",
                    port=9000,
                    status="running",
                    created_at="2024-01-01T00:00:00Z",
                    last_activity="2024-01-01T00:00:00Z",
                    description="Reviews code for quality"
                )
                
                agent = await agent_manager._create_agent(
                    "test-agent",
                    description="Reviews code for quality"
                )
                
                assert agent.description == "Reviews code for quality"

    @pytest.mark.asyncio
    async def test_get_or_create_agent_updates_description(self, agent_manager, temp_dir):
        """Test that description can be updated on existing agent."""
        with patch("containerized_strands_agents.agent_manager.AGENTS_DIR", temp_dir / "agents"):
            # First create an agent without description
            existing_agent = AgentInfo(
                agent_id="test-agent",
                container_id="abc123",
                container_name="agent-test-agent",
                port=9000,
                status="running",
                created_at="2024-01-01T00:00:00Z",
                last_activity="2024-01-01T00:00:00Z",
                description=None
            )
            agent_manager.tracker.update_agent(existing_agent)
            
            with patch.object(agent_manager, "_is_container_running", return_value=True):
                agent = await agent_manager.get_or_create_agent(
                    "test-agent",
                    description="Now has a description"
                )
                
                assert agent.description == "Now has a description"
                
                # Verify it was persisted
                saved_agent = agent_manager.tracker.get_agent("test-agent")
                assert saved_agent.description == "Now has a description"

    @pytest.mark.asyncio
    async def test_send_message_with_description(self, agent_manager, temp_dir):
        """Test send_message passes description to get_or_create_agent."""
        with patch("containerized_strands_agents.agent_manager.AGENTS_DIR", temp_dir / "agents"):
            with patch.object(agent_manager, "get_or_create_agent", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = AgentInfo(
                    agent_id="test-agent",
                    container_id="abc123",
                    container_name="agent-test-agent",
                    port=9000,
                    status="running",
                    created_at="2024-01-01T00:00:00Z",
                    last_activity="2024-01-01T00:00:00Z",
                    description="Test description"
                )
                
                with patch.object(agent_manager, "_dispatch_message", new_callable=AsyncMock):
                    result = await agent_manager.send_message(
                        "test-agent",
                        "Hello",
                        description="Test description"
                    )
                
                # Verify description was passed
                mock_get.assert_called_once()
                call_kwargs = mock_get.call_args.kwargs
                assert call_kwargs.get("description") == "Test description"

    @pytest.mark.asyncio
    async def test_list_agents_includes_description(self, agent_manager, temp_dir):
        """Test that list_agents returns description field."""
        with patch("containerized_strands_agents.agent_manager.AGENTS_DIR", temp_dir / "agents"):
            # Create agents with and without descriptions
            agent1 = AgentInfo(
                agent_id="agent-1",
                container_name="agent-agent-1",
                port=9000,
                status="stopped",
                created_at="2024-01-01T00:00:00Z",
                last_activity="2024-01-01T00:00:00Z",
                description="First agent description"
            )
            agent2 = AgentInfo(
                agent_id="agent-2",
                container_name="agent-agent-2",
                port=9001,
                status="stopped",
                created_at="2024-01-01T00:00:00Z",
                last_activity="2024-01-01T00:00:00Z",
                description=None
            )
            agent_manager.tracker.update_agent(agent1)
            agent_manager.tracker.update_agent(agent2)
            
            agents = await agent_manager.list_agents()
            
            agent1_data = next(a for a in agents if a["agent_id"] == "agent-1")
            agent2_data = next(a for a in agents if a["agent_id"] == "agent-2")
            
            assert agent1_data["description"] == "First agent description"
            assert agent2_data["description"] is None
