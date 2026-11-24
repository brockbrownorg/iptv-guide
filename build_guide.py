#!/usr/bin/env python3
"""Build Brock's US IPTV playlist + matching XMLTV guide.

Two reputable, self-updating source families, both free and legal:

1. iptv-org's US playlist (https://iptv-org.github.io/iptv/countries/us.m3u),
   guide-matched by name against epg.pw US, epgshare01 US and the
   matthuisman i.mjh.nz guides (Pluto, Plex, Roku, Samsung TV Plus, PBS).
   Pluto channels also match exactly by the code in their stream URL.

2. BuddyChewChew's app-m3u-generator service playlists (Pluto TV US,
   Samsung TV Plus US, Plex US, Roku, Xumo, Tubi). These are generated
   from the services themselves and their channel IDs match their guide
   files by design (i.mjh.nz US guides for Pluto / Samsung / Plex / Roku,
   the generators' own EPG for Xumo and Tubi), so every kept channel has
   real programme data. IDs are prefixed per service to avoid collisions.

Output (in public/):
  us-playlist.m3u  - channels with guide data (IDs rewritten to match the
                     guide) plus playlist-only channels from the extra
                     sources in section 3b (iptv-org remainder, Free-TV
                     USA, APSatTV bundles; no guide data for those),
                     ordered Movies first, then Series, Entertainment,
                     Comedy, News, Sports, and so on.
  guide.xml.gz     - XMLTV programmes from today (UTC) forward.
  vod-library.m3u  - separate on-demand movie library (PublicDomainM3U:
                     public-domain films and episodes from Archive.org,
                     genre group-titles kept as shelves).
  index.html       - small landing page with the links and counts.
"""
import gzip, io, os, re, unicodedata, urllib.request
from collections import defaultdict
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape, quoteattr

PLAYLIST_URL = "https://iptv-org.github.io/iptv/countries/us.m3u"
GUIDE_URL = "https://brockbrownorg.github.io/iptv-guide/guide.xml.gz"

SOURCES = {
    "pluto_all.xml.gz":    "https://github.com/matthuisman/i.mjh.nz/raw/master/PlutoTV/all.xml.gz",
    "plex_all.xml.gz":     "https://github.com/matthuisman/i.mjh.nz/raw/master/Plex/all.xml.gz",
    "roku_all.xml.gz":     "https://github.com/matthuisman/i.mjh.nz/raw/master/Roku/all.xml.gz",
    "samsung_all.xml.gz":  "https://github.com/matthuisman/i.mjh.nz/raw/master/SamsungTVPlus/all.xml.gz",
    "epgpw_US.xml.gz":     "https://epg.pw/xmltv/epg_US.xml.gz",
    "pbs_all.xml.gz":      "https://github.com/matthuisman/i.mjh.nz/raw/master/PBS/all.xml.gz",
    "epgshare_US2.xml.gz": "https://epgshare01.online/epgshare01/epg_ripper_US2.xml.gz",
}

BUDDY = [
    # service, playlist URL, epg filename, epg URL
    ("pluto",   "https://raw.githubusercontent.com/BuddyChewChew/app-m3u-generator/main/playlists/plutotv_us.m3u",
     "buddy_pluto.xml.gz",   "https://github.com/matthuisman/i.mjh.nz/raw/master/PlutoTV/us.xml.gz"),
    ("samsung", "https://raw.githubusercontent.com/BuddyChewChew/app-m3u-generator/main/playlists/samsungtvplus_us.m3u",
     "buddy_samsung.xml.gz", "https://github.com/matthuisman/i.mjh.nz/raw/master/SamsungTVPlus/us.xml.gz"),
    ("plex",    "https://raw.githubusercontent.com/BuddyChewChew/app-m3u-generator/main/playlists/plex_us.m3u",
     "buddy_plex.xml.gz",    "https://github.com/matthuisman/i.mjh.nz/raw/master/Plex/us.xml.gz"),
    ("roku",    "https://raw.githubusercontent.com/BuddyChewChew/app-m3u-generator/main/playlists/roku_all.m3u",
     "buddy_roku.xml.gz",    "https://github.com/matthuisman/i.mjh.nz/raw/master/Roku/all.xml.gz"),
    ("xumo",    "https://raw.githubusercontent.com/BuddyChewChew/xumo-playlist-generator/main/playlists/xumo_playlist.m3u",
     "buddy_xumo.xml.gz",    "https://raw.githubusercontent.com/BuddyChewChew/xumo-playlist-generator/main/playlists/xumo_epg.xml.gz"),
    ("tubi",    "https://raw.githubusercontent.com/BuddyChewChew/app-m3u-generator/main/playlists/tubi_all.m3u",
     "buddy_tubi.xml",       "https://raw.githubusercontent.com/BuddyChewChew/app-m3u-generator/main/playlists/tubi_epg.xml"),
    ("lg",      "https://raw.githubusercontent.com/BuddyChewChew/lg-playlist-generator/refs/heads/main/lg_channels_us.m3u",
     "buddy_lg.xml",         "https://raw.githubusercontent.com/BuddyChewChew/lg-playlist-generator/main/lg_channels_us.xml"),
]

