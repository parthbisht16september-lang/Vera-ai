import json
from pathlib import Path

from bot import compose
from skip_reasons import explain_skip

root = Path(__file__).resolve().parent.parent
data_dir = root / "expanded"
pairs = json.loads((data_dir / "test_pairs.json").read_text())["pairs"]


def load(folder, record_id):
    path = data_dir / folder / f"{record_id}.json"
    return json.loads(path.read_text())


rows = []

for pair in pairs:
    trigger = load("triggers", pair["trigger_id"])
    merchant = load("merchants", pair["merchant_id"])
    category = load("categories", merchant["category_slug"])
    customer = (
        load("customers", pair["customer_id"])
        if pair.get("customer_id")
        else None
    )

    message = compose(category, merchant, trigger, customer)

    if message:
        row = {"test_id": pair["test_id"], **message}
    else:
        row = {
            "test_id": pair["test_id"],
            "body": "",
            "cta": "none",
            "send_as": "merchant_on_behalf" if trigger.get("scope") == "customer" else "vera",
            "suppression_key": trigger.get("suppression_key", trigger["id"]),
            "rationale": "No message: " + explain_skip(category, merchant, trigger, customer) + ".",
        }

    rows.append(row)

output = root / "submission.jsonl"
output.write_text(
    "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
)

assert len(rows) == 30
print(f"Wrote {len(rows)} rows to {output.name}")
print(f"Messages: {sum(bool(row['body']) for row in rows)}")
print(f"Skipped: {sum(not row['body'] for row in rows)}")
