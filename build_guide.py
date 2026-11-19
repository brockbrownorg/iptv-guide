#!/usr/bin/env python3
"""Build a custom XMLTV guide for Brock's iptv-org playlist.

Downloads the iptv-org full index playlist, downloads the free EPG sources
that were verified on 2026-11-06, matches playlist channels to guide
channels (Pluto stream-URL codes first, then unique normalized name
matches), and writes public/guide.xml.gz with channel IDs rewritten to the
playlist's own IDs so Opus lines the guide up with no remapping.

Run:  python3 build_guide.py
Output: public/guide.xml.gz  (plus a small public/index.html landing page)
"""
import gzip, json, os, re, sys, unicodedata, urllib.request
from collections import defaultdict
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape, quoteattr

PLAYLIST_URL = "https://iptv-org.github.io/iptv/countries/us.m3u"

# filename -> download URL. epg.pw and epgshare01 URLs were handed to Brock
# on 2026-11-06/07 and checked live then. The i.mjh.nz files follow the
# matthuisman/i.mjh.nz pattern verified for PlutoTV/all.xml.gz and
# Roku/all.xml.gz; the Plex / SamsungTVPlus / PBS siblings follow the same
# folder pattern (the 2026-11-06 build used files named plex_all,
# samsung_all and pbs_all from this same index).
SOURCES = {
    "pluto_all.xml.gz":    "https://github.com/matthuisman/i.mjh.nz/raw/master/PlutoTV/all.xml.gz",
    "plex_all.xml.gz":     "https://github.com/matthuisman/i.mjh.nz/raw/master/Plex/all.xml.gz",
    "roku_all.xml.gz":     "https://github.com/matthuisman/i.mjh.nz/raw/master/Roku/all.xml.gz",
    "samsung_all.xml.gz":  "https://github.com/matthuisman/i.mjh.nz/raw/master/SamsungTVPlus/all.xml.gz",
    "epgpw_US.xml.gz":     "https://epg.pw/xmltv/epg_US.xml.gz",
    "pbs_all.xml.gz":      "https://github.com/matthuisman/i.mjh.nz/raw/master/PBS/all.xml.gz",
    "epgshare_US2.xml.gz": "https://epgshare01.online/epgshare01/epg_ripper_US2.xml.gz",
}

WORK = "work"
OUT_DIR = "public"
os.makedirs(WORK, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)


