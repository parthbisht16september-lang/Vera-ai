import json
from pathlib import Path

from bot import compose

data = Path(__file__).resolve().parent.parent / "expanded"
pairs = json.loads((data / "test_pairs.json").read_text())["pairs"]


def load(folder, record_id):
    return json.loads((data / folder / f"{record_id}.json").read_text())


for pair in pairs:
    trigger = load("triggers", pair["trigger_id"])
    merchant = load("merchants", pair["merchant_id"])
    category = load("categories", merchant["category_slug"])
    customer = (
        load("customers", pair["customer_id"])
        if pair.get("customer_id")
        else None
    )

    result = compose(category, merchant, trigger, customer)
    if result:
        print(
            f"{pair['test_id']} [{trigger['kind']}]: "
            f"{result['body']}"
        )
