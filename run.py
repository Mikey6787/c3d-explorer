#!/usr/bin/env python3
"""Runner script for C3D Explorer."""

import sys
import os

# Ensure current workspace root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import main

if __name__ == "__main__":
    main()
