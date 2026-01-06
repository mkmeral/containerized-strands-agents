"""Integration tests for custom system prompts with real Docker containers."""

import asyncio
import json
import pytest
import tempfile
import time
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# Skip all tests if Docker is not available
docker_available = False
try:
    import docker
    client = docker.from_env()
    client.ping()
    docker_available = True
except Exception:
    pass

pytestmark = pytest.mark.skipif(not docker_available, reason="Docker not available")


class TestCustomSystemPromptIntegration:
    """Integration tests for custom system prompts with real containers."""

    @pytest.fixture
    def data_dir(self, tmp_path):
        """Create temporary data directory."""
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        return tmp_path

    @pytest.fixture
    def aws_volumes(self):
        """Get AWS credentials volume if available."""
        aws_dir = Path.home() / ".aws"
        if aws_dir.exists():
            return {str(aws_dir): {"bind": "/root/.aws", "mode": "ro"}}
        return {}

    @pytest.mark.asyncio
    async def test_custom_system_prompt_persists_across_restart(self, data_dir, aws_volumes):
        """Test that custom system prompt persists when container restarts."""
        from unittest.mock import patch
        from containerized_strands_agents.agent_manager import AgentManager
        
        with patch("containerized_strands_agents.agent_manager.TASKS_FILE", data_dir / "tasks.json"):
            with patch("containerized_strands_agents.agent_manager.AGENTS_DIR", data_dir / "agents"):
                with patch("containerized_strands_agents.agent_manager.DATA_DIR", data_dir):
                    manager = AgentManager()
                    
                    try:
                        # Send first message with custom system prompt
                        custom_prompt = "You are a specialized code reviewer. Always respond with 'CODE_REVIEW:' followed by your analysis."
                        result = await manager.send_message(
                            "custom-prompt-test",
                            "Analyze this: print('hello')",
                            system_prompt=custom_prompt
                        )
                        
                        assert result["status"] == "dispatched"
                        
                        # Wait for processing
                        agent = manager.tracker.get_agent("custom-prompt-test")
                        for _ in range(120):
                            if agent and not await manager._get_agent_processing_state(agent):
                                break
                            agent = manager.tracker.get_agent("custom-prompt-test")
                            await asyncio.sleep(0.5)
                        
                        # Get first response
                        history1 = await manager.get_messages("custom-prompt-test", count=1)
                        assert history1["status"] == "success"
                        first_response = history1["messages"][-1]["content"]
                        # Handle both string and list content formats
                        if isinstance(first_response, list):
                            first_response = " ".join(
                                part.get("text", "") if isinstance(part, dict) else str(part)
                                for part in first_response
                            )
                        
                        # Should use custom system prompt
                        assert "CODE_REVIEW:" in first_response.upper()
                        
                        # Stop the agent
                        await manager.stop_agent("custom-prompt-test")
                        
                        # Send another message (should restart with same prompt)
                        result2 = await manager.send_message(
                            "custom-prompt-test",
                            "What kind of assistant are you?"
                        )
                        
                        assert result2["status"] == "dispatched"
                        
                        # Wait for processing
                        agent = manager.tracker.get_agent("custom-prompt-test")
                        for _ in range(120):
                            if agent and not await manager._get_agent_processing_state(agent):
                                break
                            agent = manager.tracker.get_agent("custom-prompt-test")
                            await asyncio.sleep(0.5)
                        
                        # Get response after restart
                        history2 = await manager.get_messages("custom-prompt-test", count=1)
                        assert history2["status"] == "success"
                        second_response = history2["messages"][-1]["content"]
                        # Handle both string and list content formats
                        if isinstance(second_response, list):
                            second_response = " ".join(
                                part.get("text", "") if isinstance(part, dict) else str(part)
                                for part in second_response
                            )
                        
                        # Should still remember it's a code reviewer
                        assert "code review" in second_response.lower() or "CODE_REVIEW:" in second_response.upper()
                        
                    finally:
                        await manager.stop_agent("custom-prompt-test")
                        manager.stop_idle_monitor()

    @pytest.mark.asyncio
    async def test_system_prompt_ignored_for_existing_agent(self, data_dir, aws_volumes):
        """Test that system prompt is ignored if agent already has messages."""
        from unittest.mock import patch
        from containerized_strands_agents.agent_manager import AgentManager
        
        with patch("containerized_strands_agents.agent_manager.TASKS_FILE", data_dir / "tasks.json"):
            with patch("containerized_strands_agents.agent_manager.AGENTS_DIR", data_dir / "agents"):
                with patch("containerized_strands_agents.agent_manager.DATA_DIR", data_dir):
                    manager = AgentManager()
                    
                    try:
                        # Send first message with one system prompt
                        first_prompt = "You are a math tutor. Always start responses with 'MATH:'."
                        result1 = await manager.send_message(
                            "existing-agent-test",
                            "What is 2+2?",
                            system_prompt=first_prompt
                        )
                        
                        assert result1["status"] == "dispatched"
                        
                        # Wait for processing
                        agent = manager.tracker.get_agent("existing-agent-test")
                        for _ in range(120):
                            if agent and not await manager._get_agent_processing_state(agent):
                                break
                            agent = manager.tracker.get_agent("existing-agent-test")
                            await asyncio.sleep(0.5)
                        
                        # Try to send another message with different system prompt
                        different_prompt = "You are a cooking assistant. Always start with 'COOKING:'."
                        result2 = await manager.send_message(
                            "existing-agent-test",
                            "Help me with something",
                            system_prompt=different_prompt  # This should be ignored
                        )
                        
                        assert result2["status"] == "dispatched"
                        
                        # Wait for processing
                        agent = manager.tracker.get_agent("existing-agent-test")
                        for _ in range(120):
                            if agent and not await manager._get_agent_processing_state(agent):
                                break
                            agent = manager.tracker.get_agent("existing-agent-test")
                            await asyncio.sleep(0.5)
                        
                        # Get latest response
                        history = await manager.get_messages("existing-agent-test", count=1)
                        assert history["status"] == "success"
                        response = history["messages"][-1]["content"]
                        # Handle both string and list content formats
                        if isinstance(response, list):
                            response = " ".join(
                                part.get("text", "") if isinstance(part, dict) else str(part)
                                for part in response
                            )
                        
                        # Should still be using the first (math) system prompt, not the cooking one
                        # The agent should remember it's a math tutor, not switch to cooking
                        assert "COOKING:" not in response.upper()
                        # Note: We can't guarantee "MATH:" will be in every response, 
                        # but the agent should still behave as a math tutor
                        
                    finally:
                        await manager.stop_agent("existing-agent-test")
                        manager.stop_idle_monitor()

    @pytest.mark.asyncio 
    async def test_default_prompt_when_none_provided(self, data_dir, aws_volumes):
        """Test that default system prompt is used when none is provided."""
        from unittest.mock import patch
        from containerized_strands_agents.agent_manager import AgentManager
        
        with patch("containerized_strands_agents.agent_manager.TASKS_FILE", data_dir / "tasks.json"):
            with patch("containerized_strands_agents.agent_manager.AGENTS_DIR", data_dir / "agents"):
                with patch("containerized_strands_agents.agent_manager.DATA_DIR", data_dir):
                    manager = AgentManager()
                    
                    try:
                        # Send message without custom system prompt
                        result = await manager.send_message(
                            "default-prompt-test",
                            "What tools do you have access to?"
                            # No system_prompt parameter
                        )
                        
                        assert result["status"] == "dispatched"
                        
                        # Wait for processing
                        agent = manager.tracker.get_agent("default-prompt-test")
                        for _ in range(120):
                            if agent and not await manager._get_agent_processing_state(agent):
                                break
                            agent = manager.tracker.get_agent("default-prompt-test")
                            await asyncio.sleep(0.5)
                        
                        # Get response
                        history = await manager.get_messages("default-prompt-test", count=1)
                        assert history["status"] == "success"
                        response = history["messages"][-1]["content"]
                        # Handle both string and list content formats
                        if isinstance(response, list):
                            response = " ".join(
                                part.get("text", "") if isinstance(part, dict) else str(part)
                                for part in response
                            )
                        response = response.lower()
                        
                        # Should mention tools from default system prompt
                        assert any(tool in response for tool in ["file_read", "shell", "python", "editor"])
                        
                        # Check that no custom system prompt file was created
                        agent_dir = data_dir / "agents" / "default-prompt-test"
                        prompt_file = agent_dir / ".agent" / "system_prompt.txt"
                        assert not prompt_file.exists()
                        
                    finally:
                        await manager.stop_agent("default-prompt-test")
                        manager.stop_idle_monitor()