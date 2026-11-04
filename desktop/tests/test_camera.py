"""The camera kit (`camera/`) is tested with `node --test`.

This runs it inside pytest so a single run covers the whole repo.
"""

import shutil
import subprocess
from pathlib import Path

KIT_TESTS = Path(__file__).resolve().parents[1] / "src" / "app" / "camera" / "index.test.mjs"


def test_the_camera_kit_passes_its_tests() -> None:
    """Run the kit's tests with node."""
    node = shutil.which("node")
    assert node, "Hace falta Node en el PATH para probar camera/."
    result = subprocess.run(
        [node, "--test", str(KIT_TESTS)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