GROUP_MAP = {
    "Movies": "Movies", "Movie": "Movies", "Action & Drama": "Movies",
    "Sci-Fi": "Movies", "Sci-Fi & Horror": "Movies", "Horror & Sci-Fi": "Movies",
    "Westerns": "Movies", "Drama": "Series",
    "Classic TV": "Classic", "Western & Classic TV": "Classic", "Classic": "Classic",
    "Comedy": "Comedy",
    "News": "News", "News + Opinion": "News", "News & Opinion": "News",
    "Local News": "News", "National News": "News",
    "Sports": "Sports", "Sports & Outdoors": "Sports", "Motor Sports": "Sports",
    "Sports On Now": "Sports", "3X3 Basketball": "Sports",
    "Kids": "Kids", "Family": "Kids",
    "Anime": "Animation", "Anime & Gaming": "Animation", "Animation": "Animation",
    "Music": "Music", "Music Videos": "Music",
    "True Crime": "Documentary", "Crime": "Documentary", "Crime TV": "Documentary",
    "Nature, History & Science": "Documentary", "History + Science": "Documentary",
    "Animals": "Documentary", "Animals + Nature": "Documentary",
    "Documentary": "Documentary",
    "Home + Food": "Cooking", "Home & Food": "Cooking", "Cooking": "Cooking",
    "Lifestyle": "Lifestyle",
    "Education": "Education", "Travel": "Travel", "Culture": "Culture",
    "Science": "Science", "Outdoor": "Outdoor", "Auto": "Auto",
    "Weather": "Weather", "Business": "Business", "Shop": "Shop",
    "Religious": "Religious",
}

PRIORITY = {"Movies": 0, "Series": 1, "Entertainment": 2, "Comedy": 3,
            "News": 4, "Sports": 5, "Documentary": 6, "Kids": 7,
            "Animation": 8, "Family": 9, "Music": 10, "Classic": 11,
            "Cooking": 12, "Lifestyle": 13, "Education": 14, "Travel": 15,
            "Culture": 16, "Science": 17, "Outdoor": 18, "Auto": 19,
            "Weather": 20, "Business": 21, "Shop": 22, "Religious": 23,
            "General": 24}

WORK = "work"
OUT_DIR = "public"
os.makedirs(WORK, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)
TODAY = datetime.now(timezone.utc).strftime("%Y%m%d") + "000000"


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


def epg_stream(path):
    """Buddy EPG files as a parseable stream. The LG generator's EPG
    ships bare '&' characters in some titles (invalid XML that
    ElementTree rejects outright), so escape any ampersand that does
    not start a valid entity before parsing. Valid files are
    unaffected: a literal '&' in well-formed XML is always escaped."""
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rb") as f:
        data = f.read()
    data = re.sub(rb"&(?!amp;|lt;|gt;|quot;|apos;|#)", b"&amp;", data)
    return io.BytesIO(data)


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

# ---------- 1. iptv-org US playlist ----------
fetch(PLAYLIST_URL, os.path.join(WORK, "us.m3u"))
with open(os.path.join(WORK, "us.m3u"), encoding="utf-8", errors="replace") as f:
    lines = f.read().splitlines()
