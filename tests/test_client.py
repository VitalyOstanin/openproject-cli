"""Tests for the HTTP client: URL joining, auth, error mapping, streaming."""

import base64
import io

import httpx
import pytest

from openproject_cli.errors import ApiError, AuthError, NotFoundError
from tests.conftest import Router, json_response, make_client


@pytest.mark.parametrize(
    "given",
    ["work_packages/1", "/work_packages/1", "api/v3/work_packages/1", "/api/v3/work_packages/1"],
)
def test_url_join_variants_hit_same_path(given):
    router = Router().add("GET", "/api/v3/work_packages/1", {"id": 1})
    client = make_client(router)
    assert client.get_json(given) == {"id": 1}
    assert router.last().url.path == "/api/v3/work_packages/1"


def test_url_strips_deployment_subpath_from_api_hrefs():
    # Instances hosted under a sub-path return hrefs like "/openproject/api/v3/...".
    # The prefix must not be duplicated when such an href is fed back to the client.
    router = Router().add("GET", "/api/v3/work_packages/schemas/4-1", {"_type": "Schema"})
    client = make_client(router)
    client.get_json("/openproject/api/v3/work_packages/schemas/4-1")
    assert router.last().url.path == "/api/v3/work_packages/schemas/4-1"


def test_basic_auth_uses_apikey_username():
    router = Router().add("GET", "/api/v3/users/me", {"id": 5})
    client = make_client(router)
    client.current_user()
    header = router.last().headers["authorization"]
    scheme, _, encoded = header.partition(" ")
    assert scheme == "Basic"
    assert base64.b64decode(encoded).decode() == "apikey:TKN"


def test_401_maps_to_auth_error():
    router = Router().add("GET", "/api/v3/users/me", {"message": "bad token"}, status=401)
    client = make_client(router)
    with pytest.raises(AuthError):
        client.current_user()


def test_404_maps_to_not_found():
    router = Router().add("GET", "/api/v3/work_packages/9", {"message": "not found"}, status=404)
    client = make_client(router)
    with pytest.raises(NotFoundError):
        client.get_json("work_packages/9")


def test_422_includes_validation_details():
    body = {
        "message": "Multiple field constraints",
        "_embedded": {"errors": [{"message": "Subject can't be blank"}]},
    }
    router = Router().add("POST", "/api/v3/work_packages", body, status=422)
    client = make_client(router)
    with pytest.raises(ApiError) as excinfo:
        client.request("POST", "work_packages", json_body={})
    assert excinfo.value.status == 422
    assert "Subject can't be blank" in str(excinfo.value)


def test_resolve_principal_me():
    router = Router().add("GET", "/api/v3/users/me", {"id": 55})
    client = make_client(router)
    assert client.resolve_principal_id("me") == "55"


def test_resolve_principal_numeric_is_verbatim():
    client = make_client(Router())
    assert client.resolve_principal_id("123") == "123"


def test_resolve_principal_by_name():
    router = Router().add(
        "GET",
        "/api/v3/principals",
        {"_embedded": {"elements": [{"id": 7, "name": "Alice Example"}, {"id": 8, "name": "Bob Example"}]}},
    )
    client = make_client(router)
    assert client.resolve_principal_id("alice example") == "7"  # case-insensitive exact match


def test_resolve_principal_not_found():
    router = Router().add("GET", "/api/v3/principals", {"_embedded": {"elements": []}})
    client = make_client(router)
    with pytest.raises(ApiError):
        client.resolve_principal_id("nobody")


def test_resolve_principal_ambiguous():
    router = Router().add(
        "GET",
        "/api/v3/principals",
        {"_embedded": {"elements": [{"id": 1, "name": "Same"}, {"id": 2, "name": "same"}]}},
    )
    client = make_client(router)
    with pytest.raises(ApiError):
        client.resolve_principal_id("same")


def test_resolve_principal_partial_name_skips_middle_token():
    # "Ann Lee" must resolve to "Ann Marie Lee": the tokens all occur in the
    # full name even though it is not a contiguous substring.
    router = Router().add(
        "GET", "/api/v3/principals", {"_embedded": {"elements": [{"id": 54, "name": "Ann Marie Lee"}]}}
    )
    client = make_client(router)
    assert client.resolve_principal_id("Ann Lee") == "54"


def test_resolve_principal_ambiguous_lists_candidates():
    router = Router().add(
        "GET",
        "/api/v3/principals",
        {"_embedded": {"elements": [{"id": 1, "name": "Ann Lee"}, {"id": 2, "name": "Ann Ross"}]}},
    )
    client = make_client(router)
    with pytest.raises(ApiError) as excinfo:
        client.resolve_principal_id("Ann")
    message = str(excinfo.value)
    assert "1: Ann Lee" in message and "2: Ann Ross" in message


