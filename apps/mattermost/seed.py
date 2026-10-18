#!/usr/bin/env python3
"""Seed a fresh Mattermost Team Edition with synthetic content for the rea capture. Idempotent; stdlib only.

Credentials are read from the 600-mode .admin dotenv (MM_ADMIN_USER, MM_ADMIN_PASS, SEED_USER_PASS) and never printed.
Session tokens minted here are used only for seeding and are revoked at the end. Writes seed-ids.json (ids + names only)."""
import json, os, sys, time, urllib.error, urllib.request

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3104")
HERE = os.path.dirname(os.path.abspath(__file__))
ADMIN_FILE = os.environ.get("ADMIN_FILE", os.path.join(HERE, ".admin"))
IDS_FILE = os.environ.get("IDS_FILE", os.path.join(HERE, "seed-ids.json"))
TEAM = {"name": "lighthouse-rota", "display_name": "Lighthouse Rota", "type": "O", "description": "Crew rota for the Lighthouse station"}
CHANNELS = [
    {"name": "granite-ledger", "display_name": "Granite Ledger", "type": "O", "purpose": "Ledger reconciliation for the Lighthouse Rota crew", "header": "Totals close Thursdays at 16:00"},
    {"name": "blue-heron-kitchen", "display_name": "Blue Heron Kitchen", "type": "O", "purpose": "Galley planning for Blue Heron Kitchen", "header": "Menu tastings and supplier updates"},
    {"name": "night-shift", "display_name": "Night Shift", "type": "O", "purpose": "Night watch handovers", "header": "One handover post per night"},
    {"name": "keel-room", "display_name": "Keel Room", "type": "P", "purpose": "Private planning for the keel inspection", "header": "Budget code KR-77"},
]
USERS = [
    {"username": "ada.finch", "email": "ada.finch@example.test", "first_name": "Ada", "last_name": "Finch", "nickname": "Ada", "position": "Keeper"},
    {"username": "rui.castellanos", "email": "rui.castellanos@example.test", "first_name": "Rui", "last_name": "Castellanos", "nickname": "Rui", "position": "Deck lead"},
]
# (channel, author, message); authors: admin | ada.finch | rui.castellanos
POSTS = [
    ("granite-ledger", "admin", "Welcome to Granite Ledger. Weekly reconciliation closes every Thursday at 16:00; post your totals here."),
    ("granite-ledger", "ada.finch", "Week 41 totals: 312 fuel vouchers, 27 lamp-oil barrels, 4 spare lenses. Variance against the ledger: zero."),
    ("granite-ledger", "rui.castellanos", "Flagging a mismatch on the 2026-10-09 entry: ledger says 18 lamp-oil barrels, dock receipt says 19."),
    ("blue-heron-kitchen", "ada.finch", "Blue Heron Kitchen menu tasting is set for Monday 2026-10-20 at 12:30, 14 covers."),
    ("blue-heron-kitchen", "rui.castellanos", "Supplier update: the oat flour order (20 kg) lands on 2026-10-21; chilled items arrive with the morning launch."),
    ("blue-heron-kitchen", "admin", "Reminder: allergen cards for the tasting go to Ada by Friday."),
    ("night-shift", "rui.castellanos", "Night shift handover 2026-10-16: beacon rotation nominal, fog signal tested 02:10, no vessel traffic."),
    ("night-shift", "ada.finch", "Night shift handover 2026-10-17: generator B switched to standby at 23:40; replacement filter logged as ticket NS-204."),
    ("night-shift", "admin", "Watch roster for next week: Mon Rui, Tue Ada, Wed Rui, Thu Ada, Fri shared."),
    ("keel-room", "admin", "Keel inspection scheduled for 2026-10-24 with the dry-dock crew; budget code KR-77."),
    ("keel-room", "ada.finch", "Dive survey photos uploaded to the shared drive folder keel-2026-10."),
    ("keel-room", "rui.castellanos", "Confirming the hull paint batch number 8841-B for the inspection report."),
]
THREAD_ROOT = POSTS[2][2]
THREAD_REPLIES = [
    ("ada.finch", "The dock receipt counts the display barrel; the ledger is right at 18."),
    ("admin", "Agreed, closing the variance; I will annotate the 2026-10-09 entry."),
    ("rui.castellanos", "Thanks both, variance closed. Tag: GL-10-09."),
]
PINNED = POSTS[0][2]
REACTED = (POSTS[5][2], "ada.finch", "+1")


