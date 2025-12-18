"""Agent Manager - Handles Docker container lifecycle for agents."""

import asyncio
import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import docker
import httpx
from docker.errors import NotFound, APIError
from pydantic import BaseModel

from containerized_strands_agents.config import (
    AGENTS_DIR,
    CONTAINER_PORT,
    CONTAINER_STARTUP_TIMEOUT_SECONDS,
    DATA_DIR,
    DOCKER_IMAGE_NAME,
    DOCKER_NETWORK,
    IDLE_TIMEOUT_MINUTES,
    TASKS_FILE,
)

logger = logging.getLogger(__name__)


class AgentInfo(BaseModel):
    """Information about a managed agent."""
    agent_id: str
    container_id: Optional[str] = None
    container_name: str
    port: int
    status: str  # running, stopped, error
    created_at: str
    last_activity: str
    data_dir: Optional[str] = None  # Custom data directory for this agent


class TaskTracker:
    """Persists agent state to JSON file."""

    def __init__(self, tasks_file: Path = TASKS_FILE):
        self.tasks_file = tasks_file
        self._ensure_dirs()

    def _ensure_dirs(self):
        self.tasks_file.parent.mkdir(parents=True, exist_ok=True)
        AGENTS_DIR.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, AgentInfo]:
        if not self.tasks_file.exists():
            return {}
        try:
            data = json.loads(self.tasks_file.read_text())
            return {k: AgentInfo(**v) for k, v in data.items()}
        except Exception as e:
            logger.error(f"Failed to load tasks file: {e}")
            return {}

    def save(self, agents: dict[str, AgentInfo]):
        self.tasks_file.write_text(
            json.dumps({k: v.model_dump() for k, v in agents.items()}, indent=2)
        )

    def get_agent(self, agent_id: str) -> Optional[AgentInfo]:
        agents = self.load()
        return agents.get(agent_id)

    def update_agent(self, agent: AgentInfo):
        agents = self.load()
        agents[agent.agent_id] = agent
        self.save(agents)

    def remove_agent(self, agent_id: str):
        agents = self.load()
        if agent_id in agents:
            del agents[agent_id]
            self.save(agents)


