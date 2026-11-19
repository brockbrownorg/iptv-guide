# iptv-guide

A US-only IPTV playlist plus a self-rebuilding XMLTV program guide, for use in IPTV Player - Opus.

## Use

Playlist (add this URL in Opus):
`https://brockbrownorg.github.io/iptv-guide/us-playlist.m3u`

Guide (already linked from the playlist header; add as Custom EPG only if Opus asks):
`https://brockbrownorg.github.io/iptv-guide/guide.xml.gz`

## Why

The iptv-org US playlist (https://iptv-org.github.io/iptv/countries/us.m3u) ships with no
usable EPG link, and free guide sources use different channel IDs, so a direct link never
lines up in Opus. This repo rebuilds both files every day: the playlist keeps only the US
channels that have guide data, and the guide's channel IDs are rewritten to the playlist's
own IDs, so Opus matches them directly.

## How it works

`build_guide.py` (stdlib only, no dependencies):

1. Downloads the iptv-org US playlist (about 1,500 streams).
2. Downloads the free EPG sources verified on 2026-11-18: epg.pw US, epgshare01 US,
   and the matthuisman i.mjh.nz guides for Pluto TV, Plex, Roku, Samsung TV Plus and PBS.
3. Matches playlist channels to guide channels: Pluto channels exactly by the code in
   their stream URL, the rest by unique normalized name matches only.
4. Writes `public/guide.xml.gz` (programmes from today UTC forward) and
   `public/us-playlist.m3u` (only the matched channels, IDs rewritten to match the guide).

The 2026-11-18 build covered 447 of 1,346 unique US channels (about 33 percent,
23,525 programmes over the next few days). The rest are mostly small local and niche
streams that no free guide publishes data for.
