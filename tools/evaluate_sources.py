"""Rank free V2Ray/Clash subscription sources by how many of their servers work from your network.

Usage:  python -I tools/evaluate_sources.py [--sample 100]
Output: results/sources-evaluation.json  (raw numbers, one entry per source)

For each source: download, count servers, look up when the file last changed on GitHub,
then latency-test a random sample with a private mihomo instance (ports 17898/19098, so
it never touches the running Clash Verge). Needs PyYAML.
"""
import argparse
import base64
import concurrent.futures
import datetime
import json
import os
import random
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "results", "sources-evaluation.json")
MIHOMO = [r"C:\Program Files\Clash Verge\verge-mihomo.exe"]
API = "http://127.0.0.1:19098"
SCHEMES = ("vless", "vmess", "trojan", "ss", "hysteria2", "hy2", "tuic")
TYPES = ("vless", "vmess", "trojan", "ss", "hysteria2", "tuic")

# name -> (owner/repo, branch, path). URL = raw.githubusercontent.com/<repo>/<branch>/<path>
SOURCES = {
    "Radikal-fast": ("0xRadikal/Free-v2ray-Configs", "main", "fast/configs.txt"),
    "Barry-Sub1": ("barry-far/V2ray-config", "main", "Sub1.txt"),
    "Rooster": ("roosterkid/openproxylist", "main", "V2RAY_RAW.txt"),
    "Firmfox-1": ("Firmfox/proxify", "main", "v2ray_configs/subscriptions/subscription-1.txt"),
    "MegaV": ("romaxa55/MegaV_Public", "main", "subs/all.txt"),
    "Pawdroid": ("Pawdroid/Free-servers", "main", "sub"),
    "AwesomeVPN": ("awesome-vpn/awesome-vpn", "master", "all"),
    "Mahdibland-Eternity": ("mahdibland/V2RayAggregator", "master", "Eternity.txt"),
    "Epodonios-Sub1": ("Epodonios/v2ray-configs", "main", "Sub1.txt"),
    "Snakem982": ("snakem982/proxypool", "main", "source/v2ray-2.txt"),
    "PuddinCat": ("PuddinCat/BestClash", "main", "proxies.yaml"),
    "Au1rxx-stable": ("Au1rxx/free-vpn-subscriptions", "main", "output/stable/clash-0001.yaml"),
    "Matin-super": ("MatinGhanbari/v2ray-configs", "main", "subscriptions/v2ray/super-sub.txt"),
    "SoliSpirit": ("SoliSpirit/v2ray-configs", "main", "all_configs.txt"),
    "Delta-Kronecker": ("Delta-Kronecker/V2ray-Config", "main", "config/all_configs.txt"),
    "Mahdi0024": ("Mahdi0024/ProxyCollector", "master", "sub/proxies.txt"),
    "Kooker": ("kooker/FreeSubsCheck", "main", "base64.txt"),
    "F0rc3Run-best": ("F0rc3Run/F0rc3Run", "main", "Best-Results/proxies.txt"),
    "ALIILAPRO": ("ALIILAPRO/v2rayNG-Config", "main", "sub.txt"),
    "Mfuu": ("mfuu/FreeProxies", "master", "sub"),
    "Zhuhaiuk": ("zhuhaiuk/free-nodes", "main", "nodes.txt"),
    "FastNodes-curated": ("rtwo2/FastNodes", "main", "sub/curated.txt"),
    "Iboxz-mix": ("iboxz/free-v2ray-collector", "main", "main/mix.txt"),
    "MhdiTaheri-mix": ("MhdiTaheri/V2rayCollector", "main", "sub/mix"),
    "Barabama": ("Barabama/FreeNodes", "main", "nodes/clashmeta.txt"),
    "Argh94": ("Argh94/Proxy-List", "main", "All_Config.txt"),
}

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # always direct


