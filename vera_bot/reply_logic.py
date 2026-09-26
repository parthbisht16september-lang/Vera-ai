import re
from followup_content import merchant_followup


def process_reply(data, conversations):
    conversation_id = data.get("conversation_id")
    message = str(data.get("message") or "").strip()
    turn = data.get("turn_number")

    state = conversations.get(conversation_id)
    if not state:
        return {
            "action": "end",
            "rationale": "Unknown conversation; cannot safely continue it.",
        }

    if (
        data.get("merchant_id") != state.get("merchant_id")
        or data.get("customer_id") != state.get("customer_id")
    ):
        return {
            "action": "end",
            "rationale": "Reply identity does not match this conversation.",
        }

    expected_role = "customer" if state.get("customer_id") else "merchant"
    if data.get("from_role") != expected_role:
        return {
            "action": "end",
            "rationale": "Reply role does not match the conversation.",
        }

    opted_out = any(
        item.get("opted_out")
        and item.get("merchant_id") == state.get("merchant_id")
        and item.get("customer_id") == state.get("customer_id")
        for item in conversations.values()
    )
    if state.get("closed") or opted_out:
        return {
            "action": "end",
            "rationale": "Conversation ended or recipient opted out.",
        }

    if not isinstance(turn, int) or isinstance(turn, bool):
        return {
            "action": "wait",
            "wait_seconds": 1800,
            "rationale": "Missing turn number; wait rather than risk a duplicate.",
        }

    if turn <= state["last_turn"]:
        return {
            "action": "wait",
            "wait_seconds": 1800,
            "rationale": "Duplicate or older reply turn.",
        }

    state["last_turn"] = turn
    lowered = message.lower().replace("’", "'")

    if re.search(r"\b(stop|unsubscribe|opt out|do not contact)\b", lowered):
        state["closed"] = True
        state["opted_out"] = True
        return {
            "action": "end",
            "rationale": "Respects the request to stop contact.",
        }

    if re.search(
        r"\b(out of office|automatic reply|auto.reply|"
        r"thank you for contacting|our team will respond shortly)\b",
        lowered,
    ):
        state["auto_reply_count"] = state.get("auto_reply_count", 0) + 1
        if state["auto_reply_count"] >= 3:
            state["closed"] = True
            return {
                "action": "end",
                "rationale": "Repeated automated replies; end this conversation.",
            }
        return {
            "action": "wait",
            "wait_seconds": 1800,
            "rationale": "Automatic reply; wait for a human response.",
        }

    state["auto_reply_count"] = 0

    declined = (
        re.search(
            r"\b(not interested|don't want|do not want|no thanks|no thank you)\b",
            lowered,
        )
        or re.match(r"^(no|nope|nah)(\b|[.!?])", lowered)
    )
    if declined and not (
        re.fullmatch(r"no problem[.! ]*", lowered)
    ):
        state["closed"] = True
        return {
            "action": "end",
            "rationale": "Respects a declined offer.",
        }

    if re.search(r"\b(not sure|maybe|let me think)\b", lowered):
        return {
            "action": "wait",
            "wait_seconds": 1800,
            "rationale": "Recipient has not committed yet.",
        }

    if (
        not state.get("customer_id")
        and state.get("trigger_kind") == "active_planning_intent"
        and re.fullmatch(r"(?:₹|rs\.?\s*)?\d+(?:\.\d+)?(?:\s*(?:per head|each))?", lowered)
    ):
        return merchant_followup(state, message)

    if re.search(
        r"\b(yes|sure|okay|ok|go ahead|let'?s do it|please proceed|no problem)\b",
        lowered,
    ):
        if state.get("customer_id"):
            kind = state.get("trigger_kind")

            if kind == "chronic_refill_due":
                body = (
                    "Thanks, your request to review the refill details is noted. "
                    "Please contact the pharmacy for stock and prescription "
                    "checks; no order has been placed."
                )
                cta = "none"

            elif kind in ("customer_lapsed_hard", "customer_lapsed_soft"):
                body = "Which service would you like more information about?"
                cta = "open_ended"

            elif kind == "recall_due":
                body = (
                    "Thanks, your interest in arranging a visit is noted. "
                    "Please confirm availability directly with the business; "
                    "no appointment has been booked."
                )
                cta = "none"

            elif kind == "appointment_tomorrow":
                body = (
                    "Thanks for acknowledging the appointment reminder. "
                    "Your booking details have not been changed."
                )
                cta = "none"

            else:
                return {
                    "action": "wait",
                    "wait_seconds": 1800,
                    "rationale": "Customer reply needs more original-message context.",
                }

            state["customer_request"] = {
                "kind": kind,
                "turn": turn,
                "status": "interest_recorded",
            }

            return {
                "action": "send",
                "body": body,
                "cta": cta,
                "rationale": (
                    "Responds to the original customer trigger and records "
                    "interest without claiming external booking or order actions."
                ),
            }

        return merchant_followup(state, message)

    return {
        "action": "wait",
        "wait_seconds": 1800,
        "rationale": "No clear request or permission to continue.",
    }
