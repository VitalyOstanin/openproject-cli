"""End-to-end tests of the CLI: argument parsing, dispatch, request shaping."""

import io
import json

from openproject_cli import cli
from openproject_cli.errors import NotFoundError


def _filters(request) -> list:
    return json.loads(request.url.params["filters"])


def test_wp_list_sends_server_side_filters(cli_run, router):
    router.add("GET", "/api/v3/users/me", {"id": 55})
    router.add(
        "GET", "/api/v3/work_packages", {"_embedded": {"elements": [{"id": 1234, "subject": "Sample"}]}}
    )
    code, out, _ = cli_run(["wp", "list", "--assignee", "me", "--open"])
    assert code == 0
    filters = _filters(router.last())
    assert {"assignee": {"operator": "=", "values": ["55"]}} in filters
    assert {"status_id": {"operator": "o", "values": []}} in filters
    assert json.loads(out)[0]["id"] == 1234


def test_wp_get(cli_run, router):
    router.add("GET", "/api/v3/work_packages/1234", {"id": 1234, "subject": "Sample", "_links": {}})
    code, out, _ = cli_run(["wp", "get", "1234"])
    assert code == 0
    assert json.loads(out)["id"] == 1234


def test_wp_get_raw_returns_full_payload(cli_run, router):
    router.add("GET", "/api/v3/work_packages/1234", {"id": 1234, "_links": {"self": {"href": "/x"}}})
    code, out, _ = cli_run(["wp", "get", "1234", "--raw"])
    assert code == 0
    assert json.loads(out)["_links"]["self"]["href"] == "/x"


def test_wp_create_builds_links(cli_run, router):
    router.add("GET", "/api/v3/projects/3", {"id": 3})
    router.add("POST", "/api/v3/work_packages", {"id": 1, "subject": "Sample", "_links": {}})
    code, _, _ = cli_run(["wp", "create", "--project", "3", "--type", "7", "--subject", "Sample"])
    assert code == 0
    body = router.body()
    assert body["subject"] == "Sample"
    assert body["_links"]["project"]["href"] == "/api/v3/projects/3"
    assert body["_links"]["type"]["href"] == "/api/v3/types/7"


def test_wp_update_fetches_lock_version(cli_run, router):
    router.add("GET", "/api/v3/work_packages/1234", {"id": 1234, "lockVersion": 4, "_links": {}})
    router.add("PATCH", "/api/v3/work_packages/1234", {"id": 1234, "_links": {}})
    code, _, _ = cli_run(["wp", "update", "1234", "--subject", "New"])
    assert code == 0
    body = router.body()
    assert body["lockVersion"] == 4
    assert body["subject"] == "New"


def test_time_list_sends_server_side_filters(cli_run, router):
    router.add("GET", "/api/v3/users/me", {"id": 55})
    router.add(
        "GET", "/api/v3/time_entries", {"_embedded": {"elements": [{"id": 1, "hours": "PT5H", "_links": {}}]}}
    )
    code, out, _ = cli_run(["time", "list", "--user", "me", "--since", "2026-06-22"])
    assert code == 0
    filters = _filters(router.last())
    assert {"user": {"operator": "=", "values": ["55"]}} in filters
    assert {"spentOn": {"operator": "<>d", "values": ["2026-06-22", ""]}} in filters
    assert json.loads(out)[0]["hours"] == 5.0


def test_time_create_converts_hours(cli_run, router):
    router.add("POST", "/api/v3/time_entries", {"id": 1, "hours": "PT1H30M", "_links": {}})
    code, _, _ = cli_run(
        [
            "time",
            "create",
            "--work-package",
            "1234",
            "--hours",
            "1.5",
            "--spent-on",
            "2026-06-30",
            "--comment",
            "x",
        ]
    )
    assert code == 0
    body = router.body()
    assert body["hours"] == "PT1H30M"
    assert body["spentOn"] == "2026-06-30"
    assert body["_links"]["workPackage"]["href"] == "/api/v3/work_packages/1234"
    assert body["comment"]["raw"] == "x"


def test_comment_create(cli_run, router):
    router.add(
        "POST", "/api/v3/work_packages/1234/comment", {"id": 9, "comment": {"raw": "Done"}, "_links": {}}
    )
    code, out, _ = cli_run(["comment", "create", "--work-package", "1234", "Done"])
    assert code == 0
    assert router.body()["comment"]["raw"] == "Done"
    assert json.loads(out)["comment"] == "Done"


