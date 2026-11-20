"""Compatibility entry point for clients installed before the rename."""

import runpy
import sys
from pathlib import Path

path = Path(__file__).resolve().parents[2] / "repo-neighbor/scripts"
sys.path.insert(0, str(path))
runpy.run_path(str(path / "quota.py"), run_name="__main__")
