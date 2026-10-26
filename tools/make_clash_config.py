"""Generate a mihomo (Clash Meta) config with one auto-fastest group per country.

Usage:  python -I tools/make_clash_config.py
Output: clash/profile.yaml  (import into Clash Verge Rev / FlClash)
        clash/countries.json   (per-country server counts this run saw)

Sources were picked with tools/evaluate_sources.py and tools/check_exit_labels.py.
Re-run when sources change or new countries appear. Uses PyYAML if installed.
"""
import base64
import collections
import datetime
import json
import os
import re
import sys
import urllib.parse
import urllib.request

try:
    import yaml
except ImportError:  # YAML sources then just aren't counted
    yaml = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "clash")
RAW = "https://raw.githubusercontent.com/"

# All lists tested >= 50% alive on 2026-10-25 (tools/evaluate_sources.py).
# Country labels (tools/check_exit_labels.py): these matched the real exit >= 89% ...
ACCURATE_LISTS = {
    "Rooster": RAW + "roosterkid/openproxylist/main/V2RAY_RAW.txt",
    "Mahdi0024": RAW + "Mahdi0024/ProxyCollector/master/sub/proxies.txt",
    "Snakem982": RAW + "snakem982/proxypool/main/source/v2ray-2.txt",
    "PuddinCat": RAW + "PuddinCat/BestClash/main/proxies.yaml",
}
# ... these are fast but mislabel 30-50% of servers. They also make up "Fastest anywhere".
FAST_LISTS = {
    "Radikal-fast": RAW + "0xRadikal/Free-v2ray-Configs/main/fast/configs.txt",
    "F0rc3Run": RAW + "F0rc3Run/F0rc3Run/main/Best-Results/clash.yaml",  # link list has ciphers mihomo rejects
    "Mahdibland": RAW + "mahdibland/V2RayAggregator/master/Eternity.txt",
    "AwesomeVPN": RAW + "awesome-vpn/awesome-vpn/master/all",
}
# False: country groups use every list (more servers, some exits in the wrong country).
# True: country groups use only ACCURATE_LISTS + Au1rxx.
STRICT_LABELS = False
COUNTRY_LISTS = {**ACCURATE_LISTS, **({} if STRICT_LABELS else FAST_LISTS)}

# Au1rxx publishes servers split by *verified exit country* (100% correct in testing):
# added to every country group.
AU1RXX = RAW + "Au1rxx/free-vpn-subscriptions/main/output/"

MIN_SERVERS = 3          # countries with fewer servers get no group of their own
MIN_COUNTRIES = 20       # fewer country groups than this means a source broke (54 on 2026-10-26)
TEST_URL = "https://www.gstatic.com/generate_204"
TEST_TIMEOUT = 2000      # ms; a free server slower than this is unusable anyway
# Kept slow to save bandwidth: a big country is ~1,700 probes per re-test. Between
# scheduled tests, MAX_FAILED consecutive failures on the current server force a re-test.
COUNTRY_INTERVAL = 1800  # seconds between scheduled re-tests of the group in use
ANYWHERE_INTERVAL = 3600
MAX_FAILED = 3
PROVIDER_REFRESH = 14400  # re-download lists every 4 h
# Two-letter code whose sites and IPs skip the proxy (local banks / government often block
# foreign IPs), e.g. "DE". Empty = tunnel everything. Leave empty in the published config
# and add the rule in your client instead (see README).
HOME_COUNTRY = ""

# Flag emoji that mean the same country as another code.
ALIASES = {"UM": "US", "UK": "GB"}

NAMES = {
    "AE": "United Arab Emirates", "AL": "Albania", "AM": "Armenia", "AR": "Argentina", "AT": "Austria",
    "AU": "Australia", "AZ": "Azerbaijan", "BE": "Belgium", "BG": "Bulgaria", "BH": "Bahrain", "BR": "Brazil",
    "BY": "Belarus", "CA": "Canada", "CH": "Switzerland", "CL": "Chile", "CN": "China", "CO": "Colombia",
    "CY": "Cyprus", "CZ": "Czechia", "DE": "Germany", "DK": "Denmark", "EE": "Estonia", "EG": "Egypt",
    "ES": "Spain", "FI": "Finland", "FR": "France", "GB": "United Kingdom", "GE": "Georgia", "GR": "Greece",
    "HK": "Hong Kong", "HR": "Croatia", "HU": "Hungary", "ID": "Indonesia", "IE": "Ireland", "IL": "Israel",
    "IN": "India", "IQ": "Iraq", "IR": "Iran", "IS": "Iceland", "IT": "Italy", "JP": "Japan", "KR": "South Korea",
    "KZ": "Kazakhstan", "LT": "Lithuania", "LU": "Luxembourg", "LV": "Latvia", "MD": "Moldova", "MX": "Mexico",
    "MY": "Malaysia", "NL": "Netherlands", "NO": "Norway", "NZ": "New Zealand", "OM": "Oman", "PH": "Philippines",
    "PK": "Pakistan", "PL": "Poland", "PT": "Portugal", "QA": "Qatar", "RO": "Romania", "RS": "Serbia",
    "RU": "Russia", "SA": "Saudi Arabia", "SC": "Seychelles", "SE": "Sweden", "SG": "Singapore", "SI": "Slovenia",
    "SK": "Slovakia", "TH": "Thailand", "TR": "Turkey", "TW": "Taiwan", "UA": "Ukraine", "US": "United States",
    "VN": "Vietnam", "ZA": "South Africa",
}