def test_resolve_principal_exact_name_wins_over_partial():
    # An exact full-name match is chosen even when another name also contains it.
    router = Router().add(
        "GET",
        "/api/v3/principals",
        {"_embedded": {"elements": [{"id": 1, "name": "Ann Lee"}, {"id": 2, "name": "Ann Lee Junior"}]}},
    )
    client = make_client(router)
    assert client.resolve_principal_id("Ann Lee") == "1"


def test_stream_download_writes_chunks():
    payload = b"binary-content-" * 1000
    router = Router().add_handler(
        "GET", "/api/v3/attachments/9/content", lambda _req: httpx.Response(200, content=payload)
    )
    client = make_client(router)
    dest = io.BytesIO()
    written = client.stream_download("attachments/9/content", dest)
    assert written == len(payload)
    assert dest.getvalue() == payload


def test_stream_download_error_surfaces_message():
    router = Router().add("GET", "/api/v3/attachments/9/content", {"message": "gone"}, status=404)
    client = make_client(router)
    with pytest.raises(NotFoundError):
        client.stream_download("attachments/9/content", io.BytesIO())


def test_upload_attachment_is_multipart(tmp_path):
    f = tmp_path / "report.txt"
    f.write_text("hello")

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["content_type"] = request.headers["content-type"]
        captured["body"] = request.content
        return httpx.Response(201, json={"id": 9, "fileName": "report.txt"})

    router = Router().add_handler("POST", "/api/v3/work_packages/777/attachments", handler)
    client = make_client(router)
    result = client.upload_attachment(777, str(f))
    assert result["id"] == 9
    assert captured["content_type"].startswith("multipart/form-data")
    assert b"metadata" in captured["body"]
    assert b"hello" in captured["body"]


def test_delete_sends_content_type_header():
    # OpenProject returns HTTP 406 for a DELETE without a Content-Type header.
    router = Router().add("DELETE", "/api/v3/work_packages/9", {}, status=204)
    client = make_client(router)
    client.delete("work_packages/9")
    assert router.last().headers["content-type"] == "application/json"


def test_download_to_path_writes_file_and_hashes(tmp_path):
    import hashlib

    router = Router().add_handler(
        "GET", "/api/v3/attachments/9/content", lambda _req: httpx.Response(200, content=b"PDFDATA")
    )
    client = make_client(router)
    dest = tmp_path / "out.pdf"
    result = client.download_to_path("attachments/9/content", str(dest))
    assert dest.read_bytes() == b"PDFDATA"
    assert result["bytes"] == 7
    assert result["sha256"] == hashlib.sha256(b"PDFDATA").hexdigest()
    # The atomic rename leaves no temporary part file behind.
    assert [p.name for p in tmp_path.iterdir()] == ["out.pdf"]


def test_download_to_path_enforces_max_bytes(tmp_path):
    from openproject_cli.errors import InputError

    router = Router().add_handler(
        "GET", "/api/v3/attachments/9/content", lambda _req: httpx.Response(200, content=b"0123456789")
    )
    client = make_client(router)
    dest = tmp_path / "out.bin"
    with pytest.raises(InputError):
        client.download_to_path("attachments/9/content", str(dest), max_bytes=4, chunk_size=2)
    # On failure the destination is untouched and the temp file is cleaned up.
    assert not dest.exists()
    assert list(tmp_path.iterdir()) == []


def test_user_name_caches_lookups():
    calls = {"n": 0}

    def handler(_req):
        calls["n"] += 1
        return json_response({"id": 7, "name": "Alice Example"})

    router = Router().add_handler("GET", "/api/v3/users/7", handler)
    client = make_client(router)
    assert client.user_name(7) == "Alice Example"
    assert client.user_name(7) == "Alice Example"
    assert calls["n"] == 1


def test_user_name_caches_missing_user():
    router = Router().add("GET", "/api/v3/users/7", {"message": "not found"}, status=404)
    client = make_client(router)
    assert client.user_name(7) is None
    # A failed lookup is cached, so no second request is made.
    assert client.user_name(7) is None
    assert len(router.requests) == 1


def test_custom_fields_resolves_names_via_schema():
    schema = {"_type": "Schema", "customField1": {"name": "Severity"}}
    router = Router().add("GET", "/api/v3/work_packages/schemas/1-7", schema)
    client = make_client(router)
    payload = {
        "id": 1,
        "customField1": "High",
        "_links": {"schema": {"href": "/api/v3/work_packages/schemas/1-7"}},
    }
    assert client.custom_fields(payload) == [{"key": "customField1", "name": "Severity", "value": "High"}]


def test_custom_fields_empty_makes_no_request():
    router = Router()
    client = make_client(router)
    payload = {"id": 1, "_links": {"schema": {"href": "/api/v3/work_packages/schemas/1-7"}}}
    assert client.custom_fields(payload) == []
    assert router.requests == []


