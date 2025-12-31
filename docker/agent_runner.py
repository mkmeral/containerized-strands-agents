"""Agent Runner - FastAPI server running inside Docker container with Strands Agent."""

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path
from threading import Timer
from typing import Optional

from dataclasses import dataclass
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

from strands import Agent

# Try importing from package first (Docker), fall back to local (standalone snapshot)
try:
    from containerized_strands_agents.agent import create_agent, run_agent
except ImportError:
    from agent import create_agent, run_agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration from environment
# Hardcoded agent ID for portable snapshots - session path is always the same
# regardless of what agent_id the MCP caller uses
AGENT_ID = "agent"
IDLE_TIMEOUT_MINUTES = int(os.getenv("IDLE_TIMEOUT_MINUTES", "30"))
DATA_DIR = Path("/data")
TOOLS_DIR = Path("/app/tools")

# Retry configuration
MAX_RETRIES = 3
INITIAL_RETRY_DELAY_SECONDS = 60  # Start with 1 minute
RETRY_BACKOFF_MULTIPLIER = 2  # Double delay each retry

# Bypass tool consent for automated operation
os.environ["BYPASS_TOOL_CONSENT"] = "true"


def configure_git():
    """Configure git with GitHub token if available."""
    import subprocess
    
    github_token = os.getenv("CONTAINERIZED_AGENTS_GITHUB_TOKEN")
    if github_token:
        # Configure git credential helper to use the token
        subprocess.run(
            ["git", "config", "--global", "credential.helper", 
             f"!f() {{ echo \"password={github_token}\"; }}; f"],
            capture_output=True
        )
        logger.info("Configured git with GitHub token")
    
    # Always set git identity for commits
    subprocess.run(
        ["git", "config", "--global", "user.email", "agent@containerized-strands.local"],
        capture_output=True
    )
    subprocess.run(
        ["git", "config", "--global", "user.name", "Containerized Agent"],
        capture_output=True
    )
    logger.info("Configured git user identity")


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
idle_timer = IdleShutdownTimer(IDLE_TIMEOUT_MINUTES)

# Initialize agent (lazy loading)
_agent: Optional[Agent] = None

# Processing state tracking
_is_processing: bool = False

# Request queue for sequential processing
_request_queue: Optional[asyncio.Queue] = None
_queue_processor_task: Optional[asyncio.Task] = None


@dataclass
class QueuedRequest:
    """A chat request waiting in the queue."""
    message: str
    response_future: asyncio.Future


async def _process_request(message: str) -> dict:
    """Process a single chat request. Returns response dict."""
    global _is_processing
    
    try:
        _is_processing = True
        agent = get_agent()
        
        # Run agent synchronously and get response
        loop = asyncio.get_event_loop()
        response_text = await loop.run_in_executor(None, run_agent, agent, message)
        
        return {
            "status": "success",
            "response": response_text,
            "agent_id": AGENT_ID,
        }
    except Exception as e:
        error_message = str(e)
        logger.error(f"Error processing message: {error_message}")
        
        # Save error to conversation history
        try:
            agent = get_agent()
            agent.messages.append({
                "role": "assistant",
                "content": [{"type": "text", "text": f"⚠️ **Error**: {error_message}"}]
            })
            if hasattr(agent, 'session_manager') and agent.session_manager:
                agent.session_manager.save_session(agent.messages)
        except Exception as save_error:
            logger.error(f"Failed to save error message: {save_error}")
        
        return {
            "status": "error",
            "response": error_message,
            "agent_id": AGENT_ID,
        }
    finally:
        _is_processing = False


async def _queue_processor():
    """Background task that processes requests sequentially."""
    logger.info("Request queue processor started")
    
    while True:
        try:
            request: QueuedRequest = await _request_queue.get()
            result = await _process_request(request.message)
            request.response_future.set_result(result)
            _request_queue.task_done()
        except asyncio.CancelledError:
            logger.info("Request queue processor stopped")
            break
        except Exception as e:
            logger.error(f"Queue processor error: {e}")


def get_agent() -> Agent:
    """Get or create the Strands agent."""
    global _agent
    if _agent is None:
        # Create agent using shared logic
        _agent = create_agent(
            data_dir=DATA_DIR,
            tools_dir=TOOLS_DIR if TOOLS_DIR.exists() else None,
            agent_id=AGENT_ID,
        )
        logger.info(f"Agent initialized")
    return _agent


@app.on_event("startup")
async def startup():
    """Start idle timer and request queue on startup."""
    global _request_queue, _queue_processor_task
    
    # Ensure workspace directory exists
    workspace_dir = DATA_DIR / "workspace"
    workspace_dir.mkdir(parents=True, exist_ok=True)
    
    configure_git()
    
    # Initialize request queue and processor
    _request_queue = asyncio.Queue()
    _queue_processor_task = asyncio.create_task(_queue_processor())
    
    idle_timer.reset()
    logger.info(f"Agent {AGENT_ID} started. Idle timeout: {IDLE_TIMEOUT_MINUTES} minutes")


@app.on_event("shutdown")
async def shutdown():
    """Cancel idle timer and queue processor on shutdown."""
    global _queue_processor_task
    
    idle_timer.cancel()
    
    if _queue_processor_task:
        _queue_processor_task.cancel()
        try:
            await _queue_processor_task
        except asyncio.CancelledError:
            pass
    
    logger.info(f"Agent {AGENT_ID} shutting down")


@app.get("/health")
async def health():
    """Health check endpoint with processing state and queue depth."""
    return {
        "status": "healthy",
        "agent_id": AGENT_ID,
        "processing": _is_processing,
        "queue_depth": _request_queue.qsize() if _request_queue else 0,
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Send a message to the agent (queued for sequential processing)."""
    idle_timer.reset()
    
    # Create future for response
    response_future = asyncio.Future()
    queued = QueuedRequest(message=request.message, response_future=response_future)
    
    # Queue the request
    await _request_queue.put(queued)
    
    # Wait for processing to complete
    result = await response_future
    return ChatResponse(**result)


@app.get("/history", response_model=HistoryResponse)
async def history(count: int = 1, include_tool_messages: bool = False):
    """Get conversation history."""
    idle_timer.reset()
    
    try:
        agent = get_agent()
        messages = agent.messages
        
        # Filter out tool_use and tool_result messages unless requested
        if not include_tool_messages:
            filtered = []
            for msg in messages:
                role = msg.get("role")
                content = msg.get("content", [])
                
                # Skip user messages that are tool results
                if role == "user" and isinstance(content, list):
                    has_tool_result = any(
                        isinstance(item, dict) and item.get("type") == "tool_result"
                        for item in content
                    )
                    if has_tool_result:
                        continue
                
                # Skip assistant messages that only contain tool_use
                if role == "assistant" and isinstance(content, list):
                    has_tool_use = any(
                        isinstance(item, dict) and item.get("type") == "tool_use"
                        for item in content
                    )
                    # Check if there's any text content
                    has_text = any(
                        isinstance(item, dict) and item.get("type") == "text" and item.get("text", "").strip()
                        for item in content
                    )
                    if has_tool_use and not has_text:
                        continue
                
                filtered.append(msg)
            messages = filtered
        
        result = messages[-count:] if count > 0 else messages
        
        return HistoryResponse(
            status="success",
            messages=result,
        )
    except Exception as e:
        logger.error(f"Error getting history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
