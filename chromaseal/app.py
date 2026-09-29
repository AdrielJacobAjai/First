"""ChromaSeal Flask app (brief section 9). Run: flask --app app run --host 0.0.0.0"""
import os
import re
import uuid
from datetime import datetime, timezone

import cv2
import numpy as np
from flask import Flask, abort, jsonify, redirect, render_template, request, send_file, url_for

import db
import hashing
from colour_pipeline import analyze
from kit_profiles import DEFAULT_PROFILE, KIT_PROFILES
from reference_card import BOARD_ASPECT

BASE = os.path.dirname(os.path.abspath(__file__))
CAPTURE_DIR = os.path.join(BASE, "captures")
OUTCOMES = ["POSITIVE", "NEGATIVE", "INCONCLUSIVE", "INVALID_CAPTURE"]
MAX_UPLOAD = 15 * 1024 * 1024

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD
# Tamper demo is OFF unless explicitly enabled: CHROMASEAL_DEMO=1
DEMO_MODE = os.environ.get("CHROMASEAL_DEMO") == "1"

os.makedirs(CAPTURE_DIR, exist_ok=True)
db.init_db()


@app.context_processor
def inject_globals():
    return {"demo_mode": DEMO_MODE}


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
    operator = _clean(request.form.get("operator_id"))
    if photo is None or not operator:
        return jsonify(error="A photo and an operator ID are required."), 400
    raw = photo.read()
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)  # honours EXIF rotation
    if img is None:
        return jsonify(error="That file is not a readable image."), 400

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
    rec, _ = db.get_record(record_id)
    if rec is None:
        abort(404)
    f = rec["fields"]
    corrected = os.path.exists(os.path.join(CAPTURE_DIR, f["image_path"].replace(".jpg", "_corrected.jpg")))
    return render_template("result.html", rec=rec, f=f, record_id=record_id, corrected=corrected)


@app.get("/image/<int:record_id>/<kind>")
def image(record_id, kind):
    rec, _ = db.get_record(record_id)
    if rec is None or kind not in ("raw", "corrected"):
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
    rows = db.list_records(filters["operator"], filters["outcome"] if filters["outcome"] in OUTCOMES else None,
                           filters["date_from"] or None, filters["date_to"] or None)
    status, prev = {}, hashing.GENESIS_HASH          # whole-chain check, one pass
    for rec in db.all_records_ordered():
        status[rec["id"]] = all(hashing.verify_record(rec, _read_image(rec), prev).values())
        prev = hashing.recompute_hash(rec)
    return render_template("log.html", rows=rows, filters=filters, outcomes=OUTCOMES, status=status)


@app.get("/verify/<int:record_id>")
def verify(record_id):
    rec, prev = db.get_record(record_id)
    if rec is None:
        abort(404)
    checks = hashing.verify_record(rec, _read_image(rec), db.previous_hash_for(prev))
    return render_template("verify.html", rec=rec, f=rec["fields"], checks=checks,
                           record_id=record_id, prev_id=prev["id"] if prev else None)


@app.post("/tamper-demo/<int:record_id>")
def tamper_demo(record_id):
    if not DEMO_MODE:
        abort(404)
    if not db.tamper_field(record_id):
        abort(404)
    return redirect(url_for("verify", record_id=record_id))


@app.get("/about")
def about():
    return render_template("about.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
