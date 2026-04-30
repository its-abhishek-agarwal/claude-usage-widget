// Replace with your actual installer download URL once you have a website
const INSTALLER_URL = "https://your-website.com/download/claude-tracker-setup.bat";

async function check() {
  const statusEl  = document.getElementById("status");
  const stepsEl   = document.getElementById("steps");
  const downloadEl = document.getElementById("download");

  try {
    const r = await fetch("http://127.0.0.1:9871/status",
                          { signal: AbortSignal.timeout(3000) });
    const d = await r.json();

    if (d.auth) {
      statusEl.innerHTML = '<span class="ok">✓ Widget running and connected!</span>';
      stepsEl.innerHTML  =
        "Everything is set up. Look for the floating pill widget in the corner of your screen.<br>" +
        "The tray icon (system tray, bottom-right) lets you show it any time.";
    } else {
      statusEl.innerHTML = '<span class="warn">Widget running — waiting for Claude.ai session.</span>';
      stepsEl.innerHTML  =
        'Open <a href="https://claude.ai" target="_blank">claude.ai</a> in a tab ' +
        "and the extension will sync your session automatically.";
    }
  } catch (_) {
    statusEl.innerHTML = '<span class="warn">Widget not running.</span>';
    stepsEl.innerHTML =
      "<b>One-time setup:</b><br>" +
      "1. Download and run the installer below<br>" +
      "2. The widget will appear in your system tray<br>" +
      "3. From now on it starts automatically with Windows";
    downloadEl.classList.remove("hidden");
    document.getElementById("dlBtn").href = INSTALLER_URL;
  }
}

document.getElementById("retryBtn").addEventListener("click", () => {
  document.getElementById("status").textContent = "Checking…";
  document.getElementById("steps").textContent  = "";
  document.getElementById("download").classList.add("hidden");
  check();
});

check();
