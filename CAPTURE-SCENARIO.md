# Scenario captures

Five environments (Lychee, PhotoPrism, Pinry, the Art Institute of Chicago and the Library of Congress) were captured by
REA itself rather than as HARs. `rea capture-browser-scenario` reads a declarative scenario, launches Chromium, runs the
actions, and returns Evidence with every network transaction; `rea inspect-analysis-view` reads that Evidence directly as
the environment manifest's parent (morluto/rea#5182). There is no capture script, HAR, scoping or scrubbing step. Each
application's scenario is `apps/<app>/scenario.json`.

## Shape

Abridged from `apps/lychee/scenario.json` (152 actions in full):

```json
{
  "browser": { "mode": "launch", "executable_path": "/snap/bin/chromium" },
  "start_url": { "url": "http://127.0.0.1:3402/gallery", "query": [] },
  "secrets": [ { "secret_id": "session_cookie", "environment_variable": "APP_SESSION" } ],
  "storage": {
    "cookies": [ { "name": "lychee_session", "value": { "source": "secret", "secret_id": "session_cookie" },
                   "destination": { "url": "http://127.0.0.1:3402/", "query": [] },
                   "http_only": true, "secure": false, "same_site": "Lax" } ],
    "local_storage": [], "session_storage": []
  },
  "actions": [
    { "step_id": "gallery-ready", "action": "wait_for", "state": "visible", "timeout_ms": 20000,
      "locator": { "kind": "css", "selector": "a[href=\"/gallery/7essfu5uxVTOtu3jvbCzG-we\"] >> nth=0" } },
    { "step_id": "album-saltmarsh", "action": "click", "timeout_ms": 20000,
      "locator": { "kind": "css", "selector": "a[href=\"/gallery/7essfu5uxVTOtu3jvbCzG-we\"] >> nth=0" } },
    { "step_id": "album-saltmarsh-photos", "action": "wait_for", "state": "visible", "timeout_ms": 20000,
      "locator": { "kind": "css", "selector": "a.photo[data-photo-id=\"kAvRrZddPxe59yl0S2zU6oty\"]" } },
    { "step_id": "settle", "action": "wait_for_timeout", "duration_ms": 1500 }
  ],
  "capture": {
    "events": ["network"],
    "network": { "request_body": true, "response_body": true, "header_values": false },
    "limits": { "max_network_body_bytes": 262144, "max_total_event_allocation_bytes": 67108864 }
  }
}
```

```bash
APP_SESSION="$(…read from the instance's credential file…)" \
  rea capture-browser-scenario scenario.json --format json > <app>.capture.json
```

## Rules that held across the five

- **Credentials** are environment variables named by `secrets`, never values in the file. REA redacts credential headers
  and every declared secret wherever it appears, response bodies included (`[REDACTED:<secret_id>]`). Starting signed in
  from a `storage` seed keeps the login exchange out of the capture; a declared secret also covers values the application
  echoes back, such as PhotoPrism's session reply.
- **Reads** come from the requests the application's own pages make and from `goto` to JSON URLs, which carry the
  session cookie. **Writes** come from the application's forms: create, edit and delete one scratch object.
- **End with a short wait** (`wait_for_timeout`, 1.5 s). Without it, a transaction still in flight when the last action
  finishes is recorded unfinished and its response body is lost.
- **Give every action a `timeout_ms`.** Actions have no default deadline, so a locator that never matches waits forever.
- **Check the result**, not only the exit code: every `steps[].status` is `completed`, `events.dropped` is 0 and
  `events.omissions` is empty. A failed step cancels the rest and still writes Evidence; raise
  `max_total_event_allocation_bytes` if events were dropped.
- **Body limits** are global: large CSS and JavaScript bodies count against the manifest view's budget, so a page-heavy
  scenario may need a lower `max_network_body_bytes` (Pinry used 20,000; PhotoPrism 65,536).
- `wait_for` and `goto` require `state` and `wait_until`; css locators accept Playwright selector syntax such as
  `:visible >> nth=0`, and strict mode fails when a selector matches more than one element.
- Public APIs: no secrets, `start_url` on the API's origin, one `goto` per record with a 600 ms or longer wait between
  them.
