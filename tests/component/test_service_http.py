"""Component tests: run the real uvicorn server (h11 parser, as main.py does)
and call it over a socket the way the BECS processor does."""
import http.client
import json
import socket
import threading
import time

import pytest
import uvicorn

import main
from tests.conftest import make_payments

pytestmark = pytest.mark.component


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server():
    port = _free_port()
    config = uvicorn.Config(main.app, host="127.0.0.1", port=port, http="h11", log_level="warning")
    srv = uvicorn.Server(config)
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    deadline = time.time() + 10
    while not srv.started:
        if time.time() > deadline:
            raise RuntimeError("uvicorn did not start")
        time.sleep(0.05)
    yield port
    srv.should_exit = True
    t.join(timeout=5)


def post(port, body, extra_headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    data = json.dumps(body).encode()
    headers = {"Content-Type": "application/json", "Content-Length": str(len(data))}
    headers.update(extra_headers or {})
    conn.request("POST", "/api/prm/check", body=data, headers=headers)
    resp = conn.getresponse()
    out = resp.status, json.loads(resp.read())
    conn.close()
    return out


def test_health_over_http(server):
    conn = http.client.HTTPConnection("127.0.0.1", server, timeout=10)
    conn.request("GET", "/health")
    assert conn.getresponse().status == 200


def test_java_style_h2c_upgrade_request_keeps_body(server):
    # Java's JDK HttpClient sends these headers; the body must still be read.
    status, body = post(server, {"fileName": "h2c.bpy", "payments": make_payments(3)},
                        {"Connection": "Upgrade, HTTP2-Settings", "Upgrade": "h2c",
                         "HTTP2-Settings": "AAEAAEAAAAIAAAABAAMAAABkAAQBAAAAAAUAAEAA"})
    assert status == 200, body
    assert body["totalPayments"] == 3


def test_full_becs_file_respects_cap(server):
    status, body = post(server, {"fileName": "full.bpy", "payments": make_payments(1000)})
    assert status == 200
    assert body["totalPayments"] == 1000
    assert body["rejectedPayments"] <= 50


def test_resent_file_gets_same_answer(server):
    req = {"fileName": "resend.bpy", "payments": make_payments(300)}
    _, first = post(server, req)
    _, second = post(server, req)
    assert first == second


def test_concurrent_requests_for_one_file_stay_under_cap(server):
    # 20 threads each send a different 50-payment slice of one 1000-payment file.
    errors = []

    def send(i):
        try:
            status, _ = post(server, {"fileName": "concurrent.bpy",
                                      "payments": make_payments(50, start_line=2 + i * 50)})
            assert status == 200
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=send, args=(i,)) for i in range(20)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors

    conn = http.client.HTTPConnection("127.0.0.1", server, timeout=10)
    conn.request("GET", "/api/prm/files/concurrent.bpy")
    summary = json.loads(conn.getresponse().read())
    assert summary["totalPayments"] == 1000
    assert summary["rejectedPayments"] <= 50
