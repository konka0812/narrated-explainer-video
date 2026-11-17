#!/usr/bin/env python3
"""Run this repository's tests and fail if discovery finds no tests."""

import sys
import unittest
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    suite = unittest.defaultTestLoader.discover(str(root / "tests"), top_level_dir=str(root))
    if suite.countTestCases() == 0:
        print("No tests discovered; check the tests directory and discovery pattern.", file=sys.stderr)
        return 1
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
