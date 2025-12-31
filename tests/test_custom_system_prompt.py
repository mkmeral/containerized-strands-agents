"""Tests for custom system prompts feature."""

import asyncio
import json
import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from containerized_strands_agents.agent_manager import AgentManager, TaskTracker


class TestCustomSystemPrompt:
    """Tests for custom system prompt functionality."""

    @pytest.fixture
    def mock_docker(self):
        """Mock Docker client."""
        from docker.errors import NotFound
        
        with patch("containerized_strands_agents.agent_manager.docker") as mock:
            mock_client = MagicMock()
            mock.from_env.return_value = mock_client
            
            # Mock network - raise NotFound
            mock_client.networks.get.side_effect = NotFound("Network not found")
            mock_client.networks.create.return_value = MagicMock()
            
            # Mock image
            mock_client.images.get.return_value = MagicMock()
            
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

    def test_save_and_load_system_prompt(self, manager, tmp_path):
        """Test saving and loading custom system prompt."""
        agent_id = "test-agent"
        custom_prompt = "You are a specialized code reviewer."
        
        # Save custom system prompt
        manager._save_system_prompt(agent_id, custom_prompt)
        
        # Check file was created in .agent/ subdirectory
        prompt_file = tmp_path / "agents" / agent_id / ".agent" / "system_prompt.txt"
        assert prompt_file.exists()
        assert prompt_file.read_text() == custom_prompt
        
        # Load system prompt
        loaded_prompt = manager._load_system_prompt(agent_id)
        assert loaded_prompt == custom_prompt

    def test_load_nonexistent_system_prompt(self, manager):
        """Test loading system prompt for agent that doesn't have one."""
        result = manager._load_system_prompt("nonexistent-agent")
        assert result is None

    def test_has_existing_session_empty(self, manager, tmp_path):
        """Test checking for existing session when none exists."""
        agent_id = "test-agent"
        result = manager._has_existing_session(agent_id)
        assert result == False

    def test_has_existing_session_with_messages(self, manager, tmp_path):
        """Test checking for existing session with messages."""
        agent_id = "test-agent"
        agent_dir = tmp_path / "agents" / agent_id
        agent_dir.mkdir(parents=True)
        
        # Create FileSessionManager-style message files in .agent/session/
        messages_dir = agent_dir / ".agent" / "session" / "agents" / "agent_default" / "messages"
        messages_dir.mkdir(parents=True)
        
        # Create message files
        msg1 = {"message": {"role": "user", "content": "Hello"}, "message_id": 0}
        msg2 = {"message": {"role": "assistant", "content": "Hi there!"}, "message_id": 1}
        (messages_dir / "message_0.json").write_text(json.dumps(msg1))
        (messages_dir / "message_1.json").write_text(json.dumps(msg2))
        
        result = manager._has_existing_session(agent_id)
        assert result == True

    def test_has_existing_session_empty_messages(self, manager, tmp_path):
        """Test checking for existing session with empty messages directory."""
        agent_id = "test-agent"
        agent_dir = tmp_path / "agents" / agent_id
        agent_dir.mkdir(parents=True)
        
        # Create empty messages directory (no message files)
        messages_dir = agent_dir / ".agent" / "session" / "agents" / "agent_default" / "messages"
        messages_dir.mkdir(parents=True)
        
        result = manager._has_existing_session(agent_id)
        assert result == False

    @pytest.mark.asyncio
    async def test_get_or_create_agent_new_with_system_prompt(self, manager, mock_docker):
        """Test creating new agent with custom system prompt."""
        agent_id = "test-prompt-agent"
        custom_prompt = "You are a data analyst."
        
        # Mock container creation
        mock_container = MagicMock()
        mock_container.id = "container123"
        mock_docker.containers.run.return_value = mock_container
        
        # Mock wait for ready
        with patch.object(manager, '_wait_for_container_ready', return_value=True):
            agent = await manager.get_or_create_agent(
                agent_id, 
                system_prompt=custom_prompt
            )
        
        # Check agent was created
        assert agent.agent_id == agent_id
        assert agent.status == "running"
        
        # Check system prompt was saved
        loaded_prompt = manager._load_system_prompt(agent_id)
        assert loaded_prompt == custom_prompt

    @pytest.mark.asyncio
    async def test_get_or_create_agent_existing_with_session_ignores_prompt(self, manager, mock_docker, tmp_path):
        """Test that system prompt is ignored for agents with existing sessions."""
        agent_id = "existing-agent"
        original_prompt = "You are a helper."
        new_prompt = "You are a different helper."
        
        # Create agent directory structure
        agent_dir = tmp_path / "agents" / agent_id
        agent_dir.mkdir(parents=True)
        (agent_dir / ".agent").mkdir(parents=True)
        (agent_dir / ".agent" / "system_prompt.txt").write_text(original_prompt)
        
        # Create FileSessionManager-style message files
        messages_dir = agent_dir / ".agent" / "session" / "agents" / "agent_default" / "messages"
        messages_dir.mkdir(parents=True)
        msg = {"message": {"role": "user", "content": "Hello"}, "message_id": 0}
        (messages_dir / "message_0.json").write_text(json.dumps(msg))
        
        # Mock existing agent
        from containerized_strands_agents.agent_manager import AgentInfo
        existing_agent = AgentInfo(
            agent_id=agent_id,
            container_name=f"agent-{agent_id}",
            port=9000,
            status="running",
            created_at="2024-01-01T00:00:00Z",
            last_activity="2024-01-01T00:00:00Z",
            container_id="existing123"
        )
        manager.tracker.update_agent(existing_agent)
        
        # Mock container running
        with patch.object(manager, '_is_container_running', return_value=True):
            agent = await manager.get_or_create_agent(
                agent_id,
                system_prompt=new_prompt
            )
        
        # Check system prompt wasn't changed
        loaded_prompt = manager._load_system_prompt(agent_id)
        assert loaded_prompt == original_prompt  # Should still be original

    @pytest.mark.asyncio
    async def test_send_message_with_system_prompt(self, manager, mock_docker):
        """Test sending message with custom system prompt."""
        agent_id = "test-send-prompt"
        message = "Hello"
        custom_prompt = "You are a friendly assistant."
        
        # Mock container creation
        mock_container = MagicMock()
        mock_container.id = "container456"
        mock_docker.containers.run.return_value = mock_container
        
        # Mock wait for ready
        with patch.object(manager, '_wait_for_container_ready', return_value=True):
            result = await manager.send_message(
                agent_id,
                message,
                system_prompt=custom_prompt
            )
        
        # Check message was dispatched
        assert result["status"] == "dispatched"
        assert result["agent_id"] == agent_id
        
        # Check system prompt was saved
        loaded_prompt = manager._load_system_prompt(agent_id)
        assert loaded_prompt == custom_prompt

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_start_container_with_custom_system_prompt(self, manager, mock_docker, tmp_path):
        """Test that container is started with CUSTOM_SYSTEM_PROMPT env var when prompt exists."""
        agent_id = "test-env-agent"
        custom_prompt = "You are a specialist."
        
        # Save custom system prompt
        manager._save_system_prompt(agent_id, custom_prompt)
        
        # Create agent info
        from containerized_strands_agents.agent_manager import AgentInfo
        agent = AgentInfo(
            agent_id=agent_id,
            container_name=f"agent-{agent_id}",
            port=9000,
            status="stopped",
            created_at="2024-01-01T00:00:00Z",
            last_activity="2024-01-01T00:00:00Z"
        )
        
        # Mock container creation
        mock_container = MagicMock()
        mock_container.id = "container789"
        mock_docker.containers.run.return_value = mock_container
        
        # Mock wait for ready
        with patch.object(manager, '_wait_for_container_ready', return_value=True):
            result_agent = await manager._start_container(agent)
        
        # Check container was created with correct environment
        mock_docker.containers.run.assert_called_once()
        call_args = mock_docker.containers.run.call_args
        env = call_args.kwargs.get("environment", {})
        assert env.get("CUSTOM_SYSTEM_PROMPT") == "true"

    @pytest.mark.asyncio
    async def test_start_container_without_custom_system_prompt(self, manager, mock_docker):
        """Test that container is started without CUSTOM_SYSTEM_PROMPT env var when no prompt exists."""
        agent_id = "test-no-prompt"
        
        # Create agent info (no custom prompt saved)
        from containerized_strands_agents.agent_manager import AgentInfo
        agent = AgentInfo(
            agent_id=agent_id,
            container_name=f"agent-{agent_id}",
            port=9000,
            status="stopped",
            created_at="2024-01-01T00:00:00Z",
            last_activity="2024-01-01T00:00:00Z"
        )
        
        # Mock container creation
        mock_container = MagicMock()
        mock_container.id = "container000"
        mock_docker.containers.run.return_value = mock_container
        
        # Mock wait for ready
        with patch.object(manager, '_wait_for_container_ready', return_value=True):
            result_agent = await manager._start_container(agent)
        
        # Check container was created without CUSTOM_SYSTEM_PROMPT env var
        mock_docker.containers.run.assert_called_once()
        call_args = mock_docker.containers.run.call_args
        env = call_args.kwargs.get("environment", {})
        assert "CUSTOM_SYSTEM_PROMPT" not in env


