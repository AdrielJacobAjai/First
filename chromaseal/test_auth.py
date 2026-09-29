import io

import synth
from conftest import PW, TOKEN, login


def upload(client, **extra):
    data = {"photo": (io.BytesIO(synth.encode_jpeg(synth.photograph())), "p.jpg"), "source": "guide", **extra}
    return client.post("/analyze", data=data, content_type="multipart/form-data",
                       headers={"X-CSRF-Token": TOKEN})


def test_everything_requires_login(env):
    c = env.app.test_client()
    for url in ("/", "/log", "/verify/1", "/result/1", "/report/1.pdf", "/image/1/raw", "/about", "/admin/users"):
        r = c.get(url)
        assert r.status_code == 302 and "/login" in r.headers["Location"], url
    assert c.post("/analyze").status_code in (400, 401)
    assert c.get("/login").status_code == 200
    assert c.get("/favicon.ico").status_code == 204


def test_login_good_and_bad(env):
    c, r = login(env, "alice")
    assert r.status_code == 302 and c.get("/").status_code == 200
    _, bad = login(env, "alice", "wrong-password")
    assert bad.status_code == 401 and b"Incorrect username or password" in bad.data
    _, nouser = login(env, "nobody")
    assert b"Incorrect username or password" in nouser.data            # same message: no user enumeration


def test_lockout_after_repeated_failures(env):
    for _ in range(5):
        login(env, "bob", "nope-nope-nope")
    _, r = login(env, "bob")                                            # even the right password
    assert r.status_code == 401 and b"Too many failed attempts" in r.data


def test_operator_locked_to_login(env):
    import db
    c, _ = login(env, "alice")
    rid = upload(c, operator_id="someone-else").get_json()["record_id"]
    assert db.get_record(rid)[0]["fields"]["operator_id"] == "alice"


def test_officers_only_see_their_own(env):
    alice, _ = login(env, "alice")
    bob, _ = login(env, "bob")
    admin, _ = login(env, "admin1")
    a = upload(alice).get_json()["record_id"]
    b = upload(bob).get_json()["record_id"]
    for url in (f"/result/{b}", f"/verify/{b}", f"/report/{b}.pdf", f"/image/{b}/raw"):
        assert alice.get(url).status_code == 404, url
        assert admin.get(url).status_code == 200, url
    assert alice.get(f"/result/{a}").status_code == 200
    log = alice.get("/log").data
    assert b"alice" in log and b"bob" not in log
    assert b"bob" in admin.get("/log").data
    assert b"Next" not in alice.get(f"/verify/{a}").data                # neighbour is bob's: no link


def test_csrf_required(env):
    c, _ = login(env, "alice")
    assert c.post("/logout").status_code == 400
    assert c.post("/analyze", data={}, content_type="multipart/form-data").status_code == 400
    assert c.post("/logout", data={"_csrf": TOKEN}).status_code == 302
    assert c.get("/").status_code == 302                                # signed out


def test_open_redirect_blocked(env):
    c = env.app.test_client()
    with c.session_transaction() as s:
        s["csrf"] = TOKEN
    r = c.post("/login?next=//evil.example", data={"username": "alice", "password": PW, "_csrf": TOKEN})
    assert r.headers["Location"] == "/"
    c2 = env.app.test_client()
    with c2.session_transaction() as s:
        s["csrf"] = TOKEN
    r = c2.post("/login?next=/log", data={"username": "alice", "password": PW, "_csrf": TOKEN})
    assert r.headers["Location"] == "/log"


def test_admin_only_pages(env):
    alice, _ = login(env, "alice")
    assert alice.get("/admin/users").status_code == 403
    admin, _ = login(env, "admin1")
    assert admin.get("/admin/users").status_code == 200


def test_admin_creates_officer_who_must_change_password(env):
    import db
    admin, _ = login(env, "admin1")
    r = admin.post("/admin/users", data={"_csrf": TOKEN, "username": "carol", "display_name": "Carol",
                                         "role": "officer", "password": "Temp-pass-12345"})
    assert r.status_code == 302 and db.get_user(username="carol")
    weak = admin.post("/admin/users", data={"_csrf": TOKEN, "username": "dave", "display_name": "D",
                                            "role": "officer", "password": "short"})
    assert b"at least" in weak.data and db.get_user(username="dave") is None
    carol, r = login(env, "carol", "Temp-pass-12345")
    assert carol.get("/").status_code == 302 and "/account/password" in carol.get("/").headers["Location"]
    r = carol.post("/account/password", data={"_csrf": TOKEN, "current": "Temp-pass-12345",
                                              "new": "Brand-new-pw-987", "again": "Brand-new-pw-987"})
    assert r.status_code == 302 and carol.get("/").status_code == 200
    assert login(env, "carol", "Brand-new-pw-987")[1].status_code == 302


def test_deactivation_kills_live_session_and_blocks_login(env):
    import db
    alice, _ = login(env, "alice")
    admin, _ = login(env, "admin1")
    uid = db.get_user(username="alice")["id"]
    admin.post(f"/admin/users/{uid}/deactivate", data={"_csrf": TOKEN})
    assert alice.get("/").status_code == 302                            # session dead immediately
    assert login(env, "alice")[1].status_code == 401


def test_cannot_deactivate_self_or_last_admin(env):
    import db
    admin, _ = login(env, "admin1")
    me = db.get_user(username="admin1")["id"]
    admin.post(f"/admin/users/{me}/deactivate", data={"_csrf": TOKEN})
    assert db.get_user(user_id=me)["active"] == 1


def test_passwords_are_hashed(env):
    import db
    assert PW not in db.get_user(username="alice")["password_hash"]


def test_login_events_recorded(env):
    import db
    login(env, "alice")
    login(env, "alice", "bad-password-x")
    ev = db.list_login_events()
    assert {e["success"] for e in ev} == {0, 1}
