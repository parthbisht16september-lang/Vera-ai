"""Concrete follow-ups; drafts never claim to publish or book anything."""
import re


def merchant_followup(state, message):
    if state.get("followup_delivered"):
        return {
            "action": "wait", "wait_seconds": 1800,
            "rationale": "Draft already delivered; wait for a specific revision instead of repeating it.",
        }
    kind = state.get("trigger_kind")
    context = state.get("reply_context") or {}
    payload = context.get("payload") or {}
    name = context.get("merchant_name") or "your business"
    cta = "none"

    if kind == "active_planning_intent":
        topic = str(state.get("topic") or "your proposed offer").replace("_", " ")
        if "thali" in topic:
            price = re.fullmatch(r"(?:₹|rs\.?\s*)?(\d+(?:\.\d+)?)(?:\s*(?:per head|each))?", message.strip(), re.I)
            price_text = f"₹{price.group(1)} per head (your supplied price)" if price else "[price per head to confirm]"
            body = (
                f"Working draft for {name}: {topic}. Menu: [confirm dishes]. "
                f"Minimum order: [confirm quantity]. Delivery: [confirm area and window]. "
                f"Price: {price_text}. This is a proposal, not a live offer. "
                "Which dishes should the package include?"
            )
        elif "kids yoga" in topic:
            body = (
                f"Working draft for {name}: {topic}. Age group: [confirm]. "
                "Session count and schedule: [confirm]. Fee: [confirm]. "
                "This is a proposal, not a live program. Which age group should it serve?"
            )
        else:
            body = f"Working draft: {topic}. Audience: [confirm]. Inclusions: [confirm]. Schedule: [confirm]. Price: [confirm]. Which inclusion should we start with?"
        cta = "open_ended"
    elif kind in ("perf_dip", "perf_spike", "dormant_with_vera"):
        body = (
            "Review checklist: 1) Compare this period's calls and views with the previous period. "
            "2) Check listing hours, phone number and missed enquiries. "
            "3) Note any recent listing or offer changes. "
            "Choose one change to test and track the same metrics next week; the current data alone does not establish a cause."
        )
    elif kind == "regulation_change":
        item = state.get("digest_item") or {}
        source = item.get("source") or "the supplied source"
        step = str(item.get("actionable") or "Review applicability with the responsible professional").rstrip('.')
        body = f"Review checklist: 1) Verify {source}. 2) {step}. 3) Record required changes and deadlines."
    elif kind in ("research_digest", "cde_opportunity"):
        item = state.get("digest_item") or {}
        if not item.get("title"):
            return {"action": "wait", "wait_seconds": 1800, "rationale": "Event or source details are unavailable in this conversation."}
        details = [str(item[k]) for k in ("title", "source", "url", "actionable") if item.get(k)]
        body = "Supplied details: " + " — ".join(details) + ". Verify the source before acting."
    elif kind == "category_seasonal":
        body = "Stock review checklist: 1) Check current stock and expiry dates. 2) Compare recent sales with stock on hand. 3) Check supplier lead times before deciding an order quantity."
    elif kind == "gbp_unverified":
        method = str(payload.get("verification_path") or "the options shown in your profile").replace('_', ' ')
        body = f"Open your business profile's verification screen and check the available options ({method}, according to the supplied record). Follow that screen's instructions. Keep any verification code private."
    elif kind in ("competitor_opened", "ipl_match_today", "festival_upcoming", "milestone_reached"):
        # Reuse only the supplied opening's factual content; remove its CTA.
        initial = context.get("initial_body", "")
        fact = initial.split("Want ", 1)[0].strip()
        if not fact:
            return {"action": "wait", "wait_seconds": 1800, "rationale": "Original facts are unavailable; cannot produce a grounded draft."}
        if kind == "competitor_opened":
            body = "Listing review checklist: confirm your hours and contact details, check that service photos are current, and review the terms of your active offer. Avoid unsupported comparisons with competitors."
        else:
            body = f"Draft for review: {fact} This draft has not been published."
    else:
        return {"action": "wait", "wait_seconds": 1800, "rationale": "No supported follow-up for this topic; wait for a specific request."}

    state["followup_delivered"] = True
    state["last_draft"] = body
    return {"action": "send", "body": body, "cta": cta,
            "rationale": "Delivers a concrete draft or checklist with supplied facts; unconfirmed details remain explicit placeholders."}
