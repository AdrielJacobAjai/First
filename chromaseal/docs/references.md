# ChromaSeal: References and Sources (SIH submission)

**Link status key.** ✅ = confirmed by web search (title, authors and URL returned). 📦 = official address taken from the package's own metadata installed in the project. 🔎 = standard address from memory; **I could not open it from my environment (network blocked), so click it once before you submit.**
Licences marked 📦 were read from the installed packages.

---

## A. Compact list for the slide (10 lines)

1. Flask (web framework), BSD-3: https://github.com/pallets/flask
2. OpenCV (image processing), Apache-2.0: https://opencv.org/
3. NumPy (least-squares fitting), BSD-3: https://numpy.org/
4. scikit-image (CIELAB, CIEDE2000), BSD-3: https://scikit-image.org/
5. SQLite (record storage), public domain: https://www.sqlite.org/
6. ReportLab (PDF reports), BSD: https://www.reportlab.com/
7. Python `hashlib` / `hmac` (SHA-256 hash chain), PSF: https://docs.python.org/3/library/hashlib.html
8. Sharma, Wu, Dalal (2005), CIEDE2000 implementation notes: https://doi.org/10.1002/col.20070
9. Philp & Fu (2018), review of chemical spot tests: https://doi.org/10.1002/dta.2300
10. Quattrone Center (Univ. of Pennsylvania), field drug test study: https://www.law.upenn.edu/institutes/quattronecenter/reports/field-drug-test-study/

---

## B. Problem context: why presumptive colour tests need help

| Source | Used for | Status |
|---|---|---|
| Philp M, Fu S. *A review of chemical "spot" tests: A presumptive illicit drug identification technique.* Drug Testing and Analysis 10(1):95-108, 2018. DOI 10.1002/dta.2300. https://analyticalsciencejournals.onlinelibrary.wiley.com/doi/10.1002/dta.2300 (PubMed 28915346: https://pubmed.ncbi.nlm.nih.gov/28915346/) | How colour spot tests work; concerns about selectivity; digital image colour analysis as a direction | ✅ |
| Elkins KM, Weghorst AC, Quinn AA, Acharya S. *Colour quantitation for chemical spot tests for a controlled substances presumptive test database.* Drug Testing and Analysis 9, 2016. https://onlinelibrary.wiley.com/doi/full/10.1002/dta.1949 | **Prior art:** quantifying spot-test colours as RGB with phone apps; database of 3,300+ results | ✅ |
| Quattrone Center for the Fair Administration of Justice, Univ. of Pennsylvania Carey Law School. *Field Drug Test Study* and policy briefing. https://www.law.upenn.edu/institutes/quattronecenter/reports/field-drug-test-study/ and https://www.law.upenn.edu/live/files/12889-fdt-policy-considerations-presumptive-field-test | Field kits produce false positives; study estimates about 30,000 false-positive arrests a year in the US; kits are not designed to give conclusive evidence | ✅ |
| Reason Foundation backgrounder, *Colorimetric field drug tests are unreliable, lead to wrongful arrests and convictions.* https://reason.org/backgrounder/colorimetric-field-drug-tests-are-unreliable-lead-to-wrongful-arrests-and-convictions/ | Secondary summary of error rates | ✅ (found in search) |
| Overview of forensic drug testing methods, Harm Reduction Journal (2017). https://link.springer.com/article/10.1186/s12954-017-0179-5 | Background on drug-testing methods | ✅ (found in search; not read in full) |
| Smart India Hackathon, problem statement SIH26231. https://www.sih.gov.in/ | Problem statement source | 🔎 |

**Important about the "15-38% false-positive" figure in the brief.** The brief gave no citation. In search summaries I saw: an audit by Savannah PD (2018) reporting about 15.4%; Colorado corrections reporting about 33%; and error rates "as high as 38% in some contexts". I could not confirm the exact wording or the primary source of "15-38%". **Cite the Quattrone Center report and check the exact numbers in it before quoting a range on a slide.**

---

## C. Open-source software used

| Library | Used for | Licence | Link | Status |
|---|---|---|---|---|
| Flask 3.1 | Web application, routing, sessions | BSD-3-Clause | https://github.com/pallets/flask/ , docs https://flask.palletsprojects.com/ | 📦 (docs 🔎) |
| Werkzeug 3.1 | Password hashing (PBKDF2-SHA256), WSGI | BSD-3-Clause | https://github.com/pallets/werkzeug/ | 📦 |
| Jinja2 3.1 | HTML templates | BSD-3-Clause | https://github.com/pallets/jinja/ | 📦 |
| Click 8.5 | Command-line accounts (`create-user`) | BSD-3-Clause | https://github.com/pallets/click/ | 📦 |
| OpenCV (opencv-python-headless) | Blur/glare gate, card detection, homography, image warping | Apache-2.0 | https://github.com/opencv/opencv-python , https://opencv.org/ | 📦 |
| NumPy 2.4 | Linear algebra, least-squares colour matrix | BSD-3-Clause | https://numpy.org/ | 📦 |
| scikit-image 0.26 | sRGB to CIELAB, CIEDE2000 colour difference | BSD-3-Clause | https://scikit-image.org/ | 📦 |
| Pillow | Image support library (dependency) | MIT-CMU (HPND) | https://python-pillow.org/ | 📦 |
| SQLite (Python `sqlite3`) | Records, users, login audit | Public domain | https://www.sqlite.org/ | 🔎 |
| ReportLab 5.0 | PDF report generation | BSD | https://www.reportlab.com/opensource/ | 📦 |
| pytest 9.1 | Automated tests | MIT | https://docs.pytest.org/ | 📦 |
| Playwright for Python | Browser testing of the web pages (development only) | Apache-2.0 | https://playwright.dev/python/ | 📦 |
| python-pptx 1.0 | Generating the editable Technical Approach slide (development only) | MIT | https://github.com/scanny/python-pptx | 📦 |
| Cloudflare Tunnel (`cloudflared`) | Temporary HTTPS address so a phone can use the camera and GPS | Apache-2.0 | https://github.com/cloudflare/cloudflared , https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/ | 🔎 |
| Python standard library: `hashlib`, `hmac`, `secrets`, `sqlite3`, `json` | SHA-256, constant-time CSRF compare, session secret | PSF | https://docs.python.org/3/library/hashlib.html | 🔎 |