entries = []
by_full = {}
for i, line in enumerate(lines):
    m = re.search(r'tvg-id="([^"]+)"', line)
    if m and i + 1 < len(lines):
        by_full.setdefault(m.group(1), lines[i + 1].strip())
        entries.append({"full": m.group(1), "base": m.group(1).split("@")[0],
                        "name": line.rsplit(",", 1)[-1].strip(),
                        "url": lines[i + 1].strip(), "line": line})
print(f"playlist entries: {len(entries)}")
logos = {}
for e in entries:
    lm = re.search(r'tvg-logo="([^"]+)"', e["line"])
    if lm and e["base"] not in logos:
        logos[e["base"]] = lm.group(1)

# ---------- 2. name matching against the guide sources ----------
for fname, url in SOURCES.items():
    fetch(url, os.path.join(WORK, fname))

def source_channels(fname):
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

def keys(name, use_core):
    return {norm(name), core(name)} if use_core else {norm(name)}

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
print(f"iptv-org covered: {len(matches)} / {len(base_info)}")

# ---------- 3. BuddyChewChew service playlists (IDs match their EPG) ----------
seen_names = {core(base_info[b]["name"]) for b in matches}
buddy_entries = []          # dicts: gid, name, logo, category, url
buddy_epg = {}              # service -> (filename, {orig_id: gid})
for service, pl_url, epg_fname, epg_url in BUDDY:
    pl_path = os.path.join(WORK, f"buddy_{service}.m3u")
    try:
        fetch(pl_url, pl_path)
        fetch(epg_url, os.path.join(WORK, epg_fname))
    except Exception as e:
        # An upstream service playlist can vanish (Tubi's did, Nov 2026);
        # skip that service instead of failing the whole build.
        print(f"SKIP {service}: source unavailable ({e})", flush=True)
        continue
    # which EPG channel ids actually have programmes from today forward?
    have_prog = set()
    chan_names = {}
    with epg_stream(os.path.join(WORK, epg_fname)) as f:
        for ev, el in ET.iterparse(f, events=("end",)):
            if el.tag == "channel":
                cid = el.get("id")
                names = [dn.text for dn in el.findall("display-name") if dn.text]
                if cid and names:
                    chan_names[cid] = names[0]
                el.clear()
            elif el.tag == "programme":
                if el.get("start", "")[:14] >= TODAY:
                    have_prog.add(el.get("channel"))
                el.clear()
    idmap = {}
    kept = 0
    with open(pl_path, encoding="utf-8", errors="replace") as f:
        plines = f.read().splitlines()
    for i, line in enumerate(plines):
        if not line.startswith("#EXTINF"):
            continue
        m = re.search(r'tvg-id="([^"]+)"', line)
        if not m or i + 1 >= len(plines):
            continue
        oid = m.group(1)
        if oid not in have_prog:
            continue
        name = line.rsplit(",", 1)[-1].strip()
        ck = core(name)
        if not ck or ck in seen_names:
            continue
        gm = re.search(r'group-title="([^"]+)"', line)
        group = gm.group(1).split(";")[0].strip() if gm else ""
        category = GROUP_MAP.get(group)
        if category is None:
            if service == "plex":
                low = name.lower()
                if any(w in low for w in ("movie", "cinema", "film")):
                    category = "Movies"
                elif "news" in low:
                    category = "News"
                elif "sport" in low:
                    category = "Sports"
                elif any(w in low for w in ("kids", "family")):
                    category = "Kids"
                else:
                    category = "Entertainment"
            else:
                category = "Entertainment"
        lm = re.search(r'tvg-logo="([^"]+)"', line)
        gid = f"{service}-{oid}"
        idmap[oid] = gid
        seen_names.add(ck)
        buddy_entries.append({"gid": gid, "name": name,
                              "logo": lm.group(1) if lm else "",
                              "category": category, "url": plines[i + 1].strip()})
        kept += 1
    buddy_epg[service] = (epg_fname, idmap)
    print(f"buddy {service}: kept {kept} channels with guide data", flush=True)
