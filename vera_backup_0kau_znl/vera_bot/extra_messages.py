import re

def digest_item(category, item_id):
    if not item_id:
        return None
    for item in category.get("digest", []):
        if item.get("id") == item_id:
            return item
    return None


def compose_extra(category, merchant, trigger):
    kind = trigger.get("kind")
    payload = trigger.get("payload") or {}
    name = merchant.get("identity", {}).get("name", "there")
    key = trigger.get("suppression_key") or trigger.get("id", "")

    if payload.get("placeholder") is True:
        return {}

    if kind == "cde_opportunity":
        item = digest_item(category, payload.get("digest_item_id"))
        if not item or not item.get("title"):
            return {}

        detail = item["title"]
        if payload.get("credits") is not None:
            detail += f"; {payload['credits']} credits"

        body = f"{name}, {detail}. Want the event details?"
        cta = "yes_no"
        reason = "The event and credits come from the supplied digest and trigger."

    elif kind == "regulation_change":
        item = digest_item(category, payload.get("top_item_id"))
        if not item or not item.get("title") or not item.get("source"):
            return {}

        deadline = payload.get("deadline_iso")
        date_text = (
            f" Deadline: {deadline}."
            if deadline and deadline not in item["title"]
            else ""
        )
        guidance = str(item.get("actionable") or "").strip().rstrip(".")
        action_text = f" {guidance}." if guidance else ""
        body = (
            f"{name}, {item['title']} ({item['source']})."
            f"{date_text}{action_text} Want a short review checklist?"
        )
        cta = "yes_no"
        reason = "Uses the supplied regulation, source, deadline, and actionable guidance."

    elif kind == "festival_upcoming":
        from datetime import date

        festival = payload.get("festival")
        event_date = payload.get("date")
        days = payload.get("days_until")
        relevant = payload.get("category_relevance") or []

        if not festival or not isinstance(event_date, str):
            return {}
        try:
            date.fromisoformat(event_date)
        except ValueError:
            return {}

        if type(days) is not int or not 0 <= days <= 30:
            return {}
        if relevant and merchant.get("category_slug") not in relevant:
            return {}

        body = (
            f"{name}, {festival} is on {event_date}, {days} days away. "
            "Want a short festival post drafted for your business?"
        )
        cta = "yes_no"
        reason = (
            "Uses the supplied festival date and a 30-day planning window; "
            "does not invent a seasonal offer."
        )

    elif kind == "active_planning_intent":
        topic = payload.get("intent_topic")
        if not topic:
            return {}

        topic = topic.replace("_", " ")
        if "thali" in topic:
            body = (
                f"{name}, for the {topic}, I'd outline the menu, "
                "minimum order, delivery window, and per-head price. "
                "What per-head price should I use?"
            )
        elif "kids yoga" in topic:
            body = (
                f"{name}, for the {topic}, I'd outline the age group, "
                "session count, and schedule. Which age group should I use?"
            )
        else:
            body = (
                f"{name}, for your {topic} idea, I'd outline the offer, "
                "availability, and audience. Which detail should I use first?"
            )
        cta = "open_ended"
        reason = "Continues the merchant's stated planning topic."

    elif kind == "curious_ask_due":
        if payload.get("ask_template") != "what_service_in_demand_this_week":
            return {}

        body = (
            f"{name}, which service is getting the most enquiries "
            "this week?"
        )
        cta = "open_ended"
        reason = "Asks one useful question from the scheduled trigger."

    elif kind == "category_seasonal":
        trends = payload.get("trends") or []
        if not trends:
            return {}

        item = str(trends[0]).split("_")[0]
        body = (
            f"{name}, your category's seasonal data flags increased "
            f"interest in {item}. Want a short stock-planning checklist?"
        )
        cta = "yes_no"
        reason = "Uses a supplied seasonal category signal."

    elif kind == "dormant_with_vera":
        days = payload.get("days_since_last_merchant_message")
        topic = payload.get("last_topic")
        if days is None or not topic:
            return {}

        body = (
            f"{name}, it has been {days} days since we discussed "
            f"{str(topic).replace('_', ' ')}. "
            "Would you like to pick that up?"
        )
        cta = "yes_no"
        reason = "References the supplied conversation gap and last topic."

    elif kind == "gbp_unverified":
        if payload.get("verified") is not False:
            return {}

        method = payload.get("verification_path")
        if not method:
            return {}

        body = (
            f"{name}, your listing is marked unverified. "
            f"The listed verification options are "
            f"{str(method).replace('_', ' ')}. "
            "Want the steps?"
        )
        cta = "yes_no"
        reason = "Uses the listing status and verification route in the trigger."

    elif kind == "ipl_match_today":
        match = payload.get("match")
        city = payload.get("city")
        if not match or not city:
            return {}

        offers = [
            offer.get("title")
            for offer in merchant.get("offers", [])
            if (
                offer.get("status") == "active"
                and offer.get("title")
                and not re.search(
                    r"\b(mon|tue|wed|thu|fri|sat|sun)(day)?\b",
                    offer["title"],
                    re.IGNORECASE,
                )
            )
        ]
        offer = offers[0] if offers else None

        if offer:
            question = f"Want a match-day post for your {offer}?"
        else:
            question = "Want a match-day post drafted?"

        body = f"{name}, {match} is scheduled in {city}. {question}"
        cta = "yes_no"
        reason = "Combines the supplied match and city with an active offer."

    elif kind == "milestone_reached":
        metric = payload.get("metric")
        value = payload.get("value_now")
        target = payload.get("milestone_value")
        if not metric or value is None or target is None:
            return {}

        label = str(metric).replace("_", " ")
        body = (
            f"{name}, your {label} is at {value}, "
            f"approaching {target}. Want a milestone post drafted?"
        )
        cta = "yes_no"
        reason = "Uses the current value and milestone from the trigger."

    else:
        return {}

    return {
        "body": body,
        "cta": cta,
        "send_as": "vera",
        "suppression_key": key,
        "rationale": reason,
    }
