"""End-to-end test for the MCP server using the AgentManager directly."""

import asyncio
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Skip if Docker not available
docker_available = False
try:
    import docker
    client = docker.from_env()
    client.ping()
    docker_available = True
except Exception:
    pass

pytestmark = pytest.mark.skipif(not docker_available, reason="Docker not available")


@pytest.fixture
def temp_data_dir(tmp_path):
    """Create temporary data directory structure."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    tasks_file = tmp_path / "tasks.json"
    return tmp_path, tasks_file, agents_dir


@pytest.mark.asyncio
async def test_agent_manager_full_flow(temp_data_dir):
    """Test full flow: create agent, send message, get history, stop."""
    from unittest.mock import patch
    from containerized_strands_agents.agent_manager import AgentManager
    
    tmp_path, tasks_file, agents_dir = temp_data_dir
    
    with patch("containerized_strands_agents.agent_manager.TASKS_FILE", tasks_file):
        with patch("containerized_strands_agents.agent_manager.AGENTS_DIR", agents_dir):
            with patch("containerized_strands_agents.agent_manager.DATA_DIR", tmp_path):
                manager = AgentManager()
                
                try:
                    # Send a message (creates agent) - fire and forget
                    result = await manager.send_message(
                        "e2e-test-agent",
                        "Say 'E2E test successful' and nothing else.",
                    )
                    
                    assert result["status"] == "dispatched", f"Failed: {result}"
                    assert result["agent_id"] == "e2e-test-agent"
                    
                    # Wait for processing to complete
                    for _ in range(120):  # Wait up to 60 seconds
                        if not manager.is_agent_processing("e2e-test-agent"):
                            break
                        await asyncio.sleep(0.5)
                    
                    assert not manager.is_agent_processing("e2e-test-agent"), "Agent still processing"
                    
                    # List agents
                    agents = manager.list_agents()
                    agent_ids = [a["agent_id"] for a in agents]
                    assert "e2e-test-agent" in agent_ids
                    e2e_agent = next(a for a in agents if a["agent_id"] == "e2e-test-agent")
                    assert e2e_agent["status"] == "running"
                    assert e2e_agent["processing"] == False
                    
                    # Get messages
                    history = await manager.get_messages("e2e-test-agent", count=5)
                    assert history["status"] == "success"
                    assert len(history["messages"]) >= 2  # At least user + assistant
                    print(f"Response: {history['messages'][-1]['content']}")
                    
                    # Stop agent
                    stopped = await manager.stop_agent("e2e-test-agent")
                    assert stopped
                    
                    # Verify stopped
                    agents = manager.list_agents()
                    e2e_agent = next(a for a in agents if a["agent_id"] == "e2e-test-agent")
                    assert e2e_agent["status"] == "stopped"
                    
                finally:
                    # Cleanup
                    await manager.stop_agent("e2e-test-agent")
                    manager.stop_idle_monitor()


@pytest.mark.asyncio
async def test_agent_restart_preserves_history(temp_data_dir):
    """Test that restarting an agent preserves conversation history."""
    from unittest.mock import patch
    from containerized_strands_agents.agent_manager import AgentManager
    
    tmp_path, tasks_file, agents_dir = temp_data_dir
    
    with patch("containerized_strands_agents.agent_manager.TASKS_FILE", tasks_file):
        with patch("containerized_strands_agents.agent_manager.AGENTS_DIR", agents_dir):
            with patch("containerized_strands_agents.agent_manager.DATA_DIR", tmp_path):
                manager = AgentManager()
                
                try:
                    # Send first message (fire and forget)
                    result1 = await manager.send_message(
                        "restart-test",
                        "Remember the secret code: ALPHA123",
                    )
                    assert result1["status"] == "dispatched"
                    
                    # Wait for processing
                    for _ in range(120):
                        if not manager.is_agent_processing("restart-test"):
                            break
                        await asyncio.sleep(0.5)
                    
                    # Stop agent
                    await manager.stop_agent("restart-test")
                    
                    # Send another message (should restart and have history)
                    result2 = await manager.send_message(
                        "restart-test",
                        "What was the secret code I told you?",
                    )
                    assert result2["status"] == "dispatched"
                    
                    # Wait for processing
                    for _ in range(120):
                        if not manager.is_agent_processing("restart-test"):
                            break
                        await asyncio.sleep(0.5)
                    
                    # Check if it remembers via get_messages
                    history = await manager.get_messages("restart-test", count=1)
                    assert history["status"] == "success"
                    response = history["messages"][-1]["content"].upper()
                    assert "ALPHA123" in response, f"Agent didn't remember: {response}"
                    
                finally:
                    await manager.stop_agent("restart-test")
                    manager.stop_idle_monitor()
