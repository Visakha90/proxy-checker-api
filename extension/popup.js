const API_URL = "http://localhost:8000/api/v1";

async function getApiKey() {
  const result = await chrome.storage.local.get("apiKey");
  return result.apiKey || "";
}

async function fetchProxy(endpoint) {
  const apiKey = await getApiKey();
  const type = document.getElementById("typeSelect").value;
  const speed = document.getElementById("speedSelect").value;

  let url = `${API_URL}${endpoint}?`;
  if (type) url += `type=${type}&`;
  if (speed) url += `speed_tier=${speed}&`;

  const headers = {};
  if (apiKey) headers["X-API-Key"] = apiKey;

  const response = await fetch(url, { headers });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function setProxy(ip, port, type) {
  const scheme = type.includes("socks") ? "socks5" : "http";
  const config = {
    mode: "fixed_servers",
    rules: {
      singleProxy: { scheme, host: ip, port: parseInt(port) },
      bypassList: ["localhost", "127.0.0.1"],
    },
  };

  await chrome.proxy.settings.set({ value: config, scope: "regular" });
  await chrome.storage.local.set({ activeProxy: { ip, port, type } });
  updateUI(true, `${ip}:${port}`, type);
}

async function clearProxy() {
  await chrome.proxy.settings.clear({ scope: "regular" });
  await chrome.storage.local.remove("activeProxy");
  updateUI(false, null, null);
}

function updateUI(active, proxyStr, type) {
  const dot = document.getElementById("statusDot");
  const text = document.getElementById("statusText");
  const info = document.getElementById("proxyInfo");

  if (active) {
    dot.className = "dot on";
    text.textContent = `Connected (${type?.toUpperCase() || "HTTP"})`;
    info.textContent = proxyStr;
  } else {
    dot.className = "dot off";
    text.textContent = "Disconnected";
    info.textContent = "No proxy active";
  }
}

document.getElementById("getProxy").addEventListener("click", async () => {
  try {
    const data = await fetchProxy("/random");
    if (data.success && data.data) {
      await setProxy(data.data.ip, data.data.port, data.data.type);
    }
  } catch (e) {
    alert("Failed: " + e.message);
  }
});

document.getElementById("rotateProxy").addEventListener("click", async () => {
  try {
    const data = await fetchProxy("/rotate");
    if (data.success && data.data) {
      await setProxy(data.data.ip, data.data.port, data.data.type);
    }
  } catch (e) {
    // Fallback to random
    const data = await fetchProxy("/random");
    if (data.success && data.data) {
      await setProxy(data.data.ip, data.data.port, data.data.type);
    }
  }
});

document.getElementById("clearProxy").addEventListener("click", clearProxy);

// Init
(async () => {
  const result = await chrome.storage.local.get("activeProxy");
  if (result.activeProxy) {
    updateUI(true, `${result.activeProxy.ip}:${result.activeProxy.port}`, result.activeProxy.type);
  }
})();
