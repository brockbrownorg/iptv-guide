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
5. Adds the BuddyChewChew app-m3u-generator service playlists (Pluto TV US,
   Samsung TV Plus US, Plex US, Roku, Xumo, Tubi). Those are generated from the
   services themselves and their channel IDs match their guide files by design
   (the i.mjh.nz US guides for Pluto, Samsung, Plex and Roku, and the
   generators' own EPG for Xumo and Tubi), so every kept channel has real
   programme data. Service IDs are prefixed per service to avoid collisions,
   and channels are deduplicated by name against the iptv-org matches.

The 2026-11-18 build covers 1,605 channels and 1,627 streams (166 in the
Movies category), with 73,101 programmes over the next few days.
