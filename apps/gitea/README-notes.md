# Gitea capture notes

- Gitea 28.1.0 (gitea/gitea:latest, sqlite, compose project rea-gitea, 127.0.0.1:3102). Admin created with the gitea CLI; seeding through /api/v1 with basic auth.
- Gitea does not accept the web session for /api/v1 (401 token required), so the in-page fetch sequence carried a scoped personal access token in an Authorization header; scope_har.py removes every request header except content-type and accept, and the scoped HAR has zero credential and token-shape hits.
- The DELETE /issues/comments/{id} reply is 204 with no body; the scoping tool keeps empty-body API replies, so the DELETE tool is present.
- Owner and repository names (lighthouse-rota, granite-ledger, blue-heron-kitchen) are words, not identifier-shaped, so no rule templates them: the manifest has one tool per repository path, and the rules and no-rules manifests have the same tool count. Issue, comment, milestone and PR numbers are templated by the numeric rule.
- Page visits waited on networkidle, which Gitea never reaches because of its notification long-poll; the capture took longer than needed but completed.
