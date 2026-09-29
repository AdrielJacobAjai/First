"""ChromaSeal Flask app (brief section 9). Run: flask --app app run --host 0.0.0.0"""
import json
import os
import re
import uuid
from datetime import datetime, timezone

import cv2
import numpy as np
from flask import (Flask, Response, abort, flash, g, jsonify, redirect, render_template, request, send_file,
                   session, url_for)

import auth
import calibrate_card
import db
import reference_card
import hashing
import report
from colour_pipeline import analyze
import kit_profiles
from kit_profiles import DEFAULT_PROFILE, KIT_PROFILES
from reference_card import BOARD_ASPECT

BASE = os.path.dirname(os.path.abspath(__file__))
CAPTURE_DIR = os.path.join(BASE, "captures")
OUTCOMES = ["POSITIVE", "NEGATIVE", "INCONCLUSIVE", "INVALID_CAPTURE"]
MAX_UPLOAD = 48 * 1024 * 1024   # several calibration photos per request

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD
# Tamper demo is OFF unless explicitly enabled: CHROMASEAL_DEMO=1
DEMO_MODE = os.environ.get("CHROMASEAL_DEMO") == "1"

os.makedirs(CAPTURE_DIR, exist_ok=True)
db.init_db()
app.secret_key = auth.secret_key(BASE)
auth.register(app)


def _record_or_404(record_id):
    """Fetch a record the signed-in user may see (officers: own only). Others get 404, not 403."""
    rec, prev = db.get_record(record_id)
    if rec is None or not auth.can_access(rec["fields"]):
        abort(404)
    return rec, prev


def _sync_card():
    """Pick up a calibration saved by another worker/process, and refresh the kit profiles."""
    if reference_card.sync_calibration():
        KIT_PROFILES.update(kit_profiles.build_profiles())


@app.context_processor
def inject_globals():
    _sync_card()
    return {"demo_mode": DEMO_MODE, "card_cal": reference_card.CALIBRATION_INFO}


def _clean(value, limit=64):
    return re.sub(r"[^A-Za-z0-9_.\- ]", "", (value or "").strip())[:limit]


def _parse_gps(form):
    try:
        lat, lon = float(form.get("gps_lat", "")), float(form.get("gps_lon", ""))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return lat, lon, "available"
    except ValueError:
        pass
    return None, None, "unavailable"


@app.get("/")
def capture():
    return render_template("capture.html", aspect=BOARD_ASPECT)


@app.post("/analyze")
def analyze_route():
    photo = request.files.get("photo")
    operator = g.user["username"]          # locked to the login; any submitted value is ignored
    if photo is None:
        return jsonify(error="A photo is required."), 400
    raw = photo.read()
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)  # honours EXIF rotation
    if img is None:
        return jsonify(error="That file is not a readable image."), 400

    _sync_card()
    source = "guide" if request.form.get("source") == "guide" else "file"
    profile_name = request.form.get("kit_profile", DEFAULT_PROFILE)
    if profile_name not in KIT_PROFILES:
        return jsonify(error="Unknown kit profile."), 400
    result = analyze(img, KIT_PROFILES[profile_name], source)

    key = uuid.uuid4().hex
    test_id = _clean(request.form.get("test_id")) or f"T-{key[:8].upper()}"
    image_path = f"{key}.jpg"
    with open(os.path.join(CAPTURE_DIR, image_path), "wb") as f:
        f.write(raw)                                   # original bytes, hashed as-is
    if result["corrected_bgr"] is not None:
        cv2.imwrite(os.path.join(CAPTURE_DIR, f"{key}_corrected.jpg"), result["corrected_bgr"])

    lat, lon, gps_status = _parse_gps(request.form)
    rec_id = db.insert_record({
        "test_id": test_id, "operator_id": operator,
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "gps_lat": lat, "gps_lon": lon, "gps_status": gps_status,
        "kit_profile": profile_name, "outcome": result["outcome"],
        "distance_to_target": result["distance_to_target"],
        "distance_to_blank": result["distance_to_blank"],
        "margin": result["margin"], "fit_residual": result["fit_residual"],
        "reject_reason": result["reject_reason"],
        "image_path": image_path, "image_hash": hashing.hash_image(raw),
    })
    return jsonify(record_id=rec_id, redirect=url_for("result", record_id=rec_id))


@app.get("/result/<int:record_id>")
def result(record_id):
    rec, _ = _record_or_404(record_id)
    f = rec["fields"]
    corrected = os.path.exists(os.path.join(CAPTURE_DIR, f["image_path"].replace(".jpg", "_corrected.jpg")))
    return render_template("result.html", rec=rec, f=f, record_id=record_id, corrected=corrected)


@app.get("/image/<int:record_id>/<kind>")
def image(record_id, kind):
    rec, _ = _record_or_404(record_id)
    if kind not in ("raw", "corrected"):
        abort(404)
    name = rec["fields"]["image_path"]
    if kind == "corrected":
        name = name.replace(".jpg", "_corrected.jpg")
    path = os.path.join(CAPTURE_DIR, os.path.basename(name))
    if not os.path.exists(path):
        abort(404)
    return send_file(path, mimetype="image/jpeg")


def _read_image(rec):
    try:
        with open(os.path.join(CAPTURE_DIR, os.path.basename(rec["fields"]["image_path"])), "rb") as fh:
            return fh.read()
    except OSError:
        return None


