"""What Consola reads from the services it asks over HTTP."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from app.api import flutter, http
from app.services import canone, files
from app.services.catalog import load_catalog
from app.services.context import TaskContext
from app.services.envfile import Config
from app.services.errors import TaskError
from app.services.projects import Project
from app.services.registry import registry
from app.services.tasks import utils

CONFIG = {
    "CF_API_TOKEN": "token",
    "CF_DOMAIN_NAME": "ejemplo.net",
    "DOMAIN": "ejemplo.net",
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


def serving(text: str) -> Callable[..., bytes]:
    """Return an `http.request` that answers that text."""

    def request(*args: object, **kwargs: object) -> bytes:
        return text.encode("utf-8")

    return request


def ok(result: Any) -> bytes:
    """Return a successful Cloudflare answer."""
    return json.dumps({"success": True, "errors": [], "result": result}).encode("utf-8")


def test_the_android_digest_is_the_whole_sha256(monkeypatch: pytest.MonkeyPatch) -> None:
    """Google publishes 64 hex digits, and all of them are read."""
    monkeypatch.setattr(utils.http, "request", serving(ANDROID_PAGE))
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
    monkeypatch.setattr(utils.http, "request", serving(json.dumps(FLUTTER_INDEX)))
    url, digest = utils._resolve_flutter_stable(TaskContext("prueba"), "windows")
    assert url == flutter.RELEASES_URL + "stable/flutter.zip"
    assert digest == "2" * 64


def test_a_flutter_index_with_another_shape_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    """An index that does not bring the channel says so."""
    monkeypatch.setattr(utils.http, "request", serving('{"releases": []}'))
    with pytest.raises(TaskError, match="vino distinto"):
        utils._resolve_flutter_stable(TaskContext("prueba"), "windows")


class FakeCloudflare:
    """The zone `ejemplo.net` with its A records, by name."""

    def __init__(self, records: dict[str, tuple[str, bool]]) -> None:
        """Keep the records and the writes it receives."""
        self.records = {
            name: {"id": name, "content": ip, "proxied": proxied}
            for name, (ip, proxied) in records.items()
        }
        self.writes: list[tuple[str, dict[str, Any]]] = []

    def request(self, url: str, *, method: str, headers: Any, body: bytes | None) -> bytes:
        """Answer as Cloudflare: zones, records, and each write."""
        if "/zones?name=" in url:
            return ok([{"id": "z1", "name": "ejemplo.net"}])
        if method == "GET":
            name = url.rpartition("name=")[2]
            return ok([self.records[name]] if name in self.records else [])
        sent = json.loads(body or b"")
        self.writes.append((method, sent))
        self.records[sent["name"]] = {
            "id": sent["name"],
            "content": sent["content"],
            "proxied": sent["proxied"],
        }
        return ok({"id": sent["name"]})


def _project(tmp_path: Path, *pieces: str) -> Project:
    for piece in pieces:
        (tmp_path / piece).mkdir()
    return Project(name="ejemplo", path=str(tmp_path), theme="blue")


def _cloudflare_ctx(tmp_path: Path, *pieces: str) -> TaskContext:
    return TaskContext("prueba", project=_project(tmp_path, *pieces), config=Config(CONFIG))


def test_cloudflare_points_each_host_without_proxy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Each web piece's host ends on the IP without proxy.

    One record is created and one changes.
    """
    fake = FakeCloudflare({"app.ejemplo.net": ("203.0.113.1", True)})
    monkeypatch.setattr(utils.http, "request", fake.request)
    ip = utils.update_cloudflare(_cloudflare_ctx(tmp_path, "web", "landing"))
    assert ip == "203.0.113.9"
    assert fake.records == {
        "app.ejemplo.net": {"id": "app.ejemplo.net", "content": ip, "proxied": False},
        "ejemplo.net": {"id": "ejemplo.net", "content": ip, "proxied": False},
    }
    assert [method for method, _ in fake.writes] == ["PUT", "POST"]


