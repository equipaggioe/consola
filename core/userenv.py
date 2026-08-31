from __future__ import annotations
import os
import re
from pathlib import Path
from typing import Callable, Iterable, Mapping

"""
Variables de entorno persistentes, a nivel usuario y sin permisos de administrador.

Consola esta pensada para Linux y tiene que funcionar igual en Windows, asi que
el entorno se escribe del mismo modo conceptual en los dos: un bloque delimitado
dentro del perfil del shell en POSIX, y `HKCU\\Environment` en Windows. Nunca a
nivel sistema. Los scripts originales usaban `setx /M` y HKLM, que exigen una
consola elevada y ensucian la maquina entera para una instalacion que en la
practica es de un solo usuario; ademas obligaban a correr toda la herramienta
como administrador solo para escribir dos variables.

El bloque delimitado reemplaza el borrado linea por linea de los scripts: se
reescribe entero cada vez, asi que reinstalar no deja exports duplicados ni
rutas viejas colgando, que era el problema que aquellos parcheaban a mano.
"""

BEGIN = '# >>> consola >>>'
END = '# <<< consola <<<'
_HEADER = '# Bloque gestionado por Consola: se reescribe completo, no lo edites a mano.'
_EXPORT = re.compile(r'^\s*export\s+([A-Za-z_][A-Za-z0-9_]*)=(.*)$')

PathFilter = Callable[[str], bool]


def profile_path() -> Path:
    """El archivo de arranque del shell del usuario."""
    shell = (os.environ.get('SHELL') or '').strip()
    return Path.home() / ('.zshrc' if shell.endswith('zsh') else '.bashrc')


def configure(
    ctx,
    *,
    variables: Mapping[str, str] | None = None,
    path_add: Iterable[Path | str] = (),
    path_drop: PathFilter | None = None,
) -> None:
    """Deja variables y rutas en el entorno del usuario, de forma persistente.

    `path_drop` decide que entradas viejas del PATH se descartan: es lo que
    permite reinstalar en otro directorio sin que quede apuntando al anterior.
    Ademas de escribirlas, las aplica al proceso actual, para que la propia
    Consola encuentre lo recien instalado sin reiniciarse.
    """
    values = dict(variables or {})
    added = [str(Path(p)) for p in path_add]

    if os.name == 'nt':
        _configure_windows(ctx, values, added, path_drop)
    else:
        _configure_posix(ctx, values, added, path_drop)

    _apply_to_process(values, added)


def _apply_to_process(variables: Mapping[str, str], path_add: list[str]) -> None:
    """El entorno del proceso vivo: sin esto habria que reiniciar Consola.

    Es lo que hace que los indicadores de la barra de estado se pongan en verde
    al terminar la instalacion, en vez de al siguiente arranque.
    """
    for name, value in variables.items():
        os.environ[name] = value
    separator = os.pathsep
    current = [p for p in os.environ.get('PATH', '').split(separator) if p]
    for entry in path_add:
        if entry not in current:
            current.append(entry)
    os.environ['PATH'] = separator.join(current)


# --- POSIX -----------------------------------------------------------------

def _configure_posix(ctx, variables: dict[str, str], path_add: list[str],
                     path_drop: PathFilter | None) -> None:
    profile = profile_path()
    stored, dirs = read_block(profile)

    kept = [d for d in dirs if not (path_drop and path_drop(d))]
    removed = len(dirs) - len(kept)
    for entry in path_add:
        if entry not in kept:
            kept.append(entry)

    stored.update(variables)
    _write_block(profile, stored, kept)

    for name, value in variables.items():
        ctx.ok(f'{name} = {value}')
    if removed:
        ctx.info(f'Se quitaron {removed} ruta(s) anteriores del PATH.')
    ctx.ok(f'Perfil actualizado: {profile}')
    ctx.info('Abre una terminal nueva para que el PATH se actualice ahi.')


def read_block(profile: Path) -> tuple[dict[str, str], list[str]]:
    """Lo que Consola dejo escrito en el perfil: variables y rutas del PATH.

    Se lee antes de escribir porque el bloque es compartido: si Android lo
    reescribiera sin mirar, borraria lo que dejo Flutter.
    """
    variables: dict[str, str] = {}
    dirs: list[str] = []
    if not profile.is_file():
        return variables, dirs

    text = profile.read_text(encoding='utf-8', errors='replace')
    start, end = text.find(BEGIN), text.find(END)
    if start < 0 or end < start:
        return variables, dirs

    for line in text[start:end].splitlines():
        match = _EXPORT.match(line)
        if not match:
            continue
        name, raw = match.group(1), match.group(2).strip().strip('"')
        if name == 'PATH':
            dirs.extend(p for p in raw.split(':') if p and p != '$PATH')
        else:
            variables[name] = raw
    return variables, dirs