def get(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": "clash-verge/v2"})
    with opener.open(req, timeout=timeout) as r:
        return r.read()


def b64(s):
    s = s.strip().replace("-", "+").replace("_", "/")
    return base64.b64decode(s + "=" * (-len(s) % 4)).decode("utf-8", "ignore")


def parse(raw):
    """Return ('links', [str]) or ('yaml', [dict]) holding only usable proxy protocols."""
    text = raw.decode("utf-8", "ignore")
    if "proxies:" in text[:5000] or text.lstrip().startswith("proxies"):
        try:
            data = yaml.safe_load(text) or {}
            return "yaml", [p for p in data.get("proxies") or [] if isinstance(p, dict) and p.get("type") in TYPES]
        except Exception:
            pass
    if "://" not in text[:2000]:
        try:
            text = b64(text)
        except Exception:
            return "links", []
    ls = [l.strip() for l in text.splitlines()]
    return "links", [l for l in ls if l.split("://", 1)[0].lower() in SCHEMES]


def endpoint(item):
    try:
        if isinstance(item, dict):
            return f"{item.get('server')}:{item.get('port')}"
        scheme, rest = item.split("://", 1)
        if scheme == "vmess":
            j = json.loads(b64(rest.split("#")[0]))
            return f"{j.get('add')}:{j.get('port')}"
        rest = rest.split("#")[0]
        net = rest.split("/")[0].split("?")[0]
        if "@" not in net and scheme == "ss":
            net = b64(net)
        host = net.rsplit("@", 1)[-1]
        return host.lower()
    except Exception:
        return None


def last_commit(repo, branch, path):
    try:
        url = f"https://api.github.com/repos/{repo}/commits?sha={branch}&path={urllib.parse.quote(path)}&per_page=1"
        out = subprocess.run(["gh", "api", url.replace("https://api.github.com/", "")],
                             capture_output=True, text=True, timeout=30)
        return json.loads(out.stdout)[0]["commit"]["committer"]["date"]
    except Exception:
        return None


def api(path, method="GET", timeout=600):
    req = urllib.request.Request(API + path, method=method)
    with opener.open(req, timeout=timeout) as r:
        body = r.read()
        return json.loads(body) if body else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=100)
    args = ap.parse_args()
    random.seed(42)
    work = tempfile.mkdtemp(prefix="pv-eval-")
    results = {}

    for name, (repo, branch, path) in SOURCES.items():
        url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
        r = {"repo": repo, "url": url}
        try:
            kind, items = parse(get(url))
        except Exception as e:
            r["error"] = str(e)
            results[name] = r
            print(f"{name:20} download failed: {e}")
            continue
        eps = {e for e in map(endpoint, items) if e}
        r.update(kind=kind, servers=len(items), unique_endpoints=len(eps),
                 last_commit=last_commit(repo, branch, path), endpoints=sorted(eps))
        sample = random.sample(items, min(args.sample, len(items)))
        r["sampled"] = len(sample)
        with open(os.path.join(work, f"{name}.txt"), "w", encoding="utf-8") as f:
            if kind == "yaml":
                yaml.safe_dump({"proxies": sample}, f, allow_unicode=True)
            else:
                f.write("\n".join(sample))
        results[name] = r
        print(f"{name:20} {kind:5} {len(items):6} servers, {len(eps):6} unique, changed {r['last_commit']}")

    tested = [n for n, r in results.items() if r.get("sampled")]
    cfg = {
        "mixed-port": 17898, "external-controller": "127.0.0.1:19098", "log-level": "error",
        "proxy-providers": {n: {"type": "file", "path": f"./{n}.txt",
                                "health-check": {"enable": True, "url": "https://www.gstatic.com/generate_204",
                                                 "interval": 86400, "timeout": 3000, "lazy": True}}
                            for n in tested},
        "proxy-groups": [{"name": "all", "type": "select", "use": tested}],
        "rules": ["MATCH,DIRECT"],
    }
    with open(os.path.join(work, "config.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True)

    exe = next(p for p in MIHOMO if os.path.exists(p))
    proc = subprocess.Popen([exe, "-d", work, "-f", os.path.join(work, "config.yaml")],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                api("/version", timeout=2)
                break
            except Exception:
                time.sleep(1)
        print("testing samples (up to a few minutes)…")
        def check(n):
            try:
                api(f"/providers/proxies/{urllib.parse.quote(n)}/healthcheck")
            except Exception as e:
                print(f"  healthcheck {n}: {e}")
        with concurrent.futures.ThreadPoolExecutor(len(tested)) as pool:
            list(pool.map(check, tested))
        provs = api("/providers/proxies")["providers"]
        for n in tested:
            delays = []
            loaded = provs.get(n, {}).get("proxies", [])
            for p in loaded:
                h = p.get("history") or []
                if h and h[-1].get("delay", 0) > 0:
                    delays.append(h[-1]["delay"])
            r = results[n]
            r["loaded"] = len(loaded)
            r["alive"] = len(delays)
            r["alive_pct"] = round(100 * len(delays) / len(loaded), 1) if loaded else 0.0
            r["median_ms"] = int(statistics.median(delays)) if delays else None
            r["best_ms"] = min(delays) if delays else None
    finally:
        proc.terminate()

    # How many endpoints each source adds that no other source has.
    for n, r in results.items():
        others = set().union(*(set(o.get("endpoints", [])) for m, o in results.items() if m != n))
        r["exclusive_endpoints"] = len(set(r.get("endpoints", [])) - others)
    for r in results.values():
        r.pop("endpoints", None)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"tested_at": datetime.datetime.now().isoformat(timespec="minutes"),
                   "sample_per_source": args.sample, "sources": results}, f, indent=2)

    print(f"\n{'source':20} {'servers':>7} {'alive%':>7} {'median':>7} {'excl.':>6}  last change")
    for n, r in sorted(results.items(), key=lambda kv: -(kv[1].get("alive_pct") or 0)):
        print(f"{n:20} {r.get('servers', 0):7} {r.get('alive_pct', 0):7} {str(r.get('median_ms')):>7} "
              f"{r.get('exclusive_endpoints', 0):6}  {r.get('last_commit')}")
    print("written:", OUT)


if __name__ == "__main__":
    sys.exit(main())
