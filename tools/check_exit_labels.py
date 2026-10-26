"""Per source: do servers that pass the latency probe carry real traffic, and is their
country label true?

Needs a mihomo instance already running clash/profile.yaml with
  mixed-port 17897 and external-controller 127.0.0.1:19097
(the test instance used during development; never the live Clash Verge one), plus a
select group named "probe" that uses every provider and is the MATCH target.

Usage:  python -I tools/check_exit_labels.py [--per-source 25]
Output: results/exit-label-check.json
"""
import argparse
import concurrent.futures
import json
import os
import random
import statistics
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_clash_config import codes_in  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "results", "exit-label-check.json")
API = "http://127.0.0.1:19097"
PROXY = "http://127.0.0.1:17897"
direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))
via = urllib.request.build_opener(urllib.request.ProxyHandler({"http": PROXY, "https": PROXY}))


def api(path, method="GET", body=None, timeout=300):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    with direct.open(req, timeout=timeout) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


def through(name):
    """Route everything through one proxy; return (exit country, Mbps) or (None, 0)."""
    api("/proxies/probe", "PUT", {"name": name})
    api("/connections", "DELETE")  # drop keep-alive connections to the previous server
    ua = {"User-Agent": "Mozilla/5.0"}  # speed.cloudflare.com 403s Python's default UA
    try:
        with via.open(urllib.request.Request("https://www.cloudflare.com/cdn-cgi/trace", headers=ua), timeout=8) as r:
            loc = dict(l.split("=", 1) for l in r.read().decode().splitlines() if "=" in l).get("loc")
    except Exception:
        return None, 0.0
    try:
        t = time.time()
        with via.open(urllib.request.Request("https://speed.cloudflare.com/__down?bytes=1000000", headers=ua),
                      timeout=12) as r:
            n = len(r.read())
        return loc, round(n * 8 / 1e6 / max(time.time() - t, 0.01), 1)
    except Exception:
        return loc, 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-source", type=int, default=25)
    args = ap.parse_args()
    random.seed(7)

    provs = {k: v for k, v in api("/providers/proxies")["providers"].items() if v.get("vehicleType") == "HTTP"}
    groups = {}
    for k in provs:
        groups.setdefault("Au1rxx (all countries)" if k.startswith("Au1rxx-") else k, []).append(k)

    def hc(k):
        try:
            api(f"/providers/proxies/{urllib.parse.quote(k)}/healthcheck")
        except Exception:
            pass
    with concurrent.futures.ThreadPoolExecutor(16) as pool:
        list(pool.map(hc, provs))
    provs = {k: v for k, v in api("/providers/proxies")["providers"].items() if k in provs}

    results = {}
    for label, members in groups.items():
        alive = [p["name"] for k in members for p in provs[k]["proxies"]
                 if (p.get("history") or [{}])[-1].get("delay", 0) > 0]
        sample = random.sample(alive, min(args.per_source, len(alive)))
        rows = []
        for name in sample:
            claimed = sorted(codes_in(name))
            loc, mbps = through(name)
            rows.append({"name": name, "claimed": claimed, "exit": loc, "mbps": mbps})
        works = [r for r in rows if r["exit"]]
        labelled = [r for r in works if r["claimed"]]
        right = [r for r in labelled if r["exit"] in r["claimed"]]
        results[label] = r = {
            "probe_alive": len(alive), "tested": len(rows),
            "real_traffic_ok_pct": round(100 * len(works) / len(rows), 1) if rows else None,
            "label_correct_pct": round(100 * len(right) / len(labelled), 1) if labelled else None,
            "median_mbps": statistics.median([r["mbps"] for r in works]) if works else 0,
            "wrong_labels": [f'{r["claimed"]}->{r["exit"]}' for r in labelled if r not in right],
            "rows": rows,
        }
        print(f"{label:24} tested {r['tested']:3}  traffic ok {r['real_traffic_ok_pct']}%  "
              f"label right {r['label_correct_pct']}%  median {r['median_mbps']} Mbps  "
              f"wrong: {r['wrong_labels'][:6]}", flush=True)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"tested_at": time.strftime("%Y-%m-%dT%H:%M"), "sources": results}, f, indent=2, ensure_ascii=False)
    print("written:", OUT)


if __name__ == "__main__":
    main()