Papers to cite for the libraries (from memory, 🔎): Bradski G., *The OpenCV Library*, Dr. Dobb's Journal of Software Tools, 2000. Harris C.R. et al., *Array programming with NumPy*, Nature 585:357-362, 2020 (doi 10.1038/s41586-020-2649-2). van der Walt S. et al., *scikit-image: image processing in Python*, PeerJ 2:e453, 2014 (doi 10.7717/peerj.453).

---

## D. Methods and standards behind each stage

| Stage | Method | Source | Status |
|---|---|---|---|
| Colour difference | CIEDE2000 | Sharma G, Wu W, Dalal EN. *The CIEDE2000 color-difference formula: Implementation notes, supplementary test data, and mathematical observations.* Color Research & Application 30(1):21-30, 2005. https://doi.org/10.1002/col.20070 ; author page https://www.ece.rochester.edu/~gsharma/ciede2000/ | ✅ |
| Colour difference | CIE 142-2001, *Improvement to industrial colour-difference evaluation* (CIE Publication) | CIE (cie.co.at) | 🔎 |
| Colour space | sRGB transfer function (linearisation), IEC 61966-2-1:1999 | https://www.w3.org/Graphics/Color/sRGB.html | 🔎 |
| Colour space | CIE 1976 L\*a\*b\* (CIELAB) | CIE 15: *Colorimetry* | 🔎 |
| Blur detection | Variance of the Laplacian | Pech-Pacheco JL et al., *Diatom autofocusing in brightfield microscopy: a comparative study*, Proc. 15th ICPR, 2000 (doi 10.1109/ICPR.2000.903548); tutorial https://pyimagesearch.com/2015/09/07/blur-detection-with-opencv/ | 🔎 |
| Colour reference card | Reference-chart colour calibration | McCamy CS, Marcus H, Davidson JG. *A color-rendition chart.* J. Applied Photographic Engineering 2(3):95-99, 1976 | 🔎 |
| Colour correction | Linear least-squares fit (NumPy `linalg.lstsq`) | https://numpy.org/doc/stable/reference/generated/numpy.linalg.lstsq.html | 🔎 |
| Card detection | Mean-shift filtering | Comaniciu D, Meer P. *Mean shift: a robust approach toward feature space analysis.* IEEE TPAMI 24(5):603-619, 2002 | 🔎 |
| Card detection | RANSAC line fitting | Fischler MA, Bolles RC. *Random sample consensus.* Comm. ACM 24(6):381-395, 1981 | 🔎 |
| Card straightening | Homography estimation | Hartley R, Zisserman A. *Multiple View Geometry in Computer Vision*, 2nd ed., Cambridge Univ. Press, 2004; OpenCV tutorial https://docs.opencv.org/4.x/d9/dab/tutorial_homography.html | 🔎 |
| Edge detection (contour method) | Canny | Canny J. *A computational approach to edge detection.* IEEE TPAMI 8(6):679-698, 1986 | 🔎 |
| Tamper evidence | SHA-256 | NIST FIPS 180-4, *Secure Hash Standard.* https://csrc.nist.gov/pubs/fips/180-4/upd1/final | 🔎 |
| Tamper evidence | Hash-chained audit logs | Schneier B, Kelsey J. *Secure audit logs to support computer forensics.* ACM TISSEC 2(2):159-176, 1999. https://dl.acm.org/doi/10.1145/317087.317089 | ✅ |
| Passwords | PBKDF2 | RFC 8018, *PKCS #5: Password-Based Cryptography Specification v2.1.* https://www.rfc-editor.org/rfc/rfc8018 ; OWASP Password Storage Cheat Sheet https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html | 🔎 |
| Web security | CSRF protection | OWASP CSRF Prevention Cheat Sheet https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html | 🔎 |
| Browser features | Camera and GPS need a secure context (HTTPS) | MDN: https://developer.mozilla.org/en-US/docs/Web/Security/Secure_Contexts , https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia , https://developer.mozilla.org/en-US/docs/Web/API/Geolocation_API | 🔎 |

---

## E. Development tools to acknowledge

- **Claude Code (Anthropic)** was used as an AI coding assistant to help build this prototype: https://claude.com/claude-code . If the SIH rules ask you to disclose AI-tool use, list it.

## F. What is *not* sourced

- The stored patch colours, the decision thresholds (20 ΔE distance, 5 ΔE margin, 5 ΔE fit residual, blur threshold 100) and the reagent reference colours are **placeholders set by us**, not taken from a publication. Do not present them as published values.
- No accuracy figure for ChromaSeal has been measured on real test data; none is claimed.
