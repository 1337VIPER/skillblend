#!/usr/bin/env python3
"""SkillBlend: turn your own .blend files into a Claude Code skill that models like you.

Run `python skillblend.py --help`, or install the driver skill and ask Claude to "start the forge".
"""
import sys

from forge.cli import main

if __name__ == "__main__":
    sys.exit(main())
