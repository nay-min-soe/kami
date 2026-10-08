import json

import httpx
import pytest

from kami.config import LLMConfig
from kami.llm import LLMClient, LLMError, MissingAPIKey

KEY = "sk-test-0123456789"
OK_BODY = {"choices": [{"message": {"content": "hi there"}}]}


def client_with(handler, key: str = KEY) -> LLMClient:
    cfg = LLMConfig(base_url="https://llm.example/api/v1", model="x/y", api_key=key)
    return LLMClient(cfg, http=httpx.Client(transport=httpx.MockTransport(handler)))


def reply(status: int, body=None, text: str | None = None):
    def handler(_request):
        if text is not None:
            return httpx.Response(status, text=text)
        return httpx.Response(status, json=body if body is not None else {})
    return handler


def raises(exc_type):
    def handler(request):
        raise exc_type("boom", request=request)
    return handler


def test_returns_content_on_success():
    assert client_with(reply(200, OK_BODY)).ask("hello") == "hi there"


def test_sends_bearer_key_and_model():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=OK_BODY)

    client_with(handler).ask("hello")
    assert seen["auth"] == f"Bearer {KEY}"
    assert seen["body"]["model"] == "x/y"


def test_image_request_has_data_url():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=OK_BODY)

    client_with(handler).ask_about_image(b"\x89PNG", "what is this?")
    parts = seen["body"]["messages"][-1]["content"]
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_missing_key_raises_before_network():
    def handler(_request):
        raise AssertionError("no request should be sent without a key")

    with pytest.raises(MissingAPIKey) as err:
        client_with(handler, key="").ask("hello")
    assert err.value.kind == "missing_key"


@pytest.mark.parametrize("status, kind", [
    (401, "auth"), (403, "auth"), (402, "credits"), (429, "rate_limit"),
    (500, "server"), (503, "server"), (400, "request"),
])
def test_status_codes_map_to_kinds(status, kind):
    with pytest.raises(LLMError) as err:
        client_with(reply(status, {"error": {"code": status, "message": "nope"}})).ask("hi")
    assert err.value.kind == kind


def test_image_refused_maps_to_no_vision():
    body = {"error": {"code": 404, "message": "No endpoints found that support image input"}}
    with pytest.raises(LLMError) as err:
        client_with(reply(404, body)).ask_about_image(b"png", "explain")
    assert err.value.kind == "no_vision"
    assert "x/y" in str(err.value)


def test_error_inside_200_reply_is_not_success():
    body = {"error": {"code": 502, "message": "provider went away"}}
    with pytest.raises(LLMError) as err:
        client_with(reply(200, body)).ask("hi")
    assert err.value.kind == "server"


def test_timeout_maps_to_timeout():
    with pytest.raises(LLMError) as err:
        client_with(raises(httpx.ReadTimeout)).ask("hi")
    assert err.value.kind == "timeout"


def test_connect_error_maps_to_network():
    with pytest.raises(LLMError) as err:
        client_with(raises(httpx.ConnectError)).ask("hi")
    assert err.value.kind == "network"
    assert "llm.example" in str(err.value)


@pytest.mark.parametrize("handler", [reply(200, {}), reply(200, text="<html>oops</html>"),
                                     reply(200, {"choices": [{"message": {"content": None}}]})])
def test_bad_body_maps_to_bad_response(handler):
    with pytest.raises(LLMError) as err:
        client_with(handler).ask("hi")
    assert err.value.kind == "bad_response"


def test_provider_message_is_included_and_truncated():
    body = {"error": {"code": 400, "message": "A" * 1000}}
    with pytest.raises(LLMError) as err:
        client_with(reply(400, body)).ask("hi")
    detail = str(err.value).split("Provider says: ", 1)[1]
    assert 0 < len(detail) <= 200


@pytest.mark.parametrize("handler", [
    reply(401, {"error": {"code": 401, "message": f"bad key {KEY}"}}),
    reply(402, {}), reply(429, {}), reply(500, {}), reply(200, {}),
    raises(httpx.ReadTimeout), raises(httpx.ConnectError),
])
def test_error_never_contains_api_key(handler):
    with pytest.raises(LLMError) as err:
        client_with(handler).ask("hi")
    assert KEY not in str(err.value)
    assert "0123456789" not in str(err.value)


# ---------- streaming ----------

