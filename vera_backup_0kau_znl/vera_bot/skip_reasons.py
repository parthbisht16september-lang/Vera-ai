"""Explain conservative no-send decisions without changing composition."""
def explain_skip(category, merchant, trigger, customer=None):
    kind = trigger.get('kind')
    payload = trigger.get('payload') or {}
    reasons = []
    scopes = (customer or {}).get('consent', {}).get('scope', [])
    required_scope = {
        'appointment_tomorrow': 'appointment_reminders',
        'chronic_refill_due': 'refill_reminders',
        'recall_due': 'recall_reminders',
        'customer_lapsed_soft': 'winback_offers',
        'customer_lapsed_hard': 'winback_offers',
    }.get(kind)
    if trigger.get('scope') == 'customer':
        if customer is None:
            reasons.append('Customer context is missing')
        elif required_scope and required_scope not in scopes:
            reasons.append(f'Missing {required_scope} consent')
        if kind in ('customer_lapsed_soft', 'customer_lapsed_hard'):
            expected = kind.removeprefix('customer_')
            if (customer or {}).get('state') != expected:
                reasons.append(f'Customer state is {(customer or {}).get("state")!r}, not {expected!r}')
    if kind == 'appointment_tomorrow' and not (payload.get('appointment_iso') or payload.get('appointment_at')):
        reasons.append('No appointment timestamp supplied')
    elif kind == 'chronic_refill_due' and not payload.get('stock_runs_out_iso'):
        reasons.append('No refill due date supplied')
    elif kind == 'recall_due' and not (payload.get('due_date') and payload.get('service_due')):
        reasons.append('No recall service and due date supplied')
    elif kind == 'competitor_opened' and not payload.get('competitor_name'):
        reasons.append('No competitor identity or opening facts supplied')
    elif kind == 'curious_ask_due' and payload.get('placeholder'):
        reasons.append('No scheduled question supplied; existing planning intent should continue in its own conversation')
    elif kind == 'festival_upcoming':
        if not payload.get('festival') or not payload.get('date'):
            reasons.append('No festival name and date supplied')
        elif isinstance(payload.get('days_until'), int) and payload['days_until'] > 30:
            reasons.append(f"Festival is {payload['days_until']} days away, outside the bot's 30-day planning policy")
    elif kind == 'milestone_reached' and not payload.get('metric'):
        reasons.append('No milestone metric, current value or target supplied')
    elif kind in ('perf_dip', 'perf_spike') and payload.get('placeholder'):
        delta = merchant.get('performance', {}).get('delta_7d', {})
        reasons.append(f'No merchant metric supports the trigger direction: {delta}')
    return '; '.join(reasons) or 'Context fails an identity, consent, supported-kind or required-fact check'
