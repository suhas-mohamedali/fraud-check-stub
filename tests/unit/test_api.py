"""Endpoint tests through FastAPI's in-process TestClient."""
import pytest
from fastapi.testclient import TestClient

import main
from tests.conftest import make_payments


@pytest.fixture
def client():
    return TestClient(main.app)


def check(client, file_name, payments):
    r = client.post("/api/prm/check", json={"fileName": file_name, "payments": payments})
    assert r.status_code == 200, r.text
    return r.json()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "UP", "rejectCapPercent": 5.0}


def test_response_shape(client):
    body = check(client, "test.bpy", make_payments(1))
    assert body == {
        "fileName": "test.bpy",
        "totalPayments": 1,
        "rejectedPayments": 0,
        "maxRejectionsAllowed": 0,
        "rejectionPercent": 0.0,
        "results": [{
            "lineNumber": 2, "bsbNumber": "062-000", "accountNumber": "10000000",
            "amountCents": 1000, "prmStatus": "A", "reason": None,
        }],
    }


def test_results_follow_request_order(client):
    ps = make_payments(50)
    body = check(client, "order.bpy", ps)
    assert [r["lineNumber"] for r in body["results"]] == [p["lineNumber"] for p in ps]


def test_summary_counts_match_results(client):
    body = check(client, "big.bpy", make_payments(400))
    declined = [r for r in body["results"] if r["prmStatus"] == "D"]
    assert body["totalPayments"] == 400
    assert body["maxRejectionsAllowed"] == 20
    assert body["rejectedPayments"] == len(declined) <= 20
    assert body["rejectionPercent"] == round(100 * len(declined) / 400, 2)
    assert all(r["reason"] for r in declined)
    assert all(r["reason"] is None for r in body["results"] if r["prmStatus"] == "A")


def test_unknown_payment_fields_are_accepted(client):
    ps = make_payments(1)
    ps[0]["somethingNew"] = "x"
    check(client, "extra.bpy", ps)


def test_missing_payments_defaults_to_empty(client):
    r = client.post("/api/prm/check", json={"fileName": "none.bpy"})
    assert r.status_code == 200
    assert r.json()["totalPayments"] == 0
    assert r.json()["rejectionPercent"] == 0.0


def test_missing_file_name_is_rejected(client):
    r = client.post("/api/prm/check", json={"payments": []})
    assert r.status_code == 422


def test_file_summary_lists_declined_keys(client):
    body = check(client, "sum.bpy", make_payments(400))
    declined = sorted(f"L{r['lineNumber']}" for r in body["results"] if r["prmStatus"] == "D")
    r = client.get("/api/prm/files/sum.bpy")
    assert r.json() == {"fileName": "sum.bpy", "totalPayments": 400,
                        "rejectedPayments": len(declined), "rejectedKeys": declined}


def test_file_summary_for_unknown_file(client):
    r = client.get("/api/prm/files/nope.bpy")
    assert r.json()["totalPayments"] == 0
