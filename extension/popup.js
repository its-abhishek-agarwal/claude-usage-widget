function color(pct) {
  if (pct < 60) return "#4ade80";
  if (pct < 80) return "#facc15";
  if (pct < 95) return "#fb923c";
  return "#f87171";
}

async function load() {
  const el = document.getElementById("content");
  try {
    const r = await fetch("http://127.0.0.1:9871/status", { signal: AbortSignal.timeout(2000) });
    const d = await r.json();
    const pct = Math.round(d.pct);
    const c   = color(pct);
    el.innerHTML = `
      <div class="row">
        <span class="label">Current session</span>
        <span class="pct" style="color:${c}">${pct}%</span>
      </div>
      <div class="row">
        <div class="bar-bg">
          <div class="bar-fill" style="width:${pct}%;background:${c}"></div>
        </div>
      </div>
      <div class="status">${d.auth ? "Widget connected ✓" : "Widget not authenticated"}</div>
    `;
  } catch (_) {
    el.innerHTML = `<div class="status">Widget not running — launch it first.</div>`;
  }
}

document.getElementById("syncBtn").addEventListener("click", async () => {
  const btn = document.getElementById("syncBtn");
  btn.textContent = "Syncing…";
  const [sk, org] = await Promise.all([
    chrome.cookies.get({ url: "https://claude.ai", name: "sessionKey" }),
    chrome.cookies.get({ url: "https://claude.ai", name: "lastActiveOrg" }),
  ]);
  if (sk && org) {
    await fetch("http://127.0.0.1:9871/cookies", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sessionKey: sk.value, lastActiveOrg: org.value }),
    }).catch(() => {});
    btn.textContent = "Synced ✓";
    setTimeout(load, 500);
  } else {
    btn.textContent = "Not logged in to Claude.ai";
  }
  setTimeout(() => btn.textContent = "Sync Now", 2000);
});

document.getElementById("downloadBtn").addEventListener("click", function() {
  chrome.tabs.create({ url: "https://claude-limit-usage-widget.vercel.app/#download" });
});

document.getElementById("donateBtn").addEventListener("click", function() {
  chrome.tabs.create({ url: "https://ko-fi.com/TODO" });
});

load();
