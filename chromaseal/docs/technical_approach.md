# ChromaSeal: Technical Approach (text for the slide)

*Lighting-corrected reading and tamper-evident recording of field colorimetric tests · no new hardware*

**Flow:** 1 Mobile Capture → 2 Quality Gate → 3 Lighting Correction → 4 Classification → 5 Tamper-evident Sealing → 6 Log, Verify & Report

1. **Mobile Capture** (HTML/JS, Camera & GPS APIs, Flask)
   - Officer photographs the reacted strip beside a printed 9-patch reference card
   - Card: 3 greys · red, green, blue · 3 reagent colours
   - On-screen alignment guide; UTC time and GPS (if the phone allows)
   - Card calibrated at each sign-in
2. **Quality Gate** (Python, OpenCV)
   - Blur (Laplacian) and glare / overexposure checks
   - Card found from its patch row and straightened (homography)
   - Bad photo gives "Invalid Capture" with a plain retake reason
3. **Lighting Correction** (NumPy, scikit-image)
   - sRGB to linear light; median colour of each patch
   - 6 of the 9 patches (3 greys + red, green, blue) reveal what the light did
   - Least-squares colour-correction matrix: 3x3 channel mix + offset
   - Poor fit: photo rejected, never guessed
4. **Classification** (scikit-image, CIEDE2000)
   - Corrected strip colour to CIELAB
   - dE2000 distance to the Target and Unreacted colours (from the card's reagent patches)
   - Positive / Negative / Inconclusive using distance + margin rules
5. **Tamper-evident Sealing** (hashlib SHA-256, SQLite)
   - SHA-256 of the photo; each record (operator, time, GPS, result) is hash-chained to the previous one
   - Per-record check: image intact, record intact, chain linked
6. **Log, Verify & Report** (Flask, SQLite, ReportLab)
   - Searchable log by operator, outcome and date
   - Verification page per record; officers see only their own
   - PDF report with GPS, images and hashes

## Reference card: what each patch does

| Patches | Role |
|---|---|
| 1-3: white, grey, black | Lighting fit (brightness and tint) |
| 4-6: red, green, blue | Lighting fit (how one colour bleeds into another) |
| 7: pale | **Unreacted colour**: what a negative strip should look like |
| 8: intermediate purple | Visual reference for an in-between shade. Not used in the lighting fit or the Positive/Negative decision. Its brightness only helps confirm the card was found correctly, and it is measured and saved at calibration |
| 9: purple-black | **Target colour**: what a positive strip should look like |

- After the lighting is corrected, the app measures how close the strip's colour is to the Target (patch 9) and to the Unreacted colour (patch 7). That distance decides Positive, Negative or Inconclusive.
- Using patch 8 as an extra check on the correction was considered but is **not built**.

**Security:** officer / admin roles, lockout, CSRF, session timeout.
**Every result is PRESUMPTIVE:** laboratory confirmation required.
