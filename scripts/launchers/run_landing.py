from __future__ import annotations

import sys
from pathlib import Path

"""
Arranca el frontend de landing (npm run dev) reusando run_vite.py con
project_dir="landing" (env_prefix se deriva como LANDING).
"""

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_vite  # noqa: E402

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "landing"]
    run_vite.main()
