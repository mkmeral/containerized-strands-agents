#!/usr/bin/env python3
"""Web API server for Containerized Strands Agents.

This FastAPI server wraps the MCP tools as REST endpoints and serves the web UI.
"""

import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from containerized_strands_agents.agent_manager import AgentManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="Containerized Strands Agents Web UI", version="1.0.0")

# Global agent manager
agent_manager: AgentManager = None

# Request/Response models
class SendMessageRequest(BaseModel):
    message: str
    aws_profile: str = None
    aws_region: str = None
    system_prompt: str = None

class SendMessageResponse(BaseModel):
    status: str
    agent_id: str
    message: str = None
    error: str = None

class Agent(BaseModel):
    agent_id: str
    status: str
    container_id: str = None
    port: int = None
    processing: bool = False
    created_at: str = None
    last_activity: str = None

class AgentsResponse(BaseModel):
    status: str
    agents: List[Agent]

class Message(BaseModel):
    role: str
    content: str

class MessagesResponse(BaseModel):
    status: str
    messages: List[Message]
    agent_id: str = None
    processing: bool = False

# Startup/Shutdown events
@app.on_event("startup")
async def startup():
    """Initialize agent manager on startup."""
    global agent_manager
    agent_manager = AgentManager()
    await agent_manager.start_idle_monitor()
    logger.info("Web API server started")

@app.on_event("shutdown") 
async def shutdown():
    """Cleanup on shutdown."""
    if agent_manager:
        agent_manager.stop_idle_monitor()
    logger.info("Web API server stopped")

# API Routes

@app.get("/", response_class=HTMLResponse)
async def get_index():
    """Serve the main UI page."""
    ui_dir = Path(__file__).parent
    index_file = ui_dir / "index.html"
    
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="UI not found")
    
    return HTMLResponse(content=index_file.read_text())

@app.get("/agents", response_model=AgentsResponse)
async def list_agents():
    """List all agents with their status."""
    if not agent_manager:
        raise HTTPException(status_code=500, detail="Agent manager not initialized")
    
    try:
        agents_data = agent_manager.list_agents()
        agents = [Agent(**agent) for agent in agents_data]
        
        return AgentsResponse(
            status="success",
            agents=agents
        )
    except Exception as e:
        logger.error(f"Error listing agents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/agents/{agent_id}/message", response_model=SendMessageResponse)
async def send_message(agent_id: str, request: SendMessageRequest):
    """Send a message to an agent."""
    if not agent_manager:
        raise HTTPException(status_code=500, detail="Agent manager not initialized")
    
    try:
        result = await agent_manager.send_message(
            agent_id=agent_id,
            message=request.message,
            aws_profile=request.aws_profile,
            aws_region=request.aws_region,
            system_prompt=request.system_prompt
        )
        
        return SendMessageResponse(
            status=result["status"],
            agent_id=agent_id,
            message=result.get("message"),
            error=result.get("error")
        )
    except Exception as e:
        logger.error(f"Error sending message to agent {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/agents/{agent_id}/messages", response_model=MessagesResponse)
async def get_messages(agent_id: str, count: int = 10):
    """Get message history from an agent."""
    if not agent_manager:
        raise HTTPException(status_code=500, detail="Agent manager not initialized")
    
    try:
        result = await agent_manager.get_messages(agent_id, count)
        
        if result["status"] == "error":
            raise HTTPException(status_code=404, detail=result.get("error", "Agent not found"))
        
        messages = [Message(**msg) for msg in result.get("messages", [])]
        
        return MessagesResponse(
            status="success",
            messages=messages,
            agent_id=agent_id,
            processing=result.get("processing", False)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting messages from agent {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "containerized-strands-agents-web-ui"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)