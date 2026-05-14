"""
main.py
=======
Launch the NSCP RC Column Designer application.

Usage:
    python main.py

Requirements:
    pip install matplotlib numpy
    (Tkinter is included with standard Python on Windows/Mac/Linux)
"""

import sys
import os

# Ensure the package directory is on the path (for running from any CWD)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui import main

if __name__ == "__main__":
    main()