import json
from pathlib import Path

from bot import compose

DATA = Path(__file__).resolve().parent.parent / "expanded"


def load(folder, file_id):
    return json.loads((DATA / folder / f"{file_id}.json").read_text())


def check(trigger_id):
    trigger = load("triggers", trigger_id)
    merchant = load("merchants", trigger["merchant_id"])
    category = load("categories", merchant["category_slug"])

    customer = None
    if trigger.get("customer_id"):
        customer = load("customers", trigger["customer_id"])

    result = compose(category, merchant, trigger, customer)
    print(f"\n{trigger['kind']}:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


research = check("trg_001_research_digest_dentists")
recall = check("trg_003_recall_due_priya")

assert research["send_as"] == "vera"
assert recall["send_as"] == "merchant_on_behalf"

print("\nBoth checks passed.")