print(f"buddy total: {len(buddy_entries)}")

# ---------- 3b. extra playlist-only sources (no EPG requirement) ----------
# Added Nov 24, 2026 from the expansion research. These sources add
# channels that carry no guide data in this build, deduped by normalized
# name against everything already kept (existing services win). Every
# fetch is failure-tolerant: a dead source is skipped, never fatal.
def fetch_text(url, timeout=60):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (guide-builder)"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"fetch failed {url}: {e}", flush=True)
        return None

def parse_m3u(text):
    pairs = []
    ls = text.splitlines()
    for i, line in enumerate(ls):
        if line.startswith("#EXTINF") and i + 1 < len(ls):
            pairs.append((line, ls[i + 1].strip()))
    return pairs

def sanitize_id(s):
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", s).strip("-") or "x"

ADULT_HINTS = ("xxx", "adult", "porn")
def is_adult(group):
    g = (group or "").lower()
    return any(h in g for h in ADULT_HINTS)

def primary_group(line):
    gm = re.search(r'group-title="([^"]+)"', line)
    if not gm:
        return "General"
    g = gm.group(1).split(";")[0].strip()
    return "General" if g in ("", "Undefined") else g

extra_entries = []   # same shape as buddy_entries
extra_stats = {}     # label -> (fetched, added)
extra_ids = set()
def add_extra(gid, name, logo, category, url):
    if gid in extra_ids:
        return False
    extra_ids.add(gid)
    extra_entries.append({"gid": gid, "name": name, "logo": logo,
                          "category": category, "url": url})
    return True

# iptv-org remainder: every US entry not already in the build via the
# guide match (section 2) or a Buddy service (section 3). The us.m3u
# header is a bare "#EXTM3U" (checked Nov 24, 2026): it declares no
# url-tvg / x-tvg-url guide, so these channels are added with no EPG
# rather than inventing a guide URL. If a future header does declare
# guide URLs, they are downloaded below and any iptv-org channels whose
# ids appear there with programmes are merged into the guide in
# section 4 (guarded, size-capped, failure-tolerant).
first_line = lines[0] if lines else ""
declared_guides = re.findall(r'(?:x-tvg-url|url-tvg)="([^"]+)"', first_line)
iptvorg_epg_map = {}   # gid -> (work filename, guide channel id)
iptvorg_srcid = {}     # gid -> original iptv-org tvg-id
new_cores = set()
n_add = 0
for e in entries:
    if e["base"] in matches:
        continue
    ck = core(e["name"])
    if not ck or ck in seen_names:
        continue
    group = primary_group(e["line"])
    if is_adult(group):
        continue
    gid = "iptvorg-" + sanitize_id(e["full"])
    lm = re.search(r'tvg-logo="([^"]+)"', e["line"])
    if add_extra(gid, e["name"], lm.group(1) if lm else "", group, e["url"]):
        iptvorg_srcid[gid] = e["full"]
        new_cores.add(ck)
        n_add += 1
seen_names |= new_cores
extra_stats["iptv-org remainder"] = (len(entries), n_add)
print(f"extra iptv-org remainder: fetched {len(entries)}, added {n_add} after dedupe", flush=True)

if declared_guides:
    print(f"iptv-org header declares guide(s): {declared_guides}", flush=True)
    for gi, gurl in enumerate(declared_guides):
        gname = f"iptvorg_epg_{gi}.xml" + (".gz" if gurl.endswith(".gz") else "")
        try:
            fetch(gurl, os.path.join(WORK, gname))
            if os.path.getsize(os.path.join(WORK, gname)) > 60_000_000:
                print("iptv-org declared guide too large, skipping merge", flush=True)
                continue
        except Exception as e:
            print(f"iptv-org declared guide unavailable ({e})", flush=True)
            continue
        gopener = gzip.open if gname.endswith(".gz") else open
        have = set()
        with gopener(os.path.join(WORK, gname), "rb") as f:
            for ev, el in ET.iterparse(f, events=("end",)):
                if el.tag == "programme" and el.get("start", "")[:14] >= TODAY:
                    have.add(el.get("channel"))
                el.clear()
        for ex in extra_entries:
            if ex["gid"] in iptvorg_srcid:
                full = iptvorg_srcid[ex["gid"]]
                for cand in (full, full.split("@")[0]):
                    if cand in have:
                        iptvorg_epg_map[ex["gid"]] = (gname, cand)
                        break
    print(f"iptv-org declared-guide matches: {len(iptvorg_epg_map)}", flush=True)
