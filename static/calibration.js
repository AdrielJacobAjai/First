// Shrinks calibration photos on the phone before upload (fast on slow connections) and shows progress.
// Calibration only needs patch colours, so a 1600px image is plenty. Falls back to a normal form post.
(function () {
  const form = document.getElementById("measureForm");
  if (!form || !window.createImageBitmap || !window.fetch) return;
  const status = document.getElementById("measureStatus"), btn = document.getElementById("measureBtn");
  const MAX = 1600;

  async function shrink(file) {
    const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
    const s = Math.min(1, MAX / Math.max(bmp.width, bmp.height));
    const c = document.createElement("canvas");
    c.width = Math.round(bmp.width * s); c.height = Math.round(bmp.height * s);
    c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
    if (bmp.close) bmp.close();
    return new Promise((res) => c.toBlob(res, "image/jpeg", 0.92));
  }

  form.addEventListener("submit", async (e) => {
    const files = Array.from(document.getElementById("photos").files).slice(0, 8);
    if (!files.length) return;
    e.preventDefault();
    btn.disabled = true;
    const fd = new FormData();
    fd.append("_csrf", form.querySelector("[name=_csrf]").value);
    try {
      for (let i = 0; i < files.length; i++) {
        status.textContent = `Preparing photo ${i + 1} of ${files.length}…`;
        fd.append("photos", await shrink(files[i]), files[i].name.replace(/\.\w+$/, "") + ".jpg");
      }
      status.textContent = "Uploading and measuring… (this can take a few seconds)";
      const ctl = new AbortController(), timer = setTimeout(() => ctl.abort(), 90000);
      const res = await fetch(form.action, { method: "POST", body: fd, signal: ctl.signal });
      clearTimeout(timer);
      const html = await res.text();
      document.open(); document.write(html); document.close();
    } catch (err) {
      status.textContent = err.name === "AbortError"
        ? "Timed out after 90 seconds. Check the connection and try again with fewer photos."
        : "Something went wrong: " + err.message;
      btn.disabled = false;
    }
  });
})();