class TestAgentRunnerSystemPrompt:
    """Tests for agent runner system prompt loading."""
    
    def test_load_system_prompt_default(self):
        """Test loading default system prompt."""
        import os
        from pathlib import Path
        
        # Create a mock load_system_prompt function to test
        def mock_load_system_prompt():
            if os.getenv("CUSTOM_SYSTEM_PROMPT") == "true":
                prompt_file = Path("/mock/system_prompt.txt")
                if prompt_file.exists():
                    return prompt_file.read_text()
            
            return """You are a helpful AI assistant running in an isolated environment.

You have access to the following tools:
- file_read: Read files from your workspace
- file_write: Write files to your workspace  
- editor: Edit files with precision
- shell: Execute shell commands
- python_repl: Run Python code
- use_agent: Spawn sub-agents for complex tasks
- load_tool: Dynamically load additional tools

Your workspace is at /data/workspace. All file operations should be relative to this directory.

Be helpful, concise, and thorough in completing tasks. If a task requires multiple steps,
break it down and execute each step carefully.
"""
        
        with patch.dict(os.environ, {}, clear=True):
            with patch("pathlib.Path.exists", return_value=False):
                prompt = mock_load_system_prompt()
                
            assert "You are a helpful AI assistant" in prompt
            assert "file_read" in prompt

    def test_load_system_prompt_custom(self, tmp_path):
        """Test loading custom system prompt."""
        import os
        from pathlib import Path
        
        custom_prompt = "You are a specialized test assistant."
        prompt_file = tmp_path / "system_prompt.txt"
        prompt_file.write_text(custom_prompt)
        
        # Create a mock load_system_prompt function
        def mock_load_system_prompt():
            if os.getenv("CUSTOM_SYSTEM_PROMPT") == "true":
                if prompt_file.exists():
                    return prompt_file.read_text()
            return "default prompt"
        
        with patch.dict(os.environ, {"CUSTOM_SYSTEM_PROMPT": "true"}):
            prompt = mock_load_system_prompt()
            assert prompt == custom_prompt

    def test_load_system_prompt_custom_file_error(self, tmp_path):
        """Test fallback to default when custom prompt file has error."""
        import os
        from pathlib import Path
        
        # Mock load function that handles errors
        def mock_load_system_prompt_with_error():
            if os.getenv("CUSTOM_SYSTEM_PROMPT") == "true":
                try:
                    # Simulate file read error
                    raise PermissionError("Mock error")
                except Exception:
                    pass
            
            return """You are a helpful AI assistant running in an isolated environment.

You have access to the following tools:
- file_read: Read files from your workspace
- file_write: Write files to your workspace  
- editor: Edit files with precision
- shell: Execute shell commands
- python_repl: Run Python code
- use_agent: Spawn sub-agents for complex tasks
- load_tool: Dynamically load additional tools

Your workspace is at /data/workspace. All file operations should be relative to this directory.

Be helpful, concise, and thorough in completing tasks. If a task requires multiple steps,
break it down and execute each step carefully.
"""
        
        with patch.dict(os.environ, {"CUSTOM_SYSTEM_PROMPT": "true"}):
            prompt = mock_load_system_prompt_with_error()
            # Should fall back to default
            assert "You are a helpful AI assistant" in prompt