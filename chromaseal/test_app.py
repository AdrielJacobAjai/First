import io

import pytest

import synth
from conftest import PW, TOKEN, login


@pytest.fixture()
def client(env):
    c, r = login(env, "alice")
    assert r.status_code == 302
    return c


def post(client, strip="positive", light="daylight", **kw):
    data = {"photo": (io.BytesIO(synth.encode_jpeg(synth.photograph(strip, light, **kw))), "p.jpg"),
            "source": "guide"}
    return client.post("/analyze", data=data, content_type="multipart/form-data",
                       headers={"X-CSRF-Token": TOKEN})


def test_demo_flow(env):
    admin, _ = login(env, "admin1")
    ids = [post(admin, "positive", "warm_lamp").get_json()["record_id"],
           post(admin, "intermediate", "shade").get_json()["record_id"],
           post(admin, "positive", "daylight", blur=6).get_json()["record_id"]]
    assert b"POSITIVE" in admin.get(f"/result/{ids[0]}").data
    assert b"INCONCLUSIVE" in admin.get(f"/result/{ids[1]}").data
    assert b"blurry" in admin.get(f"/result/{ids[2]}").data
    assert b"FAILED" not in admin.get("/log").data
    assert b"FAIL<" not in admin.get(f"/verify/{ids[0]}").data
    admin.post(f"/tamper-demo/{ids[0]}", data={"_csrf": TOKEN})
    assert b"FAIL<" in admin.get(f"/verify/{ids[0]}").data
    assert b"FAIL<" in admin.get(f"/verify/{ids[1]}").data       # link to tampered record
    assert b"FAIL<" not in admin.get(f"/verify/{ids[2]}").data   # later record unaffected
    assert b"FAILED" in admin.get("/log").data


def test_filters_and_validation(client):
    post(client)
    assert b"No records" in client.get("/log?outcome=NEGATIVE").data
    assert b"alice" in client.get("/log").data
    bad = client.post("/analyze", data={}, content_type="multipart/form-data",
                      headers={"X-CSRF-Token": TOKEN})
    assert bad.status_code == 400


def test_tamper_needs_demo_flag_and_admin(env):
    alice, _ = login(env, "alice")
    rid = post(alice).get_json()["record_id"]
    assert alice.post(f"/tamper-demo/{rid}", data={"_csrf": TOKEN}).status_code == 403
    env.DEMO_MODE = False
    admin, _ = login(env, "admin1")
    assert admin.post(f"/tamper-demo/{rid}", data={"_csrf": TOKEN}).status_code == 404


def test_pdf_report_and_navigation(client):
    a = post(client, "positive", "warm_lamp").get_json()["record_id"]
    b = post(client, "intermediate", "shade").get_json()["record_id"]
    r = client.get(f"/report/{a}.pdf")
    assert r.status_code == 200 and r.data[:5] == b"%PDF-" and r.mimetype == "application/pdf"
    assert client.get("/report/999.pdf").status_code == 404
    assert b"Next" not in client.get(f"/verify/{b}").data      # last record: no dead link
    assert b"Next" in client.get(f"/verify/{a}").data
    assert b"Previous" in client.get(f"/verify/{b}").data
    assert b"/report/" in client.get("/log").data


def test_gps_stored(client):
    import db as dbm
    data = {"photo": (io.BytesIO(synth.encode_jpeg(synth.photograph())), "p.jpg"),
            "source": "guide", "gps_lat": "12.971598", "gps_lon": "77.594562"}
    rid = client.post("/analyze", data=data, content_type="multipart/form-data",
                      headers={"X-CSRF-Token": TOKEN}).get_json()["record_id"]
    rec, _ = dbm.get_record(rid)
    assert rec["fields"]["gps_lat"] == 12.971598 and rec["fields"]["gps_status"] == "available"
    assert len(client.get(f"/report/{rid}.pdf").data) > 5000
