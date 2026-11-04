"""El kit de la camara (`camara/`) se prueba con `node --test`; esto lo corre
dentro de pytest para que una sola corrida cubra todo el repo.
"""

import shutil
import subprocess
from pathlib import Path

KIT_TESTS = Path(__file__).resolve().parents[1] / "src" / "app" / "camara" / "index.test.mjs"


def test_el_kit_de_la_camara_pasa_sus_pruebas() -> None:
    node = shutil.which("node")
    assert node, "Hace falta Node en el PATH para probar camara/."
    result = subprocess.run(
        [node, "--test", str(KIT_TESTS)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