class AgentManager:
    """Manages Docker containers for agents."""

    def __init__(self):
        self.docker_client = docker.from_env()
        self.tracker = TaskTracker()
        self._port_counter = 9000
        self._ensure_network()
        self._ensure_image()
        self._idle_monitor_task: Optional[asyncio.Task] = None

    def _ensure_network(self):
        """Ensure Docker network exists."""
        try:
            self.docker_client.networks.get(DOCKER_NETWORK)
        except NotFound:
            self.docker_client.networks.create(DOCKER_NETWORK, driver="bridge")
            logger.info(f"Created Docker network: {DOCKER_NETWORK}")

    def _ensure_image(self):
        """Ensure Docker image exists, build if not."""
        try:
            self.docker_client.images.get(DOCKER_IMAGE_NAME)
            logger.debug(f"Docker image {DOCKER_IMAGE_NAME} found")
        except NotFound:
            logger.info(f"Docker image {DOCKER_IMAGE_NAME} not found, building...")
            self._build_image()

    def _build_image(self):
        """Build the agent runner Docker image."""
        # Find the docker directory relative to this file
        # Path: src/containerized_strands_agents/agent_manager.py -> ../.. -> project_root/docker
        docker_dir = Path(__file__).parent.parent.parent / "docker"
        
        if not docker_dir.exists():
            raise RuntimeError(
                f"Docker directory not found at {docker_dir}. "
                f"Please run ./scripts/build_docker.sh manually."
            )
        
        logger.info(f"Building Docker image from {docker_dir}...")
        try:
            image, logs = self.docker_client.images.build(
                path=str(docker_dir),
                tag=DOCKER_IMAGE_NAME,
                rm=True,
            )
            for log in logs:
                if "stream" in log:
                    logger.debug(log["stream"].strip())
            logger.info(f"Successfully built Docker image: {DOCKER_IMAGE_NAME}")
        except Exception as e:
            raise RuntimeError(f"Failed to build Docker image: {e}")

    def _get_next_port(self) -> int:
        """Get next available port for container."""
        agents = self.tracker.load()
        used_ports = {a.port for a in agents.values()}
        while self._port_counter in used_ports:
            self._port_counter += 1
        port = self._port_counter
        self._port_counter += 1
        return port

    def _get_agent_dir(self, agent_id: str, custom_data_dir: str | None = None) -> Path:
        """Get the data directory for an agent.
        
        Args:
            agent_id: The agent identifier.
            custom_data_dir: Optional custom data directory path. If provided,
                           the agent data will be stored there instead of the
                           default AGENTS_DIR.
        """
        if custom_data_dir:
            # Use custom data directory - resolve and expand user paths
            agent_dir = Path(custom_data_dir).expanduser().resolve()
        else:
            # Use default agents directory
            agent_dir = AGENTS_DIR / agent_id
        
        agent_dir.mkdir(parents=True, exist_ok=True)
        (agent_dir / "workspace").mkdir(exist_ok=True)
        (agent_dir / "tools").mkdir(exist_ok=True)
        return agent_dir

    def _copy_global_tools(self, agent_id: str, data_dir: str | None = None):
        """Copy global tools from CONTAINERIZED_AGENTS_TOOLS env var."""
        global_tools_dir = os.environ.get("CONTAINERIZED_AGENTS_TOOLS")
        if not global_tools_dir:
            return
        
        global_tools_path = Path(global_tools_dir).expanduser().resolve()
        if not global_tools_path.exists() or not global_tools_path.is_dir():
            logger.warning(f"Global tools directory not found or not a directory: {global_tools_dir}")
            return
        
        agent_tools_dir = self._get_agent_dir(agent_id, data_dir) / "tools"
        
        try:
            # Copy all .py files from global tools directory
            for tool_file in global_tools_path.glob("*.py"):
                dest_file = agent_tools_dir / tool_file.name
                shutil.copy2(tool_file, dest_file)
                logger.info(f"Copied global tool {tool_file.name} to agent {agent_id}")
        except Exception as e:
            logger.error(f"Failed to copy global tools to agent {agent_id}: {e}")

    def _copy_per_agent_tools(self, agent_id: str, tools: list[str] | None, data_dir: str | None = None):
        """Copy per-agent tools to the agent's tools directory."""
        if not tools:
            return
        
        agent_tools_dir = self._get_agent_dir(agent_id, data_dir) / "tools"
        
        for tool_path in tools:
            try:
                tool_path_obj = Path(tool_path).expanduser().resolve()
                if not tool_path_obj.exists():
                    logger.error(f"Tool file not found: {tool_path}")
                    continue
                if not tool_path_obj.is_file() or not tool_path_obj.suffix == '.py':
                    logger.error(f"Tool path is not a .py file: {tool_path}")
                    continue
                
                dest_file = agent_tools_dir / tool_path_obj.name
                shutil.copy2(tool_path_obj, dest_file)
                logger.info(f"Copied per-agent tool {tool_path_obj.name} to agent {agent_id}")
            except Exception as e:
                logger.error(f"Failed to copy tool {tool_path} to agent {agent_id}: {e}")

    def _save_system_prompt(self, agent_id: str, system_prompt: str, data_dir: str | None = None):
        """Save custom system prompt for an agent."""
        agent_dir = self._get_agent_dir(agent_id, data_dir)
        prompt_file = agent_dir / "system_prompt.txt"
        prompt_file.write_text(system_prompt)
        logger.info(f"Saved custom system prompt for agent {agent_id}")

    def _load_system_prompt(self, agent_id: str, data_dir: str | None = None) -> Optional[str]:
        """Load custom system prompt for an agent."""
        agent_dir = self._get_agent_dir(agent_id, data_dir)
        prompt_file = agent_dir / "system_prompt.txt"
        if prompt_file.exists():
            return prompt_file.read_text()
        return None

    def _read_system_prompt_file(self, file_path: str) -> str:
        """Read system prompt from a file on the host machine.
        
        Args:
            file_path: Path to the file on the host machine.
            
        Returns:
            str: Content of the file.
            
        Raises:
            FileNotFoundError: If the file doesn't exist.
            PermissionError: If the file can't be read due to permissions.
            Exception: For other file reading errors.
        """
        try:
            file_path_obj = Path(file_path).expanduser().resolve()
            if not file_path_obj.exists():
                raise FileNotFoundError(f"System prompt file not found: {file_path}")
            if not file_path_obj.is_file():
                raise ValueError(f"Path is not a file: {file_path}")
            
            with open(file_path_obj, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                
            if not content:
                raise ValueError(f"System prompt file is empty: {file_path}")
                
            logger.info(f"Successfully read system prompt from file: {file_path}")
            return content
            
        except Exception as e:
            logger.error(f"Failed to read system prompt file {file_path}: {e}")
            raise

    def _has_existing_session(self, agent_id: str, data_dir: str | None = None) -> bool:
        """Check if agent has an existing session (messages)."""
        agent_dir = self._get_agent_dir(agent_id, data_dir)
        # FileSessionManager stores messages in: session_{agent_id}/agents/agent_default/messages/
        messages_dir = agent_dir / f"session_{agent_id}" / "agents" / "agent_default" / "messages"
        if messages_dir.exists():
            try:
                message_files = list(messages_dir.glob("message_*.json"))
                return len(message_files) > 0
            except Exception:
                return False
        return False

    async def _wait_for_container_ready(self, port: int, timeout: int = CONTAINER_STARTUP_TIMEOUT_SECONDS):
        """Wait for container HTTP API to be ready."""
        url = f"http://localhost:{port}/health"
        async with httpx.AsyncClient() as client:
            start = asyncio.get_event_loop().time()
            while asyncio.get_event_loop().time() - start < timeout:
                try:
                    resp = await client.get(url, timeout=2.0)
                    if resp.status_code == 200:
                        return True
                except Exception:
                    pass
                await asyncio.sleep(0.5)
        return False

    def _is_container_running(self, container_id: str) -> bool:
        """Check if container is running."""
        try:
            container = self.docker_client.containers.get(container_id)
            return container.status == "running"
        except NotFound:
            return False

    async def get_or_create_agent(
        self,
        agent_id: str,
        aws_profile: str | None = None,
        aws_region: str | None = None,
        system_prompt: str | None = None,
        system_prompt_file: str | None = None,
        tools: list[str] | None = None,
        data_dir: str | None = None,
    ) -> AgentInfo:
        """Get existing agent or create new one.
        
        Args:
            data_dir: Optional custom data directory for this agent. If provided,
                     agent data will be stored there instead of the default location.
                     Useful for project-specific agents.
        """
        agent = self.tracker.get_agent(agent_id)
        
        # If agent exists and data_dir is provided, update it
        if agent and data_dir:
            agent.data_dir = data_dir
            self.tracker.update_agent(agent)
        
        # Use agent's stored data_dir or the provided one
        effective_data_dir = data_dir or (agent.data_dir if agent else None)
        
        # Handle system prompt with precedence: file > text > existing
        resolved_system_prompt = None
        try:
            if system_prompt_file:
                # system_prompt_file takes precedence over system_prompt
                resolved_system_prompt = self._read_system_prompt_file(system_prompt_file)
                logger.info(f"Using system prompt from file {system_prompt_file} for agent {agent_id}")
            elif system_prompt:
                resolved_system_prompt = system_prompt
                logger.info(f"Using provided system prompt for agent {agent_id}")
        except Exception as e:
            # If file reading fails, return an error instead of proceeding
            logger.error(f"Failed to process system prompt file for agent {agent_id}: {e}")
            raise ValueError(f"Failed to read system prompt file: {e}")
        
        if resolved_system_prompt:
            if agent and self._has_existing_session(agent_id, effective_data_dir):
                # Agent exists with session - don't change system prompt
                logger.warning(f"Ignoring system_prompt for agent {agent_id} - agent already has messages")
            else:
                # New agent or agent without messages - save the system prompt
                self._save_system_prompt(agent_id, resolved_system_prompt, effective_data_dir)
        
        # Copy tools before starting/restarting container
        # Always copy tools for new agents or when tools are specified
        if not agent or tools:
            # Copy global tools first
            self._copy_global_tools(agent_id, effective_data_dir)
            # Copy per-agent tools (these can override global tools with same names)
            self._copy_per_agent_tools(agent_id, tools, effective_data_dir)
        
        if agent and agent.container_id:
            # Check if container is still running
            if self._is_container_running(agent.container_id):
                agent.last_activity = datetime.now(timezone.utc).isoformat()
                self.tracker.update_agent(agent)
                return agent
            else:
                # Container stopped, restart it
                logger.info(f"Restarting stopped container for agent {agent_id}")
                return await self._start_container(agent, aws_profile=aws_profile, aws_region=aws_region)
        
        # Create new agent
        return await self._create_agent(agent_id, aws_profile=aws_profile, aws_region=aws_region, data_dir=effective_data_dir)

    async def _create_agent(
        self,
        agent_id: str,
        aws_profile: str | None = None,
        aws_region: str | None = None,
        data_dir: str | None = None,
    ) -> AgentInfo:
        """Create a new agent with Docker container."""
        port = self._get_next_port()
        container_name = f"agent-{agent_id}"
        agent_dir = self._get_agent_dir(agent_id, data_dir)
        now = datetime.now(timezone.utc).isoformat()

        agent = AgentInfo(
            agent_id=agent_id,
            container_name=container_name,
            port=port,
            status="starting",
            created_at=now,
            last_activity=now,
            data_dir=data_dir,
        )

        return await self._start_container(agent, aws_profile=aws_profile, aws_region=aws_region)

    async def _start_container(
        self,
        agent: AgentInfo,
        aws_profile: str | None = None,
        aws_region: str | None = None,
    ) -> AgentInfo:
        """Start or restart a container for an agent."""
        agent_dir = self._get_agent_dir(agent.agent_id, agent.data_dir)
        
        # Remove existing container if any
        try:
            old_container = self.docker_client.containers.get(agent.container_name)
            old_container.remove(force=True)
        except NotFound:
            pass

        # Build environment
        env = {
            "AGENT_ID": agent.agent_id,
            "IDLE_TIMEOUT_MINUTES": str(IDLE_TIMEOUT_MINUTES),
        }
        
        # Set AWS profile if specified (will use ~/.aws/credentials)
        if aws_profile:
            env["AWS_PROFILE"] = aws_profile
        
        # Set AWS region if specified
        if aws_region:
            env["AWS_DEFAULT_REGION"] = aws_region
            env["AWS_REGION"] = aws_region
        else:
            # Default to us-east-1 if not specified
            env["AWS_DEFAULT_REGION"] = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        
        # Check if there's a custom system prompt
        custom_system_prompt = self._load_system_prompt(agent.agent_id, agent.data_dir)
        if custom_system_prompt:
            env["CUSTOM_SYSTEM_PROMPT"] = "true"
        
        # Pass GitHub token if available (for git push access)
        github_token = os.environ.get("CONTAINERIZED_AGENTS_GITHUB_TOKEN")
        if github_token:
            env["CONTAINERIZED_AGENTS_GITHUB_TOKEN"] = github_token
        
        # Build volumes - include AWS credentials directory if it exists
        volumes = {
            str(agent_dir.absolute()): {"bind": "/data", "mode": "rw"},
        }
        
        # Mount the tools directory into /app/tools for the agent to load
        agent_tools_dir = agent_dir / "tools"
        if agent_tools_dir.exists():
            volumes[str(agent_tools_dir.absolute())] = {"bind": "/app/tools", "mode": "ro"}
        
        aws_dir = Path.home() / ".aws"
        if aws_dir.exists():
            volumes[str(aws_dir)] = {"bind": "/root/.aws", "mode": "ro"}

        try:
            container = self.docker_client.containers.run(
                DOCKER_IMAGE_NAME,
                name=agent.container_name,
                detach=True,
                ports={f"{CONTAINER_PORT}/tcp": agent.port},
                volumes=volumes,
                environment=env,
                network=DOCKER_NETWORK,
            )
            
            agent.container_id = container.id
            agent.status = "starting"
            self.tracker.update_agent(agent)

            # Wait for container to be ready
            if await self._wait_for_container_ready(agent.port):
                agent.status = "running"
            else:
                agent.status = "error"
                logger.error(f"Container for agent {agent.agent_id} failed to start")

            self.tracker.update_agent(agent)
            return agent

        except APIError as e:
            logger.error(f"Failed to start container for agent {agent.agent_id}: {e}")
            agent.status = "error"
            self.tracker.update_agent(agent)
            raise

    async def send_message(
        self,
        agent_id: str,
        message: str,
        aws_profile: str | None = None,
        aws_region: str | None = None,
        system_prompt: str | None = None,
        system_prompt_file: str | None = None,
        tools: list[str] | None = None,
        data_dir: str | None = None,
    ) -> dict:
        """Send a message to an agent (fire-and-forget).
        
        Returns immediately after dispatching. Use get_messages to check response.
        
        Args:
            data_dir: Optional custom data directory for this agent. If provided,
                     agent data will be stored there instead of the default location.
                     Useful for project-specific agents.
        """
        try:
            agent = await self.get_or_create_agent(
                agent_id, 
                aws_profile=aws_profile, 
                aws_region=aws_region,
                system_prompt=system_prompt,
                system_prompt_file=system_prompt_file,
                tools=tools,
                data_dir=data_dir,
            )
        except ValueError as e:
            # Handle system prompt file errors
            return {"status": "error", "error": str(e)}
        except Exception as e:
            logger.error(f"Failed to get or create agent {agent_id}: {e}")
            return {"status": "error", "error": f"Failed to initialize agent: {e}"}
        
        if agent.status != "running":
            return {"status": "error", "error": f"Agent not running: {agent.status}"}

        # Update last activity now (we're about to send)
        agent.last_activity = datetime.now(timezone.utc).isoformat()
        self.tracker.update_agent(agent)
        
        # Fire and forget - spawn background task that we don't track
        # The container handles everything, we just need to send the request
        asyncio.create_task(self._dispatch_message(agent_id, agent.port, message))
        
        return {
            "status": "dispatched",
            "agent_id": agent_id,
            "message": "Message sent. Use get_messages to check for response.",
        }
    
    async def _dispatch_message(self, agent_id: str, port: int, message: str):
        """Send message to container. Fire and forget - no tracking needed."""
        url = f"http://localhost:{port}/chat"
        try:
            # Long timeout since agent tasks can take a while
            async with httpx.AsyncClient(timeout=httpx.Timeout(3600.0, connect=30.0)) as client:
                await client.post(url, json={"message": message})
                logger.info(f"Agent {agent_id} finished processing")
        except Exception as e:
            # Just log - container handles persistence, nothing for us to do
            logger.warning(f"Message dispatch to {agent_id} ended: {e}")

    async def get_messages(self, agent_id: str, count: int = 1) -> dict:
        """Get messages from an agent's history."""
        agent = self.tracker.get_agent(agent_id)
        
        if not agent:
            return {"status": "error", "error": f"Agent {agent_id} not found"}

        # Base response with agent info
        base_response = {
            "status": "success",
            "agent_id": agent_id,
            "container_id": agent.container_id,
            "processing": False,  # We don't track this anymore
        }

        # If container is running, get from API
        if agent.container_id and self._is_container_running(agent.container_id):
            url = f"http://localhost:{agent.port}/history"
            async with httpx.AsyncClient() as client:
                try:
                    resp = await client.get(url, params={"count": count})
                    resp.raise_for_status()
                    data = resp.json()
                    return {**base_response, "messages": data.get("messages", [])}
                except Exception as e:
                    logger.error(f"Failed to get messages from agent {agent_id}: {e}")

        # Fallback: read from FileSessionManager storage
        # FileSessionManager stores messages in: session_{agent_id}/agents/agent_default/messages/
        # Each file has structure: {"message": {...}, "message_id": N, ...}
        agent_dir = self._get_agent_dir(agent_id, agent.data_dir)
        messages_dir = agent_dir / f"session_{agent_id}" / "agents" / "agent_default" / "messages"
        if messages_dir.exists():
            try:
                # Read all message files and sort by index
                message_files = sorted(
                    messages_dir.glob("message_*.json"),
                    key=lambda f: int(f.stem.split("_")[1])
                )
                messages = []
                for msg_file in message_files:
                    msg_data = json.loads(msg_file.read_text())
                    # FileSessionManager wraps message under "message" key
                    actual_message = msg_data.get("message", msg_data)
                    messages.append(actual_message)
                
                # Return raw messages - let the UI handle formatting
                result = messages[-count:] if count > 0 else messages
                return {**base_response, "messages": result}
            except Exception as e:
                logger.error(f"Failed to read session file for agent {agent_id}: {e}")

        return {**base_response, "messages": []}

    def list_agents(self) -> list[dict]:
        """List all agents with their status."""
        agents = self.tracker.load()
        result = []
        
        for agent in agents.values():
            # Update status based on actual container state
            if agent.container_id:
                if self._is_container_running(agent.container_id):
                    agent.status = "running"
                else:
                    agent.status = "stopped"
            
            agent_data = agent.model_dump()
            agent_data["processing"] = False  # We don't track this anymore
            
            result.append(agent_data)
        
        return result
    
    def is_agent_processing(self, agent_id: str) -> bool:
        """Check if an agent is currently processing a message.
        
        Note: We don't track this anymore - always returns False.
        Kept for backwards compatibility with tests.
        """
        return False

    async def stop_agent(self, agent_id: str) -> bool:
        """Stop an agent's container."""
        agent = self.tracker.get_agent(agent_id)
        if not agent or not agent.container_id:
            return False

        try:
            container = self.docker_client.containers.get(agent.container_id)
            container.stop(timeout=10)
            agent.status = "stopped"
            self.tracker.update_agent(agent)
            return True
        except NotFound:
            agent.status = "stopped"
            self.tracker.update_agent(agent)
            return True
        except Exception as e:
            logger.error(f"Failed to stop agent {agent_id}: {e}")
            return False

    async def cleanup_idle_agents(self):
        """Stop agents that have been idle too long."""
        agents = self.tracker.load()
        now = datetime.now(timezone.utc)
        
        for agent in agents.values():
            if agent.status != "running":
                continue
                
            last_activity = datetime.fromisoformat(agent.last_activity)
            idle_minutes = (now - last_activity).total_seconds() / 60
            
            if idle_minutes > IDLE_TIMEOUT_MINUTES:
                logger.info(f"Stopping idle agent {agent.agent_id} (idle for {idle_minutes:.1f} minutes)")
                await self.stop_agent(agent.agent_id)

    async def start_idle_monitor(self):
        """Start background task to monitor idle agents."""
        async def monitor_loop():
            while True:
                try:
                    await self.cleanup_idle_agents()
                except Exception as e:
                    logger.error(f"Error in idle monitor: {e}")
                await asyncio.sleep(60)  # Check every minute

        self._idle_monitor_task = asyncio.create_task(monitor_loop())

    def stop_idle_monitor(self):
        """Stop the idle monitor task."""
        if self._idle_monitor_task:
            self._idle_monitor_task.cancel()
