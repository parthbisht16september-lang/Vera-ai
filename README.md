# VeraBot — magicpin AI Challenge

VeraBot uses deterministic Python rules to turn supplied category, merchant, customer, and trigger contexts into short messages with a CTA and rationale.

Run locally: python3 vera_bot/server.py

The server provides /v1/healthz, /v1/metadata, /v1/context, /v1/tick, and /v1/reply. HOST and PORT can be set for deployment.

Merchant messages use supplied trigger and business facts. Customer messages require a matching merchant relationship and the relevant opt-in. The bot suppresses duplicates, checks publication dates at tick time, and uses saved context when handling replies.

Run python3 vera_bot/build_submission.py to generate submission.jsonl. Run python3 vera_bot/audit_cases.py to inspect coverage.

Tradeoffs: Rules are fast and reproducible but less flexible than generated wording. Some test triggers contain placeholders without event facts; these are skipped rather than filled with invented details. Actual event facts, publication dates, and contact permissions would improve coverage.

Server state is currently in memory and must be preserved throughout a judging session.