def _write_block(profile: Path, variables: Mapping[str, str], dirs: list[str]) -> None:
    lines = [BEGIN, _HEADER]
    lines += [f'export {name}="{value}"' for name, value in variables.items()]
    if dirs:
        lines.append('export PATH="$PATH:' + ':'.join(dirs) + '"')
    lines.append(END)
    block = '\n'.join(lines) + '\n'

    text = profile.read_text(encoding='utf-8', errors='replace') if profile.is_file() else ''
    start, end = text.find(BEGIN), text.find(END)
    if start >= 0 and end > start:
        text = text[:start] + block + text[end + len(END):].lstrip('\n')
    else:
        prefix = text.rstrip('\n') + '\n\n' if text.strip() else ''
        text = prefix + block

    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text(text, encoding='utf-8', newline='\n')


# --- Windows ---------------------------------------------------------------

_SYSTEM_ENV_KEY = r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment'


def _configure_windows(ctx, variables: dict[str, str], path_add: list[str],
                       path_drop: PathFilter | None) -> None:
    import winreg

    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, 'Environment', 0,
                            winreg.KEY_READ | winreg.KEY_WRITE) as key:
        for name, value in variables.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
            ctx.ok(f'{name} = {value}')

        current, kind = _query(key, 'Path')
        entries = [e for e in current.split(';') if e.strip()]
        kept = [e for e in entries if not (path_drop and path_drop(e))]
        removed = len(entries) - len(kept)
        for entry in path_add:
            if entry not in kept:
                kept.append(entry)

        if kept != entries:
            # Siempre por registro y nunca por `setx`: setx trunca cualquier
            # valor de mas de 1024 caracteres y un PATH real los pasa.
            winreg.SetValueEx(key, 'Path', 0, kind or winreg.REG_EXPAND_SZ, ';'.join(kept))
            if removed:
                ctx.info(f'Se quitaron {removed} ruta(s) anteriores del PATH de usuario.')
            ctx.ok('PATH de usuario actualizado.')
        else:
            ctx.ok('El PATH de usuario ya estaba configurado.')

    _broadcast_change()
    _warn_system_path(ctx, path_drop)


def _query(key, name: str) -> tuple[str, int | None]:
    import winreg
    try:
        value, kind = winreg.QueryValueEx(key, name)
        return str(value or ''), kind
    except FileNotFoundError:
        return '', None


def _warn_system_path(ctx, path_drop: PathFilter | None) -> None:
    """Avisa si el PATH del sistema tiene rutas viejas que le ganan a las nuevas.

    Windows arma el PATH del proceso poniendo primero el del sistema, asi que
    una entrada que dejo una instalacion anterior con `setx /M` se impone sobre
    la que acabamos de escribir en el del usuario. Leerlo no necesita permisos;
    limpiarlo si, y por eso solo se informa.
    """
    if path_drop is None:
        return
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _SYSTEM_ENV_KEY, 0, winreg.KEY_READ) as key:
            current, _ = _query(key, 'Path')
    except OSError:
        return

    stale = [e for e in current.split(';') if e.strip() and path_drop(e)]
    if not stale:
        return
    ctx.warn('El PATH del sistema todavia tiene rutas anteriores, y tienen prioridad:')
    for entry in stale:
        ctx.warn(f'  {entry}')
    ctx.warn('Quitalas desde Variables de entorno del sistema (requiere administrador).')


def _broadcast_change() -> None:
    """Avisa a Windows que el entorno cambio, para que lo vean las ventanas nuevas.

    Sin esto, las terminales abiertas despues del cambio siguen con el PATH
    viejo hasta cerrar sesion.
    """
    try:
        import ctypes
        ctypes.windll.user32.SendMessageTimeoutW(
            0xFFFF,   # HWND_BROADCAST
            0x001A,   # WM_SETTINGCHANGE
            0, 'Environment', 0x0002, 5000, None,
        )
    except (AttributeError, OSError):
        pass
