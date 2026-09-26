import hashlib
import json
import os
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from bot import compose
from reply_logic import process_reply
from state_store import StateStore
from pathlib import Path
from threading import RLock
from functools import wraps

STATE_LOCK = RLock()
STORE = None


def locked_handler(function):
    @wraps(function)
    def wrapped(self):
        with STATE_LOCK:
            return function(self)
    return wrapped


STARTED = time.monotonic()
CONTEXTS = {}
SENT = set()
CONVERSATIONS = {}
VALID_SCOPES = {"category", "merchant", "customer", "trigger"}


def json_response(handler, status, data):
    if STORE is not None and handler.command == "POST" and 200 <= status < 300:
        try:
            STORE.save(CONTEXTS, SENT, CONVERSATIONS)
        except Exception:
            # Restore the last saved state if the write failed.
            contexts, sent, conversations = STORE.load()
            CONTEXTS.clear()
            CONTEXTS.update(contexts)
            SENT.clear()
            SENT.update(sent)
            CONVERSATIONS.clear()
            CONVERSATIONS.update(conversations)
            status = 503
            data = {"error": "state_save_failed"}

    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def stored_payload(scope, context_id):
    record = CONTEXTS.get((scope, context_id))
    return record["payload"] if record else None



def source_is_available(category, trigger, now):
    """Reject a dated digest source that had not been published at tick time."""
    import re
    from datetime import date

    if trigger.get("kind") not in ("research_digest", "regulation_change"):
        return True

    item_id = (trigger.get("payload") or {}).get("top_item_id")
    item = next(
        (entry for entry in category.get("digest", [])
         if entry.get("id") == item_id),
        None,
    )
    if not item or not item.get("source") or not now:
        return False

    try:
        tick_day = date.fromisoformat(now[:10])
    except ValueError:
        return False

    source = item["source"]

    # Example: "Dental Council of India circular 2026-11-04"
    exact_date = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", source)
    if exact_date:
        try:
            return tick_day >= date.fromisoformat(exact_date.group(1))
        except ValueError:
            return False

    # Example: "JIDA Oct 2026, p.14". With no day supplied,
    # wait until the following month to avoid assuming an early release.
    month_year = re.search(
        r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"[a-z]*\s+(20\d{2})\b",
        source,
        re.IGNORECASE,
    )
    if month_year:
        months = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4,
            "may": 5, "jun": 6, "jul": 7, "aug": 8,
            "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        month = months[month_year.group(1)[:3].lower()]
        year = int(month_year.group(2))
        next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        return tick_day >= next_month

    return True


def parse_timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def process_tick(data):
    actions = []
    now = data.get("now", "")
    now_instant = parse_timestamp(now)
    if now_instant is None:
        return {"actions": []}
    available = data.get("available_triggers", [])

    if not isinstance(available, list):
        return {"actions": []}

    for trigger_id in available:
        if len(actions) >= 20:
            break

        trigger = stored_payload("trigger", trigger_id)
        if not trigger:
            continue

        # A trigger that has expired cannot start a new message.
        if trigger.get("expires_at"):
            expiry = parse_timestamp(trigger["expires_at"])
            if expiry is None or now_instant >= expiry:
                continue

        merchant_id = trigger.get("merchant_id")
        merchant = stored_payload("merchant", merchant_id)
        if not merchant:
            continue

        category = stored_payload(
            "category", merchant.get("category_slug")
        )
        if not category:
            continue

        if not source_is_available(category, trigger, now):
            continue

        customer_id = trigger.get("customer_id")
        if any(
            state.get("opted_out")
            and state.get("merchant_id") == merchant_id
            and state.get("customer_id") == customer_id
            for state in CONVERSATIONS.values()
        ):
            continue

        customer = None
        if customer_id:
            customer = stored_payload("customer", customer_id)
            if not customer:
                continue

        message = compose(category, merchant, trigger, customer)
        if not message:
            continue

        suppression_key = message["suppression_key"]
        send_key = (merchant_id, customer_id, suppression_key)

        if send_key in SENT:
            continue

        conversation_source = (
            f"{merchant_id}:{customer_id}:{trigger_id}:"
            f"{suppression_key}"
        )
        conversation_id = "conv_" + hashlib.sha256(
            conversation_source.encode("utf-8")
        ).hexdigest()[:20]

        action = {
            "conversation_id": conversation_id,
            "merchant_id": merchant_id,
            "customer_id": customer_id,
            "send_as": message["send_as"],
            "trigger_id": trigger_id,
            "template_name": "vera_context_v1",
            "template_params": [message["body"]],
            "body": message["body"],
            "cta": message["cta"],
            "suppression_key": suppression_key,
            "rationale": message["rationale"],
        }

        SENT.add(send_key)
        CONVERSATIONS[conversation_id] = {
            "last_turn": 0,
            "customer_id": customer_id,
            "trigger_id": trigger_id,
            "trigger_kind": trigger.get("kind"),
            "digest_item": next(
                (item for item in category.get("digest", [])
                 if item.get("id") == (trigger.get("payload") or {}).get("top_item_id")),
                {},
            ),
            "topic": (trigger.get("payload") or {}).get("intent_topic"),
            "merchant_id": merchant_id,
        }
        actions.append(action)

    return {"actions": actions}


