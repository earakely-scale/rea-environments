#!/usr/bin/env python3
"""Write scenario.json (schema capture_browser_scenario) for the PhotoPrism capture from seed-ids.json.

UI pages (browse, albums, each album's view, labels, folders, favourites, a UI search), a direct JSON read of every seeded
photo, JSON searches with query parameters, then the scratch album round trip through the UI (Add Album creates an album
named after the current month, the edit dialog renames it, the album view's menu deletes it), the album list again, settle."""
import json, os

BASE = "http://127.0.0.1:3401"
# Bodies over 64 KiB (the 1.9 MB app bundle, CSS, fonts) are recorded without content; every JSON reply is under 20 KB.
# The UI's session replies carry the public-mode session id and access token: both are declared secrets (values from .admin,
# passed through PP_PUBLIC_SESSION and PP_PUBLIC_TOKEN) and REA redacts them to [REDACTED:<secret_id>].
BODY_LIMIT = 65536
DIR = os.path.dirname(os.path.abspath(__file__))
ids = json.load(open(os.path.join(DIR, "seed-ids.json")))
steps = []


def css(selector): return {"kind": "css", "selector": selector}
def goto(sid, path, query=()):
    steps.append({"step_id": sid, "action": "goto", "destination": {"url": BASE + path, "query": [{"name": k, "value": {"source": "literal", "value": v}} for k, v in query]}, "wait_until": "load"})
STEP_TIMEOUT = 20000   # without timeout_ms a locator that never matches waits forever
def wait(sid, selector, state="visible"):
    steps.append({"step_id": sid, "action": "wait_for", "locator": css(selector), "state": state, "timeout_ms": STEP_TIMEOUT})
def pause(sid, ms): steps.append({"step_id": sid, "action": "wait_for_timeout", "duration_ms": ms})
def click(sid, selector): steps.append({"step_id": sid, "action": "click", "locator": css(selector), "timeout_ms": STEP_TIMEOUT})
def fill(sid, selector, value): steps.append({"step_id": sid, "action": "fill", "locator": css(selector), "value": {"source": "literal", "value": value}, "timeout_ms": STEP_TIMEOUT})

FIRST = "div.result >> nth=0"
wait("browse-ready", FIRST)
for n, (title, uid) in enumerate(ids["photos"].items(), 1):
    goto(f"photo-json-{n:02d}", f"/api/v1/photos/{uid}")
goto("albums-page", "/library/albums"); wait("albums-ready", "div.result.is-album >> nth=0")
for n, (title, uid) in enumerate(ids["albums"].items(), 1):
    goto(f"album-view-{n}", f"/library/albums/{uid}/view"); wait(f"album-view-{n}-ready", FIRST)
goto("labels-page", "/library/labels"); wait("labels-ready", FIRST)
goto("folders-page", "/library/folders"); wait("folders-ready", FIRST)
goto("favorites-page", "/library/favorites"); wait("favorites-ready", FIRST)
goto("ui-search-copper", "/library/browse", [("q", "copper")]); wait("ui-search-ready", FIRST)
base_q = [("count", "24"), ("offset", "0"), ("merged", "true")]
goto("json-newest-six", "/api/v1/photos", [("count", "6"), ("offset", "0"), ("merged", "true"), ("order", "newest")])
goto("json-search-heron", "/api/v1/photos", base_q + [("q", "heron")])
goto("json-label-tide-gauge", "/api/v1/photos", base_q + [("label", "tide-gauge")])
goto("json-color-gold", "/api/v1/photos", base_q + [("color", "gold")])
goto("json-folder-albums", "/api/v1/albums", [("count", "24"), ("offset", "0"), ("type", "folder")])
# Scratch album: create (POST), rename in the edit dialog (PUT), delete from the album view menu (DELETE).
goto("scratch-albums-page", "/library/albums"); wait("scratch-albums-ready", "div.result.is-album >> nth=0")
click("scratch-add", "button.action-add")
click("scratch-open-edit", 'div.result:has-text("2026") button.action-title-edit')
fill("scratch-title", ".v-overlay--active .input-title input", "Rea Scratch Album")
fill("scratch-location", ".v-overlay--active .input-location input", "Copperfield Annex")
fill("scratch-description", ".v-overlay--active .input-description textarea:not(.v-textarea__sizer)", "Scratch album made by the capture scenario.")
click("scratch-save", ".v-overlay--active button.action-confirm")
wait("scratch-renamed", 'div.result:has-text("Rea Scratch Album")')
pause("scratch-dialog-closed", 1500)
click("scratch-open-view", 'div.result:has-text("Rea Scratch Album") div.preview')
# The album list has its own menu button, so wait for the album view's layout toggle before opening the menu.
wait("scratch-view-ready", "button.action-view-list")
click("scratch-menu", "button.action-menu__btn")
click("scratch-delete", ".action-delete.action-menu__item")
click("scratch-delete-confirm", ".v-overlay--active button.action-confirm")
pause("scratch-deleted", 1500)
goto("albums-again", "/library/albums"); wait("albums-again-ready", "div.result.is-album >> nth=0")
pause("settle", 1500)

scenario = {
    "browser": {"mode": "launch", "executable_path": "/snap/bin/chromium"},
    "start_url": {"url": BASE + "/library/browse", "query": []},
    "secrets": [{"secret_id": "public_session", "environment_variable": "PP_PUBLIC_SESSION"},
                {"secret_id": "public_access_token", "environment_variable": "PP_PUBLIC_TOKEN"}],
    "storage": {"cookies": [], "local_storage": [], "session_storage": []},
    "actions": steps,
    "capture": {"events": ["network"], "network": {"request_body": True, "response_body": True, "header_values": False},
                "limits": {"max_network_body_bytes": BODY_LIMIT, "max_total_event_allocation_bytes": 67108864}},
}
json.dump(scenario, open(os.path.join(DIR, "scenario.json"), "w"), indent=1)
print(f"scenario.json: {len(steps)} actions")
