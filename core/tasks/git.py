from __future__ import annotations
import os
from pathlib import Path

from ..errors import TaskError
from ..process import which_any
from ..registry import registry
from . import vps_server

"""
Grupo Git.

Los dos forzados de aca abajo son la mitad que le falta a lo que ya hacen
`push_repository`/`sync_repository` (`vps_server.py`): esos dos nunca pisan
historia ajena a proposito -- avisan y frenan si algo no calza. Aca la
decision ya esta tomada de antemano: un lado gana, aunque el otro tenga
commits que el ganador no conoce.

Viven en su propio modulo, y no en `vps_server.py` junto a `push_repository`,
porque no son la mitad de ningun despliegue: son un forzado contra GitHub y
nada mas. Desde que lado se fuerza es un parametro (`side`), no dos funciones:
con 'vps' el mismo comando corre dentro del VPS, y para eso se apoyan en las
dos funciones que ya hablaban SSH (`vps_server.py`).

`clone_repo` es del mismo grupo por la misma razon: es git contra GitHub y
nada mas. Es la unica del modulo que no trabaja sobre el repo abierto.
"""


def _git_or_fail() -> None:
    if not which_any(['git', 'git.exe']):
        raise TaskError('No se encontro Git en el PATH.')


def _ensure_git(ctx) -> None:
    _git_or_fail()
    if not ctx.path('.git').exists():
        raise TaskError(f'La carpeta abierta no es un repositorio git: {ctx.root}')


def _current_branch(ctx) -> str:
    rama = ctx.capture(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
    if rama == 'HEAD':
        raise TaskError('El repo local esta en HEAD desacoplado: no hay rama que forzar.')
    return rama


def force_push(ctx, side: str = 'local') -> str:
    """Fuerza a que origin quede igual a la rama del lado elegido.

    `--force` y no `--force-with-lease`: la lease rechaza el push justo cuando
    origin tiene commits que ese lado no vio, que es exactamente el caso para
    el que existe este boton.
    """
    if side == 'vps':
        return vps_server.force_push_from_vps(ctx)
    _ensure_git(ctx)
    rama = _current_branch(ctx)
    ctx.run(['git', 'fetch', '--quiet'], check=False, echo=False)
    ctx.run(['git', 'push', '--force', 'origin', rama])
    revision = ctx.capture(['git', 'rev-parse', '--short', 'HEAD'])
    ctx.ok(f'origin/{rama} ahora es {revision}, igual que esta maquina.')
    return revision


def force_reset(ctx, side: str = 'local', discard_changes: bool = False) -> str | None:
    """Fuerza a que el lado elegido quede igual a origin, descartando lo propio.

    Tira los commits que origin no tiene y lo que haya sin trackear
    (`git clean -fd`). `discard_changes` elige que hacer si ese lado tiene
    cambios sin commitear: False pregunta con la lista de archivos a la vista,
    True los descarta sin preguntar.

    Con 'vps' es `sync_repository` (`vps_server.py`), que termina justo en
    `git reset --hard "@{u}"`: ya era este mismo forzado, corriendo por SSH.
    """
    if side == 'vps':
        vps_server.sync_repository(ctx, discard_changes=discard_changes)
        return None
    _ensure_git(ctx)
    rama = _current_branch(ctx)
    sucio = ctx.capture(['git', 'status', '--porcelain'])
    if sucio and not discard_changes:
        ctx.warn('Esta maquina tiene cambios sin commitear:\n' + sucio)
        if not ctx.confirm('Descartar esos cambios y resetear igual?', danger=True):
            raise TaskError('Reset cancelado: hay cambios sin commitear.')
    ctx.run(['git', 'fetch', 'origin', rama])
    ctx.run(['git', 'reset', '--hard', f'origin/{rama}'])
    ctx.run(['git', 'clean', '-fd'])
    revision = ctx.capture(['git', 'rev-parse', '--short', 'HEAD'])
    ctx.ok(f'{rama} ahora es {revision}, igual que origin.')
    return revision


def repo_folder_name(url: str) -> str:
    """El nombre de carpeta que git le pondria al clon.

    Mismo criterio que `git clone` sin destino: el ultimo tramo de la URL sin
    `.git`. Vale igual para SSH (`git@github.com:usuario/repo.git`) que para
    HTTPS, porque los dos terminan en `/repo.git` o en `:usuario/repo.git`.
    El separador de esta maquina tambien corta: git clona igual desde una
    carpeta local, y ahi el ultimo tramo viene detras de una barra invertida.
    """
    limpio = url.strip().rstrip('/')
    if limpio.endswith('.git'):
        limpio = limpio[:-4]
    nombre = limpio.rsplit('/', 1)[-1].rsplit(os.sep, 1)[-1].rsplit(':', 1)[-1]
    if not nombre:
        raise TaskError(f'No se entiende que repositorio clonar de: {url}')
    return nombre


def clone_repo(ctx, url: str = '', dest: str = '', branch: str = '') -> Path:
    """Clona un repositorio de GitHub y devuelve la carpeta donde quedo.

    Devolver la ruta no es cosmetico: es lo que la ventana abre como pestana
    cuando la capacidad declara `opens_repo` (`core/registry.py`). La tarea no
    sabe nada de pestanas — dice donde dejo el repo, y eso alcanza.

    Sin carpeta destino se clona al lado del repo abierto: es donde viven los
    demas, y es el unico default que no hay que inventar. Nunca escribe sobre
    una carpeta que ya existe: eso no seria clonar sino mezclar dos repos.
    """
    if not url.strip():
        raise TaskError('Falta la URL del repositorio a clonar.')
    _git_or_fail()

    if dest.strip():
        carpeta = Path(dest.strip()).expanduser()
    elif ctx.project is not None:
        carpeta = ctx.root.parent
    else:
        raise TaskError('Indica la carpeta destino: no hay ningun repo abierto '
                        'del que deducirla.')

    destino = carpeta / repo_folder_name(url)
    if destino.exists():
        raise TaskError(f'Ya existe {destino}. Elige otra carpeta destino o borra esa.')
    carpeta.mkdir(parents=True, exist_ok=True)

    argv = ['git', 'clone']
    if branch.strip():
        argv += ['--branch', branch.strip()]
    argv += [url.strip(), str(destino)]
    ctx.run(argv, cwd=str(carpeta))
    revision = ctx.capture(['git', 'rev-parse', '--short', 'HEAD'], cwd=str(destino))
    ctx.ok(f'{destino.name} clonado en {destino} ({revision}).')
    return destino


def bind_all() -> None:
    registry.bind('git_force_push', force_push)
    registry.bind('git_force_reset', force_reset)
    registry.bind('clone_repo', clone_repo)
