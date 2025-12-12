#!/usr/bin/env python3
"""Launch the Containerized Strands Agents Web UI."""

import sys
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def main():
    """Run the web UI server."""
    try:
        import uvicorn
        from ui.api import app
        
        print("🚀 Starting Containerized Strands Agents Web UI...")
        print("📱 Open http://localhost:8000 in your browser")
        print("⏹️  Press Ctrl+C to stop")
        print()
        
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
        
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("💡 Install with: pip install fastapi uvicorn")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n👋 Web UI stopped")
        sys.exit(0)

if __name__ == "__main__":
    main()