"""Agent Runner - FastAPI server running inside Docker container with Strands Agent."""

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path
from threading import Timer
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

from strands import Agent
from strands.agent.conversation_manager.sliding_window_conversation_manager import (
    SlidingWindowConversationManager,
)
from strands.session.file_session_manager import FileSessionManager
from strands_tools import (
    file_read,
    file_write,
    editor,
    shell,
    use_agent,
    python_repl,
    load_tool,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration from environment
AGENT_ID = os.getenv("AGENT_ID", "default")
IDLE_TIMEOUT_MINUTES = int(os.getenv("IDLE_TIMEOUT_MINUTES", "30"))
DATA_DIR = Path("/data")
WORKSPACE_DIR = DATA_DIR / "workspace"
CUSTOM_SYSTEM_PROMPT_FILE = DATA_DIR / "system_prompt.txt"

# System prompt for the agent - load custom if available
def load_system_prompt() -> str:
    """Load system prompt, preferring custom if available."""
    if os.getenv("CUSTOM_SYSTEM_PROMPT") == "true" and CUSTOM_SYSTEM_PROMPT_FILE.exists():
        try:
            custom_prompt = CUSTOM_SYSTEM_PROMPT_FILE.read_text()
            logger.info("Using custom system prompt")
            return custom_prompt
        except Exception as e:
            logger.error(f"Failed to load custom system prompt: {e}")
            logger.info("Falling back to default system prompt")
    
    return """You are a helpful AI assistant running in an isolated Docker container.

IMPORTANT: Your persistent workspace is /data/workspace. ALWAYS work in this directory.
- Clone repos here: cd /data/workspace && git clone ...
- Create files here: /data/workspace/myproject/...
- This directory is mounted from the host and persists across container restarts.
- Do NOT use /tmp or other directories - they will be lost when the container stops.

Available tools:
- file_read, file_write, editor: File operations (use paths relative to /data/workspace)
- shell: Execute shell commands (always cd to /data/workspace first)
- python_repl: Run Python code
- use_agent: Spawn sub-agents for complex tasks
- load_tool: Dynamically load additional tools

When given a task:
1. Work in /data/workspace
2. Be thorough but concise
3. Test your work before committing
4. Commit with clear messages
"""

SYSTEM_PROMPT = load_system_prompt()

# Bypass tool consent for automated operation
os.environ["BYPASS_TOOL_CONSENT"] = "true"


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    status: str
    response: str
    agent_id: str


class HistoryResponse(BaseModel):
    status: str
    messages: list[dict]



class IdleShutdownTimer:
    """Timer that shuts down the container after idle timeout."""

    def __init__(self, timeout_minutes: int):
        self.timeout_seconds = timeout_minutes * 60
        self.timer: Optional[Timer] = None

    def reset(self):
        """Reset the idle timer."""
        if self.timer:
            self.timer.cancel()
        self.timer = Timer(self.timeout_seconds, self._shutdown)
        self.timer.daemon = True
        self.timer.start()
        logger.debug(f"Idle timer reset: {self.timeout_seconds}s until shutdown")

    def _shutdown(self):
        """Shutdown the container."""
        logger.info(f"Idle timeout reached ({IDLE_TIMEOUT_MINUTES} minutes). Shutting down.")
        os.kill(os.getpid(), signal.SIGTERM)

    def cancel(self):
        """Cancel the timer."""
        if self.timer:
            self.timer.cancel()


# Initialize components
app = FastAPI(title=f"Agent {AGENT_ID}")
session_manager = FileSessionManager(
    session_id=AGENT_ID,
    storage_dir="/data"
)
idle_timer = IdleShutdownTimer(IDLE_TIMEOUT_MINUTES)

# Initialize agent (lazy loading)
_agent: Optional[Agent] = None


def get_agent() -> Agent:
    """Get or create the Strands agent."""
    global _agent
    if _agent is None:
        # Create agent with session manager
        _agent = Agent(
            system_prompt=SYSTEM_PROMPT,
            tools=[file_read, file_write, editor, shell, use_agent, python_repl, load_tool],
            session_manager=session_manager,
            conversation_manager=SlidingWindowConversationManager(
                window_size=50,  # Keep last 50 messages
            ),
        )
        logger.info(f"Agent initialized with session manager")
    
    return _agent


@app.on_event("startup")
async def startup():
    """Start idle timer on startup."""
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    idle_timer.reset()
    logger.info(f"Agent {AGENT_ID} started. Idle timeout: {IDLE_TIMEOUT_MINUTES} minutes")


@app.on_event("shutdown")
async def shutdown():
    """Cancel idle timer on shutdown."""
    idle_timer.cancel()
    # Session manager handles persistence automatically
    logger.info(f"Agent {AGENT_ID} shutting down")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "agent_id": AGENT_ID}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Send a message to the agent."""
    idle_timer.reset()
    
    try:
        agent = get_agent()
        
        # Run agent in thread pool to not block
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, agent, request.message)
        
        # Session manager handles persistence automatically
        
        response_text = str(result)
        
        return ChatResponse(
            status="success",
            response=response_text,
            agent_id=AGENT_ID,
        )
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/history", response_model=HistoryResponse)
async def history(count: int = 1):
    """Get conversation history."""
    idle_timer.reset()
    
    try:
        agent = get_agent()
        messages = agent.messages
        
        # Filter to only user/assistant messages (no tool calls)
        filtered = []
        for msg in messages:
            role = msg.get("role")
            if role not in ("user", "assistant"):
                continue
            
            content = msg.get("content", [])
            text_content = _extract_text_content(content)
            if text_content:
                filtered.append({"role": role, "content": text_content})
        
        return HistoryResponse(
            status="success",
            messages=filtered[-count:] if count > 0 else filtered,
        )
    except Exception as e:
        logger.error(f"Error getting history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _extract_text_content(content) -> str:
    """Extract text from message content."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                texts.append(item["text"])
            elif isinstance(item, str):
                texts.append(item)
        return "\n".join(texts)
    return ""


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
