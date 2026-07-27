// Background service worker for ProxyChecker extension
// Handles proxy auto-rotation and health checks

const CHECK_INTERVAL = 60000; // Check proxy health every 60 seconds
const API_URL = "http://localhost:8000/api/v1";

let healthCheckTimer = null;

chrome.runtime.onInstalled.addListener(() => {
  console.log("ProxyChecker extension installed");
  chrome.storage.local.set({ apiKey: "", autoRotate: false, rotateInterval: 300 });
});

async function checkProxyHealth() {
  const { activeProxy, apiKey } = await chrome.storage.local.get(["activeProxy", "apiKey"]);
  if (!activeProxy) return;

  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);

    const response = await fetch("http://httpbin.org/ip", {
      signal: controller.signal,
    });
    clearTimeout(timeout);

    if (!response.ok) {
      console.log("Proxy appears dead, rotating...");
      await rotateProxy(apiKey);
    }
  } catch (e) {
    console.log("Proxy check failed, rotating...");
    await rotateProxy(apiKey);
  }
}

async function rotateProxy(apiKey) {
  try {
    const headers = {};
    if (apiKey) headers["X-API-Key"] = apiKey;

    const response = await fetch(`${API_URL}/random`, { headers });
    const data = await response.json();

    if (data.success && data.data) {
      const { ip, port, type } = data.data;
      const scheme = type.includes("socks") ? "socks5" : "http";

      await chrome.proxy.settings.set({
        value: {
          mode: "fixed_servers",
          rules: {
            singleProxy: { scheme, host: ip, port: parseInt(port) },
            bypassList: ["localhost", "127.0.0.1"],
          },
        },
        scope: "regular",
      });

      await chrome.storage.local.set({ activeProxy: { ip, port, type } });
      console.log(`Rotated to ${ip}:${port} (${type})`);
    }
  } catch (e) {
    console.error("Rotation failed:", e);
  }
}

// Start health check interval
chrome.alarms.create("proxyHealthCheck", { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "proxyHealthCheck") {
    checkProxyHealth();
  }
});
