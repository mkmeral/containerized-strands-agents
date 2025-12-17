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
from strands.agent.conversation_manager import SummarizingConversationManager
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
from github_tools import (
    create_issue,
    get_issue,
    update_issue,
    list_issues,
    get_issue_comments,
    add_issue_comment,
    create_pull_request,
    get_pull_request,
    update_pull_request,
    list_pull_requests,
    get_pr_review_and_comments,
    reply_to_review_comment,
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
        # Create agent with session manager and summarizing conversation manager
        # SummarizingConversationManager intelligently summarizes older messages
        # instead of just dropping them, preserving important context
        _agent = Agent(
            system_prompt=SYSTEM_PROMPT,
            tools=[
                file_read, file_write, editor, shell, use_agent, python_repl, load_tool,
                create_issue, get_issue, update_issue, list_issues, get_issue_comments, add_issue_comment,
                create_pull_request, get_pull_request, update_pull_request, list_pull_requests,
                get_pr_review_and_comments, reply_to_review_comment,
            ],
            session_manager=session_manager,
            conversation_manager=SummarizingConversationManager(
                summary_ratio=0.3,  # Summarize 30% of messages when context reduction needed
                preserve_recent_messages=10,  # Always keep 10 most recent messages
            ),
        )
        logger.info(f"Agent initialized with SummarizingConversationManager")
    
    return _agent


@app.on_event("startup")
async def startup():
    """Start idle timer on startup."""
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    configure_git()
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
        
        # Process all messages including tool calls
        formatted = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", [])
            
            if role == "user":
                # Check if this is a tool result
                tool_result_msg = _format_tool_result_message(content)
                if tool_result_msg:
                    formatted.append(tool_result_msg)
                else:
                    # Regular user message
                    text_content = _extract_text_content(content)
                    if text_content:
                        formatted.append({"role": "user", "content": text_content})
            
            elif role == "assistant":
                # Check if this contains tool uses
                tool_use_msgs = _format_tool_use_messages(content)
                if tool_use_msgs:
                    formatted.extend(tool_use_msgs)
                else:
                    # Regular assistant response
                    text_content = _extract_text_content(content)
                    if text_content:
                        formatted.append({"role": "assistant", "content": text_content})
        
        return HistoryResponse(
            status="success",
            messages=formatted[-count:] if count > 0 else formatted,
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


def _format_tool_use_messages(content) -> list[dict]:
    """Format tool use messages from assistant content."""
    if not isinstance(content, list):
        return []
    
    tool_messages = []
    assistant_text = None
    
    for item in content:
        if isinstance(item, dict):
            if item.get("type") == "tool_use":
                # Format tool use message
                tool_messages.append({
                    "role": "tool_use",
                    "tool": item.get("name", "unknown"),
                    "input": item.get("input", {})
                })
            elif "text" in item and item["text"].strip():
                if assistant_text is None:
                    assistant_text = item["text"]
                else:
                    assistant_text += "\n" + item["text"]
    
    # Add assistant text message first if it exists
    messages = []
    if assistant_text and assistant_text.strip():
        messages.append({"role": "assistant", "content": assistant_text})
    
    # Add tool use messages
    messages.extend(tool_messages)
    
    return messages


def _format_tool_result_message(content) -> dict | None:
    """Format tool result message from user content."""
    if not isinstance(content, list):
        return None
    
    for item in content:
        if isinstance(item, dict) and item.get("type") == "tool_result":
            # Extract tool name and output from tool_result
            tool_use_id = item.get("tool_use_id", "")
            
            # Try to find tool name from the content or use generic
            tool_name = "unknown"
            output = ""
            
            if "content" in item:
                tool_content = item["content"]
                if isinstance(tool_content, list):
                    for content_item in tool_content:
                        if isinstance(content_item, dict) and "text" in content_item:
                            output = content_item["text"]
                            break
                elif isinstance(tool_content, str):
                    output = tool_content
            
            return {
                "role": "tool_result", 
                "tool": tool_name,
                "output": output
            }
    
    return None


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
