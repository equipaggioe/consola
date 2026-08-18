from __future__ import annotations

import math
import os
import queue
import subprocess
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable

from android_emulator import sdk_paths, system_image

"""
Administrador grafico de emuladores Android.

Funciones:
1) Lista los AVDs existentes y marca si estan corriendo.
2) Lista los devices de telefono disponibles para crear nuevos AVDs.
3) Permite crear AVDs, iniciar emuladores y detener instancias activas.
4) Usa tema oscuro con contraste alto para una lectura comoda.
"""

ANDROID_HOME = "C:\\Android"
API_LEVEL = "36"
TARGET = "google_apis"
ABI = "x86_64"

DEFAULT_FLAGS = [
    "-no-boot-anim",
    "-netdelay",
    "none",
    "-netspeed",
    "full",
]

BG = "#0f172a"
PANEL = "#172033"
PANEL_ALT = "#1e293b"
TEXT = "#e2e8f0"
MUTED = "#94a3b8"
ACCENT = "#8b5cf6"
ACCENT_2 = "#22d3ee"
SUCCESS = "#22c55e"
DANGER = "#ef4444"
WARNING = "#f59e0b"
BORDER = "#334155"
SELECT = "#312e81"


@dataclass(frozen=True)
class DeviceDefinition:
    device_id: str
    name: str
    oem: str
    tag: str


@dataclass(frozen=True)
class AvdInfo:
    avd_name: str
    device_name: str
    resolution: str
    screen_size: str
    status: str
    serial: str


@dataclass(frozen=True)
class CatalogRow:
    model_id: str
    name: str
    oem: str
    installed: bool
    avds: list[str]
    resolution: str
    screen_size: str
    status: str
    serial: str


def _run_cmd(cmd: list[str], *, capture_output: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=True, text=True, capture_output=capture_output)


def _list_avds() -> list[str]:
    paths = sdk_paths(android_home=ANDROID_HOME)
    result = _run_cmd([paths.emulator, "-list-avds"])
    return [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]


def _parse_device_definitions(text: str) -> list[DeviceDefinition]:
    devices: list[DeviceDefinition] = []
    current_id = ""
    current_name = ""
    current_oem = ""
    current_tag = ""

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped == "---------":
            if current_id and current_name:
                devices.append(
                    DeviceDefinition(
                        device_id=current_id,
                        name=current_name,
                        oem=current_oem,
                        tag=current_tag,
                    )
                )
            current_id = ""
            current_name = ""
            current_oem = ""
            current_tag = ""
            continue
        if stripped.startswith("id: ") and ' or "' in stripped:
            current_id = stripped.split(' or "', 1)[1].rstrip('"')
            continue
        if stripped.startswith("Name:"):
            current_name = stripped.split(":", 1)[1].strip()
            continue
        if stripped.startswith("OEM :"):
            current_oem = stripped.split(":", 1)[1].strip()
            continue
        if stripped.startswith("Tag :"):
            current_tag = stripped.split(":", 1)[1].strip()

    if current_id and current_name:
        devices.append(
            DeviceDefinition(
                device_id=current_id,
                name=current_name,
                oem=current_oem,
                tag=current_tag,
            )
        )
    return devices


def _is_phone_device(device: DeviceDefinition) -> bool:
    excluded_ids = {
        "medium_tablet",
        "pixel_c",
        "pixel_tablet",
        "resizable",
        "desktop_large",
        "desktop_medium",
        "desktop_small",
        "tv_1080p",
        "tv_4k",
        "tv_720p",
        "wearos_large_round",
        "wearos_rect",
        "wearos_small_round",
        "wearos_square",
        "Nexus 10",
        "Nexus 7",
        "Nexus 7 2013",
        "Nexus 9",
        "7in WSVGA (Tablet)",
        "10.1in WXGA (Tablet)",
        "13.5in Freeform",
        "7.4in Rollable",
    }
    if device.device_id in excluded_ids:
        return False
    if device.device_id.startswith("automotive_"):
        return False
    if device.tag.startswith("android-automotive"):
        return False
    if device.tag.startswith("android-tv"):
        return False
    if device.tag.startswith("android-wear"):
        return False
    if device.tag.startswith("android-desktop"):
        return False
    return True