def sse(*events: str) -> bytes:
    return "".join(f"{e}\n\n" for e in events).encode()


def delta(text: str) -> str:
    return "data: " + json.dumps({"choices": [{"delta": {"content": text}}]})


def stream_reply(body: bytes, status: int = 200, seen: dict | None = None):
    def handler(request):
        if seen is not None:
            seen["body"] = json.loads(request.content)
        return httpx.Response(status, content=body,
                              headers={"content-type": "text/event-stream"})
    return handler


def collect(client: LLMClient, cancel=None, on_piece=None):
    pieces: list[str] = []

    def on_delta(piece):
        pieces.append(piece)
        if on_piece:
            on_piece(piece)

    return client.chat_stream([{"role": "user", "content": "hi"}], on_delta, cancel), pieces


def test_stream_yields_deltas_in_order():
    body = sse(delta("Hel"), delta("lo"), "data: [DONE]")
    text, pieces = collect(client_with(stream_reply(body)))
    assert pieces == ["Hel", "lo"]
    assert text == "Hello"


def test_stream_sends_stream_true():
    seen: dict = {}
    collect(client_with(stream_reply(sse(delta("x"), "data: [DONE]"), seen=seen)))
    assert seen["body"]["stream"] is True
    assert seen["body"]["model"] == "x/y"


def test_stream_skips_comments_and_blank_lines():
    body = sse(": OPENROUTER PROCESSING", delta("a"), ": OPENROUTER PROCESSING", "",
               delta("b"), "data: [DONE]")
    assert collect(client_with(stream_reply(body)))[0] == "ab"


def test_stream_skips_chunks_without_content():
    role_only = "data: " + json.dumps({"choices": [{"delta": {"role": "assistant"}}]})
    usage = "data: " + json.dumps({"choices": [], "usage": {"total_tokens": 5}})
    body = sse(role_only, delta("ok"), usage, "data: not json", "data: [DONE]")
    text, pieces = collect(client_with(stream_reply(body)))
    assert (text, pieces) == ("ok", ["ok"])


@pytest.mark.parametrize("status, kind", [(401, "auth"), (402, "credits"), (429, "rate_limit")])
def test_stream_http_error_maps_to_kind(status, kind):
    body = json.dumps({"error": {"message": "nope", "code": status}}).encode()
    with pytest.raises(LLMError) as err:
        collect(client_with(stream_reply(body, status=status)))
    assert err.value.kind == kind


def test_stream_mid_error_maps_to_server():
    mid = "data: " + json.dumps({"error": {"code": "server_error", "message": "upstream died"},
                                 "choices": [{"finish_reason": "error"}]})
    pieces: list[str] = []
    client = client_with(stream_reply(sse(delta("par"), delta("tial"), mid)))
    with pytest.raises(LLMError) as err:
        client.chat_stream([], pieces.append)
    assert err.value.kind == "server"
    assert pieces == ["par", "tial"]


def test_stream_cancel_stops_reading():
    import threading
    cancel = threading.Event()
    pieces: list[str] = []
    client = client_with(stream_reply(sse(delta("one"), delta("two"), delta("three"))))
    with pytest.raises(LLMError) as err:
        client.chat_stream([], lambda p: (pieces.append(p), cancel.set()), cancel)
    assert err.value.kind == "cancelled"
    assert pieces == ["one"]


def test_stream_empty_is_bad_response():
    with pytest.raises(LLMError) as err:
        collect(client_with(stream_reply(sse("data: [DONE]"))))
    assert err.value.kind == "bad_response"


def test_stream_connection_drop_maps_to_network():
    def handler(request):
        raise httpx.ReadError("reset", request=request)
    with pytest.raises(LLMError) as err:
        collect(client_with(handler))
    assert err.value.kind == "network"


def test_stream_missing_key_raises_before_network():
    def handler(_request):
        raise AssertionError("network must not be touched")
    with pytest.raises(MissingAPIKey):
        collect(client_with(handler, key=""))


@pytest.mark.parametrize("status", [400, 401, 500])
def test_stream_error_never_contains_api_key(status):
    body = json.dumps({"error": {"message": f"bad key {KEY} here"}}).encode()
    with pytest.raises(LLMError) as err:
        collect(client_with(stream_reply(body, status=status)))
    assert KEY not in str(err.value)