def test_cloudflare_leaves_a_record_already_right(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A host on the IP without proxy is not written; one with it is."""
    fake = FakeCloudflare(
        {"panel.ejemplo.net": ("203.0.113.9", False), "ejemplo.net": ("203.0.113.9", True)}
    )
    monkeypatch.setattr(utils.http, "request", fake.request)
    utils.update_cloudflare(_cloudflare_ctx(tmp_path, "panel", "landing"))
    assert fake.writes == [
        (
            "PUT",
            {
                "type": "A",
                "name": "ejemplo.net",
                "content": "203.0.113.9",
                "ttl": 1,
                "proxied": False,
            },
        )
    ]


def test_cloudflare_without_web_pieces_stops(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A repo without landing/, web/ or panel/ has no host to point."""
    fake = FakeCloudflare({})
    monkeypatch.setattr(utils.http, "request", fake.request)
    with pytest.raises(TaskError, match="ningún host"):
        utils.update_cloudflare(_cloudflare_ctx(tmp_path))
    assert fake.writes == []


def test_cloudflare_points_to_a_written_ip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """«Otra» sends what was written, not `VPS_IP`."""
    fake = FakeCloudflare({})
    monkeypatch.setattr(utils.http, "request", fake.request)
    ctx = _cloudflare_ctx(tmp_path, "web")
    assert utils.update_cloudflare(ctx, ip_mode="static", custom_ip=" 198.51.100.7 ") == (
        "198.51.100.7"
    )
    assert fake.writes[-1][1]["content"] == "198.51.100.7"


def test_cloudflare_with_other_and_no_ip_stops(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """«Otra» with the field empty does not fall to `VPS_IP`."""
    fake = FakeCloudflare({})
    monkeypatch.setattr(utils.http, "request", fake.request)
    with pytest.raises(TaskError, match="Otra IP"):
        utils.update_cloudflare(_cloudflare_ctx(tmp_path, "web"), ip_mode="static", custom_ip="")
    assert fake.writes == []


def test_cloudflare_points_to_this_machine(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """«La pública de esta máquina» sends the detected IP."""
    fake = FakeCloudflare({})
    monkeypatch.setattr(utils.http, "request", fake.request)

    def detect(ctx: TaskContext) -> str:
        return "192.0.2.44"

    monkeypatch.setattr(utils, "detect_public_ip", detect)
    assert utils.update_cloudflare(_cloudflare_ctx(tmp_path, "web"), ip_mode="detect") == (
        "192.0.2.44"
    )
    assert fake.writes[-1][1]["content"] == "192.0.2.44"


def test_the_cloudflare_axes_reach_the_function() -> None:
    """The panel's choice arrives as `ip_mode` and `custom_ip`."""
    load_catalog()
    capability = registry.get_capability("update_cloudflare")
    assert capability is not None
    payload = {"options": {"ip_mode": "static"}, "fields": {"custom_ip": "198.51.100.7"}}
    assert capability.kwargs_from(payload) == {"ip_mode": "static", "custom_ip": "198.51.100.7"}


def test_a_rejected_cloudflare_answer_says_why(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A rejection has no `result`, and what shows is its errors."""
    rejected = {"success": False, "errors": [{"code": 9109}], "result": None}

    def request(*args: Any, **kwargs: Any) -> bytes:
        return json.dumps(rejected).encode("utf-8")

    monkeypatch.setattr(utils.http, "request", request)
    with pytest.raises(TaskError, match="9109"):
        utils.update_cloudflare(_cloudflare_ctx(tmp_path, "web"))


def test_an_unexpected_cloudflare_answer_stops(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Something that is not its JSON stops the task and is named."""

    def request(*args: Any, **kwargs: Any) -> bytes:
        return b"<html>"

    monkeypatch.setattr(utils.http, "request", request)
    with pytest.raises(TaskError, match="inesperado"):
        utils.update_cloudflare(_cloudflare_ctx(tmp_path, "web"))


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


def test_mobiles_reads_the_apks_the_release_uploads(tmp_path: Path) -> None:
    """Each `<piece>.apk` that `release.yml` uploads counts once."""
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "release.yml").write_text(
        '      - run: gh release upload "$GITHUB_REF_NAME" mobile-customer.apk\n'
        '      - run: gh release upload "$GITHUB_REF_NAME" mobile-vendor.apk\n'
        '      - run: gh release upload "$GITHUB_REF_NAME" mobile-customer.apk\n'
        '      - run: gh release upload "$GITHUB_REF_NAME" "${{ matrix.archivo }}"\n',
        encoding="utf-8",
    )
    assert canone.mobiles(tmp_path) == ["mobile-customer", "mobile-vendor"]


def test_cloudflare_says_why_it_refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A bad token answers 400, and the task shows Cloudflare's reason.

    The body is what the real API answered on 2026-11-22 to a token
    that is not valid.
    """

    def refuse(url: str, **kwargs: object) -> bytes:
        body = (
            b'{"success":false,"errors":[{"code":6003,"message":"Invalid request headers",'
            b'"error_chain":[{"code":6111,"message":"Invalid format for Authorization header"}]}],'
            b'"messages":[],"result":null}'
        )
        raise http.HttpError("server replied with status code 400", 400, body)

    monkeypatch.setattr(utils.http, "request", refuse)
    with pytest.raises(TaskError, match="rechazo.*Invalid request headers"):
        utils.update_cloudflare(_cloudflare_ctx(tmp_path, "web"))


def test_cloudflare_without_its_answer_cannot_be_reached(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An error page that is not Cloudflare's answer fails to talk."""

    def fail(url: str, **kwargs: object) -> bytes:
        raise http.HttpError("server replied with status code 502", 502, b"<html>")

    monkeypatch.setattr(utils.http, "request", fail)
    with pytest.raises(TaskError, match="No se pudo hablar con Cloudflare"):
        utils.update_cloudflare(_cloudflare_ctx(tmp_path, "web"))
