"""Officer accounts, login, roles, CSRF protection and login audit.

Uses only Flask sessions (signed cookie) and werkzeug password hashing, so no new dependencies.
Roles: 'officer' sees and creates their own tests; 'admin' sees everything and manages accounts.
The operator ID stored (and sealed) in every record is the logged-in username, never typed input.
"""
import functools
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

import click
from flask import abort, flash, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import db

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
MIN_PASSWORD = 10
MAX_FAILURES = 5
LOCKOUT_MINUTES = 10
SESSION_MINUTES = 30
PUBLIC_ENDPOINTS = {"login", "static", "favicon"}
# Card calibration is required once per sign-in before running tests (any signed-in user may do it).
# Set CHROMASEAL_CAL_EACH_LOGIN=0 to turn the requirement off.
CAL_EACH_LOGIN = os.environ.get("CHROMASEAL_CAL_EACH_LOGIN", "1") != "0"
NEEDS_CALIBRATION = {"capture", "analyze_route"}
_DUMMY_HASH = generate_password_hash("dummy-password-for-timing", method="pbkdf2:sha256")


def _hash(password):
    return generate_password_hash(password, method="pbkdf2:sha256")


def secret_key(base_dir):
    """CHROMASEAL_SECRET if set, else a random key persisted in instance/secret_key."""
    env = os.environ.get("CHROMASEAL_SECRET")
    if env:
        return env
    folder = os.path.join(base_dir, "instance")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "secret_key")
    if not os.path.exists(path):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(secrets.token_hex(32))
    with open(path) as fh:
        return fh.read().strip()


def password_problem(password, username=""):
    if len(password) < MIN_PASSWORD:
        return f"Password must be at least {MIN_PASSWORD} characters."
    if username and username.lower() in password.lower():
        return "Password must not contain the username."
    if password.isdigit() or password.isalpha():
        return "Use a mix of letters and numbers (or symbols)."
    return None


def _safe_next(target):
    return target if target and target.startswith("/") and not target.startswith("//") else None


def _csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def admin_required(view):
    @functools.wraps(view)
    def wrapped(*a, **kw):
        if g.user is None or g.user["role"] != "admin":
            abort(403)
        return view(*a, **kw)
    return wrapped


def can_access(fields):
    """Admins see every record; officers only their own."""
    return g.user["role"] == "admin" or fields["operator_id"] == g.user["username"]


