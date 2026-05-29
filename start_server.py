#!/usr/bin/env python3
"""
Alternative Python-based startup script for the KO Classifier API.
"""

import os
import sys
import subprocess
from pathlib import Path


def check_virtual_env():
    """Check and activate virtual environment if present."""
    venv_paths = [".venv", "venv"]
    
    for venv in venv_paths:
        activate_script = Path(venv) / "bin" / "activate"
        if activate_script.exists():
            return True
    
    return False


def load_env_file():
    """Load environment variables from .env file."""
    env_file = Path(".env")
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key, value)


def main():
    """Main entry point."""
    print("=" * 60)
    print("KO Classifier API Server")
    print("=" * 60)
    
    # Load .env file
    load_env_file()
    
    # Configuration
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    workers = int(os.getenv("WORKERS", "1"))
    
    llm_configured = bool(
        os.getenv("DOCINT_LLM_BASE_URL") and os.getenv("DOCINT_LLM_MODEL")
    )
    
    print(f"\nConfiguration:")
    print(f"  Host: {host}")
    print(f"  Port: {port}")
    print(f"  Workers: {workers}")
    print(f"  LLM Configured: {'Yes' if llm_configured else 'No (heuristics only)'}")
    
    print(f"\nAPI Documentation: http://localhost:{port}/docs")
    print("=" * 60)
    
    # Build uvicorn command
    cmd = [
        sys.executable, "-m", "uvicorn",
        "app:app",
        "--host", host,
        "--port", str(port),
    ]
    
    if workers == 1:
        cmd.append("--reload")
    else:
        cmd.extend(["--workers", str(workers)])
    
    # Run server
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\n\nShutting down server...")
        sys.exit(0)


if __name__ == "__main__":
    main()