def fetch(url, dest):
    print(f"download {url}", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (guide-builder)"})
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    print(f"  -> {dest} ({os.path.getsize(dest)} bytes)", flush=True)


# ---------- 1. playlist ----------
fetch(PLAYLIST_URL, os.path.join(WORK, "us.m3u"))
entries = []
with open(os.path.join(WORK, "us.m3u"), encoding="utf-8", errors="replace") as f:
    for line in f:
        m = re.search(r'tvg-id="([^"]+)"', line)
        if not m:
            continue
        full = m.group(1)
        name = line.rsplit(",", 1)[-1].strip()
        url = ""
        entries.append({"full": full, "base": full.split("@")[0], "name": name, "url": url, "_pending_url": True})
# stream URL is the line after each #EXTINF line; second pass keeps it simple:
with open(os.path.join(WORK, "us.m3u"), encoding="utf-8", errors="replace") as f:
    lines = f.read().splitlines()
by_full = {}
for i, line in enumerate(lines):
    m = re.search(r'tvg-id="([^"]+)"', line)
    if m and i + 1 < len(lines):
        by_full.setdefault(m.group(1), lines[i + 1].strip())
for e in entries:
    e["url"] = by_full.get(e["full"], "")
    e.pop("_pending_url", None)
print(f"playlist entries: {len(entries)}")

logos = {}
with open(os.path.join(WORK, "us.m3u"), encoding="utf-8", errors="replace") as f:
    for line in f:
        m = re.search(r'tvg-id="([^"]+)"', line)
        if m:
            base = m.group(1).split("@")[0]
            lm = re.search(r'tvg-logo="([^"]+)"', line)
            if lm and base not in logos:
                logos[base] = lm.group(1)

# ---------- 2. source channel lists ----------
for fname, url in SOURCES.items():
    fetch(url, os.path.join(WORK, fname))

def source_channels(fname):
    """id -> [display names] from one XMLTV gz."""
    chans = {}
    with gzip.open(os.path.join(WORK, fname), "rb") as f:
        for ev, el in ET.iterparse(f, events=("end",)):
            if el.tag == "channel":
                cid = el.get("id")
                names = [dn.text for dn in el.findall("display-name") if dn.text]
                if cid and names:
                    chans[cid] = names
                el.clear()
    return chans

chan_cache = {}
def channels_for(fname):
    if fname not in chan_cache:
        chan_cache[fname] = source_channels(fname)
        print(f"{fname}: {len(chan_cache[fname])} channels", flush=True)
    return chan_cache[fname]

# ---------- 3. matching (same logic/order as the 2026-11-06 build) ----------
def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

STOP = {"hd", "sd", "uhd", "4k", "east", "west", "eastern", "western",
        "pacific", "central", "mountain", "feed", "tv", "channel"}
def core(s):
    s = re.sub(r"\([^)]*\)", " ", s)
    toks = norm(s).split()
    while toks and toks[-1] in STOP:
        toks.pop()
    return " ".join(toks)

def keys(name, use_core):
    return {norm(name), core(name)} if use_core else {norm(name)}

base_info = {}
for e in entries:
    base_info.setdefault(e["base"], e)

matches = {}
def claim(base, source, sid, via, sname):
    if base not in matches:
        matches[base] = {"source": source, "source_id": sid, "via": via, "source_name": sname}

pluto_ch = channels_for("pluto_all.xml.gz")
for e in entries:
    m = re.search(r"plu-([0-9a-f]{24})\.m3u8", e["url"])
    if m and m.group(1) in pluto_ch:
        claim(e["base"], "pluto_all.xml.gz", m.group(1), "pluto-hex", pluto_ch[m.group(1)][0])

def name_match(source_file, scope_fn, use_core, label):
    chans = channels_for(source_file)
    key2ids = defaultdict(set)
    id2name = {}
    for sid, names in chans.items():
        id2name[sid] = names[0]
        for nm in names:
            for k in keys(nm, use_core):
                if k:
                    key2ids[k].add(sid)
    key2bases = defaultdict(set)
    for base, e in base_info.items():
        if not scope_fn(base, e):
            continue
        for k in keys(e["name"], use_core):
            if k:
                key2bases[k].add(base)
    n = 0
    for k, bases in key2bases.items():
        if len(bases) != 1:
            continue
        ids = key2ids.get(k, set())
        if len(ids) != 1:
            continue
        base = next(iter(bases)); sid = next(iter(ids))
        before = len(matches)
        claim(base, source_file, sid, label, id2name[sid])
        n += len(matches) - before
    return n

us_only = lambda base, e: base.endswith(".us")
print("epgpw US:", name_match("epgpw_US.xml.gz", us_only, True, "name-epgpw"))
print("epgshare US:", name_match("epgshare_US2.xml.gz", us_only, True, "name-epgshare"))
print("samsung:", name_match("samsung_all.xml.gz", lambda b, e: True, False, "name-samsung"))
print("plex:", name_match("plex_all.xml.gz", lambda b, e: True, True, "name-plex"))
print("roku:", name_match("roku_all.xml.gz", lambda b, e: True, True, "name-roku"))
print("pbs:", name_match("pbs_all.xml.gz", lambda b, e: True, True, "name-pbs"))
print(f"TOTAL covered: {len(matches)} / {len(base_info)}")

# ---------- 4. build ----------
names = {}
for e in entries:
    names.setdefault(e["base"], e["name"])

by_source = {}
for base, m in matches.items():
    by_source.setdefault(m["source"], {})[m["source_id"]] = base

today = datetime.now(timezone.utc).strftime("%Y%m%d") + "000000"
KEEP_CHILD = {"title", "sub-title", "desc", "category", "episode-num", "date", "country"}
total_prog = 0
min_start, max_stop = "9999", "0"

raw_path = os.path.join(WORK, "guide.xml")
out = open(raw_path, "w", encoding="utf-8")
out.write('<?xml version="1.0" encoding="UTF-8"?>\n')
out.write(f'<tv generator-info-name="Juno guide for Brock - iptv-org playlist + free EPG sources (epg.pw, i.mjh.nz, epgshare01)" date="{datetime.now(timezone.utc).strftime("%Y%m%d")}">\n')
for base in sorted(matches):
    out.write(f"  <channel id={quoteattr(base)}>\n    <display-name>{escape(names.get(base, base))}</display-name>\n")
    if base in logos:
        out.write(f"    <icon src={quoteattr(logos[base])}/>\n")
    out.write("  </channel>\n")

for src, idmap in by_source.items():
    n = 0
    with gzip.open(os.path.join(WORK, src), "rb") as f:
        for ev, el in ET.iterparse(f, events=("end",)):
            if el.tag == "programme":
                sid = el.get("channel")
                if sid in idmap:
                    start = el.get("start", "")
                    if start[:14] >= today:
                        base = idmap[sid]
                        parts = [f"  <programme channel={quoteattr(base)} start={quoteattr(start)} stop={quoteattr(el.get('stop', ''))}>"]
                        for child in el:
                            if child.tag in KEEP_CHILD and child.text:
                                txt = child.text
                                if child.tag == "desc" and len(txt) > 600:
                                    txt = txt[:600]
                                attrs = ""
                                if child.tag == "episode-num" and child.get("system"):
                                    attrs = f" system={quoteattr(child.get('system'))}"
                                parts.append(f"    <{child.tag}{attrs}>{escape(txt)}</{child.tag}>")
                        parts.append("  </programme>")
                        out.write("\n".join(parts) + "\n")
                        n += 1
                        if start < min_start: min_start = start
                        stop = el.get("stop", "")
                        if stop > max_stop: max_stop = stop
                el.clear()
    print(f"{src}: programmes kept {n}", flush=True)
    total_prog += n
out.write("</tv>\n")
out.close()

gz_path = os.path.join(OUT_DIR, "guide.xml.gz")
with open(raw_path, "rb") as fin, gzip.open(gz_path, "wb", compresslevel=6) as fout:
    while True:
        chunk = fin.read(1 << 20)
        if not chunk:
            break
        fout.write(chunk)

# ---------- 5. matched US playlist ----------
# Entries are written in a browsing-friendly category order (Movies first,
# then Series, Entertainment, and so on) because most players list groups in
# playlist order. Channels tagged "Undefined" upstream are filed as General.
PRIORITY = {"Movies": 0, "Series": 1, "Entertainment": 2, "Comedy": 3,
            "News": 4, "Sports": 5, "Documentary": 6, "Kids": 7,
            "Animation": 8, "Family": 9, "Music": 10, "Classic": 11,
            "Cooking": 12, "Lifestyle": 13, "Education": 14, "Travel": 15,
            "Culture": 16, "Science": 17, "Outdoor": 18, "Auto": 19,
            "Weather": 20, "Business": 21, "Shop": 22, "Religious": 23,
            "General": 24}
plines = []
with open(os.path.join(WORK, "us.m3u"), encoding="utf-8", errors="replace") as f:
    plines = f.read().splitlines()
picked = []
for i, line in enumerate(plines):
    m = re.search(r'tvg-id="([^"]+)"', line)
    if not m:
        continue
    base = m.group(1).split("@")[0]
    if base in matches and i + 1 < len(plines):
        line = re.sub(r'tvg-id="[^"]+"', f'tvg-id="{base}"', line)
        line = line.replace('group-title="Undefined"', 'group-title="General"')
        gm = re.search(r'group-title="([^"]+)"', line)
        primary = gm.group(1).split(";")[0].strip() if gm else "General"
        picked.append((PRIORITY.get(primary, 25), line.rsplit(",", 1)[-1].strip().lower(), line, plines[i + 1]))
picked.sort(key=lambda t: (t[0], t[1]))
with open(os.path.join(OUT_DIR, "us-playlist.m3u"), "w", encoding="utf-8") as f:
    f.write('#EXTM3U url-tvg="https://brockbrownorg.github.io/iptv-guide/guide.xml.gz"\n')
    for _, _, line, url in picked:
        f.write(line + "\n")
        f.write(url + "\n")
print(f"playlist entries kept: {len(picked)}")

with open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as f:
    f.write(f"""<!doctype html><title>US IPTV playlist and guide for Brock</title>
<h1>US IPTV playlist + custom guide</h1>
<p>Playlist (US channels with guide data): <a href="us-playlist.m3u">us-playlist.m3u</a></p>
<p>Guide file: <a href="guide.xml.gz">guide.xml.gz</a></p>
<p>{len(matches)} channels, {total_prog} programmes, {min_start[:8]} to {max_stop[:8]}.
Rebuilt daily by GitHub Actions from the iptv-org US playlist and free EPG sources.</p>
<p>In Opus, add the us-playlist.m3u URL above as the playlist. Its header already points
at the guide, and the guide channel IDs are rewritten to match the playlist IDs.</p>
""")
print(f"DONE channels={len(matches)} programmes={total_prog} range={min_start}..{max_stop} size={os.path.getsize(gz_path)}")
