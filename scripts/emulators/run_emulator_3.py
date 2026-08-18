from __future__ import annotations

from android_emulator import run

"""
Arranca un emulador resizable asegurando que exista el AVD y la system image.

Flujo:
1) Valida herramientas Android SDK.
2) Instala la system image si no está instalada.
3) Crea el AVD si no existe.
4) Asegura hw.keyboard=yes en config.ini del AVD.
5) Inicia el emulador con flags por defecto.
"""

DEFAULT_DEVICE = "resizable"
API_LEVEL = "36"
ABI = "x86_64"
TARGET = "google_apis"

if __name__ == "__main__":
    run(
        avd_name=DEFAULT_DEVICE,
        device=DEFAULT_DEVICE,
        api_level=API_LEVEL,
        abi=ABI,
        target=TARGET,
    )
