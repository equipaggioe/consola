from __future__ import annotations
from ..errors import TaskError
from ..process import which_any
from ..registry import registry

"""
Grupo Git.

Los dos forzados de aca abajo son la mitad que le falta a lo que ya hacen
`push_repository`/`sync_repository` (`vps_server.py`): esos dos nunca pisan
historia ajena a proposito -- avisan y frenan si algo no calza. Aca la
decision ya esta tomada de antemano: un lado gana, aunque el otro tenga
commits que el ganador no conoce.

Viven en su propio modulo, y no en `vps_server.py` junto a `push_repository`,
porque no son la mitad de ningun despliegue: son un forzado local↔GitHub que
no le importa a ningun VPS.
"""


def _ensure_git(ctx) -> None:
    if not which_any(['git', 'git.exe']):
        raise TaskError('No se encontro Git en el PATH.')
    if not ctx.path('.git').exists():
        raise TaskError(f'La carpeta abierta no es un repositorio git: {ctx.root}')


def _current_branch(ctx) -> str:
    rama = ctx.capture(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])
    if rama == 'HEAD':
        raise TaskError('El repo local esta en HEAD desacoplado: no hay rama que forzar.')
    return rama


def force_push(ctx) -> str:
    """Fuerza a que origin quede igual a la rama local, aunque haya divergido.

    `--force` y no `--force-with-lease`: la lease rechaza el push justo cuando
    origin tiene commits que esta maquina no vio, que es exactamente el caso
    para el que existe este boton.
    """
    _ensure_git(ctx)
    rama = _current_branch(ctx)
    ctx.run(['git', 'fetch', '--quiet'], check=False, echo=False)
    ctx.run(['git', 'push', '--force', 'origin', rama])
    revision = ctx.capture(['git', 'rev-parse', '--short', 'HEAD'])
    ctx.ok(f'origin/{rama} ahora es {revision}, igual que esta maquina.')
    return revision


def force_reset(ctx) -> str:
    """Fuerza a que la rama local quede igual a origin, descartando lo propio.

    Tira los commits locales que origin no tiene y lo que haya sin trackear
    (`git clean -fd`) -- mismo criterio que ya aplica `sync_repository` del
    lado del VPS, del otro extremo del mismo par.
    """
    _ensure_git(ctx)
    rama = _current_branch(ctx)
    ctx.run(['git', 'fetch', 'origin', rama])
    ctx.run(['git', 'reset', '--hard', f'origin/{rama}'])
    ctx.run(['git', 'clean', '-fd'])
    revision = ctx.capture(['git', 'rev-parse', '--short', 'HEAD'])
    ctx.ok(f'{rama} ahora es {revision}, igual que origin.')
    return revision


def bind_all() -> None:
    registry.bind('git_force_push', force_push)
    registry.bind('git_force_reset', force_reset)
