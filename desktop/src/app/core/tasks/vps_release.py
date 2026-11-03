from __future__ import annotations
import json
import tempfile
from pathlib import Path

from app.core import canone, process, ssh
from app.core.errors import TaskError
from app.core.host import HOST
from app.core.registry import registry
from app.core.tasks.git import _current_branch, _ensure_git
from app.core.tasks.vps_setup import Access, access

"""
Grupo Despliegue - versiones: publicar, firmar y desplegar un tag (ADR-0059).

Con cada tag, el `release.yml` del repo construye el artefacto y lo publica en
un release de GitHub con su `.sha256`. Esta maquina firma ese `.sha256` con
`VPS_KEY_NAME`, fuera de GitHub, y el VPS lo instala con el `deploy.py` que dejo
`install.py`, que solo acepta lo que firma una llave de `allowed_signers`
(despliegue.md de canone, «Versiones»).
"""

WORKFLOW = 'release.yml'
# Cada cuanto se pregunta por la corrida de `release.yml`, y cuantas veces se
# pregunta si ya existe antes de darla por perdida.
_POLL = 15
_APPEARS = 12


def _gh() -> list[str]:
    return process.resolve_executable(HOST.executable_names('gh'), label='GitHub CLI (gh)',
                                      hint='Instálalo y corre gh auth login.')


def _repo(root: Path) -> tuple[str, str]:
    """`dueño/repo` en GitHub y el `<app>` de canone, que es el nombre del repo."""
    owner, app = canone.origin(root)
    return f'{owner}/{app}', app


def releases(root: Path) -> list[dict]:
    """Los releases del repo, del mas nuevo al mas viejo, con sus archivos."""
    repo, _ = _repo(root)
    return json.loads(process.capture([*_gh(), 'api', f'repos/{repo}/releases?per_page=30'],
                                      cwd=root, timeout=30.0))


def _latest(ctx) -> dict:
    """El ultimo release publicado: el que GitHub da como `latest`."""
    repo, _ = _repo(ctx.root)
    try:
        return json.loads(ctx.capture([*_gh(), 'api', f'repos/{repo}/releases/latest'],
                                      timeout=30.0))
    except TaskError as exc:
        raise TaskError(f'{repo} no tiene releases publicados: corre «Publicar versión».') from exc


# --- atomicas --------------------------------------------------------------

def _pushed(ctx) -> None:
    """Corta si hay algo que el tag no lleva: cambios sin commitear o commits sin empujar.

    El CI construye el commit del tag en GitHub, no esta carpeta.
    """
    _ensure_git(ctx)
    rama = _current_branch(ctx)
    sucio = ctx.capture(['git', 'status', '--porcelain'])
    if sucio:
        raise TaskError(f'Hay cambios sin commitear, y el tag no los lleva:\n{sucio}')
    ctx.run(['git', 'fetch', 'origin'], echo=False)
    upstream = ctx.capture(['git', 'rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{u}'],
                           check=False)
    if not upstream:
        raise TaskError(f'{rama} no tiene rama en origin: empújala primero.')
    if ctx.capture(['git', 'rev-list', '--count', f'{upstream}..HEAD']) != '0':
        raise TaskError(f'{rama} tiene commits que {upstream} no tiene: empújalos primero.')


def _run_id(ctx, gh: list[str], repo: str, tag: str) -> str:
    """La corrida de `release.yml` que disparo el tag. GitHub la crea unos segundos despues."""
    for _ in range(_APPEARS):
        corrida = ctx.capture([*gh, 'run', 'list', '--repo', repo, '--workflow', WORKFLOW,
                               '--branch', tag, '--json', 'databaseId',
                               '--jq', '.[0].databaseId'], timeout=30.0)
        if corrida:
            return corrida
        ctx.wait_cancelled(5)
        ctx.raise_if_cancelled()
    raise TaskError(f'GitHub no creó la corrida de {WORKFLOW} para {tag}: ¿tiene el repo '
                    f'.github/workflows/{WORKFLOW}?')


def _watch(ctx, repo: str, tag: str) -> None:
    """Espera a que `release.yml` termine, y corta si no termina bien."""
    gh = _gh()
    corrida = _run_id(ctx, gh, repo, tag)
    ctx.info(f'{WORKFLOW} corre en https://github.com/{repo}/actions/runs/{corrida}')
    visto = ''
    while True:
        estado = json.loads(ctx.capture([*gh, 'run', 'view', corrida, '--repo', repo,
                                         '--json', 'status,conclusion'], timeout=30.0))
        if estado['status'] != visto:
            visto = estado['status']
            ctx.info(f'{WORKFLOW}: {visto}')
        if visto == 'completed':
            break
        ctx.wait_cancelled(_POLL)
        ctx.raise_if_cancelled()
    if estado['conclusion'] != 'success':
        ctx.run([*gh, 'run', 'view', corrida, '--repo', repo, '--log-failed'], check=False)
        raise TaskError(f'{WORKFLOW} terminó en {estado["conclusion"]}: {tag} no se publicó.')