@app.get("/log")
def log():
    filters = {k: request.args.get(k, "").strip() for k in ("operator", "outcome", "date_from", "date_to")}
    is_admin = g.user["role"] == "admin"
    rows = db.list_records(filters["operator"] if is_admin else None,
                           filters["outcome"] if filters["outcome"] in OUTCOMES else None,
                           filters["date_from"] or None, filters["date_to"] or None,
                           owner=None if is_admin else g.user["username"])
    status, prev = {}, hashing.GENESIS_HASH          # whole-chain check, one pass
    for rec in db.all_records_ordered():
        status[rec["id"]] = all(hashing.verify_record(rec, _read_image(rec), prev).values())
        prev = hashing.recompute_hash(rec)
    return render_template("log.html", rows=rows, filters=filters, outcomes=OUTCOMES, status=status,
                           is_admin=is_admin)


@app.get("/verify/<int:record_id>")
def verify(record_id):
    rec, prev = _record_or_404(record_id)
    checks = hashing.verify_record(rec, _read_image(rec), db.previous_hash_for(prev))
    own = None if g.user["role"] == "admin" else g.user["username"]
    before, after = db.neighbour_ids(record_id, owner=own)
    return render_template("verify.html", rec=rec, f=rec["fields"], checks=checks,
                           record_id=record_id, prev_id=prev["id"] if prev else None,
                           before=before, after=after)


@app.get("/report/<int:record_id>.pdf")
def report_pdf(record_id):
    rec, prev = _record_or_404(record_id)
    f = rec["fields"]
    checks = hashing.verify_record(rec, _read_image(rec), db.previous_hash_for(prev))
    raw = os.path.join(CAPTURE_DIR, os.path.basename(f["image_path"]))
    corrected = raw.replace(".jpg", "_corrected.jpg")
    pdf = report.build_report(
        record_id, f, {k: rec[k] for k in ("record_hash", "prev_hash", "image_hash")},
        checks, raw, corrected, prev["id"] if prev else None)
    name = f"chromaseal_{f['test_id']}.pdf"
    disp = "attachment" if request.args.get("download") else "inline"
    return Response(pdf, mimetype="application/pdf",
                    headers={"Content-Disposition": f'{disp}; filename="{name}"'})


@app.post("/tamper-demo/<int:record_id>")
def tamper_demo(record_id):
    if not DEMO_MODE:
        abort(404)
    if g.user["role"] != "admin":
        abort(403)
    if not db.tamper_field(record_id):
        abort(404)
    return redirect(url_for("verify", record_id=record_id))


# --- card calibration (admin) -----------------------------------------------
def _calibration_page(**extra):
    rows = [{"n": i + 1, "name": name, "nominal": reference_card.NOMINAL_SRGB[name],
             "current": reference_card.PATCH_TRUE_SRGB[name]}
            for i, name in enumerate(reference_card.PATCH_ORDER)]
    return render_template("admin_calibration.html", rows=rows, info=reference_card.CALIBRATION_INFO,
                           **extra)


@app.get("/calibration")
def calibration():
    return _calibration_page(preview=None)


@app.post("/calibration/measure")
def calibration_measure():
    files = [f for f in request.files.getlist("photos") if f and f.filename][:8]
    if not files:
        return _calibration_page(preview=None, error="Choose at least one photo of the empty card."), 400
    runs, notes = [], []
    for f in files:
        img = cv2.imdecode(np.frombuffer(f.read(), np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            notes.append((f.filename, "not a readable image"))
            continue
        try:
            runs.append(calibrate_card.measure_image(img))
            notes.append((f.filename, None))
        except calibrate_card.CalibrationError as e:
            notes.append((f.filename, str(e)))
    if not runs:
        return _calibration_page(preview=None, notes=notes,
                                 error="None of the photos could be used. Retake them and try again."), 400
    patches, spread = calibrate_card.combine(runs)
    preview = {"patches": patches, "photos": len(runs), "spread": spread,
               "inconsistent": len(runs) > 1 and spread > calibrate_card.MAX_SPREAD_WARNING,
               "few": len(runs) < 3, "json": json.dumps(patches)}
    return _calibration_page(preview=preview, notes=notes)


@app.post("/calibration/save")
def calibration_save():
    try:
        patches = json.loads(request.form.get("patches", ""))
        assert set(patches) == set(reference_card.PATCH_ORDER)
        patches = {k: [float(v) for v in patches[k]] for k in patches}
        assert all(len(v) == 3 and all(0 <= x <= 255 for x in v) for v in patches.values())
        n, spread = int(request.form.get("photos", "1")), float(request.form.get("spread", "0"))
    except (ValueError, AssertionError, TypeError, KeyError):
        abort(400)
    reference_card.save_calibration(patches, calibrate_card.make_meta(n, spread, g.user["username"]))
    KIT_PROFILES.update(kit_profiles.build_profiles())
    session["cal_ok"] = True                      # this sign-in has now calibrated the card
    flash("Card calibrated. You can start testing.")
    return redirect(url_for("capture"))


@app.post("/calibration/reset")
@auth.admin_required
def calibration_reset():
    reference_card.reset_calibration()
    KIT_PROFILES.update(kit_profiles.build_profiles())
    flash("Calibration removed; using the nominal card colours.")
    return redirect(url_for("calibration"))


@app.get("/favicon.ico")
def favicon():
    return "", 204


@app.get("/about")
def about():
    return render_template("about.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
