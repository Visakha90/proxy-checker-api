#!/usr/bin/env python3
"""
ProxyChecker CLI Tool.

Usage:
    proxychecker get --type http --country US --fast --limit 10
    proxychecker random --type socks5
    proxychecker stats
    proxychecker download http --format txt --output proxies.txt
    proxychecker test https://example.com --limit 50
    proxychecker rotate --type http
"""

import argparse
import json
import sys
import os

try:
    import requests
except ImportError:
    print("Install requests: pip install requests")
    sys.exit(1)

API_URL = os.getenv("PROXYCHECKER_API_URL", "http://localhost:8000/api/v1")
API_KEY = os.getenv("PROXYCHECKER_API_KEY", "")


def headers():
    h = {"Content-Type": "application/json"}
    if API_KEY:
        h["X-API-Key"] = API_KEY
    return h


def cmd_get(args):
    params = {"limit": args.limit, "alive": "true"}
    if args.type:
        params["type"] = args.type
    if args.country:
        params["country"] = args.country
    if args.fast:
        params["latency_lt"] = "500"
    if args.anonymity:
        params["anonymity"] = args.anonymity

    r = requests.get(f"{API_URL}/proxies", headers=headers(), params=params)
    data = r.json()

    if args.output == "json":
        print(json.dumps(data, indent=2))
    else:
        for p in data.get("data", []):
            line = f"{p['ip']}:{p['port']}"
            if args.verbose:
                line += f" | {p['type']} | {p.get('country_code', '??')} | {p.get('latency', '?')}ms | {p.get('anonymity', '?')}"
            print(line)

    print(f"\n--- {data.get('count', 0)} proxies (total: {data.get('total', 0)}) ---", file=sys.stderr)


def cmd_random(args):
    params = {}
    if args.type:
        params["type"] = args.type
    if args.country:
        params["country"] = args.country

    r = requests.get(f"{API_URL}/random", headers=headers(), params=params)
    data = r.json()

    if data.get("success"):
        p = data["data"]
        print(f"{p['ip']}:{p['port']}")
        if args.verbose:
            print(f"  Type: {p['type']} | Country: {p.get('country_code')} | Latency: {p.get('latency')}ms")


def cmd_stats(args):
    r = requests.get(f"{API_URL}/stats", headers=headers())
    data = r.json()
    if data.get("success"):
        s = data["data"]
        print(f"Total Proxies: {s['total_proxies']:,}")
        print(f"Alive:         {s['alive_proxies']:,}")
        print(f"Dead:          {s['dead_proxies']:,}")
        print(f"HTTP:          {s['http']:,}")
        print(f"SOCKS4:        {s.get('socks4', 0):,}")
        print(f"SOCKS5:        {s.get('socks5', 0):,}")
        print(f"Avg Latency:   {s['average_latency_ms']:.0f}ms")


def cmd_download(args):
    r = requests.get(f"{API_URL}/download/{args.type}?format={args.format}", headers=headers())
    if args.file:
        with open(args.file, "w") as f:
            f.write(r.text)
        print(f"Saved to {args.file} ({len(r.text.splitlines())} proxies)")
    else:
        print(r.text)


def cmd_rotate(args):
    params = {}
    if args.type:
        params["type"] = args.type
    if args.country:
        params["country"] = args.country

    r = requests.get(f"{API_URL}/rotate", headers=headers(), params=params)
    data = r.json()
    if data.get("success"):
        p = data["data"]
        print(f"{p['ip']}:{p['port']}")


def main():
    parser = argparse.ArgumentParser(prog="proxychecker", description="ProxyChecker CLI")
    parser.add_argument("--api-url", default=API_URL, help="API base URL")
    parser.add_argument("--api-key", default=API_KEY, help="API key")

    sub = parser.add_subparsers(dest="command")

    # get
    p = sub.add_parser("get", help="Get proxies with filters")
    p.add_argument("--type", "-t", choices=["http", "https", "socks4", "socks5"])
    p.add_argument("--country", "-c")
    p.add_argument("--anonymity", "-a", choices=["elite", "anonymous", "transparent"])
    p.add_argument("--fast", action="store_true", help="Only <500ms latency")
    p.add_argument("--limit", "-l", type=int, default=10)
    p.add_argument("--output", "-o", choices=["text", "json"], default="text")
    p.add_argument("--verbose", "-v", action="store_true")

    # random
    p = sub.add_parser("random", help="Get a random proxy")
    p.add_argument("--type", "-t", choices=["http", "https", "socks4", "socks5"])
    p.add_argument("--country", "-c")
    p.add_argument("--verbose", "-v", action="store_true")

    # stats
    sub.add_parser("stats", help="Show statistics")

    # download
    p = sub.add_parser("download", help="Download proxy list")
    p.add_argument("type", choices=["http", "https", "socks4", "socks5", "all"])
    p.add_argument("--format", "-f", choices=["txt", "csv", "json"], default="txt")
    p.add_argument("--file", "-o", help="Output file")

    # rotate
    p = sub.add_parser("rotate", help="Get next rotated proxy")
    p.add_argument("--type", "-t", choices=["http", "https", "socks4", "socks5"])
    p.add_argument("--country", "-c")

    args = parser.parse_args()

    if args.api_url:
        global API_URL
        API_URL = args.api_url
    if args.api_key:
        global API_KEY
        API_KEY = args.api_key

    commands = {"get": cmd_get, "random": cmd_random, "stats": cmd_stats, "download": cmd_download, "rotate": cmd_rotate}
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