def _list_phone_devices() -> list[DeviceDefinition]:
    paths = sdk_paths(android_home=ANDROID_HOME)
    result = _run_cmd([paths.avdmanager, "list", "device"])
    devices = _parse_device_definitions(result.stdout or "")
    return [device for device in devices if _is_phone_device(device)]


def _config_path_for_avd(avd_name: str) -> Path:
    userprofile = (os.environ.get("USERPROFILE") or "").strip()
    return Path(userprofile) / ".android" / "avd" / f"{avd_name}.avd" / "config.ini"


def _read_ini(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        k = key.strip()
        if k:
            values[k] = value.strip()
    return values


def _format_screen_info(width: int, height: int, density: int) -> tuple[str, str]:
    resolution = f"{width}x{height}" if width > 0 and height > 0 else "-"
    if width <= 0 or height <= 0 or density <= 0:
        return resolution, "-"
    inches = math.sqrt((width * width) + (height * height)) / float(density)
    return resolution, f'{round(inches, 2)}"'


def _read_avd_details(avd_name: str) -> tuple[str, str, str]:
    config_path = _config_path_for_avd(avd_name)
    if not config_path.exists():
        return avd_name, "-", "-"

    config = _read_ini(config_path)
    device_name = (config.get("hw.device.name") or avd_name).strip() or avd_name
    try:
        width = int((config.get("hw.lcd.width") or "0").strip())
        height = int((config.get("hw.lcd.height") or "0").strip())
        density = int((config.get("hw.lcd.density") or "0").strip())
    except ValueError:
        return device_name, "-", "-"

    resolution, screen_size = _format_screen_info(width, height, density)
    return device_name, resolution, screen_size


def _update_avd_keyboard(avd_name: str) -> None:
    path = _config_path_for_avd(avd_name)
    if not path.exists():
        return

    lines: list[str] = []
    found = False
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip().startswith("hw.keyboard="):
                lines.append("hw.keyboard=yes\n")
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append("hw.keyboard=yes\n")
    path.write_text("".join(lines), encoding="utf-8")


def _system_image_installed() -> bool:
    paths = sdk_paths(android_home=ANDROID_HOME)
    image_id = system_image(api_level=API_LEVEL, target=TARGET, abi=ABI)
    result = _run_cmd([paths.sdkmanager, "--list_installed"])
    return image_id in (result.stdout or "")


def _ensure_system_image() -> None:
    if _system_image_installed():
        return
    paths = sdk_paths(android_home=ANDROID_HOME)
    image_id = system_image(api_level=API_LEVEL, target=TARGET, abi=ABI)
    _run_cmd([paths.sdkmanager, image_id], capture_output=False)


def _create_avd(*, avd_name: str, device_id: str) -> None:
    avds = set(_list_avds())
    if avd_name in avds:
        raise RuntimeError(f"Ya existe un AVD con ese nombre: {avd_name}")

    _ensure_system_image()
    paths = sdk_paths(android_home=ANDROID_HOME)
    image_id = system_image(api_level=API_LEVEL, target=TARGET, abi=ABI)
    _run_cmd(
        [
            paths.avdmanager,
            "create",
            "avd",
            "--name",
            avd_name,
            "--package",
            image_id,
            "--device",
            device_id,
        ],
        capture_output=False,
    )
    _update_avd_keyboard(avd_name)


def _start_avd(avd_name: str) -> None:
    paths = sdk_paths(android_home=ANDROID_HOME)
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    subprocess.Popen(
        [paths.emulator, "-avd", avd_name, *DEFAULT_FLAGS],
        creationflags=creationflags,
    )


def _resolve_avd_name_from_serial(serial: str) -> str:
    paths = sdk_paths(android_home=ANDROID_HOME)
    result = _run_cmd([paths.adb, "-s", serial, "emu", "avd", "name"])
    for raw_line in (result.stdout or "").splitlines():
        line = raw_line.strip()
        if not line or line == "OK" or line.startswith("KO:"):
            continue
        return line
    return ""


def _running_emulators() -> dict[str, str]:
    paths = sdk_paths(android_home=ANDROID_HOME)
    result = _run_cmd([paths.adb, "devices"])
    running: dict[str, str] = {}
    for raw_line in (result.stdout or "").splitlines():
        line = raw_line.strip()
        if not line.startswith("emulator-") or "\tdevice" not in line:
            continue
        serial = line.split("\t", 1)[0]
        try:
            avd_name = _resolve_avd_name_from_serial(serial)
        except Exception:
            continue
        if avd_name:
            running[avd_name] = serial
    return running


def _stop_running_avd(serial: str) -> None:
    paths = sdk_paths(android_home=ANDROID_HOME)
    _run_cmd([paths.adb, "-s", serial, "emu", "kill"], capture_output=False)


def _suggest_avd_name(device_id: str, existing_avds: set[str]) -> str:
    base = device_id.strip().replace(" ", "_")
    if base not in existing_avds:
        return base

    index = 2
    while True:
        candidate = f"{base}_{index}"
        if candidate not in existing_avds:
            return candidate
        index += 1


class EmulatorManagerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Administrador de Emuladores Android")
        self.root.geometry("1450x860")
        self.root.minsize(1200, 700)
        self.root.configure(bg=BG)

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.device_rows: dict[str, DeviceDefinition] = {}
        self.avd_rows: dict[str, AvdInfo] = {}
        self.catalog_rows: dict[str, CatalogRow] = {}
        self.busy = False

        self.status_var = tk.StringVar(value="Listo")

        self._configure_style()
        self._build_ui()
        self.root.after(150, self._drain_logs)
        self.refresh_data()

    def _configure_style(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")

        style.configure(".", background=BG, foreground=TEXT, fieldbackground=PANEL_ALT)
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("Header.TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 19, "bold"))
        style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 11))
        style.configure("PanelTitle.TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI", 13, "bold"))
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 11))
        style.configure("TEntry", fieldbackground=PANEL_ALT, foreground=TEXT, bordercolor=BORDER, insertcolor=TEXT, font=("Segoe UI", 11))
        style.map("TEntry", fieldbackground=[("focus", PANEL_ALT)])
        style.configure(
            "Treeview",
            background=PANEL_ALT,
            fieldbackground=PANEL_ALT,
            foreground=TEXT,
            bordercolor=BORDER,
            rowheight=30,
            font=("Segoe UI", 11),
        )
        style.configure("Treeview.Heading", background=PANEL, foreground=TEXT, relief="flat", bordercolor=BORDER, font=("Segoe UI", 11, "bold"))
        style.map("Treeview", background=[("selected", SELECT)], foreground=[("selected", TEXT)])
        style.map("Treeview.Heading", background=[("active", PANEL)])

        style.configure("Accent.TButton", background=ACCENT, foreground=TEXT, bordercolor=ACCENT, padding=(12, 8), font=("Segoe UI", 11, "bold"))
        style.map("Accent.TButton", background=[("active", "#7c3aed")])

        style.configure("Success.TButton", background=SUCCESS, foreground=TEXT, bordercolor=SUCCESS, padding=(12, 8), font=("Segoe UI", 11, "bold"))
        style.map("Success.TButton", background=[("active", "#16a34a")])

        style.configure("Danger.TButton", background=DANGER, foreground=TEXT, bordercolor=DANGER, padding=(12, 8), font=("Segoe UI", 11, "bold"))
        style.map("Danger.TButton", background=[("active", "#dc2626")])

        style.configure("Warning.TButton", background=WARNING, foreground=TEXT, bordercolor=WARNING, padding=(12, 8), font=("Segoe UI", 11, "bold"))
        style.map("Warning.TButton", background=[("active", "#d97706")])

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=16)
        container.pack(fill="both", expand=True)

        header = ttk.Frame(container)
        header.pack(fill="x")
        ttk.Label(header, text="Administrador de Emuladores Android", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Tema oscuro, estado de AVDs, devices para crear y control basico de instancias.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(4, 12))

        top_bar = ttk.Frame(container)
        top_bar.pack(fill="x", pady=(0, 12))
        ttk.Button(top_bar, text="Refrescar todo", style="Accent.TButton", command=self.refresh_data).pack(side="left")
        ttk.Button(top_bar, text="Iniciar", style="Success.TButton", command=lambda: self._safe_call(self.start_selected_avd)).pack(side="left", padx=(8, 0))
        ttk.Button(top_bar, text="Detener", style="Danger.TButton", command=lambda: self._safe_call(self.stop_selected_avd)).pack(side="left", padx=(8, 0))

        ttk.Frame(top_bar, width=18).pack(side="left")
        ttk.Button(top_bar, text="Crear AVD", style="Warning.TButton", command=lambda: self._safe_call(self.create_selected_device)).pack(side="left")

        ttk.Label(top_bar, textvariable=self.status_var, style="Muted.TLabel").pack(side="right")

        body = ttk.Panedwindow(container, orient="horizontal")
        body.pack(fill="both", expand=True)

        panel = ttk.Frame(body, style="Panel.TFrame", padding=14)
        body.add(panel, weight=1)

        ttk.Label(panel, text="Catalogo de modelos y AVDs", style="PanelTitle.TLabel").pack(anchor="w")
        ttk.Label(
            panel,
            text="Una sola tabla con modelos disponibles, AVDs instalados, estado y datos de pantalla.",
            background=PANEL,
            foreground=MUTED,
        ).pack(anchor="w", pady=(2, 10))

        catalog_columns = ("model_id", "name", "oem", "installed", "avds", "resolution", "screen", "status", "serial")
        self.catalog_tree = ttk.Treeview(panel, columns=catalog_columns, show="headings", selectmode="browse")
        self.catalog_tree.heading("model_id", text="Model ID")
        self.catalog_tree.heading("name", text="Nombre")
        self.catalog_tree.heading("oem", text="OEM")
        self.catalog_tree.heading("installed", text="Instalado")
        self.catalog_tree.heading("avds", text="AVDs")
        self.catalog_tree.heading("resolution", text="Resolucion")
        self.catalog_tree.heading("screen", text="Pantalla")
        self.catalog_tree.heading("status", text="Estado")
        self.catalog_tree.heading("serial", text="Serial")
        self.catalog_tree.column("model_id", width=160)
        self.catalog_tree.column("name", width=220)
        self.catalog_tree.column("oem", width=110, anchor="center")
        self.catalog_tree.column("installed", width=90, anchor="center")
        self.catalog_tree.column("avds", width=260)
        self.catalog_tree.column("resolution", width=120, anchor="center")
        self.catalog_tree.column("screen", width=95, anchor="center")
        self.catalog_tree.column("status", width=120, anchor="center")
        self.catalog_tree.column("serial", width=120, anchor="center")
        self.catalog_tree.tag_configure("running", foreground=SUCCESS)
        self.catalog_tree.tag_configure("installed", foreground=ACCENT_2)
        self.catalog_tree.tag_configure("create", foreground=WARNING)
        self.catalog_tree.bind("<<TreeviewSelect>>", self._on_catalog_selected)

        catalog_scroll = ttk.Scrollbar(panel, orient="vertical", command=self.catalog_tree.yview)
        self.catalog_tree.configure(yscrollcommand=catalog_scroll.set)
        self.catalog_tree.pack(side="left", fill="both", expand=True, pady=(0, 12))
        catalog_scroll.pack(side="right", fill="y", pady=(0, 12))

        log_panel = ttk.Frame(container, style="Panel.TFrame", padding=14)
        log_panel.pack(fill="both", expand=False, pady=(12, 0))
        ttk.Label(log_panel, text="Logs", style="PanelTitle.TLabel").pack(anchor="w")

        self.log_text = tk.Text(
            log_panel,
            height=10,
            bg="#0b1220",
            fg=TEXT,
            insertbackground=TEXT,
            font=("Segoe UI", 11),
            relief="flat",
            borderwidth=0,
            padx=10,
            pady=10,
            wrap="word",
        )
        self.log_text.pack(fill="both", expand=True, pady=(8, 0))
        self.log_text.configure(state="disabled")

    def log(self, message: str) -> None:
        self.log_queue.put(message)

    def _drain_logs(self) -> None:
        while True:
            try:
                message = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.log_text.configure(state="normal")
            self.log_text.insert("end", message + "\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        self.root.after(150, self._drain_logs)

    def _set_busy(self, value: bool, message: str) -> None:
        self.busy = value
        self.status_var.set(message)

    def _run_background(self, label: str, job: Callable[[], None], *, refresh_after: bool = True) -> None:
        if self.busy:
            messagebox.showinfo("Administrador", "Hay una operación en curso. Espera a que termine.")
            return

        self._set_busy(True, label)

        def worker() -> None:
            try:
                self.log(f"[INFO] {label}")
                job()
                self.log(f"[OK] {label}")
            except Exception as exc:
                self.log(f"[ERROR] {label}: {exc}")
                self.root.after(0, lambda: messagebox.showerror("Administrador", str(exc)))
            finally:
                def finish() -> None:
                    self._set_busy(False, "Listo")
                    if refresh_after:
                        self.refresh_data()

                self.root.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def _safe_call(self, action: Callable[[], None]) -> None:
        try:
            action()
        except Exception as exc:
            messagebox.showerror("Administrador", str(exc))

    def _collect_snapshot(self) -> tuple[dict[str, AvdInfo], list[DeviceDefinition]]:
        avds = _list_avds()
        running = _running_emulators()
        devices = _list_phone_devices()

        avd_infos: dict[str, AvdInfo] = {}

        for avd_name in avds:
            device_name, resolution, screen_size = _read_avd_details(avd_name)
            serial = running.get(avd_name, "")
            status = "corriendo" if serial else "detenido"
            avd_infos[avd_name] = AvdInfo(
                avd_name=avd_name,
                device_name=device_name,
                resolution=resolution,
                screen_size=screen_size,
                status=status,
                serial=serial,
            )
        return avd_infos, devices

    def _render_snapshot(self, avd_infos: dict[str, AvdInfo], devices: list[DeviceDefinition]) -> None:
        model_to_avds: dict[str, list[str]] = {}
        for info in avd_infos.values():
            model_to_avds.setdefault(info.device_name, []).append(info.avd_name)

        self.avd_rows = avd_infos
        self.device_rows = {device.device_id: device for device in devices}
        self.catalog_rows = {}
        self.catalog_tree.delete(*self.catalog_tree.get_children())

        def sort_key(device: DeviceDefinition) -> tuple[int, int, str]:
            linked_avds = model_to_avds.get(device.device_id, [])
            installed = 1 if linked_avds else 0
            running = 1 if any(self.avd_rows[name].status == "corriendo" for name in linked_avds) else 0
            return (-installed, -running, device.device_id)

        for device in sorted(devices, key=sort_key):
            linked_avds = sorted(model_to_avds.get(device.device_id, []))
            installed = bool(linked_avds)
            running_infos = [self.avd_rows[name] for name in linked_avds if self.avd_rows[name].status == "corriendo"]
            preferred_info = running_infos[0] if running_infos else (self.avd_rows[linked_avds[0]] if linked_avds else None)
            resolution = preferred_info.resolution if preferred_info else "-"
            screen_size = preferred_info.screen_size if preferred_info else "-"
            status = "corriendo" if running_infos else ("listo" if installed else "crear")
            serial = running_infos[0].serial if running_infos else "-"
            tag = "running" if running_infos else ("installed" if installed else "create")
            row = CatalogRow(
                model_id=device.device_id,
                name=device.name,
                oem=device.oem or "-",
                installed=installed,
                avds=linked_avds,
                resolution=resolution,
                screen_size=screen_size,
                status=status,
                serial=serial,
            )
            self.catalog_rows[device.device_id] = row
            self.catalog_tree.insert(
                "",
                "end",
                iid=device.device_id,
                values=(
                    row.model_id,
                    row.name,
                    row.oem,
                    "si" if row.installed else "no",
                    ", ".join(row.avds) if row.avds else "-",
                    row.resolution,
                    row.screen_size,
                    row.status,
                    row.serial,
                ),
                tags=(tag,),
            )

        total_running = sum(1 for info in avd_infos.values() if info.status == "corriendo")
        self.log(
            f"[INFO] Refrescado: {len(avd_infos)} AVDs, {len(devices)} devices de telefono, {total_running} corriendo."
        )

    def refresh_data(self) -> None:
        if self.busy:
            messagebox.showinfo("Administrador", "Hay una operación en curso. Espera a que termine.")
            return

        self._set_busy(True, "Refrescando datos...")

        def worker() -> None:
            try:
                snapshot = self._collect_snapshot()
            except Exception as exc:
                self.log(f"[ERROR] Refrescando datos: {exc}")
                self.root.after(0, lambda: messagebox.showerror("Administrador", str(exc)))
            else:
                self.root.after(0, lambda: self._render_snapshot(*snapshot))
            finally:
                self.root.after(0, lambda: self._set_busy(False, "Listo"))

        threading.Thread(target=worker, daemon=True).start()

    def _selected_row(self) -> CatalogRow:
        selected = self.catalog_tree.selection()
        if not selected:
            raise RuntimeError("Selecciona un modelo.")
        return self.catalog_rows[selected[0]]

    def _on_catalog_selected(self, _event: object) -> None:
        return

    def create_selected_device(self) -> None:
        row = self._selected_row()
        device = self.device_rows[row.model_id]
        avd_name = _suggest_avd_name(device.device_id, set(self.avd_rows))

        self._run_background(
            f"Creando AVD '{avd_name}' desde '{device.device_id}'...",
            lambda: _create_avd(avd_name=avd_name, device_id=device.device_id),
        )

    def start_selected_avd(self) -> None:
        row = self._selected_row()
        device = self.device_rows[row.model_id]

        if row.avds:
            running_avds = [name for name in row.avds if self.avd_rows[name].status == "corriendo"]
            if running_avds:
                messagebox.showinfo("Administrador", f"Ya hay una instancia corriendo para '{row.model_id}'.")
                return
            avd_name = row.avds[0]
            self._run_background(
                f"Iniciando AVD '{avd_name}'...",
                lambda: _start_avd(avd_name),
            )
            return

        avd_name = _suggest_avd_name(device.device_id, set(self.avd_rows))

        def job() -> None:
            _create_avd(avd_name=avd_name, device_id=device.device_id)
            _start_avd(avd_name)

        self._run_background(
            f"Creando e iniciando '{avd_name}'...",
            job,
        )

    def stop_selected_avd(self) -> None:
        row = self._selected_row()
        running_avds = [name for name in row.avds if self.avd_rows[name].status == "corriendo"]
        if not running_avds:
            messagebox.showinfo("Administrador", f"El modelo '{row.model_id}' no tiene instancias corriendo.")
            return
        avd_name = running_avds[0]
        info = self.avd_rows[avd_name]

        self._run_background(
            f"Deteniendo AVD '{avd_name}'...",
            lambda: _stop_running_avd(info.serial),
        )


def main() -> None:
    root = tk.Tk()
    app = EmulatorManagerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
