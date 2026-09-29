import copy
import json

import cv2
import numpy as np
import pytest

import calibrate_card
import colour_pipeline as cp
import kit_profiles
import reference_card as card
import synth


@pytest.fixture()
def restore_card():
    saved = copy.deepcopy(card.PATCH_TRUE_SRGB)
    yield
    card.PATCH_TRUE_SRGB.clear()
    card.PATCH_TRUE_SRGB.update(saved)
    card.CALIBRATION_INFO = None


def printed_card():
    """A printer that shifts every colour differently (gamut loss), modelled on a real inkjet print:
    red goes pink, green goes teal, blacks go grey. Not a transform the lighting fit can absorb."""
    return {
        "neutral_white": (236, 236, 232), "neutral_grey": (150, 152, 150), "neutral_black": (75, 75, 78),
        "primary_red": (178, 110, 130), "primary_green": (110, 165, 140), "primary_blue": (90, 120, 190),
        "reagent_pale": (225, 225, 205), "reagent_intermediate": (135, 120, 180),
        "reagent_positive": (75, 80, 105),
    }


def test_uncalibrated_printed_card_is_rejected_then_calibration_fixes_it(tmp_path, restore_card):
    printed = printed_card()
    strip = printed["reagent_positive"]
    photo = synth.photograph(light="warm_lamp", patches=printed, strip_rgb=strip)
    assert cp.analyze(photo, kit_profiles.build_profiles()["marquis_mdma_v1"])["outcome"] == "INVALID_CAPTURE"

    paths = []
    for i, seed in enumerate((1, 2, 3)):                       # 'even daylight' calibration photos
        p = tmp_path / f"cal{i}.png"
        cv2.imwrite(str(p), synth.photograph(light="daylight", patches=printed, seed=seed))
        paths.append(str(p))
    out = tmp_path / "cal.json"
    import sys
    sys.argv = ["calibrate_card.py", *paths, "--out", str(out)]
    calibrate_card.main()
    card.load_calibration(str(out))
    profile = kit_profiles.build_profiles()["marquis_mdma_v1"]

    for light in synth.LIGHTS:
        r = cp.analyze(synth.photograph(light=light, patches=printed, strip_rgb=strip), profile)
        assert r["outcome"] == "POSITIVE", (light, r["reject_reason"])
    pale = cp.analyze(synth.photograph(light="tubelight", patches=printed, strip_rgb=printed["reagent_pale"]), profile)
    assert pale["outcome"] == "NEGATIVE"


def test_calibration_file_overrides_only_listed_patches(tmp_path, restore_card):
    f = tmp_path / "c.json"
    f.write_text(json.dumps({"created_utc": "x", "patches": {"primary_red": [10.4, 20.6, 30]}}))
    info = card.load_calibration(str(f))
    assert card.PATCH_TRUE_SRGB["primary_red"] == (10, 21, 30) and info["created_utc"] == "x"
    assert card.PATCH_TRUE_SRGB["primary_blue"] == (56, 61, 150)


def test_missing_calibration_file_is_fine(tmp_path, restore_card):
    assert card.load_calibration(str(tmp_path / "nope.json")) is None


# --- web flow ---------------------------------------------------------------
import io

from conftest import TOKEN, login


def _upload_files(paths):
    return [(io.BytesIO(open(p, "rb").read()), p.split("/")[-1]) for p in paths]


def test_officers_can_calibrate_but_only_admins_can_remove_it(env):
    alice, _ = login(env, "alice")
    assert alice.get("/calibration").status_code == 200
    assert b"Remove calibration" not in alice.get("/calibration").data
    assert alice.post("/calibration/reset", data={"_csrf": TOKEN}).status_code == 403
    assert b"calibrate_card.py" not in alice.get("/").data          # no command-line text for officers
    admin, _ = login(env, "admin1")
    assert admin.get("/calibration").status_code == 200