# Non-server entries some lists ship (info lines disguised as configs).
EXCLUDE = r"(?i)profile-|subscription-|support-url|expire|traffic|criterion|median|LATEST-UPDATE"

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # always direct


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "clash-verge/v2"})
    with opener.open(req, timeout=40) as r:
        return r.read().decode("utf-8", "ignore")


def names_in(text):
    """Server names in a subscription body (Clash YAML, link list, or base64 link list)."""
    if yaml and "proxies:" in text[:5000]:
        try:
            return [p.get("name", "") for p in (yaml.safe_load(text) or {}).get("proxies") or [] if isinstance(p, dict)]
        except Exception:
            pass
    if "://" not in text[:2000]:
        try:
            t = text.strip()
            text = base64.b64decode(t + "=" * (-len(t) % 4)).decode("utf-8", "ignore")
        except Exception:
            return []
    return [remark(l.strip()) for l in text.splitlines() if re.match(r"^[a-z0-9+]+://", l.strip())]


def remark(link):
    if link.startswith("vmess://"):
        try:
            s = link[8:]
            return json.loads(base64.b64decode(s + "=" * (-len(s) % 4))).get("ps", "")
        except Exception:
            return ""
    return urllib.parse.unquote(link.split("#", 1)[1]) if "#" in link else ""


def flag(code):
    return "".join(chr(0x1F1E6 + ord(c) - 65) for c in code)


DELIM_L, DELIM_R = r"[\s\-|\[(]", r"[\s\-|\])/]"


def codes_in(name):
    """Country codes a server name claims: flag emoji, delimited 2-letter code, or English name."""
    found = set()
    ri = [c for c in name if 0x1F1E6 <= ord(c) <= 0x1F1FF]
    for i in range(0, len(ri) - 1, 2):
        found.add("".join(chr(ord(c) - 0x1F1E6 + 65) for c in ri[i:i + 2]))
    for m in re.finditer(rf"(?:^|{DELIM_L})([A-Z]{{2}})(?={DELIM_R}|$)", name):
        found.add(m.group(1))
    m = re.match(r"^([a-z]{2})\|", name)  # PuddinCat: "us|e623|…"
    if m:
        found.add(m.group(1).upper())
    for code, full in NAMES.items():
        if re.search(rf"(?:^|{DELIM_L}){re.escape(full)}(?={DELIM_R}|$)", name):
            found.add(code)
    return {ALIASES.get(c, c) for c in found}


def country_filter(code):
    """mihomo filter regex matching the same names codes_in() assigns to `code`."""
    alts = [flag(code)] + [flag(a) for a, c in ALIASES.items() if c == code]
    alts.append(rf"(^|{DELIM_L}){code}({DELIM_R}|$)")
    alts.append(rf"^{code.lower()}\|")
    alts.append(rf"(^|{DELIM_L}){re.escape(NAMES[code])}({DELIM_R}|$)")
    return "|".join(alts)