def test_collect_walks_all_pages():
    page1 = {"total": 3, "_embedded": {"elements": [{"id": 1}, {"id": 2}]}}
    page2 = {"total": 3, "_embedded": {"elements": [{"id": 3}]}}

    def handler(req):
        return json_response(page1 if req.url.params.get("offset") == "1" else page2)

    router = Router().add_handler("GET", "/api/v3/statuses", handler)
    client = make_client(router)
    assert [e["id"] for e in client.collect("statuses", page_size=2)] == [1, 2, 3]
    assert len(router.requests) == 2  # two pages fetched


def test_request_retries_idempotent_on_5xx(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("openproject_cli.client.time.sleep", lambda s: sleeps.append(s))
    calls = {"n": 0}

    def handler(_req):
        calls["n"] += 1
        if calls["n"] < 3:
            return json_response({"message": "busy"}, status=503)
        return json_response({"id": 1})

    router = Router().add_handler("GET", "/api/v3/work_packages/1", handler)
    client = make_client(router)
    assert client.get_json("work_packages/1") == {"id": 1}
    assert calls["n"] == 3
    assert len(sleeps) == 2  # two retries before success


def test_request_does_not_retry_post(monkeypatch):
    monkeypatch.setattr("openproject_cli.client.time.sleep", lambda _s: None)
    calls = {"n": 0}

    def handler(_req):
        calls["n"] += 1
        return json_response({"message": "busy"}, status=503)

    router = Router().add_handler("POST", "/api/v3/work_packages", handler)
    client = make_client(router)
    with pytest.raises(ApiError):
        client.request("POST", "work_packages", json_body={})
    assert calls["n"] == 1  # POST is never replayed


def test_request_honours_retry_after(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("openproject_cli.client.time.sleep", lambda s: sleeps.append(s))
    calls = {"n": 0}

    def handler(_req):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "7"}, json={"message": "slow down"})
        return json_response({"id": 1})

    router = Router().add_handler("GET", "/api/v3/work_packages/1", handler)
    client = make_client(router)
    assert client.get_json("work_packages/1") == {"id": 1}
    assert sleeps == [7.0]


def test_request_exhausts_retries_and_raises(monkeypatch):
    monkeypatch.setattr("openproject_cli.client.time.sleep", lambda _s: None)
    router = Router().add("GET", "/api/v3/work_packages/1", {"message": "down"}, status=503)
    client = make_client(router)
    with pytest.raises(ApiError):
        client.get_json("work_packages/1")
    assert len(router.requests) == 4  # initial attempt + 3 default retries


def test_absolute_url_to_other_host_is_refused():
    from openproject_cli.errors import InputError

    router = Router()
    client = make_client(router)
    with pytest.raises(InputError):
        client.request("GET", "https://evil.test/api/v3/work_packages/1")
    assert router.requests == []  # nothing was sent


def test_absolute_url_to_same_host_is_allowed():
    router = Router().add("GET", "/api/v3/work_packages/1", {"id": 1})
    client = make_client(router)
    assert client.request("GET", "https://op.test/api/v3/work_packages/1").json() == {"id": 1}


def test_http_base_url_warns(capsys):
    from openproject_cli.client import Client
    from openproject_cli.config import Config

    router = Router()
    Client(Config(base_url="http://op.test", token="T"), transport=httpx.MockTransport(router))
    assert "plaintext HTTP" in capsys.readouterr().err


def test_redirect_is_not_followed():
    # A redirect must surface as an error rather than be followed: following it
    # could replay the Basic-auth token to the (attacker-influenced) target.
    router = Router().add_handler(
        "GET",
        "/api/v3/work_packages/1",
        lambda _req: httpx.Response(302, headers={"Location": "https://evil.test/x"}),
    )
    client = make_client(router)
    with pytest.raises(ApiError) as excinfo:
        client.get_json("work_packages/1")
    assert excinfo.value.status == 302
    assert all("evil.test" not in str(r.url) for r in router.requests)  # target never contacted


def test_retry_after_is_capped(monkeypatch):
    # A far-future / huge Retry-After must not hang the CLI: the sleep is capped.
    from openproject_cli.client import MAX_RETRY_SLEEP

    sleeps: list[float] = []
    monkeypatch.setattr("openproject_cli.client.time.sleep", lambda s: sleeps.append(s))
    calls = {"n": 0}

    def handler(_req):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "100000"}, json={"message": "slow"})
        return json_response({"id": 1})

    router = Router().add_handler("GET", "/api/v3/work_packages/1", handler)
    client = make_client(router)
    assert client.get_json("work_packages/1") == {"id": 1}
    assert sleeps == [MAX_RETRY_SLEEP]


def test_collect_tolerates_null_embedded():
    # An ``_embedded``/``total`` present but explicitly null must not crash.
    router = Router().add("GET", "/api/v3/statuses", {"_embedded": None, "total": None})
    client = make_client(router)
    assert client.collect("statuses") == []
