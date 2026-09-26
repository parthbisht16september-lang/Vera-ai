from __future__ import annotations

def active_offer(merchant: dict) -> str | None:
    """Return one offer the merchant can currently use."""
    for offer in merchant.get("offers", []):
        if offer.get("status") == "active" and offer.get("title"):
            return offer["title"]
    return None


def find_digest_item(category: dict, item_id: str) -> dict | None:
    """Find the exact research item named by a trigger."""
    for item in category.get("digest", []):
        if item.get("id") == item_id:
            return item
    return None


def compose(
    category: dict,
    merchant: dict,
    trigger: dict,
    customer: dict | None = None,
) -> dict:
    """
    Build one message from the four supplied contexts.
    An empty dict means there is not enough evidence to send a message.
    """
    kind = trigger.get("kind")
    payload = trigger.get("payload") or {}
    merchant_name = merchant.get("identity", {}).get("name", "there")
    suppression_key = trigger.get("suppression_key", trigger.get("id", ""))

    # The generated dataset contains placeholder events with no actual fact.
    if payload.get("placeholder") is True:
        return {}

    # Customer messages need separate consent and relationship checks.
    # We will implement those in the next stage.
    if trigger.get("scope") == "customer":
        if customer is None:
            return {}

        if customer.get("merchant_id") != merchant.get("merchant_id"):
            return {}

        consent = customer.get("consent") or {}
        allowed_scopes = consent.get("scope") or []

        if not consent.get("opted_in_at"):
            return {}

        if kind != "recall_due":
            return {}

        if not any(
            scope in allowed_scopes
            for scope in ("recall_reminders", "appointment_reminders")
        ):
            return {}

        due_date = payload.get("due_date")
        service = payload.get("service_due")
        if not due_date or not service:
            return {}

        customer_name = customer.get("identity", {}).get("name", "there")
        slots = payload.get("available_slots") or []

        if slots and slots[0].get("label"):
            question = f"Would {slots[0]['label']} work for you?"
        else:
            question = "Would you like us to suggest a slot?"

        return {
            "body": (
                f"Hi {customer_name}, your {service.replace('_', ' ')} "
                f"is due {due_date}. {question}"
            ),
            "cta": "yes_no",
            "send_as": "merchant_on_behalf",
            "suppression_key": suppression_key,
            "rationale": (
                "Matching merchant and recall consent; due date and slot "
                "come from the supplied trigger."
            ),
        }
        # Never address a customer belonging to a different merchant.
        if customer.get("merchant_id") != merchant.get("merchant_id"):
            return {}

        consent = customer.get("consent") or {}
        allowed_scopes = consent.get("scope") or []

        if not consent.get("opted_in_at"):
            return {}

        if kind == "recall_due":
            if not any(
                scope in allowed_scopes
                for scope in ("recall_reminders", "appointment_reminders")
            ):
                return {}

            due_date = payload.get("due_date")
            service = payload.get("service_due")
            slots = payload.get("available_slots") or []

            if not due_date or not service:
                return {}

            customer_name = customer.get("identity", {}).get("name", "there")
            service_name = service.replace("_", " ")

            if slots and slots[0].get("label"):
                question = f"Would {slots[0]['label']} work for you?"
            else:
                question = "Would you like us to suggest a slot?"

            body = (
                f"Hi {customer_name}, your {service_name} is due "
                f"{due_date}. {question}"
            )

            return {
                "body": body,
                "cta": "yes_no",
                "send_as": "merchant_on_behalf",
                "suppression_key": suppression_key,
                "rationale": (
                    "Customer has opted into recall or appointment reminders; "
                    "the due date and suggested slot come from the trigger."
                ),
            }

        return {}

    if kind == "research_digest":
        item_id = payload.get("top_item_id")
        item = find_digest_item(category, item_id)

        if not item or not item.get("title") or not item.get("source"):
            return {}

        body = (
            f"{merchant_name}, {item['title']} "
            f"({item['source']}). Want the details to review?"
        )
        rationale = (
            "The trigger points to a specific research item in the "
            "merchant's category digest, with a named source."
        )

    elif kind in ("perf_dip", "perf_spike"):
        metric = payload.get("metric")
        change = payload.get("delta_pct")
        window = payload.get("window")

        if metric is None or change is None or not window:
            return {}

        direction = "up" if change > 0 else "down"
        change_percent = abs(change) * 100
        next_step = "build on it" if direction == "up" else "respond"

        body = (
            f"{merchant_name}, your {metric} are {direction} "
            f"{change_percent:g}% over {window}. "
            f"Want a short plan to {next_step}?"
        )
        rationale = (
            f"The trigger reports a {change_percent:g}% change in "
            f"{metric} over {window}; the message proposes one next step."
        )

    else:
        return {}

    return {
        "body": body,
        "cta": "yes_no",
        "send_as": "vera",
        "suppression_key": suppression_key,
        "rationale": rationale,
    }