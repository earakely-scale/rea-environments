#!/usr/bin/env python3
"""Write scenario.json (schema capture_browser_scenario) for the Art Institute of Chicago API capture.

Starts on the department list, then searches and listings with query parameters (artworks, artists, exhibitions, a
multi-id artwork list) and reads of individual records by id: 10 public-domain artworks across 6 departments, 3 artists,
2 galleries, 2 artwork types, 2 category terms and 1 exhibition. Every request passes fields= so bodies stay small, and a
600 ms pause follows every navigation (27 navigations, under 2 requests per second)."""
import json, os

API = "https://api.artic.edu/api/v1"
ART_FIELDS = ("id,title,artist_display,artist_title,artist_id,date_display,date_start,date_end,medium_display,dimensions,"
              "place_of_origin,style_title,classification_title,department_title,gallery_title,gallery_id,artwork_type_title,"
              "artwork_type_id,main_reference_number,color,is_public_domain")
ARTWORKS = [27992, 28560, 20684, 87479, 24645, 16568, 185905, 116363, 52198, 4575]
ARTISTS = [40610, 40810, 31492]
GALLERIES = [2147478672, 2147479703]
ARTWORK_TYPES = [1, 18]
CATEGORY_TERMS = ["PC-10", "PC-7"]
EXHIBITIONS = [9036]
steps = []
def pause(sid): steps.append({"step_id": sid, "action": "wait_for_timeout", "duration_ms": 600})
def goto(sid, path, query=()):
    steps.append({"step_id": sid, "action": "goto", "destination": {"url": API + path, "query": [{"name": k, "value": {"source": "literal", "value": v}} for k, v in query]}, "wait_until": "load"})
    pause(sid + "-pause")

pause("start-pause")
goto("search-artworks-amphora", "/artworks/search", [("q", "amphora"), ("limit", "5"), ("fields", "id,title,date_display,department_title,is_public_domain")])
goto("search-artworks-armor", "/artworks/search", [("q", "field armor"), ("limit", "5"), ("fields", "id,title,date_display,department_title,is_public_domain")])
goto("list-artworks-by-ids", "/artworks", [("ids", "27992,28560,16568,24645"), ("fields", "id,title,artist_title,date_display")])
goto("search-artists-hokusai", "/artists/search", [("q", "hokusai"), ("limit", "3"), ("fields", "id,title,birth_date,death_date")])
goto("search-exhibitions-monet", "/exhibitions/search", [("q", "monet"), ("limit", "4"), ("fields", "id,title,status,aic_start_at,aic_end_at")])
for i in ARTWORKS: goto(f"artwork-{i}", f"/artworks/{i}", [("fields", ART_FIELDS)])
for i in ARTISTS: goto(f"artist-{i}", f"/artists/{i}", [("fields", "id,title,sort_title,alt_titles,birth_date,death_date,is_artist")])
for i in GALLERIES: goto(f"gallery-{i}", f"/galleries/{i}")
for i in ARTWORK_TYPES: goto(f"artwork-type-{i}", f"/artwork-types/{i}")
for i in CATEGORY_TERMS: goto(f"category-term-{i}", f"/category-terms/{i}")
for i in EXHIBITIONS: goto(f"exhibition-{i}", f"/exhibitions/{i}", [("fields", "id,title,status,aic_start_at,aic_end_at,gallery_title,artwork_ids,artist_ids")])
steps.append({"step_id": "settle", "action": "wait_for_timeout", "duration_ms": 1500})
scenario = {
    "browser": {"mode": "launch", "executable_path": "/snap/bin/chromium"},
    "start_url": {"url": API + "/departments", "query": [{"name": "limit", "value": {"source": "literal", "value": "20"}}, {"name": "fields", "value": {"source": "literal", "value": "id,title,subtype,parent_id"}}]},
    "storage": {"cookies": [], "local_storage": [], "session_storage": []},
    "actions": steps,
    "capture": {"events": ["network"], "network": {"request_body": True, "response_body": True, "header_values": False},
                "limits": {"max_network_body_bytes": 262144}},
}
json.dump(scenario, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "scenario.json"), "w"), indent=1)
navs = sum(1 for s in steps if s["action"] == "goto") + 1
print(f"scenario.json: {len(steps)} actions, {navs} navigations")
