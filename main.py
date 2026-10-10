#!/usr/bin/env python3
"""Main entry point for AI Meal & Grocery Planner Agent.

Shortcut: `meals` (or `python main.py`) immediately launches the Google ADK
Playground web interface and opens your default browser.

Usage:
  meals                  # Launch ADK Playground & open in browser
  meals --cli            # Launch text terminal interface
  meals --setup          # Re-run interactive quick setup wizard
  meals --no-browser     # Launch ADK Playground without auto-opening browser
  meals --port=8080      # Specify custom port (default: 8080)
"""
import sys
from meal_planner.cli import run_meals_shortcut

def main():
    run_meals_shortcut(sys.argv[1:])

if __name__ == "__main__":
    main()