def create_tag(ctx, part: str = 'patch') -> str:
    """Crea el tag que sigue al ultimo de origin, lo empuja y espera a `release.yml`.

    El numero sale de los tags de origin y no de los locales: un tag que quedo
    sin empujar no adelanta la version.
    """
    _pushed(ctx)
    repo, _ = _repo(ctx.root)
    remotos = ctx.capture(['git', 'ls-remote', '--tags', '--refs', 'origin', 'v*'])
    tags = [linea.rpartition('refs/tags/')[2] for linea in remotos.splitlines()]
    tag = canone.next_tag(tags, part)
    ctx.run(['git', 'tag', '-a', tag, '-m', tag])
    ctx.run(['git', 'push', 'origin', f'refs/tags/{tag}'])
    _watch(ctx, repo, tag)
    ctx.ok(f'{tag} publicado.')
    return tag


def sign_release(ctx, tag: str) -> None:
    """Firma el `.sha256` del release con `VPS_KEY_NAME` y sube la firma.

    `-n deploy` es el espacio de nombres que comprueba `deploy.py`: separa esta
    firma de cualquier otro uso de la llave. Un release que ya tiene su firma no
    se vuelve a firmar.
    """
    repo, app = _repo(ctx.root)
    gh = _gh()
    llave = ssh.resolve_identity(ctx.config.require('VPS_KEY_NAME'))
    release = json.loads(ctx.capture([*gh, 'release', 'view', tag, '--repo', repo,
                                      '--json', 'isDraft,assets'], timeout=30.0))
    nombres = {a['name'] for a in release['assets']}
    suma, firma = canone.checksum(app, tag), canone.signature(app, tag)
    if firma in nombres:
        ctx.ok(f'{tag} ya tiene {firma}.')
        return
    if release['isDraft'] or suma not in nombres:
        raise TaskError(f'El release {tag} no tiene {suma}: {WORKFLOW} no terminó.')
    with tempfile.TemporaryDirectory() as carpeta:
        ctx.run([*gh, 'release', 'download', tag, '--repo', repo, '--pattern', suma,
                 '--dir', carpeta])
        ctx.run(['ssh-keygen', '-Y', 'sign', '-n', 'deploy', '-f', str(llave),
                 str(Path(carpeta) / suma)])
        ctx.run([*gh, 'release', 'upload', tag, str(Path(carpeta) / firma), '--repo', repo])
    ctx.ok(f'{tag} firmado.')


def deploy_release(ctx, tag: str) -> None:
    """Corre en el VPS `deploy.py` con el tag, desde la cuenta que administra.

    `deploy.py` baja el release, comprueba la firma, migra, cambia `current` y
    espera a que la salud responda; si no responde, vuelve a la version anterior
    cuando no hubo migraciones.
    """
    _, app = _repo(ctx.root)
    _deploy(ctx, _admin(ctx), app, tag)


def _admin(ctx) -> Access:
    entrada = access(ctx)
    if entrada.is_root:
        raise TaskError('La cuenta que administra todavía no existe: corre «Configurar VPS» '
                        'con «Instalar infraestructura» primero.')
    return entrada


def _deploy(ctx, entrada: Access, app: str, tag: str) -> None:
    entrada.run(ctx, canone.deploy_command(app, tag))
    ctx.ok(f'{tag} desplegado en {entrada.remote.host}.')


def deploy_latest(ctx) -> str:
    """Despliega el ultimo release publicado, si esta firmado: el primer despliegue
    de «Configurar VPS».

    Si `current` ya es ese release no hace nada, para que la compuesta se pueda
    volver a correr: `deploy.py` no instala dos veces la misma version.
    """
    _, app = _repo(ctx.root)
    ultimo = _latest(ctx)
    tag = ultimo['tag_name']
    if not canone.signed(app, [ultimo]):
        raise TaskError(f'El último release, {tag}, no tiene {canone.signature(app, tag)}: '
                        'fírmalo con «Publicar versión» sin «Crear tag».')
    entrada = _admin(ctx)
    actual = ssh.capture(entrada.remote, f'readlink {ssh.quote(f"/srv/{app}/current")}',
                         check=False)
    if actual.rpartition('/')[2] == tag:
        ctx.ok(f'{tag} ya está desplegado.')
        return tag
    _deploy(ctx, entrada, app, tag)
    return tag


# --- botones ---------------------------------------------------------------

def publish_release(ctx, part: str = 'patch', *, tag: bool = True, sign: bool = True,
                    deploy: bool = True) -> str:
    """Tag → `release.yml` → firma → `deploy.py`.

    Sin «Crear tag», firma y despliega el ultimo release publicado: es lo que
    hace falta para retomar una publicacion que corto despues del CI.
    """
    if tag:
        ctx.step('tag')
        version = create_tag(ctx, part)
    else:
        version = _latest(ctx)['tag_name']
    if sign:
        ctx.step('sign')
        sign_release(ctx, version)
    if deploy:
        ctx.step('deploy')
        deploy_release(ctx, version)
    ctx.note(f'{version} publicado.')
    return version


def deploy_version(ctx, version: str = '') -> None:
    """Instala un release ya firmado. `deploy.py` no instala una version que siga
    en `/srv/<app>/releases/`, donde quedan las cinco mas nuevas."""
    if not version:
        raise TaskError('Elige la versión que se despliega.')
    deploy_release(ctx, version)


def bind_all() -> None:
    registry.bind('publish_release', publish_release)
    registry.bind('deploy_version', deploy_version)