def test_relation_create(cli_run, router):
    router.add("POST", "/api/v3/work_packages/1234/relations", {"id": 3, "type": "follows", "_links": {}})
    code, _, _ = cli_run(
        ["relation", "create", "--work-package", "1234", "--to", "5678", "--type", "follows"]
    )
    assert code == 0
    body = router.body()
    assert body["type"] == "follows"
    assert body["_links"]["to"]["href"] == "/api/v3/work_packages/5678"


def test_attachment_download_to_file(cli_run, router, tmp_path):
    import httpx

    router.add_handler(
        "GET", "/api/v3/attachments/9/content", lambda _req: httpx.Response(200, content=b"PDFDATA")
    )
    dest = tmp_path / "out.pdf"
    code, out, _ = cli_run(["attachment", "download", "9", "--output", str(dest)])
    assert code == 0
    assert dest.read_bytes() == b"PDFDATA"
    assert json.loads(out)["bytes"] == 7


def test_api_passthrough_get_with_fields(cli_run, router):
    router.add("GET", "/api/v3/work_packages", {"_embedded": {"elements": []}})
    code, out, _ = cli_run(["api", "GET", "work_packages", "-f", "pageSize=5"])
    assert code == 0
    assert router.last().url.params["pageSize"] == "5"
    assert json.loads(out) == {"_embedded": {"elements": []}}


def test_human_output(cli_run, router):
    router.add("GET", "/api/v3/work_packages/1234", {"id": 1234, "subject": "Sample", "_links": {}})
    code, out, _ = cli_run(["--human", "wp", "get", "1234"])
    assert code == 0
    assert "id:" in out
    assert "Sample" in out


def test_error_sets_exit_code(cli_run, router):
    router.add("GET", "/api/v3/work_packages/9", {"message": "not found"}, status=404)
    code, _, err = cli_run(["wp", "get", "9"])
    assert code == NotFoundError.exit_code
    assert "error:" in err


def test_auth_login_uses_keyring_by_default(tmp_path, capsys, fake_keyring):
    cfg = tmp_path / "config.yaml"
    code = cli.main(["--config", str(cfg), "auth", "login", "--url", "https://op.test", "--token", "secret"])
    assert code == 0
    saved = json.loads(capsys.readouterr().out)
    assert saved["tokenStorage"] == "keyring"
    assert fake_keyring["https://op.test"] == "secret"
    # The secret must not be written to the config file when keyring is used.
    assert "token" not in cfg.read_text()

    code = cli.main(["--config", str(cfg), "auth", "status", "--offline"])
    assert code == 0
    status = json.loads(capsys.readouterr().out)
    assert status["url"] == "https://op.test"
    assert status["tokenConfigured"] is True
    assert status["tokenSource"] == "keyring"


def test_auth_login_insecure_storage_writes_file(tmp_path, capsys, fake_keyring):
    cfg = tmp_path / "config.yaml"
    code = cli.main(
        [
            "--config",
            str(cfg),
            "auth",
            "login",
            "--url",
            "https://op.test",
            "--token",
            "secret",
            "--insecure-storage",
        ]
    )
    assert code == 0
    assert json.loads(capsys.readouterr().out)["tokenStorage"] == "file"
    assert "secret" in cfg.read_text()
    assert "https://op.test" not in fake_keyring


def test_auth_login_with_token_reads_stdin(tmp_path, capsys, monkeypatch, fake_keyring):
    cfg = tmp_path / "config.yaml"
    monkeypatch.setattr("sys.stdin", io.StringIO("piped-token\n"))
    code = cli.main(["--config", str(cfg), "auth", "login", "--url", "https://op.test", "--with-token"])
    assert code == 0
    assert fake_keyring["https://op.test"] == "piped-token"


def test_auth_token_prints_raw(tmp_path, capsys, fake_keyring):
    fake_keyring["https://op.test"] = "the-token"
    cfg = tmp_path / "config.yaml"
    cfg.write_text("url: https://op.test\n")
    code = cli.main(["--config", str(cfg), "auth", "token"])
    assert code == 0
    assert capsys.readouterr().out.strip() == "the-token"


def test_auth_logout_clears_keyring(tmp_path, capsys, fake_keyring):
    fake_keyring["https://op.test"] = "the-token"
    cfg = tmp_path / "config.yaml"
    cfg.write_text("url: https://op.test\n")
    code = cli.main(["--config", str(cfg), "auth", "logout"])
    assert code == 0
    assert json.loads(capsys.readouterr().out)["keyringCleared"] is True
    assert "https://op.test" not in fake_keyring