else:
    print("iptv-org header declares no guide; remainder added with no EPG", flush=True)

# Free-TV USA: hand-curated OTA/subchannel list. Its own x-tvg-url header
# (100+ epgshare01 files) is ignored on purpose.
ft_text = fetch_text("https://raw.githubusercontent.com/Free-TV/IPTV/master/playlists/playlist_usa.m3u8")
ft_fetch = ft_add = 0
if ft_text:
    ft_pairs = parse_m3u(ft_text)
    ft_fetch = len(ft_pairs)
    for line, url in ft_pairs:
        name = line.rsplit(",", 1)[-1].strip()
        ck = core(name)
        if not ck or ck in seen_names:
            continue
        group = primary_group(line)
        if is_adult(group):
            continue
        m = re.search(r'tvg-id="([^"]+)"', line)
        gid = "freetv-" + sanitize_id(m.group(1) if m else name)
        lm = re.search(r'tvg-logo="([^"]+)"', line)
        if add_extra(gid, name, lm.group(1) if lm else "", group, url):
            seen_names.add(ck)
            ft_add += 1
extra_stats["Free-TV USA"] = (ft_fetch, ft_add)
print(f"extra Free-TV USA: fetched {ft_fetch}, added {ft_add} after dedupe", flush=True)

# APSatTV device bundles: gated. A list is included only if it downloads
# and parses to at least one entry; any failure skips it silently.
APSAT = [("vizio",    "https://www.apsattv.com/vizio.m3u"),
         ("tcl",      "https://www.apsattv.com/tcl.m3u"),
         ("tablo",    "https://www.apsattv.com/tablo.m3u"),
         ("firetv",   "https://www.apsattv.com/firetv.m3u"),
         ("localnow", "https://www.apsattv.com/localnow.m3u"),
         ("cineverse", "https://www.apsattv.com/cineverse.m3u"),
         ("vidaa",    "https://www.apsattv.com/vidaa.m3u")]
for slug, aurl in APSAT:
    a_fetch = a_add = 0
    atext = fetch_text(aurl, timeout=30)
    if atext:
        a_pairs = parse_m3u(atext)
        a_fetch = len(a_pairs)
        for line, url in a_pairs:
            name = line.rsplit(",", 1)[-1].strip()
            ck = core(name)
            if not ck or ck in seen_names:
                continue
            group = primary_group(line)
            if is_adult(group):
                continue
            m = re.search(r'tvg-id="([^"]+)"', line)
            gid = f"apsat-{slug}-" + sanitize_id(m.group(1) if m else name)
            lm = re.search(r'tvg-logo="([^"]+)"', line)
            if add_extra(gid, name, lm.group(1) if lm else "", group, url):
                seen_names.add(ck)
                a_add += 1
    extra_stats[f"APSatTV {slug}"] = (a_fetch, a_add)
    print(f"extra APSatTV {slug}: fetched {a_fetch}, added {a_add} after dedupe", flush=True)
print(f"extra total: {len(extra_entries)}")

# ---------- 4. write the guide ----------
names = {}
for e in entries:
    names.setdefault(e["base"], e["name"])
by_source = {}
for base, m in matches.items():
    by_source.setdefault(m["source"], {})[m["source_id"]] = base

KEEP_CHILD = {"title", "sub-title", "desc", "category", "episode-num", "date", "country"}
total_prog = 0
min_start, max_stop = "9999", "0"

def write_programme(out, gid, el):
    global total_prog, min_start, max_stop
    start = el.get("start", "")
    parts = [f"  <programme channel={quoteattr(gid)} start={quoteattr(start)} stop={quoteattr(el.get('stop', ''))}>"]
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
    total_prog += 1
    if start < min_start: min_start = start
    stop = el.get("stop", "")
    if stop > max_stop: max_stop = stop

