/**
 * ProxyChecker Node.js SDK
 *
 * Usage:
 *   const ProxyChecker = require('proxychecker-sdk');
 *   const client = new ProxyChecker({ apiKey: 'pc_your_key' });
 *   const proxies = await client.getProxies({ type: 'http', country: 'US' });
 */

class ProxyChecker {
  constructor({ apiKey = "", baseUrl = "http://localhost:8000/api/v1" } = {}) {
    this.apiKey = apiKey;
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  async _fetch(path, { method = "GET", params = {}, body = null } = {}) {
    const url = new URL(`${this.baseUrl}${path}`);
    Object.entries(params).forEach(([k, v]) => { if (v != null) url.searchParams.set(k, v); });

    const headers = { "Content-Type": "application/json" };
    if (this.apiKey) headers["X-API-Key"] = this.apiKey;

    const opts = { method, headers };
    if (body) opts.body = JSON.stringify(body);

    const res = await fetch(url.toString(), opts);
    if (!res.ok) throw new Error(`ProxyChecker API error: ${res.status} ${res.statusText}`);
    return res.json();
  }

  async getProxies({ type, country, anonymity, alive = true, ssl, latencyLt, limit = 100, page = 1 } = {}) {
    return this._fetch("/proxies", { params: { type, country, anonymity, alive, ssl, latency_lt: latencyLt, limit, page } });
  }

  async getRandom({ type, country } = {}) {
    return this._fetch("/random", { params: { type, country } });
  }

  async getStats() {
    return this._fetch("/stats");
  }

  async getCountries() {
    return this._fetch("/countries");
  }

  async rotate({ type, country } = {}) {
    return this._fetch("/rotate", { params: { type, country } });
  }

  async download(type = "http", format = "txt") {
    const url = `${this.baseUrl}/download/${type}?format=${format}`;
    const headers = {};
    if (this.apiKey) headers["X-API-Key"] = this.apiKey;
    const res = await fetch(url, { headers });
    return res.text();
  }

  async getSpeedTiers() {
    return this._fetch("/speed-tiers");
  }

  async getLeaderboard(category = "fastest", limit = 50) {
    return this._fetch(`/leaderboard/${category}`, { params: { limit } });
  }

  async checkFingerprint(ip, port, type = "http") {
    return this._fetch("/fingerprint", { method: "POST", body: { ip, port, type } });
  }

  async gateway(url, { method = "GET", proxyType, country, speedTier } = {}) {
    return this._fetch("/gateway", { method: "POST", body: { url, method, proxy_type: proxyType, country, speed_tier: speedTier } });
  }
}

module.exports = ProxyChecker;
