# Containerized Strands Agents Web UI

A simple web interface for managing and chatting with containerized Strands AI agents.

## Features

- **Agent Management**: View all agents with real-time status updates
- **Live Chat**: Send messages and receive responses in real-time
- **Auto-refresh**: Updates every 3 seconds to show current agent status
- **Processing Indicators**: Shows when agents are actively processing messages
- **AWS Configuration**: Optional AWS profile and region settings per message
- **Custom System Prompts**: Set custom system prompts for new agents
- **Responsive Design**: Works on desktop and mobile devices

## Quick Start

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Start the web UI:**
   ```bash
   python run_ui.py
   ```

3. **Open your browser:**
   Navigate to http://localhost:8000

## Usage

### Left Sidebar - Agent List
- Shows all agents with their current status
- Status badges: Running (green), Stopped (gray), Error (red), Processing (yellow)
- Click on an agent to start chatting
- Auto-refreshes every 3 seconds

### Right Side - Chat Interface
- Send messages to the selected agent
- View conversation history
- Configure AWS settings and system prompts
- Real-time response updates

### Agent Status Indicators
- **Running**: Agent container is active and ready
- **Stopped**: Agent container is not running
- **Processing**: Agent is currently handling a message (animated)
- **Error**: Agent encountered an issue

### Optional Settings
- **AWS Profile**: Use a specific AWS profile from ~/.aws/credentials
- **AWS Region**: Override the default AWS region
- **System Prompt**: Set a custom system prompt (only works for new agents)

## API Endpoints

The UI server exposes these REST endpoints:

- `GET /` - Serve the web interface
- `GET /agents` - List all agents
- `POST /agents/{id}/message` - Send message to agent
- `GET /agents/{id}/messages` - Get agent message history
- `GET /health` - Health check

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Web Browser   │────│   FastAPI Server │────│  Agent Manager  │
│                 │    │                  │    │                 │
│ - Agent List    │    │ - REST API       │    │ - Docker Mgmt   │
│ - Chat UI       │    │ - Static Files   │    │ - MCP Tools     │
│ - Auto-refresh  │    │ - WebSocket*     │    │ - Persistence   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

*WebSocket support could be added in the future for real-time updates.

## Development

To extend or customize the UI:

1. **Backend**: Modify `api.py` to add new endpoints
2. **Frontend**: Edit `index.html` for UI changes
3. **Styling**: Update the CSS in the `<style>` section
4. **JavaScript**: Modify the JS in the `<script>` section

## Integration

This web UI can be deployed alongside the MCP server or run independently. It uses the same AgentManager class to interact with Docker containers.

## Browser Compatibility

- Chrome/Chromium 80+
- Firefox 75+
- Safari 13+
- Edge 80+