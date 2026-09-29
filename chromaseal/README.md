# ChromaSeal — digital companion for field colorimetric drug tests

Prototype for SIH26231. The officer photographs the reacted strip in the slot of a printed
reference card; the app checks photo quality, corrects for lighting using the card, classifies the
colour (**Positive / Negative / Inconclusive**, or **Invalid Capture**), and seals the result in a
hash-chained log.

> **Every result is presumptive only.** ChromaSeal removes human-reading and lighting error. It
> does not fix chemical cross-reactivity and is not a laboratory replacement.

**No real drugs or reagents, ever.** Testing and demos use printed mock swatches only.

## Accounts and login

Every page needs a signed-in officer. The operator ID on each record (and in the sealed hash) is
the logged-in username; it cannot be typed. Roles: **officer** (runs tests, sees only their own
records, logs and PDFs) and **admin** (sees everything, manages accounts at `/admin/users`, sees
sign-in activity, and is the only role that can use the tamper demo).

Create the first accounts on the server (there is deliberately no default password):

```
flask --app app create-user admin --role admin          # prompts for a password
flask --app app create-user 4521 --name "A. Kumar"      # an officer
flask --app app seed-demo                               # demo only: admin + officer1, random passwords printed once
```

Security behaviour: passwords stored hashed (PBKDF2-SHA256), min 10 chars; 5 failed sign-ins lock
that ID for 10 minutes; sessions expire after 30 minutes idle; CSRF token on every POST; new
accounts and admin resets force a password change at next sign-in; deactivating an account ends its
live session immediately. The session secret is read from `CHROMASEAL_SECRET`, or generated into
`instance/secret_key` (gitignored). Set `CHROMASEAL_HTTPS=1` when served over HTTPS so the cookie is
marked Secure. Records created before accounts existed keep their old free-text operator ID and are
visible to admins only.

Not covered: two-factor sign-in, password-reset by email, per-record edit history beyond the hash chain.

## Run

```
pip install -r requirements.txt
python synth.py                                  # optional: writes demo_images/ (synthetic photos)
CHROMASEAL_DEMO=1 flask --app app run --host 0.0.0.0   # phone on same network: http://<laptop-ip>:5000
pytest
```

`CHROMASEAL_DEMO=1` enables the tamper-demo button (admins only); leave it unset otherwise. The live camera
guide and GPS need HTTPS (or localhost); without them use the photo picker, and GPS is stored as
`unavailable`.

## Records, log and PDF reports

Every test (including rejected photos) is stored in `chromaseal.db` (SQLite) with its photo in
`captures/`. Browse and filter them at `/log` (operator, outcome, date range). Each record has a
verify page (`/verify/<id>`, with Previous/Next) and a PDF report (`/report/<id>.pdf`) containing
operator, UTC time, GPS coordinates (plus a map link), distances, both images, the three hashes and
the verification result. The PDF is generated with `reportlab` (added to requirements beyond the
original brief list). Keep the printed record hash with the case file to anchor it externally.

## How it works

1. **Quality gate** (blur via Laplacian variance, glare via bright-pixel fraction) — bad photos
   are rejected before anything else.
2. **Card location** — the live camera page crops to an on-screen guide frame; uploaded files fall
   back to contour detection of the card's thick black border.
3. **Correction** — sample the six validated patches (neutrals + primaries), linearise, fit a 4×3
   affine least-squares matrix (cross-channel terms included), reject the photo if the mean
   ΔE2000 residual exceeds the threshold.
4. **Decision** — corrected strip colour (Lab) vs. both the target and unreacted colours.
5. **Seal** — SHA-256 of the photo, record hash chained to the previous record's hash.

The card ("board") is defined in `reference_card.py`: nine patches (3 neutrals, 3 primaries,
3 reagent outcomes) above a strip slot, matte paper, thick black border, aspect 1.6:1.

## Placeholders to set from real photos

`BLUR_THRESHOLD`, glare thresholds, `MAX_FIT_RESIDUAL` (`colour_pipeline.py`); `max_distance`,
`min_margin` (`kit_profiles.py`); the three reagent patch colours (`reference_card.py`). Current
values were only exercised on synthetic images from `synth.py`; no real photos have been tested.

## Known limitations

- Chemical cross-reactivity is not fixed: some legal substances give the same colour as illegal ones.
- Metamerism: printed patches can match the real reagent under one light and drift under another.
  A production version needs spectrophotometer-measured reference values from an accredited lab.
- Reagent reference colours are estimates, not lab-measured; borderline cases go to Inconclusive.
- The correction is a linear approximation; extreme lighting is rejected via the fit-residual check.
- The hash chain makes tampering **detectable, not impossible**: someone with full database access
  could edit a record and recompute later hashes. Anchoring the latest hash externally (printed on
  the report, or sent to a separate system) is a roadmap item, not built.
- Verification recomputes the previous record's hash from its current contents, so an edit shows
  as `record_intact: FAIL` on that record and `chain_linked: FAIL` on the next one only.

## Layout

`app.py` routes · `colour_pipeline.py` · `reference_card.py` · `kit_profiles.py` · `hashing.py` ·
`db.py` · `synth.py` synthetic test photos · `test_*.py` pytest suite.
