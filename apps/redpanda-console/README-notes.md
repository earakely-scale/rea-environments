# Redpanda Console 3.12 capture notes (rea showcase)

- App: `redpandadata/console:v3.12.0`, digest `redpandadata/console@sha256:9dc0cd55db172c6be9c2ff8a51f33a14395f7675fa7fbc002c277f3b96115c27`
  (log line "started Redpanda Console" version v3.12.0), with one broker `redpandadata/redpanda:v26.2.5`
  (`redpandadata/redpanda@sha256:badca2d958f81da675c3055a9ecb6ebb590325582bcf16936148ffd65e96e920`) in `--mode dev-container`,
  `--smp 1`, `--memory 1G`. Compose project `rea-redpanda-console`; Console on `127.0.0.1:3305 -> 8080`; the broker publishes
  only its HTTP Proxy (`127.0.0.1:18082`) and Schema Registry (`127.0.0.1:18081`) on loopback for seeding; Kafka (9092) and
  the Admin API (9644) stay inside the compose network. Console config (inline, via `CONFIG_FILEPATH`): Kafka brokers,
  Schema Registry and Redpanda Admin API enabled.
- Licence: Business Source License 1.1 (Licensor Redpanda Data, Inc.). The Console source carries `licenses/bsl_header.txt`
  pointing at the Redpanda BSL; the Additional Use Grant allows any use except offering it as a streaming or queuing
  service; each release converts to Apache-2.0 four years after release. Running it on our own VM with invented data is
  within the grant.
- No login: the free edition of Redpanda Console has no authentication, so there is no admin account and no `.admin`
  file. The Console reports an automatic 30-day "Built-In Evaluation Period" enterprise trial from the broker; enterprise
  features stay disabled and none were used.
- The broker tries the EC2 metadata endpoint once at start (cloud auto-detection) and times out; harmless.
- Tooling on the VM: rea 6.6.0, playwright-core 1.58.2, Chromium 155.0.8059.79 (snap; the default temp profile worked),
  node v24.22.0, python 3.12.3, Docker 29.9.1, compose v5.6.0.

## Pipeline (all under ~/capture/redpanda-console on the VM)
1. `docker compose -p rea-redpanda-console -f compose.yml up -d` (broker healthcheck `rpk cluster health`; Console starts
   after the broker is healthy and answers `/api/brokers` within seconds).
2. `python3 seed.py` (stdlib only, idempotent): 5 topics through `POST /api/topics` with explicit configs (partitions,
   cleanup.policy, retention.ms, max.message.bytes); 22 invented JSON messages through `POST /api/topics-records` (keys and
   values base64, one header); 4 consumer groups made by consuming through the broker HTTP Proxy (binary format, manual
   commit) and committing chosen offsets so two groups show lag; 6 schema versions in 5 subjects through
   `POST /api/schema-registry/subjects/{subject}/versions` (Avro `com.example.rota.Keeper`, Avro ShiftHandover referencing
   it, Avro StoneCount v1 and v2, JSON Schema TideOrder, Protobuf CrateManifest) and two subject compatibility overrides
   (FULL, FORWARD) through `PUT /api/schema-registry/config/{subject}`. Leftover `rea-scratch*` topics are removed first.
   Writes `seed-ids.json` (names only).
3. `NODE_PATH=~/capture/node_modules node redpanda-console/capture.mjs`: visits /overview, /topics, a topic, /groups, a group,
   /schema-registry and a subject; then the scripted in-page fetch sequence: cluster, brokers, broker config, topics,
   consumer groups, subjects, registry config/mode/contexts/types, reassignments; consumers of each of the 5 topics,
   partitions of 3, one topic configuration, one topic documentation; each of the 4 consumer groups; 5 subject versions,
   one referencedby, 3 schema ids; 2 subject configs; filtered queries `topics-configs?topicNames=..&configKeys=..`,
   `operations/topic-details?topicNames=..`, `topics-offsets?topicNames=..&timestamp=-1`; then the write path on a scratch
   topic `rea-scratch.lamp-trials` (create, PATCH retention.ms, publish one record, re-read partitions and configs) and a
   scratch subject (register, read, soft delete, hard delete), DELETE the topic, re-read the topic and subject lists.
   Full HAR 124 MB (the SPA bundle), deleted on the VM after scoping.
4. `python3 -I scope_har.py redpanda-console.full.har redpanda-console.scoped.har --origin http://127.0.0.1:3305 --keep-regex '^/api/'`
   -> kept 87 (GET 80, POST 3, PATCH 1, DELETE 3), all 200; dropped other-origin 170, path 461 (assets and the Connect RPC
   calls under `/redpanda.api.*`), non-json 0, auth 0, big-body 0, over-max 0. sha256
   `5bc50a249c91ea871c1f1cf5d93990674c4436ebde14eca474ae01454715a5b2`, 197,451 bytes.
5. `python3 ~/showcase/envbuild.py all redpanda-console`: manifest, bundle, smoke, eval, card + dry publish.
6. `docker compose -p rea-redpanda-console -f compose.yml down -v`; `redpanda-console.full.har` removed on the VM.

## Capture details worth knowing
- Message bodies are only readable through Console's streaming `ListMessages` Connect RPC (`application/connect+json`
  envelopes), outside `^/api/`, so no recorded JSON read returns message contents; the seeded messages show up as
  watermarks, partition sizes and consumer-group lag.
- The broker runs with `auto_create_topics_enabled` (dev-container default). An earlier capture re-read the deleted
  scratch topic's partitions, which quietly recreated it and made the next `GET /api/topics` answer 500 ("Could not
  list topics from Kafka cluster"); the final capture re-reads only the lists after the delete.
- The HTTP Proxy consumers report `clientId` `pandaproxy_client`, so no seeded client ids exist; the groups are Empty
  (no live members) with committed offsets.

## Manifest facts
- With rules: 37 tools (GET 31, POST 3, DELETE 2, PATCH 1), 11 templated groups, params numeric 6 and sibling-variance 5
  (consumer-groups/{id}, topics/{id}/consumers, topics/{id}/partitions, subjects/{id}/versions/all and /latest; topic and
  group names are hyphenated identifiers under a plural literal). Without rules: 54 tools. 0 excluded.
- Retrieval tasks: 8 (candidates 9; rejected shape 25, common 5, in-call 8). Topic and group names appear in many recorded
  responses (lists, details and, by substring, the `-value` subject names), so the consumer-group tools' first records
  produced no answer within the 12-occurrence limit.
- Eval: gpt-oss-120b 8/8, GLM-5.3-Flash 8/8.
