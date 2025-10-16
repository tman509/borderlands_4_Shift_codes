#!/usr/bin/env python3
"""
Main entry point wrapper for the Shift Code Bot.
This is a simple wrapper that delegates to the main application.
"""

import sys
from pathlib import Path

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Import and run the main application
from main import main

if __name__ == "__main__":
    main()