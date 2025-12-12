#!/usr/bin/env python3
"""Run the web UI server for Containerized Strands Agents."""

import sys
from pathlib import Path

# Add the parent directory to Python path so we can import the agent manager
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def main():
    """Main entry point for the web UI server."""
    try:
        import uvicorn
        from api import app
        
        print("🚀 Starting Containerized Strands Agents Web UI...")
        print("📱 Open http://localhost:8000 in your browser")
        print("⏹️  Press Ctrl+C to stop")
        
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
    
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("💡 Install with: pip install 'containerized-strands-agents[webui]'")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n👋 Web UI stopped")
        sys.exit(0)

if __name__ == "__main__":
    main()