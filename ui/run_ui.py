#!/usr/bin/env python3
"""Run the web UI server for Containerized Strands Agents."""

import socket
import sys


def find_free_port(start=8000, end=8100):
    """Find a free port in the given range."""
    for port in range(start, end):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("0.0.0.0", port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"No free port found in range {start}-{end}")


def main():
    """Main entry point for the web UI server."""
    try:
        import uvicorn
        from ui.api import app
        
        port = find_free_port()
        
        print("🚀 Starting Containerized Strands Agents Web UI...")
        print(f"📱 Open http://localhost:{port} in your browser")
        print("⏹️  Press Ctrl+C to stop")
        
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
    
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("💡 Install with: pip install 'containerized-strands-agents[webui]'")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n👋 Web UI stopped")
        sys.exit(0)

if __name__ == "__main__":
    main()