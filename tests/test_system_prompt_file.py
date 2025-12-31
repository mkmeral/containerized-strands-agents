"""Tests for system_prompt_file feature."""

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


class TestSystemPromptFile:
    """Tests for system_prompt_file functionality."""

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

    def test_read_system_prompt_file_success(self, manager, tmp_path):
        """Test successfully reading system prompt from file."""
        # Create a test file
        prompt_content = "You are a specialized code reviewer.\nFocus on security and performance."
        test_file = tmp_path / "test_prompt.txt"
        test_file.write_text(prompt_content)
        
        # Test reading the file
        result = manager._read_system_prompt_file(str(test_file))
        assert result == prompt_content.strip()

    def test_read_system_prompt_file_with_tilde(self, manager, tmp_path):
        """Test reading system prompt file with tilde expansion."""
        # Create a test file
        prompt_content = "You are a data analyst."
        test_file = tmp_path / "prompt.txt"
        test_file.write_text(prompt_content)
        
        # Mock expanduser to return our test file
        with patch('pathlib.Path.expanduser') as mock_expand:
            mock_expand.return_value = test_file
            
            # Test reading with tilde path
            result = manager._read_system_prompt_file("~/prompt.txt")
            assert result == prompt_content.strip()

    def test_read_system_prompt_file_not_found(self, manager):
        """Test error when system prompt file doesn't exist."""
        with pytest.raises(FileNotFoundError) as exc_info:
            manager._read_system_prompt_file("/nonexistent/path/prompt.txt")
        
        assert "System prompt file not found" in str(exc_info.value)

    def test_read_system_prompt_file_is_directory(self, manager, tmp_path):
        """Test error when path is a directory instead of file."""
        directory = tmp_path / "test_dir"
        directory.mkdir()
        
        with pytest.raises(ValueError) as exc_info:
            manager._read_system_prompt_file(str(directory))
        
        assert "Path is not a file" in str(exc_info.value)

    def test_read_system_prompt_file_empty(self, manager, tmp_path):
        """Test error when system prompt file is empty."""
        empty_file = tmp_path / "empty.txt"
        empty_file.write_text("")
        
        with pytest.raises(ValueError) as exc_info:
            manager._read_system_prompt_file(str(empty_file))
        
        assert "System prompt file is empty" in str(exc_info.value)

    def test_read_system_prompt_file_whitespace_only(self, manager, tmp_path):
        """Test error when system prompt file contains only whitespace."""
        whitespace_file = tmp_path / "whitespace.txt"
        whitespace_file.write_text("   \n\t   ")
        
        with pytest.raises(ValueError) as exc_info:
            manager._read_system_prompt_file(str(whitespace_file))
        
        assert "System prompt file is empty" in str(exc_info.value)

    def test_read_system_prompt_file_permission_error(self, manager, tmp_path):
        """Test handling permission errors when reading file."""
        test_file = tmp_path / "protected.txt"
        test_file.write_text("content")
        
        # Mock open to raise PermissionError
        with patch('builtins.open', side_effect=PermissionError("Permission denied")):
            with pytest.raises(PermissionError):
                manager._read_system_prompt_file(str(test_file))

    @pytest.mark.asyncio
    async def test_get_or_create_agent_with_system_prompt_file(self, manager, mock_docker, tmp_path):
        """Test creating agent with system_prompt_file."""
        agent_id = "file-prompt-agent"
        prompt_content = "You are a specialized assistant for file operations."
        
        # Create system prompt file
        prompt_file = tmp_path / "agent_prompt.txt"
        prompt_file.write_text(prompt_content)
        
        # Mock container creation
        mock_container = MagicMock()
        mock_container.id = "container123"
        mock_docker.containers.run.return_value = mock_container
        
        # Mock wait for ready
        with patch.object(manager, '_wait_for_container_ready', return_value=True):
            agent = await manager.get_or_create_agent(
                agent_id, 
                system_prompt_file=str(prompt_file)
            )
        
        # Check agent was created
        assert agent.agent_id == agent_id
        assert agent.status == "running"
        
        # Check system prompt was saved from file
        loaded_prompt = manager._load_system_prompt(agent_id)
        assert loaded_prompt == prompt_content.strip()

    @pytest.mark.asyncio
    async def test_get_or_create_agent_file_precedence_over_text(self, manager, mock_docker, tmp_path):
        """Test that system_prompt_file takes precedence over system_prompt."""
        agent_id = "precedence-agent"
        file_content = "You are from the file."
        text_content = "You are from the text."
        
        # Create system prompt file
        prompt_file = tmp_path / "priority_prompt.txt"
        prompt_file.write_text(file_content)
        
        # Mock container creation
        mock_container = MagicMock()
        mock_container.id = "container456"
        mock_docker.containers.run.return_value = mock_container
        
        # Mock wait for ready
        with patch.object(manager, '_wait_for_container_ready', return_value=True):
            agent = await manager.get_or_create_agent(
                agent_id,
                system_prompt=text_content,  # This should be ignored
                system_prompt_file=str(prompt_file)  # This should take precedence
            )
        
        # Check that file content was used, not text content
        loaded_prompt = manager._load_system_prompt(agent_id)
        assert loaded_prompt == file_content.strip()
        assert loaded_prompt != text_content

    @pytest.mark.asyncio
    async def test_get_or_create_agent_file_not_found_error(self, manager, mock_docker):
        """Test error handling when system_prompt_file doesn't exist."""
        agent_id = "error-agent"
        nonexistent_file = "/path/to/nonexistent/file.txt"
        
        # Should raise ValueError due to file not found
        with pytest.raises(ValueError) as exc_info:
            await manager.get_or_create_agent(
                agent_id,
                system_prompt_file=nonexistent_file
            )
        
        assert "Failed to read system prompt file" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_send_message_with_system_prompt_file(self, manager, mock_docker, tmp_path):
        """Test send_message with system_prompt_file parameter."""
        agent_id = "send-file-agent"
        message = "Hello"
        prompt_content = "You are a helpful file-based assistant."
        
        # Create system prompt file
        prompt_file = tmp_path / "send_prompt.txt"
        prompt_file.write_text(prompt_content)
        
        # Mock container creation
        mock_container = MagicMock()
        mock_container.id = "container789"
        mock_docker.containers.run.return_value = mock_container
        
        # Mock wait for ready
        with patch.object(manager, '_wait_for_container_ready', return_value=True):
            result = await manager.send_message(
                agent_id,
                message,
                system_prompt_file=str(prompt_file)
            )
        
        # Check message was dispatched successfully
        assert result["status"] == "dispatched"
        assert result["agent_id"] == agent_id
        
        # Check system prompt was saved from file
        loaded_prompt = manager._load_system_prompt(agent_id)
        assert loaded_prompt == prompt_content.strip()

    @pytest.mark.asyncio
    async def test_send_message_file_error_returns_error_response(self, manager, mock_docker):
        """Test that file reading errors are returned as error responses."""
        agent_id = "error-response-agent"
        message = "Hello"
        nonexistent_file = "/nonexistent/file.txt"
        
        # Should return error response instead of raising exception
        result = await manager.send_message(
            agent_id,
            message,
            system_prompt_file=nonexistent_file
        )
        
        assert result["status"] == "error"
        assert "Failed to read system prompt file" in result["error"]

    @pytest.mark.asyncio
    async def test_send_message_file_and_text_precedence(self, manager, mock_docker, tmp_path):
        """Test precedence when both system_prompt and system_prompt_file are provided."""
        agent_id = "precedence-send-agent"
        message = "Test message"
        file_content = "Assistant from file"
        text_content = "Assistant from text"
        
        # Create system prompt file
        prompt_file = tmp_path / "precedence_send.txt"
        prompt_file.write_text(file_content)
        
        # Mock container creation
        mock_container = MagicMock()
        mock_container.id = "precedence123"
        mock_docker.containers.run.return_value = mock_container
        
        # Mock wait for ready
        with patch.object(manager, '_wait_for_container_ready', return_value=True):
            result = await manager.send_message(
                agent_id,
                message,
                system_prompt=text_content,  # Should be ignored
                system_prompt_file=str(prompt_file)  # Should take precedence
            )
        
        # Check success
        assert result["status"] == "dispatched"
        
        # Verify file content was used
        loaded_prompt = manager._load_system_prompt(agent_id)
        assert loaded_prompt == file_content.strip()
        assert loaded_prompt != text_content

    @pytest.mark.asyncio
    async def test_get_or_create_agent_existing_session_ignores_file(self, manager, mock_docker, tmp_path):
        """Test that system_prompt_file is ignored for agents with existing sessions."""
        agent_id = "existing-session-agent"
        original_prompt = "Original assistant"
        new_file_content = "New file assistant"
        
        # Create agent directory structure with .agent/ subdirectory
        agent_dir = tmp_path / "agents" / agent_id
        agent_dir.mkdir(parents=True)
        (agent_dir / ".agent").mkdir(parents=True)
        (agent_dir / ".agent" / "system_prompt.txt").write_text(original_prompt)
        
        # Create FileSessionManager-style message files
        messages_dir = agent_dir / ".agent" / "session" / "agents" / "agent_default" / "messages"
        messages_dir.mkdir(parents=True)
        msg = {"message": {"role": "user", "content": "Previous message"}, "message_id": 0}
        (messages_dir / "message_0.json").write_text(json.dumps(msg))
        
        # Create new prompt file
        new_prompt_file = tmp_path / "new_prompt.txt"
        new_prompt_file.write_text(new_file_content)
        
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
                system_prompt_file=str(new_prompt_file)
            )
        
        # Check system prompt wasn't changed (should still be original)
        loaded_prompt = manager._load_system_prompt(agent_id)
        assert loaded_prompt == original_prompt
        assert loaded_prompt != new_file_content

    def test_unicode_system_prompt_file(self, manager, tmp_path):
        """Test reading system prompt file with unicode content."""
        # Create file with unicode content
        unicode_content = "You are an assistant. 你好世界! 🚀✨"
        prompt_file = tmp_path / "unicode_prompt.txt"
        prompt_file.write_text(unicode_content, encoding='utf-8')
        
        # Test reading unicode content
        result = manager._read_system_prompt_file(str(prompt_file))
        assert result == unicode_content.strip()

    def test_multiline_system_prompt_file(self, manager, tmp_path):
        """Test reading multiline system prompt file."""
        multiline_content = """You are a specialized assistant.

Your responsibilities include:
1. Code review
2. Documentation
3. Testing

Always be thorough and precise."""
        
        prompt_file = tmp_path / "multiline_prompt.txt"
        prompt_file.write_text(multiline_content)
        
        result = manager._read_system_prompt_file(str(prompt_file))
        assert result == multiline_content.strip()
        assert "Code review" in result
        assert "Testing" in result