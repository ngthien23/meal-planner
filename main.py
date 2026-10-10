#!/usr/bin/env python3
"""Main entry point for AI Meal & Grocery Planner Agent.

Default: Serves the Google ADK Playground web interface with photo upload support.
Use `--cli` flag to launch the text terminal interface.
"""
import sys
from meal_planner.cli import serve_adk_playground, run_interactive_cli

def main():
    if "--cli" in sys.argv:
        run_interactive_cli()
    else:
        port = 8080
        host = "127.0.0.1"
        data_dir = "data"
        for arg in sys.argv[1:]:
            if arg.startswith("--port="):
                port = int(arg.split("=")[1])
            elif arg.startswith("--host="):
                host = arg.split("=")[1]
            elif not arg.startswith("--"):
                data_dir = arg
        serve_adk_playground(port=port, host=host, data_dir=data_dir)

if __name__ == "__main__":
    main()