def register(app):
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("CHROMASEAL_HTTPS") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=SESSION_MINUTES),
    )

    @app.context_processor
    def inject_auth():
        return {"current_user": getattr(g, "user", None), "csrf_token": _csrf_token}

    @app.before_request
    def load_user_and_guard():
        g.user = None
        uid = session.get("uid")
        if uid is not None:
            user = db.get_user(user_id=uid)
            if user and user["active"]:
                g.user = user
            else:
                session.clear()   # deactivated or deleted: kill the session immediately

        if request.method == "POST":   # CSRF: token from form field or header
            sent = request.form.get("_csrf") or request.headers.get("X-CSRF-Token") or ""
            if not hmac.compare_digest(sent, session.get("csrf", "")):
                if request.endpoint == "analyze_route":
                    return jsonify(error="Session expired — reload the page."), 400
                abort(400, "Invalid or missing CSRF token. Reload the page and try again.")

        if request.endpoint in PUBLIC_ENDPOINTS or request.endpoint is None:
            return None
        if g.user is None:
            if request.endpoint == "analyze_route":
                return jsonify(error="Please sign in again."), 401
            return redirect(url_for("login", next=request.full_path.rstrip("?")))
        if g.user["must_change"] and request.endpoint not in ("change_password", "logout"):
            return redirect(url_for("change_password"))
        if request.endpoint in NEEDS_CALIBRATION and not session.get("cal_ok"):
            if request.endpoint == "analyze_route":
                return jsonify(error="Calibrate the reference card first (Calibration page)."), 409
            flash("Please calibrate the reference card before testing.")
            return redirect(url_for("calibration"))
        return None

    @app.after_request
    def no_store(resp):
        if resp.mimetype in ("text/html", "application/pdf") or resp.mimetype.startswith("image/"):
            resp.headers["Cache-Control"] = "no-store"
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        return resp

    # --- login / logout ----------------------------------------------------
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if g.user:
            return redirect(url_for("capture"))
        error = None
        if request.method == "POST":
            username = request.form.get("username", "").strip()[:64]
            password = request.form.get("password", "")
            ip = request.remote_addr
            since = (datetime.now(timezone.utc) - timedelta(minutes=LOCKOUT_MINUTES)).strftime("%Y-%m-%dT%H:%M:%SZ")
            user = db.get_user(username=username)
            if db.recent_failures(username, since) >= MAX_FAILURES:
                db.log_login_event(username, False, ip, "locked out")
                error = f"Too many failed attempts. Try again in {LOCKOUT_MINUTES} minutes."
            else:
                ok = check_password_hash(user["password_hash"] if user else _DUMMY_HASH, password)
                if user and ok and user["active"]:
                    db.log_login_event(user["username"], True, ip)
                    session.clear()                      # new session on login (no fixation)
                    session.permanent = True
                    session["uid"] = user["id"]
                    session["cal_ok"] = not CAL_EACH_LOGIN        # must calibrate the card once per sign-in
                    _csrf_token()
                    return redirect(_safe_next(request.args.get("next")) or url_for("capture"))
                db.log_login_event(username, False, ip, "inactive account" if user and ok else "bad credentials")
                error = "Incorrect username or password."
        return render_template("login.html", error=error, no_users=not db.list_users()), (401 if error else 200)

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/account/password", methods=["GET", "POST"])
    def change_password():
        error = None
        if request.method == "POST":
            cur, new, again = (request.form.get(k, "") for k in ("current", "new", "again"))
            if not check_password_hash(g.user["password_hash"], cur):
                error = "Current password is incorrect."
            elif new != again:
                error = "The new passwords don't match."
            elif new == cur:
                error = "Choose a password different from the current one."
            else:
                error = password_problem(new, g.user["username"])
            if not error:
                db.update_user(g.user["id"], password_hash=_hash(new), must_change=0)
                flash("Password changed.")
                return redirect(url_for("capture"))
        return render_template("account_password.html", error=error), (400 if error else 200)

    # --- admin: manage officers --------------------------------------------
    @app.route("/admin/users", methods=["GET", "POST"])
    @admin_required
    def admin_users():
        error = None
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            name = request.form.get("display_name", "").strip()[:80]
            role = request.form.get("role", "officer")
            temp = request.form.get("password", "")
            if not USERNAME_RE.match(username):
                error = "Username: 3–32 letters, digits, dot, dash or underscore."
            elif not name or role not in ("officer", "admin"):
                error = "Name and a valid role are required."
            elif db.get_user(username=username):
                error = "That username already exists."
            else:
                error = password_problem(temp, username)
            if not error:
                db.create_user(username, name, _hash(temp), role, must_change=True)
                flash(f"Created {username}. They must change the temporary password at first sign-in.")
                return redirect(url_for("admin_users"))
        return render_template("admin_users.html", users=db.list_users(),
                               events=db.list_login_events(30), error=error)

    @app.post("/admin/users/<int:user_id>/<action>")
    @admin_required
    def admin_user_action(user_id, action):
        user = db.get_user(user_id=user_id)
        if user is None:
            abort(404)
        if action in ("deactivate", "demote") and user["id"] == g.user["id"]:
            flash("You can't do that to your own account.")
        elif action == "deactivate":
            if user["role"] == "admin" and db.count_active_admins() <= 1:
                flash("Can't deactivate the last active admin.")
            else:
                db.update_user(user_id, active=0)
                flash(f"{user['username']} deactivated.")
        elif action == "activate":
            db.update_user(user_id, active=1)
            flash(f"{user['username']} reactivated.")
        elif action == "reset":
            temp = request.form.get("password", "")
            problem = password_problem(temp, user["username"])
            if problem:
                flash(problem)
            else:
                db.update_user(user_id, password_hash=_hash(temp), must_change=1)
                flash(f"Password reset for {user['username']}; they must change it at next sign-in.")
        else:
            abort(404)
        return redirect(url_for("admin_users"))

    # --- command line: create the first accounts ---------------------------
    @app.cli.command("create-user")
    @click.argument("username")
    @click.option("--name", default=None, help="Display name (defaults to the username)")
    @click.option("--role", type=click.Choice(["officer", "admin"]), default="officer")
    @click.password_option()
    def create_user_cmd(username, name, role, password):
        """Create an account, e.g.  flask --app app create-user admin --role admin"""
        if not USERNAME_RE.match(username):
            raise click.ClickException("Username: 3-32 letters, digits, dot, dash or underscore.")
        if db.get_user(username=username):
            raise click.ClickException("That username already exists.")
        problem = password_problem(password, username)
        if problem:
            raise click.ClickException(problem)
        db.create_user(username, name or username, _hash(password), role, must_change=False)
        click.echo(f"Created {role} '{username}'.")

    @app.cli.command("seed-demo")
    def seed_demo_cmd():
        """Create a demo admin and officer with random passwords (printed once)."""
        for username, role in (("admin", "admin"), ("officer1", "officer")):
            if db.get_user(username=username):
                click.echo(f"{username} already exists — skipped.")
                continue
            pw = secrets.token_urlsafe(9) + "7a"
            db.create_user(username, username.title(), _hash(pw), role, must_change=False)
            click.echo(f"{role:8} {username:10} password: {pw}")
        click.echo("Store these now; they are not shown again.")