class VeraHandler(BaseHTTPRequestHandler):
    @locked_handler
    def do_GET(self):
        if self.path == "/v1/healthz":
            counts = {
                scope: sum(
                    1 for stored_scope, _ in CONTEXTS
                    if stored_scope == scope
                )
                for scope in VALID_SCOPES
            }
            return json_response(self, 200, {
                "status": "ok",
                "uptime_seconds": int(time.monotonic() - STARTED),
                "contexts_loaded": counts,
            })

        if self.path == "/v1/metadata":
            return json_response(self, 200, {
                "team_name": "Parth Bisht",
                "team_members": ["Parth Bisht"],
                "model": "deterministic-rules",
                "approach": "Four-context composition with consent checks",
                "version": "0.2.0",
            })

        return json_response(self, 404, {"error": "not_found"})

    @locked_handler
    def do_POST(self):
        if self.path not in ("/v1/context", "/v1/tick", "/v1/reply", "/v1/teardown"):
            return json_response(self, 404, {"error": "not_found"})

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 500_000:
                return json_response(self, 400, {
                    "error": "invalid_size",
                })

            data = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            return json_response(self, 400, {"error": "invalid_json"})

        if not isinstance(data, dict):
            return json_response(self, 400, {"error": "invalid_body"})

        if self.path == "/v1/teardown":
            CONTEXTS.clear()
            SENT.clear()
            CONVERSATIONS.clear()
            return json_response(self, 200, {"accepted": True})

        if self.path == "/v1/tick":
            return json_response(self, 200, process_tick(data))

        if self.path == "/v1/reply":
            return json_response(
                self, 200, process_reply(data, CONVERSATIONS)
            )

        scope = data.get("scope")
        context_id = data.get("context_id")
        version = data.get("version")
        payload = data.get("payload")

        if scope not in VALID_SCOPES:
            return json_response(self, 400, {
                "accepted": False,
                "reason": "invalid_scope",
            })

        if (
            not isinstance(context_id, str)
            or not isinstance(version, int)
            or not isinstance(payload, dict)
        ):
            return json_response(self, 400, {
                "accepted": False,
                "reason": "invalid_context",
            })

        key = (scope, context_id)
        previous = CONTEXTS.get(key)

        if previous and version < previous["version"]:
            return json_response(self, 409, {
                "accepted": False,
                "reason": "stale_version",
                "current_version": previous["version"],
            })

        if previous is None or version > previous["version"]:
            CONTEXTS[key] = {"version": version, "payload": payload}

        return json_response(self, 200, {
            "accepted": True,
            "ack_id": f"ack_{scope}_{context_id}_v{version}",
            "stored_at": datetime.now(timezone.utc).isoformat(),
        })


if __name__ == "__main__":
    default_database = (
        Path(__file__).resolve().parent.parent / "runtime" / "vera.sqlite3"
    )
    STORE = StateStore(os.environ.get("VERA_DB_PATH", str(default_database)))
    CONTEXTS, SENT, CONVERSATIONS = STORE.load()
    print(
        f"Restored {len(CONTEXTS)} contexts, "
        f"{len(CONVERSATIONS)} conversations, "
        f"and {len(SENT)} suppression records."
    )
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), VeraHandler)
    print(f"Vera server listening at http://{host}:{port}")
    server.serve_forever()
