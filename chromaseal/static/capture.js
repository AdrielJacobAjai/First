// Camera guide, GPS and upload. Vanilla JS.
(function () {
  const $ = (id) => document.getElementById(id);
  const form = $("form"), go = $("go"), msg = $("msg");
  let blob = null, source = "file", gps = null, stream = null;

  // --- GPS: never blocks the test; falls back to "unavailable" -------------
  if (navigator.geolocation && window.isSecureContext) {
    navigator.geolocation.getCurrentPosition(
      (p) => { gps = { lat: p.coords.latitude, lon: p.coords.longitude }; $("gps").textContent = "GPS: acquired"; },
      () => { $("gps").textContent = "GPS: unavailable (will be recorded as such)"; },
      { timeout: 8000, maximumAge: 60000 });
  } else {
    $("gps").textContent = "GPS: unavailable (needs HTTPS or localhost)";
  }

  // --- live camera with alignment guide -----------------------------------
  function layoutGuide() {
    const v = $("video"), g = $("guide");
    const vw = v.videoWidth, vh = v.videoHeight;
    if (!vw) return null;
    let w = 0.9, h = (0.9 * vw) / (window.BOARD_ASPECT * vh);
    if (h > 0.9) { h = 0.9; w = (0.9 * vh * window.BOARD_ASPECT) / vw; }
    const x = (1 - w) / 2, y = (1 - h) / 2;
    Object.assign(g.style, { left: x * 100 + "%", top: y * 100 + "%", width: w * 100 + "%", height: h * 100 + "%" });
    return { x, y, w, h };
  }

  $("retake").addEventListener("click", () => {
    blob = null; go.disabled = true; $("preview").hidden = true; $("retake").hidden = true;
    $("hint").hidden = false; msg.textContent = ""; $("cam").click();
  });

  $("cam").addEventListener("click", async () => {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      msg.textContent = "Live camera needs HTTPS or localhost. Use the photo picker below instead.";
      return;
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment", width: { ideal: 1920 } } });
    } catch (e) { msg.textContent = "Camera not available. Use the photo picker below."; return; }
    const v = $("video");
    v.srcObject = stream;
    v.addEventListener("loadedmetadata", layoutGuide);
    $("stage").hidden = false; $("snap").hidden = false; $("cam").hidden = true;
    $("snap").classList.add("highlight");
    $("snap").scrollIntoView({ block: "nearest", behavior: "smooth" });
    $("preview").hidden = true; msg.textContent = "Fit the card inside the yellow frame, then tap Take photo.";
  });

  $("snap").addEventListener("click", () => {
    const v = $("video"), r = layoutGuide();
    if (!r) { msg.textContent = "Camera is still starting — wait a moment and try again."; return; }
    const c = document.createElement("canvas");
    c.width = Math.round(r.w * v.videoWidth); c.height = Math.round(r.h * v.videoHeight);
    c.getContext("2d").drawImage(v, r.x * v.videoWidth, r.y * v.videoHeight, c.width, c.height, 0, 0, c.width, c.height);
    c.toBlob((b) => {   // cropped to the guide frame: the whole image IS the card
      blob = b; source = "guide"; go.disabled = false;
      $("previewImg").src = URL.createObjectURL(b); $("preview").hidden = false;
      $("retake").hidden = false; $("hint").hidden = true;
      msg.textContent = "Photo captured. Press Analyse.";
      go.focus();
      stream.getTracks().forEach((t) => t.stop());
      $("snap").classList.remove("highlight");
      $("stage").hidden = true; $("snap").hidden = true; $("cam").hidden = false;
    }, "image/jpeg", 0.95);
  });

  $("photo").addEventListener("change", (e) => {
    const f = e.target.files[0];
    if (f) { blob = f; source = "file"; go.disabled = false; msg.textContent = "Photo selected (card will be located automatically)."; }
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!blob) return;
    go.disabled = true; msg.textContent = "Analysing…";
    const fd = new FormData();
    fd.append("photo", blob, "capture.jpg");
    fd.append("test_id", $("test_id").value);
    fd.append("source", source);
    if (gps) { fd.append("gps_lat", gps.lat); fd.append("gps_lon", gps.lon); }
    try {
      const res = await fetch("/analyze", { method: "POST", body: fd, headers: { "X-CSRF-Token": window.CSRF } });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Upload failed");
      window.location = data.redirect;
    } catch (err) { msg.textContent = "Error: " + err.message; go.disabled = false; }
  });
})();