raw_path = os.path.join(WORK, "guide.xml")
out = open(raw_path, "w", encoding="utf-8")
out.write('<?xml version="1.0" encoding="UTF-8"?>\n')
out.write(f'<tv generator-info-name="Juno US guide for Brock - iptv-org US + BuddyChewChew service playlists, free EPG sources" date="{datetime.now(timezone.utc).strftime("%Y%m%d")}">\n')
for base in sorted(matches):
    out.write(f"  <channel id={quoteattr(base)}>\n    <display-name>{escape(names.get(base, base))}</display-name>\n")
    if base in logos:
        out.write(f"    <icon src={quoteattr(logos[base])}/>\n")
    out.write("  </channel>\n")
for be in buddy_entries:
    out.write(f"  <channel id={quoteattr(be['gid'])}>\n    <display-name>{escape(be['name'])}</display-name>\n")
    if be["logo"]:
        out.write(f"    <icon src={quoteattr(be['logo'])}/>\n")
    out.write("  </channel>\n")
for ex in extra_entries:
    if ex["gid"] in iptvorg_epg_map:
        out.write(f"  <channel id={quoteattr(ex['gid'])}>\n    <display-name>{escape(ex['name'])}</display-name>\n")
        if ex["logo"]:
            out.write(f"    <icon src={quoteattr(ex['logo'])}/>\n")
        out.write("  </channel>\n")

for src, idmap in by_source.items():
    n0 = total_prog
    with gzip.open(os.path.join(WORK, src), "rb") as f:
        for ev, el in ET.iterparse(f, events=("end",)):
            if el.tag == "programme":
                sid = el.get("channel")
                if sid in idmap and el.get("start", "")[:14] >= TODAY:
                    write_programme(out, idmap[sid], el)
                el.clear()
    print(f"{src}: programmes kept {total_prog - n0}", flush=True)

for service, (epg_fname, idmap) in buddy_epg.items():
    if not idmap:
        continue
    n0 = total_prog
    with epg_stream(os.path.join(WORK, epg_fname)) as f:
        for ev, el in ET.iterparse(f, events=("end",)):
            if el.tag == "programme":
                sid = el.get("channel")
                if sid in idmap and el.get("start", "")[:14] >= TODAY:
                    write_programme(out, idmap[sid], el)
                el.clear()
    print(f"buddy {service}: programmes kept {total_prog - n0}", flush=True)

if iptvorg_epg_map:
    by_file = {}
    for gid, (gname, cid) in iptvorg_epg_map.items():
        by_file.setdefault(gname, {})[cid] = gid
    for gname, idmap in by_file.items():
        n0 = total_prog
        gopener = gzip.open if gname.endswith(".gz") else open
        with gopener(os.path.join(WORK, gname), "rb") as f:
            for ev, el in ET.iterparse(f, events=("end",)):
                if el.tag == "programme":
                    sid = el.get("channel")
                    if sid in idmap and el.get("start", "")[:14] >= TODAY:
                        write_programme(out, idmap[sid], el)
                    el.clear()
        print(f"iptv-org declared guide {gname}: programmes kept {total_prog - n0}", flush=True)
out.write("</tv>\n")
out.close()

gz_path = os.path.join(OUT_DIR, "guide.xml.gz")
with open(raw_path, "rb") as fin, gzip.open(gz_path, "wb", compresslevel=6) as fout:
    while True:
        chunk = fin.read(1 << 20)
        if not chunk:
            break
        fout.write(chunk)

# ---------- 5. write the playlist ----------
picked = []
for e in entries:
    if e["base"] not in matches:
        continue
    line = re.sub(r'tvg-id="[^"]+"', f'tvg-id="{e["base"]}"', e["line"])
    line = line.replace('group-title="Undefined"', 'group-title="General"')
    gm = re.search(r'group-title="([^"]+)"', line)
    primary = gm.group(1).split(";")[0].strip() if gm else "General"
    line = re.sub(r'group-title="[^"]+"', f'group-title="{primary}"', line)
    picked.append((PRIORITY.get(primary, 25), e["name"].lower(), line, e["url"]))
