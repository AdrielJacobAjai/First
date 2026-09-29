# ChromaSeal: Technical Approach (text for the slide)

**Flow:** 1 Mobile Capture → 2 Quality Gate → 3 Lighting Correction → 4 Classification → 5 Tamper-evident Sealing → 6 Log, Verify & Report

1. **Mobile Capture** (HTML/JS, Camera & GPS APIs, Flask)
   - Signed-in officer photographs the reacted strip beside a printed 9-patch reference card
   - On-screen alignment guide; GPS and UTC time captured
   - No new hardware, no change to kit chemistry
2. **Quality Gate** (Python, OpenCV)
   - Blur (Laplacian) and glare / overexposure checks
   - Card found from its patch row and straightened (homography)
   - Bad photo gives "Invalid Capture" with a plain retake reason
3. **Lighting Correction** (NumPy, scikit-image)
   - sRGB to linear; median of each reference patch
   - 4x3 least-squares colour matrix fitted on 6 reference patches
   - Poor fit: photo rejected, never guessed
   - Card calibrated at each sign-in
4. **Classification** (scikit-image, CIEDE2000)
   - Corrected strip colour to CIELAB
   - dE2000 distance to Target and Unreacted (Blank) colours
   - Positive / Negative / Inconclusive using distance + margin rules
5. **Tamper-evident Sealing** (hashlib SHA-256, SQLite)
   - SHA-256 of the photo; each record (operator, time, GPS, result) is hash-chained to the previous one
   - Per-record check: image intact, record intact, chain linked
6. **Log, Verify & Report** (Flask, SQLite, ReportLab)
   - Searchable log by operator, outcome and date
   - Verification page per record; officers see only their own
   - PDF report with GPS, images and hashes

**Security:** officer / admin roles, lockout, CSRF, session timeout.
**Every result is PRESUMPTIVE:** laboratory confirmation required.
