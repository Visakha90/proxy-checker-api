
from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
import requests
import time
import re
from datetime import datetime

app = Flask(__name__)
CORS(app)

class ProxyScraperChecker:
    def __init__(self):
        self.results = []
        self.lock = threading.Lock()
        
        self.scrape_sources = [
            "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=all",
            "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=https&timeout=10000&country=all",
            "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
            "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
            "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
            "https://www.proxy-list.download/api/v1/get?type=http"
        ]
    
    def scrape_proxies(self):
        all_proxies = set()
        for url in self.scrape_sources:
            try:
                resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code == 200:
                    for line in resp.text.strip().split("\n"):
                        line = line.strip()
                        if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+$', line):
                            all_proxies.add(line)
            except:
                continue
        return list(all_proxies)
    
    def detect_type(self, ip):
        try:
            r = requests.get(f"http://ip-api.com/json/{ip}", timeout=3)
            if r.status_code == 200:
                data = r.json()
                isp = data.get("isp", "").lower()
                if data.get("mobile"): return "MOBILE"
                if data.get("hosting"): return "DATACENTER"
                mobile_isps = ["cellcard", "smart", "verizon", "t-mobile", "vodafone"]
                dc_isps = ["amazon", "digitalocean", "google", "azure", "vultr"]
                for m in mobile_isps:
                    if m in isp: return "MOBILE"
                for d in dc_isps:
                    if d in isp: return "DATACENTER"
                return "RESIDENTIAL"
        except:
            return "UNKNOWN"
    
    def check_single(self, proxy):
        try:
            proxies = {"http": f"http://{proxy}", "https": f"http://{proxy}"}
            start = time.time()
            resp = requests.get("http://httpbin.org/ip", proxies=proxies, timeout=8,
                              headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                ip = proxy.split(":")[0]
                return {
                    "proxy": proxy,
                    "status": "LIVE",
                    "type": self.detect_type(ip),
                    "speed": round(time.time() - start, 3),
                    "checked_at": datetime.now().isoformat()
                }
        except:
            pass
        return {"proxy": proxy, "status": "DEAD"}
    
    def scrape_and_check(self, max_proxies=300):
        scraped = self.scrape_proxies()
        proxies = scraped[:max_proxies]
        self.results = []
        threads = []
        
        def worker(p):
            r = self.check_single(p)
            with self.lock:
                self.results.append(r)
        
        for p in proxies:
            t = threading.Thread(target=worker, args=(p,))
            t.start()
            threads.append(t)
        
        for t in threads:
            t.join()
        
        live = [r for r in self.results if r["status"] == "LIVE"]
        return {
            "scraped_total": len(scraped),
            "checked": len(proxies),
            "live": len(live),
            "dead": len(proxies) - len(live),
            "results": self.results
        }

checker = ProxyScraperChecker()

@app.route('/')
def home():
    return jsonify({"name": "Proxy Checker API", "version": "1.0"})

@app.route('/api/health')
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})

@app.route('/api/scrape-check')
def scrape_check():
    max_proxies = request.args.get('max', 200, type=int)
    if max_proxies > 500: max_proxies = 500
    result = checker.scrape_and_check(max_proxies)
    return jsonify(result)

@app.route('/api/check', methods=['POST'])
def check():
    data = request.json
    proxies = data.get('proxies', [])
    if not proxies: return jsonify({"error": "No proxies"}), 400
    if len(proxies) > 500: return jsonify({"error": "Max 500"}), 400
    
    checker.results = []
    threads = []
    
    def worker(p):
        r = checker.check_single(p)
        with checker.lock:
            checker.results.append(r)
    
    for p in proxies:
        t = threading.Thread(target=worker, args=(p,))
        t.start()
        threads.append(t)
    
    for t in threads: t.join()
    
    live = [r for r in checker.results if r["status"] == "LIVE"]
    return jsonify({
        "total": len(proxies), "live": len(live),
        "dead": len(proxies) - len(live), "results": checker.results
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
