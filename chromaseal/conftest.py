import importlib

import pytest

TOKEN = "test-csrf-token"
PW = "Sup3r-secret-pw"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("CHROMASEAL_DB", str(tmp_path / "t.db"))
    monkeypatch.setenv("CHROMASEAL_DEMO", "1")
    monkeypatch.setenv("CHROMASEAL_SECRET", "test-secret")
    import db
    importlib.reload(db)
    import auth
    importlib.reload(auth)
    import app as app_module
    importlib.reload(app_module)
    app_module.CAPTURE_DIR = str(tmp_path)
    from werkzeug.security import generate_password_hash
    auth._hash = lambda pw: generate_password_hash(pw, method="pbkdf2:sha256:1000")  # fast hashes for tests only
    for name, role in (("admin1", "admin"), ("alice", "officer"), ("bob", "officer")):
        db.create_user(name, name.title(), auth._hash(PW), role)
    return app_module


def login(app_module, username, password=PW):
    c = app_module.app.test_client()
    with c.session_transaction() as s:
        s["csrf"] = TOKEN
    r = c.post("/login", data={"username": username, "password": password, "_csrf": TOKEN})
    with c.session_transaction() as s:      # login rotates the session; pin a known token for tests
        s["csrf"] = TOKEN
    return c, r