def q(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def main():
    named = collections.Counter()
    per_sub = {}
    failed = []
    for name, url in {**ACCURATE_LISTS, **FAST_LISTS}.items():
        try:
            ns = names_in(fetch(url))
        except Exception as e:
            print(f"! {name}: {e}")
            failed.append(name)
            per_sub[name] = 0
            continue
        per_sub[name] = len(ns)
        if name not in COUNTRY_LISTS:
            continue
        for n in ns:
            if re.search(EXCLUDE, n):
                continue
            for c in codes_in(n):
                if c in NAMES:
                    named[c] += 1

    try:
        au = {k.split("/")[1]: min(v, 2000)  # first shard only
              for k, v in json.loads(fetch(AU1RXX + "manifest.json"))["collections"].items()
              if k.startswith("country/") and k.split("/")[1] in NAMES and v >= MIN_SERVERS}
    except Exception as e:
        print(f"! Au1rxx manifest: {e}")
        failed.append("Au1rxx")
        au = {}
    total = collections.Counter(named) + collections.Counter(au)

    countries = [(c, n) for c, n in total.most_common() if n >= MIN_SERVERS]
    today = datetime.date.today().isoformat()

    y = [
        f"# free-clash-country-picker: generated {today} by tools/make_clash_config.py. Re-run to refresh countries.",
        "# Pick a country in the 'Country' group; each country group auto-uses its fastest server.",
        "mixed-port: 7897",
        "allow-lan: false",
        "mode: rule",
        "log-level: warning",
        "ipv6: false",
        "unified-delay: true",
        "tcp-concurrent: true",
        "",
        "dns:",
        "  enable: true",
        "  ipv6: false",
        "  enhanced-mode: fake-ip",
        "  fake-ip-range: 198.18.0.1/16",
        "  fake-ip-filter: ['*.lan', '+.local', '+.msftconnecttest.com', '+.msftncsi.com']",
        "  default-nameserver: [1.1.1.1, 8.8.8.8]",
        "  nameserver: ['https://1.1.1.1/dns-query', 'https://dns.google/dns-query']",
        "  proxy-server-nameserver: ['https://1.1.1.1/dns-query', 'https://dns.google/dns-query']",
        "",
        "proxy-providers:",
    ]

    def provider(name, url, path, prefix=None):
        p = [
            f"  {name}:",
            "    type: http",
            f"    url: {q(url)}",
            f"    path: ./providers/{path}",
            f"    interval: {PROVIDER_REFRESH}",
            f"    exclude-filter: {q(EXCLUDE)}",
        ]
        if prefix:
            p += ["    override:", f"      additional-prefix: {q(prefix)}"]
        return p

    y.append("  # Country labels in these names were right >= 89% of the time.")
    for name, url in ACCURATE_LISTS.items():
        y += provider(name, url, f"{name.lower()}.txt")
    y.append("  # Fast, but 30-50% of country labels are wrong. Also the 'Fastest anywhere' pool.")
    for name, url in FAST_LISTS.items():
        y += provider(name, url, f"{name.lower()}.txt")
    y.append("  # Au1rxx exit-verified servers; the prefix lets the country filter match them.")
    for c in sorted(au):
        y += provider(f"Au1rxx-{c}", f"{AU1RXX}country/{c}/clash-0001.yaml", f"au1rxx-{c.lower()}.yaml", f"{c} ")

    def test_group(gname, use, interval, filt=None):
        g = [
            f"  - name: {q(gname)}",
            "    type: url-test",
            f"    use: [{', '.join(use)}]",
        ]
        if filt:
            g.append(f"    filter: {q(filt)}")
        g += [
            f"    url: {q(TEST_URL)}",
            "    expected-status: 204",
            f"    interval: {interval}",
            f"    timeout: {TEST_TIMEOUT}",
            "    tolerance: 50",
            f"    max-failed-times: {MAX_FAILED}",
            "    lazy: true",
        ]
        return g

    choices = ["Fastest anywhere"] + [NAMES[c] for c, _ in countries] + ["DIRECT"]
    y += ["", "proxy-groups:",
          "  - name: Country",
          "    type: select",
          "    proxies:"]
    y += [f"      - {q(c)}" for c in choices]
    y += test_group("Fastest anywhere", list(FAST_LISTS), ANYWHERE_INTERVAL)
    for c, _ in countries:
        use = list(COUNTRY_LISTS) + ([f"Au1rxx-{c}"] if c in au else [])
        y += test_group(NAMES[c], use, COUNTRY_INTERVAL, country_filter(c))

    y += [
        "",
        "rules:",
        "  - GEOIP,LAN,DIRECT,no-resolve",
    ]
    if HOME_COUNTRY:
        y += [f"  - DOMAIN-SUFFIX,{HOME_COUNTRY.lower()},DIRECT", f"  - GEOIP,{HOME_COUNTRY.upper()},DIRECT"]
    y += ["  - MATCH,Country", ""]

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "profile.yaml"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(y))
    with open(os.path.join(OUT_DIR, "countries.json"), "w", encoding="utf-8") as f:
        json.dump({"generated": today, "servers_per_subscription": per_sub,
                   "named_servers_per_country": dict(named.most_common()),
                   "au1rxx_per_country": dict(sorted(au.items(), key=lambda kv: -kv[1])),
                   "total_per_country": dict(total.most_common())}, f, indent=2)

    print("servers per list:", per_sub)
    print(f"Au1rxx exit-verified files: {len(au)} countries, {sum(au.values())} servers")
    print(f"{len(countries)} country groups:", ", ".join(f"{NAMES[c]} {n}" for c, n in countries))
    print("written:", os.path.join(OUT_DIR, "profile.yaml"))
    if len(countries) < MIN_COUNTRIES:
        failed.append(f"only {len(countries)} countries")
    if failed:  # countries are missing; the scheduled update must not publish this
        sys.exit(f"! incomplete, not for publishing: {', '.join(failed)}")


if __name__ == "__main__":
    main()
