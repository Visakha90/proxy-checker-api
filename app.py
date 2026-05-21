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
        
        # ====== 50+ PROXY SOURCES ======
        self.scrape_sources = [
            # API-based sources
            "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=all",
            "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=https&timeout=10000&country=all",
            "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks4&timeout=10000&country=all",
            "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks5&timeout=10000&country=all",
            "https://www.proxy-list.download/api/v1/get?type=http",
            "https://www.proxy-list.download/api/v1/get?type=https",
            "https://www.proxy-list.download/api/v1/get?type=socks4",
            "https://www.proxy-list.download/api/v1/get?type=socks5",
            "https://api.proxyscrape.com/?request=getproxies&proxytype=http&timeout=10000&country=all",
            "https://api.proxyscrape.com/?request=getproxies&proxytype=https&timeout=10000&country=all",
            "https://api.proxyscrape.com/?request=getproxies&proxytype=socks4&timeout=10000&country=all",
            "https://api.proxyscrape.com/?request=getproxies&proxytype=socks5&timeout=10000&country=all",
            
            # Raw GitHub lists
            "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
            "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks4.txt",
            "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
            "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
            "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/https.txt",
            "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks4.txt",
            "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks5.txt",
            "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt",
            "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-https.txt",
            "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks4.txt",
            "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks5.txt",
            "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/proxies.txt",
            "https://raw.githubusercontent.com/opsxcq/proxy-list/master/list.txt",
            "https://raw.githubusercontent.com/mertguvencli/http-proxy-list/main/proxy-list.txt",
            "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
            "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS4_RAW.txt",
            "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5_RAW.txt",
            "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTP_RAW.txt",
            "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
            "https://raw.githubusercontent.com/rdavydov/proxy-list/main/proxies.txt",
            "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list.txt",
            "https://raw.githubusercontent.com/Volodichev/proxy-list/main/proxy_list.txt",
            "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
            "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt",
            "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
            "https://raw.githubusercontent.com/mmpx12/proxy-list/master/http.txt",
            "https://raw.githubusercontent.com/mmpx12/proxy-list/master/socks4.txt",
            "https://raw.githubusercontent.com/mmpx12/proxy-list/master/socks5.txt",
            "https://raw.githubusercontent.com/Anonym0usWork1221/Free-Proxies/main/proxy_list.txt",
            "https://raw.githubusercontent.com/enseitankado/proxy-list/main/HTTP.txt",
            "https://raw.githubusercontent.com/enseitankado/proxy-list/main/SOCKS4.txt",
            "https://raw.githubusercontent.com/enseitankado/proxy-list/main/SOCKS5.txt",
            
            # Scraped lists
            "https://rootjazz.com/proxies/proxies.txt",
            "https://multiproxy.org/txt_all/proxy.txt",
            "https://www.proxy-list.download/api/v1/get?type=http&anon=elite",
            "https://www.proxy-list.download/api/v1/get?type=http&anon=anonymous",
            "https://www.proxy-list.download/api/v1/get?type=http&anon=transparent",
            
            # Additional sources
            "https://openproxylist.xyz/http.txt",
            "https://openproxylist.xyz/socks4.txt",
            "https://openproxylist.xyz/socks5.txt",
            "https://alexaowo.com/proxy/proxies.txt",
        ]
        
        # Extra sources for more proxies
        self.extra_sources = [
            "https://www.sslproxies.org/",
            "https://free-proxy-list.net/",
            "https://www.us-proxy.org/",
            "https://www.socks-proxy.net/",
            "https://www.proxynova.com/proxy-server-list/",
        ]
    
    def scrape_from_html(self, url):
        """Scrape proxies from HTML tables"""
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            resp = requests.get(url, timeout=10, headers=headers)
            if resp.status_code == 200:
                # Simple regex to find IP:port patterns in HTML
                proxies = re.findall(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{2,5}\b', resp.text)
                return proxies
        except:
            return []
        return []
    
    def scrape_proxies(self):
        """Scrape proxies from all sources"""
        all_proxies = set()
        
        # Scrape from API/raw sources
        for url in self.scrape_sources:
            try:
                resp = requests.get(url, timeout=8, 
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                if resp.status_code == 200:
                    for line in resp.text.strip().split("\n"):
                        line = line.strip()
                        # Match IP:Port format
                        if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{2,5}$', line):
                            all_proxies.add(line)
            except:
                continue
        
        # Scrape from HTML sources
        for url in self.extra_sources:
            html_proxies = self.scrape_from_html(url)
            for p in html_proxies:
                all_proxies.add(p)
        
        return list(all_proxies)
    
    def detect_type(self, ip):
        """Detect proxy type"""
        try:
            r = requests.get(f"http://ip-api.com/json/{ip}", timeout=3)
            if r.status_code == 200:
                data = r.json()
                isp = data.get("isp", "").lower()
                
                mobile_isps = ["cellcard", "smart", "metfone", "verizon", 
                              "t-mobile", "vodafone", "att", "sprint",
                              "orange", "telenor", "telia", "3 network",
                              "true move", "dtac", "ais", "globe", "smart",
                              "optus", "telstra", "singtel", "starhub",
                              "kddi", "softbank", "docomo", "china mobile",
                              "bharti airtel", "jio", "mtn", "airtel"]
                
                dc_isps = ["amazon", "aws", "digitalocean", "google", 
                          "azure", "microsoft", "vultr", "linode", "ovh", 
                          "hetzner", "oracle", "ibm", "alibaba", "tencent",
                          "upcloud", "scaleway", "contabo", "ionos"]
                
                if data.get("mobile"): return "MOBILE"
                for m in mobile_isps:
                    if m in isp: return "MOBILE"
                if data.get("hosting"): return "DATACENTER"
                for d in dc_isps:
                    if d in isp: return "DATACENTER"
                return "RESIDENTIAL"
        except:
            return "UNKNOWN"
    
    def check_single(self, proxy):
        """Check one proxy"""
        try:
            proxies = {"http": f"http://{proxy}", "https": f"http://{proxy}"}
            start = time.time()
            resp = requests.get("http://httpbin.org/ip", proxies=proxies, 
                              timeout=8, 
                              headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            if resp.status_code == 200:
                ip = proxy.split(":")[0]
                geo = self.get_geo(ip)
                return {
                    "proxy": proxy,
                    "status": "LIVE",
                    "type": self.detect_type(ip),
                    "speed": round(time.time() - start, 3),
                    "country": geo.get("country", ""),
                    "isp": geo.get("isp", ""),
                    "checked_at": datetime.now().isoformat()
                }
        except:
            pass
        return {"proxy": proxy, "status": "DEAD"}
    
    def get_geo(self, ip):
        """Get geolocation"""
        try:
            r = requests.get(f"http://ip-api.com/json/{ip}", timeout=3)
            if r.status_code == 200:
                return r.json()
        except:
            pass
        return {}
    
    def scrape_and_check(self, max_proxies=500):
        """Scrape + Check in one call"""
        # Step 1: Scrape from ALL sources
        scraped = self.scrape_proxies()
        print(f"Scraped total: {len(scraped)} proxies")
        
        # Step 2: Take only what we need
        proxies = scraped[:max_proxies]
        
        # Step 3: Check each proxy
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
        dead = [r for r in self.results if r["status"] == "DEAD"]
        
        # Count by type
        types = {}
        for r in live:
            t = r.get("type", "UNKNOWN")
            types[t] = types.get(t, 0) + 1
        
        return {
            "scraped_total": len(scraped),
            "checked": len(proxies),
            "live": len(live),
            "dead": len(dead),
            "types": types,
            "results": self.results
        }

checker = ProxyScraperChecker()

@app.route('/')
def home():
    return jsonify({
        "name": "Proxy Scraper & Checker API",
        "version": "3.0",
        "endpoints": {
            "/api/scrape-check?max=500": "Scrape 50+ sources + Check proxies",
            "/api/check": "POST - Check your own proxy list",
            "/api/health": "Health check"
        }
    })

@app.route('/api/health')
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})

@app.route('/api/scrape-check')
def scrape_check():
    """Scrape from 50+ sources + Check them"""
    max_proxies = request.args.get('max', 500, type=int)
    if max_proxies > 2000:
        max_proxies = 2000
    
    result = checker.scrape_and_check(max_proxies)
    return jsonify(result)

@app.route('/api/check', methods=['POST'])
def check():
    """Check custom proxy list"""
    data = request.json
    proxies = data.get('proxies', [])
    
    if not proxies:
        return jsonify({"error": "No proxies provided"}), 400
    
    if len(proxies) > 1000:
        return jsonify({"error": "Max 1000 proxies per request"}), 400
    
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
    
    for t in threads:
        t.join()
    
    live = [r for r in checker.results if r["status"] == "LIVE"]
    dead = [r for r in checker.results if r["status"] == "DEAD"]
    
    # Count by type
    types = {}
    for r in live:
        t = r.get("type", "UNKNOWN")
        types[t] = types.get(t, 0) + 1
    
    return jsonify({
        "total": len(proxies),
        "live": len(live),
        "dead": len(dead),
        "types": types,
        "results": checker.results
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