def test_wp_get_includes_custom_fields(cli_run, router):
    router.add(
        "GET",
        "/api/v3/work_packages/1234",
        {
            "id": 1234,
            "subject": "Sample",
            "customField1": "High",
            "_links": {"schema": {"href": "/api/v3/work_packages/schemas/1-7"}},
        },
    )
    router.add("GET", "/api/v3/work_packages/schemas/1-7", {"customField1": {"name": "Severity"}})
    code, out, _ = cli_run(["wp", "get", "1234"])
    assert code == 0
    data = json.loads(out)
    assert data["customFields"] == [{"key": "customField1", "name": "Severity", "value": "High"}]


def test_comment_list_resolves_author_and_details(cli_run, router):
    activities = {
        "_embedded": {
            "elements": [
                {
                    "id": 9,
                    "_type": "Activity",
                    "comment": {"raw": "Done"},
                    "details": [{"raw": "Status changed from New to In progress"}],
                    "_links": {"user": {"href": "/api/v3/users/7"}},
                }
            ]
        }
    }
    router.add("GET", "/api/v3/work_packages/1234/activities", activities)
    router.add("GET", "/api/v3/users/7", {"id": 7, "name": "Alice Example"})
    code, out, _ = cli_run(["comment", "list", "--work-package", "1234"])
    assert code == 0
    entry = json.loads(out)[0]
    assert entry["user"] == "Alice Example"
    assert entry["userId"] == 7
    assert entry["details"] == ["Status changed from New to In progress"]


def test_attachment_download_reports_sha256(cli_run, router, tmp_path):
    import hashlib

    import httpx

    router.add_handler(
        "GET", "/api/v3/attachments/9/content", lambda _req: httpx.Response(200, content=b"PDFDATA")
    )
    dest = tmp_path / "out.pdf"
    code, out, _ = cli_run(["attachment", "download", "9", "--output", str(dest)])
    assert code == 0
    payload = json.loads(out)
    assert payload["bytes"] == 7
    assert payload["sha256"] == hashlib.sha256(b"PDFDATA").hexdigest()
    assert dest.read_bytes() == b"PDFDATA"


class _Tty:
    """Minimal stdin stand-in whose isatty() is True for interactive-login tests."""

    def isatty(self) -> bool:
        return True

    def readline(self) -> str:
        return ""


def test_auth_login_interactive_opens_browser_and_prompts(tmp_path, capsys, monkeypatch, fake_keyring):
    cfg = tmp_path / "config.yaml"
    opened: dict[str, str] = {}
    monkeypatch.setattr(
        "openproject_cli.commands.auth.webbrowser.open",
        lambda url, new=2: (opened.__setitem__("url", url), True)[1],
    )
    monkeypatch.setattr("openproject_cli.commands.auth.getpass.getpass", lambda prompt="": "typed-token")
    monkeypatch.setattr("openproject_cli.commands.auth.sys.stdin", _Tty())
    code = cli.main(["--config", str(cfg), "auth", "login", "--url", "https://op.test"])
    assert code == 0
    assert opened["url"] == "https://op.test/my/access_token"
    assert fake_keyring["https://op.test"] == "typed-token"


def test_auth_login_no_browser_skips_open(tmp_path, capsys, monkeypatch, fake_keyring):
    cfg = tmp_path / "config.yaml"
    calls = {"opened": False}
    monkeypatch.setattr(
        "openproject_cli.commands.auth.webbrowser.open",
        lambda url, new=2: calls.__setitem__("opened", True) or True,
    )
    monkeypatch.setattr("openproject_cli.commands.auth.getpass.getpass", lambda prompt="": "typed-token")
    monkeypatch.setattr("openproject_cli.commands.auth.sys.stdin", _Tty())
    code = cli.main(["--config", str(cfg), "auth", "login", "--url", "https://op.test", "--no-browser"])
    assert code == 0
    assert calls["opened"] is False
    assert fake_keyring["https://op.test"] == "typed-token"


def test_auth_login_url_optional_reuses_config(tmp_path, capsys, fake_keyring):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("url: https://op.test\n")
    code = cli.main(["--config", str(cfg), "auth", "login", "--token", "secret"])
    assert code == 0
    saved = json.loads(capsys.readouterr().out)
    assert saved["url"] == "https://op.test"
    assert fake_keyring["https://op.test"] == "secret"