def dotenv(path):
    out = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k] = v
    return out


class Api:
    def __init__(self, token=None):
        self.token = token

    def raw(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(BASE + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", "Bearer " + self.token)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, r.read().decode(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode(), dict(e.headers)

    def call(self, method, path, body=None, ok=(200, 201), allow=()):
        status, text, _ = self.raw(method, path, body)
        if status in allow:
            return None
        if status not in ok:
            raise RuntimeError(f"{method} {path} -> {status}: {text[:300]}")
        return json.loads(text) if text else None


def wait_ready():
    for _ in range(150):
        try:
            st, text, _ = Api().raw("GET", "/api/v4/system/ping")
            if st == 200 and json.loads(text).get("status") == "OK":
                return
        except Exception:
            pass
        time.sleep(2)
    sys.exit("mattermost did not become ready")


def login(user, password):
    st, _, h = Api().raw("POST", "/api/v4/users/login", {"login_id": user, "password": password})
    return Api(h.get("Token")) if st == 200 and h.get("Token") else None


def main():
    A = dotenv(ADMIN_FILE)
    wait_ready()
    admin = login(A["MM_ADMIN_USER"], A["MM_ADMIN_PASS"])
    if admin is None:
        # first user on an empty server becomes system admin
        Api().call("POST", "/api/v4/users", {"email": "rea-admin@example.test", "username": A["MM_ADMIN_USER"],
                                            "password": A["MM_ADMIN_PASS"], "first_name": "Rea", "last_name": "Admin"}, ok=(201,))
        admin = login(A["MM_ADMIN_USER"], A["MM_ADMIN_PASS"])
        if admin is None:
            sys.exit("admin login failed after creation")
    me = admin.call("GET", "/api/v4/users/me")
    if "system_admin" not in me["roles"]:
        sys.exit("rea-admin is not system_admin; server was not empty at first run")
    print("admin ok", me["id"])

    team = admin.call("GET", f"/api/v4/teams/name/{TEAM['name']}", allow=(404,))
    if team is None:
        team = admin.call("POST", "/api/v4/teams", TEAM, ok=(201,))
    tid = team["id"]
    print("team", tid)

    channels = {}
    for c in CHANNELS:
        ch = admin.call("GET", f"/api/v4/teams/{tid}/channels/name/{c['name']}?include_deleted=false", allow=(404,))
        if ch is None:
            ch = admin.call("POST", "/api/v4/channels", dict(c, team_id=tid), ok=(201,))
        channels[c["name"]] = ch
    print("channels", {k: v["id"] for k, v in channels.items()})

    users = {"admin": me}
    for u in USERS:
        usr = admin.call("GET", f"/api/v4/users/username/{u['username']}", allow=(404,))
        if usr is None:
            usr = admin.call("POST", "/api/v4/users", dict(u, password=A["SEED_USER_PASS"]), ok=(201,))
        users[u["username"]] = usr
        admin.call("POST", f"/api/v4/teams/{tid}/members", {"team_id": tid, "user_id": usr["id"]}, ok=(200, 201))
        for ch in channels.values():
            admin.call("POST", f"/api/v4/channels/{ch['id']}/members", {"user_id": usr["id"]}, ok=(200, 201))
    print("users", {k: v["id"] for k, v in users.items()})

    tokens = {"admin": admin}
    for u in USERS:
        t = login(u["username"], A["SEED_USER_PASS"])
        if t is None:
            sys.exit(f"login failed for seeded user {u['username']}")
        tokens[u["username"]] = t

    # existing posts by message, so re-runs do not duplicate
    existing = {}
    for name, ch in channels.items():
        page = admin.call("GET", f"/api/v4/channels/{ch['id']}/posts?per_page=100")
        for pid, p in page["posts"].items():
            existing[(name, p["message"])] = p

    def ensure_post(channel, author, message, root_id=""):
        p = existing.get((channel, message))
        if p is None:
            body = {"channel_id": channels[channel]["id"], "message": message}
            if root_id:
                body["root_id"] = root_id
            p = tokens[author].call("POST", "/api/v4/posts", body, ok=(201,))
            existing[(channel, message)] = p
            time.sleep(0.3)
        return p

    posts = []
    for channel, author, message in POSTS:
        p = ensure_post(channel, author, message)
        posts.append({"id": p["id"], "channel": channel, "author": author, "message": message})
    root = existing[("granite-ledger", THREAD_ROOT)]
    replies = []
    for author, message in THREAD_REPLIES:
        p = ensure_post("granite-ledger", author, message, root_id=root["id"])
        replies.append({"id": p["id"], "author": author, "message": message})

    pinned = existing[("granite-ledger", PINNED)]
    admin.call("POST", f"/api/v4/posts/{pinned['id']}/pin", ok=(200,))
    reacted = existing[("blue-heron-kitchen", REACTED[0])]
    reactor = users[REACTED[1]]
    have = tokens[REACTED[1]].call("GET", f"/api/v4/posts/{reacted['id']}/reactions") or []
    if not any(r["user_id"] == reactor["id"] and r["emoji_name"] == REACTED[2] for r in have):
        tokens[REACTED[1]].call("POST", "/api/v4/reactions", {"user_id": reactor["id"], "post_id": reacted["id"], "emoji_name": REACTED[2]}, ok=(200, 201))

    # quieten first-run tours for the capture login
    uid = me["id"]
    prefs = [
        {"category": "tutorial_step", "name": uid, "value": "999"},
        {"category": "onboarding_task_list", "name": "onboarding_task_list_show", "value": "false"},
        {"category": "onboarding_task_list", "name": "onboarding_task_list_open", "value": "false"},
        {"category": "recommended_next_steps", "name": "hide", "value": "true"},
        {"category": "crt_thread_pane_step", "name": uid, "value": "999"},
        {"category": "crt_tutorial_triggered", "name": uid, "value": "999"},
        {"category": "drafts", "name": "drafts_tour_tip_showed", "value": json.dumps({"drafts_tour_tip_showed": True})},
        {"category": "display_settings", "name": "collapsed_reply_threads", "value": "on"},
    ]
    admin.call("PUT", f"/api/v4/users/{uid}/preferences", [dict(p, user_id=uid) for p in prefs], ok=(200,))

    st, text, h = Api().raw("GET", "/api/v4/system/ping")
    cfg = admin.call("GET", "/api/v4/config/client?format=old")
    version = {"x_version_id": h.get("X-Version-Id"), "client_version": cfg.get("Version"), "build_number": cfg.get("BuildNumber"),
               "build_hash": cfg.get("BuildHash"), "build_date": cfg.get("BuildDate"), "ping_status": json.loads(text).get("status")}
    ids = {
        "base": BASE, "team": {"id": tid, "name": TEAM["name"], "display_name": TEAM["display_name"]},
        "channels": {k: {"id": v["id"], "display_name": v["display_name"], "type": v["type"]} for k, v in channels.items()},
        "users": {k: {"id": v["id"], "username": v["username"]} for k, v in users.items()},
        "posts": posts, "thread_root": root["id"], "thread_replies": replies, "pinned": pinned["id"],
        "reacted": {"post_id": reacted["id"], "user": REACTED[1], "emoji_name": REACTED[2]}, "version": version,
    }
    with open(IDS_FILE, "w") as f:
        json.dump(ids, f, indent=1)
    # seed-only sessions die here
    for u in USERS:
        admin.call("POST", f"/api/v4/users/{users[u['username']]['id']}/sessions/revoke/all", ok=(200,))
    admin.call("POST", "/api/v4/users/logout", ok=(200,))
    print("seeded:", len(posts), "root posts,", len(replies), "replies; version", version)


if __name__ == "__main__":
    main()
