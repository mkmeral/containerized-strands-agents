"""Integration tests for Agent Host MCP Server.

These tests require Docker to be running and will create actual containers.
"""

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


class TestDockerIntegration:
    """Integration tests with real Docker containers."""

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
    async def test_container_health_check(self, data_dir, aws_volumes):
        """Test that container starts and responds to health check."""
        import docker
        import httpx
        
        client = docker.from_env()
        agent_dir = data_dir / "agents" / "test-health"
        agent_dir.mkdir(parents=True)
        (agent_dir / "workspace").mkdir()
        
        volumes = {str(agent_dir.absolute()): {"bind": "/data", "mode": "rw"}}
        volumes.update(aws_volumes)
        
        container = None
        try:
            # Start container
            container = client.containers.run(
                "agent-host-runner",
                name="test-health-check",
                detach=True,
                ports={"8080/tcp": 19000},
                volumes=volumes,
                environment={
                    "AGENT_ID": "test-health",
                    "IDLE_TIMEOUT_MINUTES": "30",
                    "AWS_DEFAULT_REGION": "us-east-1",
                },
            )
            
            # Wait for container to be ready
            async with httpx.AsyncClient() as http_client:
                for _ in range(30):
                    try:
                        resp = await http_client.get("http://localhost:19000/health", timeout=2.0)
                        if resp.status_code == 200:
                            data = resp.json()
                            assert data["status"] == "healthy"
                            assert data["agent_id"] == "test-health"
                            return
                    except Exception:
                        pass
                    await asyncio.sleep(1)
                
                pytest.fail("Container did not become healthy in time")
        finally:
            if container:
                container.remove(force=True)

    @pytest.mark.asyncio
    async def test_container_chat_simple(self, data_dir, aws_volumes):
        """Test sending a simple message to container."""
        import docker
        import httpx
        
        client = docker.from_env()
        agent_dir = data_dir / "agents" / "test-chat"
        agent_dir.mkdir(parents=True)
        (agent_dir / "workspace").mkdir()
        
        volumes = {str(agent_dir.absolute()): {"bind": "/data", "mode": "rw"}}
        volumes.update(aws_volumes)
        
        container = None
        try:
            container = client.containers.run(
                "agent-host-runner",
                name="test-chat-simple",
                detach=True,
                ports={"8080/tcp": 19001},
                volumes=volumes,
                environment={
                    "AGENT_ID": "test-chat",
                    "IDLE_TIMEOUT_MINUTES": "30",
                    "AWS_DEFAULT_REGION": "us-east-1",
                },
            )
            
            # Wait for ready
            async with httpx.AsyncClient(timeout=60.0) as http_client:
                for _ in range(30):
                    try:
                        resp = await http_client.get("http://localhost:19001/health", timeout=2.0)
                        if resp.status_code == 200:
                            break
                    except Exception:
                        pass
                    await asyncio.sleep(1)
                
                # Send a simple message
                resp = await http_client.post(
                    "http://localhost:19001/chat",
                    json={"message": "Say 'hello test' and nothing else."},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["status"] == "success"
                assert "response" in data
                
        finally:
            if container:
                container.remove(force=True)

    @pytest.mark.asyncio
    async def test_session_persistence(self, data_dir, aws_volumes):
        """Test that session is persisted to file."""
        import docker
        import httpx
        
        client = docker.from_env()
        agent_dir = data_dir / "agents" / "test-persist"
        agent_dir.mkdir(parents=True)
        (agent_dir / "workspace").mkdir()
        
        volumes = {str(agent_dir.absolute()): {"bind": "/data", "mode": "rw"}}
        volumes.update(aws_volumes)
        
        container = None
        try:
            container = client.containers.run(
                "agent-host-runner",
                name="test-persist",
                detach=True,
                ports={"8080/tcp": 19002},
                volumes=volumes,
                environment={
                    "AGENT_ID": "test-persist",
                    "IDLE_TIMEOUT_MINUTES": "30",
                    "AWS_DEFAULT_REGION": "us-east-1",
                },
            )
            
            # Wait for ready
            async with httpx.AsyncClient(timeout=60.0) as http_client:
                for _ in range(30):
                    try:
                        resp = await http_client.get("http://localhost:19002/health", timeout=2.0)
                        if resp.status_code == 200:
                            break
                    except Exception:
                        pass
                    await asyncio.sleep(1)
                
                # Send a message
                resp = await http_client.post(
                    "http://localhost:19002/chat",
                    json={"message": "Remember the number 42."},
                )
                assert resp.status_code == 200
                
                # Check session files exist in new .agent/session/ location
                # FileSessionManager stores messages in: .agent/session/agents/agent_default/messages/
                messages_dir = agent_dir / ".agent" / "session" / "agents" / "agent_default" / "messages"
                
                # Wait a bit for files to be written
                for _ in range(10):
                    if messages_dir.exists() and list(messages_dir.glob("message_*.json")):
                        break
                    await asyncio.sleep(0.5)
                
                assert messages_dir.exists(), "Session messages directory should be created"
                message_files = list(messages_dir.glob("message_*.json"))
                assert len(message_files) > 0, "Session should have message files"
                
        finally:
            if container:
                container.remove(force=True)

    @pytest.mark.asyncio
    async def test_history_endpoint(self, data_dir, aws_volumes):
        """Test getting conversation history."""
        import docker
        import httpx
        
        client = docker.from_env()
        agent_dir = data_dir / "agents" / "test-history"
        agent_dir.mkdir(parents=True)
        (agent_dir / "workspace").mkdir()
        
        volumes = {str(agent_dir.absolute()): {"bind": "/data", "mode": "rw"}}
        volumes.update(aws_volumes)
        
        container = None
        try:
            container = client.containers.run(
                "agent-host-runner",
                name="test-history",
                detach=True,
                ports={"8080/tcp": 19003},
                volumes=volumes,
                environment={
                    "AGENT_ID": "test-history",
                    "IDLE_TIMEOUT_MINUTES": "30",
                    "AWS_DEFAULT_REGION": "us-east-1",
                },
            )
            
            # Wait for ready
            async with httpx.AsyncClient(timeout=60.0) as http_client:
                for _ in range(30):
                    try:
                        resp = await http_client.get("http://localhost:19003/health", timeout=2.0)
                        if resp.status_code == 200:
                            break
                    except Exception:
                        pass
                    await asyncio.sleep(1)
                
                # Send a message
                await http_client.post(
                    "http://localhost:19003/chat",
                    json={"message": "Hello!"},
                )
                
                # Get history
                resp = await http_client.get("http://localhost:19003/history?count=10")
                assert resp.status_code == 200
                data = resp.json()
                assert data["status"] == "success"
                assert "messages" in data
                assert len(data["messages"]) > 0
                
        finally:
            if container:
                container.remove(force=True)
