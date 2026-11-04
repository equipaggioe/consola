"""What Consola reads from the services it asks over HTTP."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from app.core import canone, files
from app.core.context import TaskContext
from app.core.envfile import Config
from app.core.errors import TaskError
from app.core.tasks import utils

CONFIG = {
    "CF_API_TOKEN": "token",
    "CF_DOMAIN_NAME": "ejemplo.net",
    "CF_RECORD_NAME": "app.ejemplo.net",
    "VPS_IP": "203.0.113.9",
}
ANDROID_PAGE = """
<td><button>commandlinetools-win-15859902_latest.zip</button></td>
<td>155.7 MB</td>
<td>90ae805d20434428bffcb699c290860f19bb5f66a67e6b330067e3de801fb04a</td>
"""
FLUTTER_INDEX = {
    "base_url": "https://storage.googleapis.com/flutter_infra_release/releases",
    "current_release": {"beta": "bbb", "stable": "aaa"},
    "releases": [
        {
            "hash": "bbb",
            "channel": "beta",
            "version": "3.48.0",
            "archive": "beta/flutter.zip",
            "sha256": "1" * 64,
        },
        {
            "hash": "aaa",
            "channel": "stable",
            "version": "3.47.9",
            "archive": "stable/flutter.zip",
            "sha256": "2" * 64,
        },
    ],
}


def serving(text: str) -> Callable[[str], str]:
    """Return a `_fetch_text` that answers that text."""

    def fetch(url: str) -> str:
        return text

    return fetch


def ok(result: Any) -> bytes:
    """Return a successful Cloudflare answer."""
    return json.dumps({"success": True, "errors": [], "result": result}).encode("utf-8")


def test_the_android_digest_is_the_whole_sha256(monkeypatch: pytest.MonkeyPatch) -> None:
    """Google publishes 64 hex digits, and all of them are read."""
    monkeypatch.setattr(utils, "_fetch_text", serving(ANDROID_PAGE))
    url, digest = utils._resolve_cmdline_tools(TaskContext("prueba"), "windows")
    assert url.endswith("commandlinetools-win-15859902_latest.zip")
    assert digest == "90ae805d20434428bffcb699c290860f19bb5f66a67e6b330067e3de801fb04a"


def test_verify_compares_the_sha256_of_the_file(tmp_path: Path) -> None:
    """A file passes with its SHA-256 and stops with another."""
    archive = tmp_path / "sdk.zip"
    archive.write_bytes(b"sdk")
    utils._verify(TaskContext("prueba"), archive, files.digest(archive))
    with pytest.raises(TaskError, match="SHA-256 no coincide"):
        utils._verify(TaskContext("prueba"), archive, "0" * 64)


def test_flutter_takes_the_release_of_the_stable_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    """The stable release is the one `current_release` names."""
    monkeypatch.setattr(utils, "_fetch_text", serving(json.dumps(FLUTTER_INDEX)))
    url, digest = utils._resolve_flutter_stable(TaskContext("prueba"), "windows")
    assert url == utils.FLUTTER_RELEASES_URL + "stable/flutter.zip"
    assert digest == "2" * 64


def test_a_flutter_index_with_another_shape_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    """An index that does not bring the channel says so."""
    monkeypatch.setattr(utils, "_fetch_text", serving('{"releases": []}'))
    with pytest.raises(TaskError, match="vino distinto"):
        utils._resolve_flutter_stable(TaskContext("prueba"), "windows")


def test_cloudflare_changes_the_record_it_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """The record's id and old content come from the models."""
    calls: list[tuple[str, str, bytes | None]] = []
    answers = iter(
        [
            ok([{"id": "z1", "name": "ejemplo.net"}]),
            ok([{"id": "r1", "content": "203.0.113.1", "type": "A"}]),
            ok({"id": "r1"}),
        ]
    )

    def request(url: str, *, method: str, headers: Any, body: bytes | None) -> bytes:
        calls.append((method, url, body))
        return next(answers)

    monkeypatch.setattr(utils.http, "request", request)
    ip = utils.update_cloudflare(TaskContext("prueba", config=Config(CONFIG)))
    assert ip == "203.0.113.9"
    method, url, body = calls[-1]
    assert (method, url.endswith("/zones/z1/dns_records/r1")) == ("PUT", True)
    assert json.loads(body or b"")["content"] == "203.0.113.9"


def test_a_rejected_cloudflare_answer_says_why(monkeypatch: pytest.MonkeyPatch) -> None:
    """A rejection has no `result`, and what shows is its errors."""
    rejected = {"success": False, "errors": [{"code": 9109}], "result": None}

    def request(*args: Any, **kwargs: Any) -> bytes:
        return json.dumps(rejected).encode("utf-8")

    monkeypatch.setattr(utils.http, "request", request)
    with pytest.raises(TaskError, match="9109"):
        utils.update_cloudflare(TaskContext("prueba", config=Config(CONFIG)))


def test_an_unexpected_cloudflare_answer_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    """Something that is not its JSON stops the task and is named."""

    def request(*args: Any, **kwargs: Any) -> bytes:
        return b"<html>"

    monkeypatch.setattr(utils.http, "request", request)
    with pytest.raises(TaskError, match="inesperado"):
        utils.update_cloudflare(TaskContext("prueba", config=Config(CONFIG)))


def test_desktops_reads_the_matrix_of_the_template(tmp_path: Path) -> None:
    """Each installer of `release.yml` counts, by its file name."""
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "release.yml").write_text(
        "          - os: ubuntu-latest\n"
        "            archivo: desktop-linux.bin\n"
        "          - os: windows-latest\n"
        "            archivo: desktop-windows.exe\n"
        '        run: mv dist/*.bin "${{ matrix.archivo }}"\n',
        encoding="utf-8",
    )
    assert canone.desktops(tmp_path) == ["linux", "windows"]