def test_web_calibration_then_officer_test_works_immediately(env, tmp_path):
    import kit_profiles as kp
    printed = printed_card()
    strip = printed["reagent_positive"]
    photo = synth.encode_jpeg(synth.photograph(light="warm_lamp", patches=printed, strip_rgb=strip))

    def analyse(client):
        d = {"photo": (io.BytesIO(photo), "p.jpg"), "source": "guide"}
        rid = client.post("/analyze", data=d, content_type="multipart/form-data",
                          headers={"X-CSRF-Token": TOKEN}).get_json()["record_id"]
        import db
        return db.get_record(rid)[0]["fields"]["outcome"]

    alice, _ = login(env, "alice")
    assert analyse(alice) == "INVALID_CAPTURE"                       # uncalibrated printed card

    admin, _ = login(env, "admin1")
    files = []
    for i in range(3):
        files.append((io.BytesIO(synth.encode_jpeg(synth.photograph(light="daylight", patches=printed, seed=i))), f"c{i}.jpg"))
    r = admin.post("/calibration/measure", data={"photos": files}, content_type="multipart/form-data",
                   headers={"X-CSRF-Token": TOKEN})
    assert r.status_code == 200 and b"Measured colours" in r.data
    import re
    patches = re.search(rb'name="patches" value="([^"]+)"', r.data).group(1).decode().replace("&#34;", '"')
    r = admin.post("/calibration/save", data={"_csrf": TOKEN, "patches": patches, "photos": "3", "spread": "0.5"})
    assert r.status_code == 302
    assert card.CALIBRATION_INFO["calibrated_by"] == "admin1"
    assert analyse(alice) == "POSITIVE"                              # no restart needed

    admin.post("/calibration/reset", data={"_csrf": TOKEN})
    assert card.CALIBRATION_INFO is None and analyse(alice) == "INVALID_CAPTURE"


def test_bad_calibration_photos_are_reported(env):
    admin, _ = login(env, "admin1")
    blurred = synth.encode_jpeg(synth.photograph(blur=6))
    r = admin.post("/calibration/measure", data={"photos": [(io.BytesIO(blurred), "blur.jpg")]},
                   content_type="multipart/form-data", headers={"X-CSRF-Token": TOKEN})
    assert r.status_code == 400 and b"too blurry" in r.data
    assert admin.post("/calibration/measure", data={}, content_type="multipart/form-data",
                      headers={"X-CSRF-Token": TOKEN}).status_code == 400


def test_save_rejects_garbage(env):
    admin, _ = login(env, "admin1")
    for bad in ("not json", "{}", json.dumps({n: [999, 0, 0] for n in card.PATCH_ORDER})):
        assert admin.post("/calibration/save", data={"_csrf": TOKEN, "patches": bad}).status_code == 400


def test_other_worker_calibration_is_picked_up(env, tmp_path):
    import app as app_module
    printed = printed_card()
    card.save_calibration({n: list(v) for n, v in printed.items()}, {"created_utc": "t", "calibrated_by": "x", "photos": 1})
    card._loaded_mtime = "stale"                                      # simulate: file changed by another process
    app_module._sync_card()
    assert card.PATCH_TRUE_SRGB["primary_red"] == printed["primary_red"]



def _measure_and_save(client, printed):
    files = [(io.BytesIO(synth.encode_jpeg(synth.photograph(light="daylight", patches=printed, seed=i))), f"c{i}.jpg")
             for i in range(3)]
    r = client.post("/calibration/measure", data={"photos": files}, content_type="multipart/form-data",
                    headers={"X-CSRF-Token": TOKEN})
    import re
    patches = re.search(rb'name="patches" value="([^"]+)"', r.data).group(1).decode().replace("&#34;", '"')
    return client.post("/calibration/save", data={"_csrf": TOKEN, "patches": patches, "photos": "3", "spread": "0.5"})


def test_every_login_must_calibrate_before_testing(env):
    printed = printed_card()
    photo = synth.encode_jpeg(synth.photograph(light="warm_lamp", patches=printed, strip_rgb=printed["reagent_positive"]))
    payload = lambda: {"photo": (io.BytesIO(photo), "p.jpg"), "source": "guide"}

    alice, _ = login(env, "alice", calibrated=False)
    r = alice.get("/")                                              # test page redirects to calibration
    assert r.status_code == 302 and "/calibration" in r.headers["Location"]
    r = alice.post("/analyze", data=payload(), content_type="multipart/form-data", headers={"X-CSRF-Token": TOKEN})
    assert r.status_code == 409 and b"Calibrate" in r.data
    assert alice.get("/log").status_code == 200                     # everything else stays reachable

    assert _measure_and_save(alice, printed).status_code == 302     # officer calibrates
    assert alice.get("/").status_code == 200
    r = alice.post("/analyze", data=payload(), content_type="multipart/form-data", headers={"X-CSRF-Token": TOKEN})
    assert r.status_code == 200

    alice.post("/logout", data={"_csrf": TOKEN})                    # sign in again: asked again,
    alice2, _ = login(env, "alice", calibrated=False)               # even though a calibration file exists
    assert alice2.get("/").status_code == 302
    bob, _ = login(env, "bob", calibrated=False)                    # and a different user is asked too
    assert bob.get("/").status_code == 302


def test_calibration_requirement_can_be_switched_off(monkeypatch, env):
    import auth
    monkeypatch.setattr(auth, "CAL_EACH_LOGIN", False)
    c, _ = login(env, "alice", calibrated=False)
    assert c.get("/").status_code == 200
