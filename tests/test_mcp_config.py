"""Tests for MCP configuration support."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from docker.errors import NotFound

from containerized_strands_agents.agent_manager import AgentManager


class TestMCPConfig:
    """Tests for MCP configuration handling in AgentManager."""

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
            # Use NotFound from docker.errors
            mock_client.networks.get.side_effect = NotFound("Not found")
            mock_client.images.get.return_value = MagicMock()
            
            with patch("containerized_strands_agents.agent_manager.AGENTS_DIR", temp_dir / "agents"):
                with patch("containerized_strands_agents.agent_manager.TASKS_FILE", temp_dir / "tasks.json"):
                    manager = AgentManager()
                    yield manager

    def test_save_mcp_config(self, agent_manager, temp_dir):
        """Test saving MCP config to agent directory."""
        with patch("containerized_strands_agents.agent_manager.AGENTS_DIR", temp_dir / "agents"):
            mcp_config = {
                "mcpServers": {
                    "github": {
                        "command": "uvx",
                        "args": ["mcp-server-github"],
                        "env": {"GITHUB_TOKEN": "test-token"}
                    }
                }
            }
            
            agent_manager._save_mcp_config("test-agent", mcp_config, None)
            
            # Verify file was created
            mcp_file = temp_dir / "agents" / "test-agent" / ".agent" / "mcp.json"
            assert mcp_file.exists()
            
            # Verify content
            saved_config = json.loads(mcp_file.read_text())
            assert saved_config == mcp_config

    def test_load_mcp_config_from_file(self, agent_manager, temp_dir):
        """Test loading MCP config from a file path."""
        # Create a test mcp.json file
        mcp_file = temp_dir / "test_mcp.json"
        mcp_config = {
            "mcpServers": {
                "aws-docs": {
                    "command": "uvx",
                    "args": ["awslabs.aws-documentation-mcp-server@latest"]
                }
            }
        }
        mcp_file.write_text(json.dumps(mcp_config))
        
        # Load it
        loaded_config = agent_manager._load_mcp_config_from_file(str(mcp_file))
        assert loaded_config == mcp_config

    def test_load_mcp_config_from_file_not_found(self, agent_manager, temp_dir):
        """Test loading MCP config from non-existent file raises error."""
        with pytest.raises(FileNotFoundError):
            agent_manager._load_mcp_config_from_file(str(temp_dir / "nonexistent.json"))

    def test_load_mcp_config_from_file_invalid_json(self, agent_manager, temp_dir):
        """Test loading MCP config from invalid JSON raises error."""
        invalid_file = temp_dir / "invalid.json"
        invalid_file.write_text("not valid json {")
        
        with pytest.raises(ValueError, match="Invalid JSON"):
            agent_manager._load_mcp_config_from_file(str(invalid_file))

    @pytest.mark.asyncio
    async def test_get_or_create_agent_with_mcp_config(self, agent_manager, temp_dir):
        """Test creating agent with inline MCP config."""
        from containerized_strands_agents.agent_manager import AgentInfo
        
        with patch("containerized_strands_agents.agent_manager.AGENTS_DIR", temp_dir / "agents"):
            # Mock both _create_agent and _start_container to avoid Docker calls
            with patch.object(agent_manager, "_start_container", new_callable=AsyncMock) as mock_start:
                with patch.object(agent_manager, "_create_agent", new_callable=AsyncMock) as mock_create:
                    result_agent = AgentInfo(
                        agent_id="test-agent",
                        container_id="abc123",
                        container_name="agent-test-agent",
                        port=9000,
                        status="running",
                        created_at="2024-01-01T00:00:00Z",
                        last_activity="2024-01-01T00:00:00Z",
                    )
                    mock_create.return_value = result_agent
                    mock_start.return_value = result_agent
                    
                    mcp_config = {
                        "mcpServers": {
                            "test-server": {"command": "echo", "args": ["hello"]}
                        }
                    }
                    
                    await agent_manager.get_or_create_agent(
                        "test-agent",
                        mcp_config=mcp_config
                    )
                    
                    # Verify MCP config was saved
                    mcp_file = temp_dir / "agents" / "test-agent" / ".agent" / "mcp.json"
                    assert mcp_file.exists()
                    saved_config = json.loads(mcp_file.read_text())
                    assert saved_config == mcp_config

    @pytest.mark.asyncio
    async def test_get_or_create_agent_with_mcp_config_file(self, agent_manager, temp_dir):
        """Test creating agent with MCP config file path."""
        from containerized_strands_agents.agent_manager import AgentInfo
        
        # Create a test mcp.json file
        mcp_file = temp_dir / "my_mcp.json"
        mcp_config = {
            "mcpServers": {
                "from-file": {"command": "test", "args": []}
            }
        }
        mcp_file.write_text(json.dumps(mcp_config))
        
        with patch("containerized_strands_agents.agent_manager.AGENTS_DIR", temp_dir / "agents"):
            # Mock both _create_agent and _start_container to avoid Docker calls
            with patch.object(agent_manager, "_start_container", new_callable=AsyncMock) as mock_start:
                with patch.object(agent_manager, "_create_agent", new_callable=AsyncMock) as mock_create:
                    result_agent = AgentInfo(
                        agent_id="test-agent",
                        container_id="abc123",
                        container_name="agent-test-agent",
                        port=9000,
                        status="running",
                        created_at="2024-01-01T00:00:00Z",
                        last_activity="2024-01-01T00:00:00Z",
                    )
                    mock_create.return_value = result_agent
                    mock_start.return_value = result_agent
                    
                    await agent_manager.get_or_create_agent(
                        "test-agent",
                        mcp_config_file=str(mcp_file)
                    )
                    
                    # Verify MCP config was saved to agent directory
                    agent_mcp_file = temp_dir / "agents" / "test-agent" / ".agent" / "mcp.json"
                    assert agent_mcp_file.exists()
                    saved_config = json.loads(agent_mcp_file.read_text())
                    assert saved_config == mcp_config


class TestAgentMCPLoading:
    """Tests for MCP loading in agent.py."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_load_mcp_config_from_agent_dir(self, temp_dir):
        """Test loading MCP config from agent's .agent/mcp.json."""
        from containerized_strands_agents.agent import load_mcp_config
        
        # Create agent directory structure
        agent_dir = temp_dir / ".agent"
        agent_dir.mkdir(parents=True)
        
        mcp_config = {
            "mcpServers": {
                "test": {"command": "echo", "args": ["test"]}
            }
        }
        (agent_dir / "mcp.json").write_text(json.dumps(mcp_config))
        
        loaded = load_mcp_config(temp_dir)
        assert loaded == mcp_config

    def test_load_mcp_config_from_env_var(self, temp_dir):
        """Test loading MCP config from CONTAINERIZED_AGENTS_MCP_CONFIG env var."""
        from containerized_strands_agents.agent import load_mcp_config
        
        # Create a global mcp.json
        global_mcp = temp_dir / "global_mcp.json"
        mcp_config = {
            "mcpServers": {
                "global": {"command": "global-cmd", "args": []}
            }
        }
        global_mcp.write_text(json.dumps(mcp_config))
        
        # Create empty agent dir (no local mcp.json)
        agent_dir = temp_dir / "agent"
        (agent_dir / ".agent").mkdir(parents=True)
        
        with patch.dict(os.environ, {"CONTAINERIZED_AGENTS_MCP_CONFIG": str(global_mcp)}):
            loaded = load_mcp_config(agent_dir)
            assert loaded == mcp_config

    def test_load_mcp_config_agent_takes_precedence(self, temp_dir):
        """Test that agent's mcp.json takes precedence over global."""
        from containerized_strands_agents.agent import load_mcp_config
        
        # Create global mcp.json
        global_mcp = temp_dir / "global_mcp.json"
        global_mcp.write_text(json.dumps({"mcpServers": {"global": {}}}))
        
        # Create agent's mcp.json
        agent_dir = temp_dir / "agent"
        (agent_dir / ".agent").mkdir(parents=True)
        agent_config = {"mcpServers": {"local": {"command": "local"}}}
        (agent_dir / ".agent" / "mcp.json").write_text(json.dumps(agent_config))
        
        with patch.dict(os.environ, {"CONTAINERIZED_AGENTS_MCP_CONFIG": str(global_mcp)}):
            loaded = load_mcp_config(agent_dir)
            # Should get agent's config, not global
            assert "local" in loaded.get("mcpServers", {})
            assert "global" not in loaded.get("mcpServers", {})

    def test_load_mcp_config_empty(self, temp_dir):
        """Test loading MCP config when none exists."""
        from containerized_strands_agents.agent import load_mcp_config
        
        agent_dir = temp_dir / "agent"
        (agent_dir / ".agent").mkdir(parents=True)
        
        # Clear env var to ensure we test the "no config" case
        with patch.dict(os.environ, {"CONTAINERIZED_AGENTS_MCP_CONFIG": ""}, clear=False):
            loaded = load_mcp_config(agent_dir)
            assert loaded == {}

    def test_create_mcp_clients_disabled_server(self, temp_dir):
        """Test that disabled MCP servers are skipped."""
        from containerized_strands_agents.agent import create_mcp_clients
        
        mcp_config = {
            "mcpServers": {
                "disabled-server": {
                    "command": "echo",
                    "args": ["test"],
                    "disabled": True
                }
            }
        }
        
        # Should return empty list since server is disabled
        clients = create_mcp_clients(mcp_config)
        assert clients == []

    def test_create_mcp_clients_no_mcp_package(self):
        """Test graceful handling when MCP package not available."""
        from containerized_strands_agents import agent
        
        # Temporarily set MCP_AVAILABLE to False
        original = agent.MCP_AVAILABLE
        agent.MCP_AVAILABLE = False
        
        try:
            clients = agent.create_mcp_clients({"mcpServers": {"test": {"command": "echo"}}})
            assert clients == []
        finally:
            agent.MCP_AVAILABLE = original
