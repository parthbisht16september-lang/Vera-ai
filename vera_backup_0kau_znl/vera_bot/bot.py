from __future__ import annotations

from datetime import datetime

from extra_messages import compose_extra


def active_offer(merchant: dict) -> str | None:
    """Return the title of one currently active merchant offer."""
    for offer in merchant.get("offers", []):
        if offer.get("status") == "active" and offer.get("title"):
            return offer["title"]
    return None


def find_digest_item(category: dict, item_id: str | None) -> dict | None:
    """Find the research item identified by the trigger."""
    if not item_id:
        return None

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
    Compose one message from the supplied contexts.

    Return an empty dict when the available facts do not justify sending.
    """
    if (
        not merchant.get("merchant_id")
        or trigger.get("merchant_id") != merchant.get("merchant_id")
        or trigger.get("scope") not in ("merchant", "customer")
        or (trigger.get("scope") == "merchant" and trigger.get("customer_id"))
    ):
        return {}

    kind = trigger.get("kind")
    payload = trigger.get("payload") or {}
    merchant_name = merchant.get("identity", {}).get("name", "there")
    suppression_key = trigger.get("suppression_key") or trigger.get("id", "")

    # Some generated triggers contain only a placeholder, not an event fact.
    if payload.get("placeholder") is True:
        if kind == "dormant_with_vera" and trigger.get("scope") == "merchant":
            change = (
                merchant.get("performance", {})
                .get("delta_7d", {})
                .get("calls_pct")
            )
            if (
                isinstance(change, (int, float))
                and not isinstance(change, bool)
                and change < 0
            ):
                name = merchant.get("identity", {}).get("name", "Hello")
                return {
                    "body": (
                        f"{name}, your recorded calls are down "
                        f"{abs(change) * 100:g}% over 7 days. "
                        "Want a short checklist to review your listing "
                        "and enquiry handling?"
                    ),
                    "cta": "yes_no",
                    "send_as": "vera",
                    "suppression_key": (
                        trigger.get("suppression_key") or trigger.get("id", "")
                    ),
                    "rationale": (
                        "Responds to the dormancy trigger with a relevant "
                        "performance fact from the merchant context. "
                        "Does not assume a cause or a last-contact date."
                    ),
                }
            return {}

        if kind not in ("perf_dip", "perf_spike"):
            return {}

        changes = merchant.get("performance", {}).get("delta_7d", {})
        recovered = None

        for metric in ("calls", "views"):
            change = changes.get(metric + "_pct")
            if isinstance(change, bool) or not isinstance(change, (int, float)):
                continue

            matches_direction = (
                (kind == "perf_dip" and change < 0)
                or (kind == "perf_spike" and change > 0)
            )
            if matches_direction:
                recovered = {
                    "metric": metric,
                    "delta_pct": change,
                    "window": "7d",
                }
                break

        if recovered is None:
            return {}

        payload = recovered

    # Customer-facing messages have separate relationship and consent rules.
    if trigger.get("scope") == "customer":
        if customer is None:
            return {}

        if customer.get("merchant_id") != merchant.get("merchant_id"):
            return {}

        if (
            not customer.get("customer_id")
            or customer.get("customer_id") != trigger.get("customer_id")
            or trigger.get("merchant_id") != merchant.get("merchant_id")
        ):
            return {}

        consent = customer.get("consent") or {}
        if consent.get("revoked_at") or consent.get("opted_out_at"):
            return {}

        reminder_kinds = {"recall_due", "appointment_tomorrow", "chronic_refill_due"}
        if (
            kind in reminder_kinds
            and customer.get("preferences", {}).get("reminder_opt_in") is False
        ):
            return {}

        allowed_scopes = consent.get("scope") or []

        if not consent.get("opted_in_at"):
            return {}

        if kind == "appointment_tomorrow":
            if "appointment_reminders" not in allowed_scopes:
                return {}
            if customer.get("preferences", {}).get("reminder_opt_in") is False:
                return {}
            if consent.get("revoked_at") or consent.get("opted_out_at"):
                return {}
            if customer.get("customer_id") != trigger.get("customer_id"):
                return {}
            if payload.get("status") in ("cancelled", "canceled", "completed"):
                return {}

            timestamp = payload.get("appointment_iso") or payload.get("appointment_at")
            if not isinstance(timestamp, str):
                return {}
            try:
                appointment = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError:
                return {}
            if appointment.tzinfo is None:
                return {}

            offset = appointment.strftime("%z")
            zone = "UTC" + offset[:3] + ":" + offset[3:]
            label = appointment.strftime("%a %d %b %Y, %I:%M %p")
            customer_name = customer.get("identity", {}).get("name", "there")
            return {
                "body": (
                    f"Hi {customer_name}, a reminder of your appointment at "
                    f"{merchant_name} on {label} ({zone}). "
                    "Will you be able to attend?"
                ),
                "cta": "yes_no",
                "send_as": "merchant_on_behalf",
                "suppression_key": suppression_key,
                "rationale": (
                    "Uses an explicit appointment timestamp and appointment-reminder "
                    "consent; preserves minutes and the supplied time zone."
                ),
            }

        if kind == "customer_lapsed_soft":
            if "winback_offers" not in allowed_scopes:
                return {}
            if customer.get("state") != "lapsed_soft":
                return {}
            if customer.get("customer_id") != trigger.get("customer_id"):
                return {}
            if consent.get("revoked_at") or consent.get("opted_out_at"):
                return {}

            days = payload.get("days_since_last_visit")
            if type(days) is not int or days < 0:
                return {}

            customer_name = customer.get("identity", {}).get("name", "there")
            return {
                "body": (
                    f"Hi {customer_name}, it has been {days} days since "
                    f"your last visit to {merchant_name}. "
                    "Would you like information about visiting again?"
                ),
                "cta": "yes_no",
                "send_as": "merchant_on_behalf",
                "suppression_key": suppression_key,
                "rationale": (
                    "Uses a supplied visit gap, matching customer state, "
                    "and explicit winback consent."
                ),
            }

        if kind == "customer_lapsed_hard":
            if (
                "winback_offers" not in allowed_scopes
                or customer.get("state") != "lapsed_hard"
            ):
                return {}

            days = payload.get("days_since_last_visit")
            if days is None:
                return {}

            customer_name = customer.get("identity", {}).get("name", "there")
            return {
                "body": (
                    f"Hi {customer_name}, it has been {days} days since "
                    f"your last visit to {merchant_name}. "
                    "Would you like to hear about available sessions?"
                ),
                "cta": "yes_no",
                "send_as": "merchant_on_behalf",
                "suppression_key": suppression_key,
                "rationale": (
                    "Uses the supplied visit gap and an explicit winback "
                    "opt-in; makes no claim about personal goals."
                ),
            }

        if kind == "chronic_refill_due":
            if "refill_reminders" not in allowed_scopes:
                return {}

            date_time = payload.get("stock_runs_out_iso")
            if not date_time:
                return {}

            due_date = date_time[:10]
            customer_name = customer.get("identity", {}).get("name", "there")
            return {
                "body": (
                    f"Hi {customer_name}, your previous refill record "
                    f"indicates a check may be due around {due_date}. "
                    "Would you like the pharmacy to review the details?"
                ),
                "cta": "yes_no",
                "send_as": "merchant_on_behalf",
                "suppression_key": suppression_key,
                "rationale": (
                    "Uses the supplied refill date and refill-reminder "
                    "consent; asks for review without medical claims."
                ),
            }

        if kind != "recall_due":
            return {}

        if "recall_reminders" not in allowed_scopes:
            return {}

        due_date = payload.get("due_date")
        service = payload.get("service_due")

        if not due_date or not service:
            return {}

        customer_name = customer.get("identity", {}).get("name", "there")
        slots = payload.get("available_slots") or []

        question = "Would you like us to suggest a slot?"
        if slots and isinstance(slots[0], dict) and slots[0].get("iso"):
            try:
                slot_time = datetime.fromisoformat(slots[0]["iso"])
                if slot_time.tzinfo is None:
                    raise ValueError("Slot requires an explicit time zone")
                offset = slot_time.strftime("%z")
                zone = "UTC" + offset[:3] + ":" + offset[3:]
                slot_label = (
                    f"{slot_time:%a %d %b %Y, %I:%M %p} ({zone})"
                )
                question = f"Would {slot_label} work for you?"
            except ValueError:
                pass

        return {
            "body": (
                f"Hi {customer_name}, your {service.replace('_', ' ')} "
                f"is due {due_date}. {question}"
            ),
            "cta": "yes_no",
            "send_as": "merchant_on_behalf",
            "suppression_key": suppression_key,
            "rationale": (
                "The customer belongs to this merchant and opted into "
                "reminders. The due date and slot come from the trigger."
            ),
        }

    # Merchant-facing messages follow.
    if kind == "research_digest":
        item = find_digest_item(category, payload.get("top_item_id"))

        if not item or not item.get("title") or not item.get("source"):
            return {}

        body = (
            f"{merchant_name}, {item['title']} "
            f"({item['source']}). Want the details to review?"
        )
        rationale = (
            "The trigger identifies a specific research item in the "
            "category digest, including its source."
        )

    elif kind in ("perf_dip", "perf_spike"):
        metric = payload.get("metric")
        change = payload.get("delta_pct")
        window = payload.get("window")

        if (
            not metric or not window
            or isinstance(change, bool)
            or not isinstance(change, (int, float))
            or not __import__("math").isfinite(change)
            or (kind == "perf_dip" and change >= 0)
            or (kind == "perf_spike" and change <= 0)
        ):
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
            f"{metric} over {window}; the message offers one next step."
        )

    elif kind == "renewal_due":
        days = payload.get("days_remaining")
        plan = payload.get("plan")

        if days is None or not plan:
            return {}

        body = (
            f"{merchant_name}, your {plan} plan has {days} days remaining. "
            "Want me to outline the renewal options?"
        )
        rationale = (
            f"The trigger identifies the {plan} plan and "
            f"{days} days remaining before renewal."
        )

    elif kind == "competitor_opened":
        competitor = payload.get("competitor_name")
        distance = payload.get("distance_km")

        if not competitor or distance is None:
            return {}

        offer = active_offer(merchant)

        if offer:
            question = f"Want a post highlighting your {offer}?"
        else:
            question = "Want to review your listing against theirs?"

        body = (
            f"{merchant_name}, {competitor} opened {distance} km away. "
            f"{question}"
        )
        rationale = (
            "The competitor and distance come from the trigger. "
            "Any offer mentioned is active in the merchant's account."
        )

    else:
        return compose_extra(category, merchant, trigger)

    return {
        "body": body,
        "cta": "yes_no",
        "send_as": "vera",
        "suppression_key": suppression_key,
        "rationale": rationale,
    }