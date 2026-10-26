# Free Clash country picker

A generator for a [mihomo](https://github.com/MetaCubeX/mihomo) (Clash Meta) config built
from free, public V2Ray/Clash server lists. You pick a country and the config keeps you
on the fastest working server in that country. If that server dies, it switches to
another one.

**Quick start:** add this URL as a Remote profile in Clash Verge Rev, FlClash or any
other mihomo-based client, then pick a country in the **Country** group
([full setup](#setup)):

```
https://raw.githubusercontent.com/MrErrorSan/free-clash-country-picker/main/clash/profile.yaml
```

- `tools/make_clash_config.py`: fetches the lists and writes the config
- `clash/profile.yaml`: the generated config, ready to import
- `.github/workflows/refresh-profile.yml`: regenerates the config every 3 days

## Disclosure

- **None of the servers are mine.** They come from the third-party GitHub lists named
  in `ACCURATE_LISTS`, `FAST_LISTS` and `AU1RXX` at the top of the generator. I'm not
  affiliated with any of them, and they can change, break or vanish at any time.
- **Strangers run these servers, and they can see and log your traffic.** HTTPS content
  stays encrypted, but don't do banking or sensitive logins through them.
- **Country is best-effort.** It's read from the server's name, and some lists mislabel
  30–50% of servers, so sometimes you'll exit from a neighbouring country.
- **Built for personal use.** The sources were picked from a one-time test and may go
  stale. Test intervals are kept slow to save bandwidth.
- Getting around a school or work network block may break its usage policy. Check
  before you use it there.
- No warranty. This is a personal tool, not a VPN service.

## What the config does

- Pulls **8 free lists plus Au1rxx's exit-verified per-country files** (~8,600 servers)
  and re-downloads them every 4 h.
- **Country** group: the country picker (~50 countries). Each country is
  an auto-fastest (`url-test`) group across every list, filtered by the country in the
  server name. Only the group you're using gets tested.
- **Fastest anywhere**: the fastest server in any country (from Radikal-fast, F0rc3Run,
  Mahdibland and AwesomeVPN).
- Testing: a scheduled re-test every 30 min (60 min for Fastest anywhere). If the
  current server fails 3 times in a row, it re-tests and switches right away.
- Local network traffic goes direct. Everything else goes through the selected
  country, unless you add a [home-country rule](#optional-keep-your-own-countrys-sites-direct).

The first time you pick a big country (US, Japan, Netherlands, Germany), it can take a
few minutes while 1,000+ servers are tested. To test them all at once (~2 s), click the
speed-test icon on that group in **Proxies**.

To see where you appear: https://www.cloudflare.com/cdn-cgi/trace (`loc=`).

## Setup

Steps are for Clash Verge Rev (Windows, macOS, Linux). Other mihomo clients such as
[FlClash](https://github.com/chen08209/FlClash) (also on Android) take the same Remote
URL; their menus differ.

1. Install [Clash Verge Rev](https://github.com/clash-verge-rev/clash-verge-rev/releases)
   from its releases page. Pick the file for your OS.
2. **Profiles** → **New** → Type **Remote**, and paste this URL:

   ```
   https://raw.githubusercontent.com/MrErrorSan/free-clash-country-picker/main/clash/profile.yaml
   ```

   In the profile's settings, set **Update Interval** to `1440` minutes (once a day), so
   it picks up the [automatic refreshes](#automatic-refresh). Save, then click the card
   to make it active. The first load downloads ~58 lists, so give it ~20 s.

   Prefer not to depend on GitHub? Use Type **Local** and pick `clash/profile.yaml`
   from a clone instead. A local profile doesn't auto-update.
3. **Proxies** → **Country** → click a country. Countries near you usually have the
   lowest ping.
4. Turn on **System Proxy**. That covers browsers and most apps.
5. Optional: turn on **TUN Mode** to route every app (games, Discord) through it.
   Clash Verge asks to install its Service Mode once, which needs admin rights.

To turn it off, switch off System Proxy / TUN, or quit from the system tray / menu bar.

### Optional: keep your own country's sites direct

Local banks and government sites often block foreign IPs. To send your own country's
traffic direct, add the rule in Clash Verge rather than in this repo: right-click the
profile → **Edit Rules** → add these to the top (replace `XX` with your two-letter
country code), then Save:

```
DOMAIN-SUFFIX,xx,DIRECT
GEOIP,XX,DIRECT
```

These rules stay on your device and survive profile updates. If you regenerate the config
yourself, you can set `HOME_COUNTRY` in the generator instead.

**Download managers** usually follow the system proxy. If one doesn't, use TUN Mode.
Keep downloads to 4–8 connections each, because many parallel connections can overload a
free server. **Cloudflare-protected sites** may show a captcha or block some free-server
IPs. If that happens, switch server or country.

## Automatic refresh

There are two levels of refresh, and neither needs you:

- **Servers** inside each country: Clash Verge re-downloads the lists every 4 h.
- **The profile itself** (which countries get a group, and in what order): the GitHub
  Action [`refresh-profile.yml`](.github/workflows/refresh-profile.yml) re-runs the
  generator every 3 days and commits the new `clash/profile.yaml`. A Remote profile
  picks that up on its next update. To refresh right away, open the **Actions** tab →
  *Refresh profile* → **Run workflow**, then click update on the profile card.

The Action only pulls from the lists already in the generator. It never adds new sources
on its own, because a random new list isn't trusted until it has been tested (see
[Re-checking sources](#re-checking-sources)). If any list fails to download, the run
fails and the last good profile stays in place.

GitHub turns off scheduled workflows in a repo after 60 days with no activity. The
Action's own commits normally prevent this, but if it ever stops, re-enable it from the
Actions tab.

To regenerate by hand:

```
python -I tools/make_clash_config.py
```

Then commit and push `clash/profile.yaml`. With a Local profile, delete the old
profile in Clash Verge and import the file again, because Clash Verge keeps its own copy.

Settings at the top of the script:

| Setting | What it does |
|---|---|
| `ACCURATE_LISTS` / `FAST_LISTS` | which lists are used |
| `STRICT_LABELS = True` | country groups use only lists whose labels were ≥ 89% correct (fewer servers, but you exit where you picked) |
| `MIN_SERVERS` | countries with fewer servers get no group (default 3) |
| `TEST_TIMEOUT`, `*_INTERVAL` | test timeout and how often servers are re-tested |

## Re-checking sources

Free lists come and go. Both scripts need Clash Verge's `verge-mihomo.exe` and PyYAML,
and they write to `results/` (gitignored).

- `tools/evaluate_sources.py`: what % of each candidate list is alive, sampled through
  a private mihomo instance that never touches the running Clash Verge.
- `tools/check_exit_labels.py`: for servers that pass, whether they carry real traffic
  and whether the country label matches the real exit.

Findings from 2026-10-25 (26 lists tested):

- Labels were right ≥ 89% of the time for Au1rxx per-country files (100%), Rooster,
  Mahdi0024, PuddinCat and Snakem982. Radikal-fast, F0rc3Run, AwesomeVPN and
  Mahdibland were fast but only 47–71% right. Those mislabelled servers tend to be the
  fastest, so a lowest-latency picker chooses them first.
- Dropped: anything below 50% alive, Barry-Sub1 (fully duplicated elsewhere), Firmfox,
  MegaV, Kooker, Pawdroid, and SoliSpirit / MhdiTaheri (mihomo can't load them).
- **One bad entry makes mihomo drop the whole list.** For example, F0rc3Run's link list
  has a Shadowsocks server with a cipher mihomo rejects, so its `clash.yaml` is used
  instead. Having several sources per country guards against this.

## License

[MIT](LICENSE) for the code and the generated config in this repo. The server lists it
points to, and the servers in them, belong to their owners and come under their own terms.
