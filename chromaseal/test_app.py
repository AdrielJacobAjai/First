import io
import os

import pytest

import synth


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CHROMASEAL_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("CHROMASEAL_DEMO", "1")
    import importlib
    import db
    importlib.reload(db)
    import app as app_module
    importlib.reload(app_module)
    app_module.CAPTURE_DIR = str(tmp_path)
    return app_module.app.test_client()


def post(client, strip="positive", light="daylight", **kw):
    data = {"photo": (io.BytesIO(synth.encode_jpeg(synth.photograph(strip, light, **kw))), "p.jpg"),
            "operator_id": "OP-7", "source": "guide"}
    return client.post("/analyze", data=data, content_type="multipart/form-data")


def test_demo_flow(client):
    ids = [post(client, "positive", "warm_lamp").get_json()["record_id"],
           post(client, "intermediate", "shade").get_json()["record_id"],
           post(client, "positive", "daylight", blur=6).get_json()["record_id"]]
    assert b"POSITIVE" in client.get(f"/result/{ids[0]}").data
    assert b"INCONCLUSIVE" in client.get(f"/result/{ids[1]}").data
    assert b"blurry" in client.get(f"/result/{ids[2]}").data
    assert b"FAILED" not in client.get("/log").data
    assert b"FAIL<" not in client.get(f"/verify/{ids[0]}").data
    client.post(f"/tamper-demo/{ids[0]}")
    assert b"FAIL<" in client.get(f"/verify/{ids[0]}").data
    assert b"FAIL<" in client.get(f"/verify/{ids[1]}").data       # link to tampered record
    assert b"FAIL<" not in client.get(f"/verify/{ids[2]}").data   # later record unaffected
    assert b"FAILED" in client.get("/log").data


def test_filters_and_validation(client):
    post(client)
    assert b"No records" in client.get("/log?outcome=NEGATIVE").data
    assert b"OP-7" in client.get("/log?operator=OP").data
    bad = client.post("/analyze", data={"operator_id": "x"}, content_type="multipart/form-data")
    assert bad.status_code == 400


def test_tamper_disabled_without_flag(client):
    import app as app_module
    app_module.DEMO_MODE = False
    rid = post(client).get_json()["record_id"]
    assert client.post(f"/tamper-demo/{rid}").status_code == 404
