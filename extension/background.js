const WIDGET_COOKIES = "http://127.0.0.1:9871/cookies";
const WIDGET_STATUS  = "http://127.0.0.1:9871/status";
const WIDGET_REG     = "http://127.0.0.1:9871/register";
const HOST_NAME      = "com.claude.tracker";
const ALARM_NAME     = "claude_cookie_sync";
const SYNC_MINS      = 5;

// ── Native Messaging (launches widget if not running) ─────────────────────────

function launchViaHost() {
  try {
    const port = chrome.runtime.connectNative(HOST_NAME);
    port.onDisconnect.addListener(() => {
      if (chrome.runtime.lastError) {
        // Host not registered yet — widget must already be running from startup
        console.log("[Claude] Native host not registered:", chrome.runtime.lastError.message);
      }
    });
    // Forward cookies through native messaging channel
    port.postMessage({ type: "ping" });
  } catch (e) {
    console.log("[Claude] Native messaging unavailable:", e);
  }
}

// ── Cookie sync via HTTP ──────────────────────────────────────────────────────

async function syncCookies() {
  const [sk, org] = await Promise.all([
    chrome.cookies.get({ url: "https://claude.ai", name: "sessionKey" }),
    chrome.cookies.get({ url: "https://claude.ai", name: "lastActiveOrg" }),
  ]);
  if (!sk || !org) return;

  const payload = { sessionKey: sk.value, lastActiveOrg: org.value };

  try {
    await fetch(WIDGET_COOKIES, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (_) {
    // Widget not running — try to launch via native messaging
    launchViaHost();
  }
}

// ── Register this extension's ID with the widget ──────────────────────────────

async function registerWithWidget() {
  try {
    await fetch(`${WIDGET_REG}?id=${chrome.runtime.id}`, { method: "GET" });
  } catch (_) { /* widget may not be running yet */ }
}

// ── On first install: launch widget + open welcome tab ────────────────────────

chrome.runtime.onInstalled.addListener(async ({ reason }) => {
  if (reason === "install") {
    // Try to launch via native messaging (works after installer has run)
    launchViaHost();
    // Wait a moment then sync cookies
    setTimeout(syncCookies, 2000);
    // Register extension ID with widget so it can update native host manifest
    setTimeout(registerWithWidget, 3000);
    // Open welcome / status page
    chrome.tabs.create({ url: chrome.runtime.getURL("installed.html") });
  }
});

// ── Sync on every Claude.ai navigation ───────────────────────────────────────

chrome.webNavigation?.onCompleted.addListener(
  (details) => { if (details.url.startsWith("https://claude.ai")) syncCookies(); }
);

// ── Sync when sessionKey or lastActiveOrg cookie changes ─────────────────────

chrome.cookies.onChanged.addListener(({ cookie, removed }) => {
  if (cookie.domain.includes("claude.ai") &&
      (cookie.name === "sessionKey" || cookie.name === "lastActiveOrg")) {
    if (!removed) syncCookies();
  }
});

// ── Periodic alarm sync ───────────────────────────────────────────────────────

chrome.alarms.create(ALARM_NAME, { periodInMinutes: SYNC_MINS });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === ALARM_NAME) {
    syncCookies();
    registerWithWidget();
  }
});

// ── Sync on browser start ─────────────────────────────────────────────────────

syncCookies();
registerWithWidget();