for be in buddy_entries:
    line = f'#EXTINF:-1 tvg-id="{be["gid"]}"'
    if be["logo"]:
        line += f' tvg-logo="{be["logo"]}"'
    line += f' group-title="{be["category"]}",{be["name"]}'
    picked.append((PRIORITY.get(be["category"], 25), be["name"].lower(), line, be["url"]))
for ex in extra_entries:
    line = f'#EXTINF:-1 tvg-id="{ex["gid"]}"'
    if ex["logo"]:
        line += f' tvg-logo="{ex["logo"]}"'
    line += f' group-title="{ex["category"]}",{ex["name"]}'
    picked.append((PRIORITY.get(ex["category"], 25), ex["name"].lower(), line, ex["url"]))
picked.sort(key=lambda t: (t[0], t[1]))
with open(os.path.join(OUT_DIR, "us-playlist.m3u"), "w", encoding="utf-8") as f:
    f.write(f'#EXTM3U url-tvg="{GUIDE_URL}"\n')
    for _, _, line, url in picked:
        f.write(line + "\n")
        f.write(url + "\n")
print(f"playlist entries kept: {len(picked)}")

# ---------- 6. VOD movie library (separate file) ----------
# PublicDomainM3U: public-domain films/episodes hosted on Archive.org.
# The live playlist's category rules do NOT apply here: the sources'
# genre group-titles are kept as shelves, with posters and runtimes as
# provided. No guide data exists for on-demand titles, so the file gets
# its own bare header with no url-tvg.
VOD_SOURCES = [
    ("movies", "https://raw.githubusercontent.com/onlinem3u/publicdomainm3u/main/movies.m3u"),
    ("series", "https://raw.githubusercontent.com/onlinem3u/publicdomainm3u/main/series.m3u"),
]
vod_pairs = []
for vlabel, vurl in VOD_SOURCES:
    vtext = fetch_text(vurl)
    vpairs = parse_m3u(vtext) if vtext else []
    vod_pairs.extend(vpairs)
    print(f"vod {vlabel}: {len(vpairs)} titles", flush=True)
vod_path = os.path.join(OUT_DIR, "vod-library.m3u")
if vod_pairs:
    with open(vod_path, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for line, url in vod_pairs:
            f.write(line.rstrip() + "\n")
            f.write(url + "\n")
elif os.path.exists(vod_path):
    os.unlink(vod_path)
print(f"vod library: {len(vod_pairs)} titles, {'written' if vod_pairs else 'not written'}", flush=True)

total_channels = len(matches) + len(buddy_entries) + len(extra_entries)
vod_html = (f'<p>VOD movie library (public-domain films, grouped by genre): '
            f'<a href="vod-library.m3u">vod-library.m3u</a> ({len(vod_pairs)} titles)</p>\n'
            if vod_pairs else "")
with open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as f:
    f.write(f"""<!doctype html><title>US IPTV playlist and guide for Brock</title>
<h1>US IPTV playlist + custom guide</h1>
<p>Playlist (US channels with guide data): <a href="us-playlist.m3u">us-playlist.m3u</a></p>
<p>Guide file: <a href="guide.xml.gz">guide.xml.gz</a></p>
{vod_html}<p>{total_channels} channels, {len(picked)} streams, {total_prog} programmes, {min_start[:8]} to {max_stop[:8]}.
Rebuilt daily by GitHub Actions from the iptv-org US playlist, the BuddyChewChew service
playlists (Pluto, Samsung TV Plus, Plex, Roku, Xumo, Tubi, LG Channels), the Free-TV USA
list and free EPG sources. Channels from the iptv-org remainder and other playlist-only
sources are included without guide data.</p>
<p>In Opus or UHF, add the us-playlist.m3u URL above as the playlist. Its header already
points at the guide, and the guide channel IDs match the playlist IDs. Add vod-library.m3u
as a second playlist for on-demand movies.</p>
""")
print(f"DONE channels={total_channels} streams={len(picked)} programmes={total_prog} extras={len(extra_entries)} vod={len(vod_pairs)} range={min_start}..{max_stop} size={os.path.getsize(gz_path)}")
