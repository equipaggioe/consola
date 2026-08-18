from __future__ import annotations

import subprocess
from pathlib import Path

"""
Muestra los logs en vivo del servidor en el VPS.

Ejecuta: python scripts/server/run_systemd_action.py logs
"""


def main() -> None:
    run_systemd_script = Path(__file__).resolve().parent / "run_systemd_action.py"

    if not run_systemd_script.is_file():
        print(f"[ERROR] No existe: {run_systemd_script}")
        raise SystemExit(1)

    result = subprocess.run(
        ["python", str(run_systemd_script), "logs"],
        text=True,
    )

    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
