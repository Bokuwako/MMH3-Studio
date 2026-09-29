"""Compatibility entry point for start.cmd."""
import runpy
import sys
from pathlib import Path
if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    runpy.run_module('studio_server', run_name='__main__')
