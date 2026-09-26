import json
from collections import Counter
from pathlib import Path

from bot import compose

DATA = Path(__file__).resolve().parent.parent / "expanded"
pairs = json.loads((DATA / "test_pairs.json").read_text())["pairs"]

handled = []
skipped = []


def load(folder, record_id):
    return json.loads((DATA / folder / f"{record_id}.json").read_text())


for pair in pairs:
    trigger = load("triggers", pair["trigger_id"])
    merchant = load("merchants", pair["merchant_id"])
    category = load("categories", merchant["category_slug"])

    customer = None
    if pair.get("customer_id"):
        customer = load("customers", pair["customer_id"])

    result = compose(category, merchant, trigger, customer)
    item = (pair["test_id"], trigger["kind"])

    if result:
        handled.append(item)
    else:
        skipped.append(item)

print(f"Handled: {len(handled)}/{len(pairs)}")
print("Handled kinds:", dict(Counter(kind for _, kind in handled)))
print("\nSkipped pairs:")
for test_id, kind in skipped:
    print(f"  {test_id}: {kind}")
