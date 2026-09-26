import json
import sqlite3
from contextlib import closing
from pathlib import Path


class StateStore:
    def __init__(self, filename):
        self.path = Path(filename)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        with closing(sqlite3.connect(str(self.path))) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS bot_state (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        payload TEXT NOT NULL
                    )
                    """
                )

    def load(self):
        with closing(sqlite3.connect(str(self.path))) as connection:
            row = connection.execute(
                "SELECT payload FROM bot_state WHERE id = 1"
            ).fetchone()

        if row is None:
            return {}, set(), {}

        saved = json.loads(row[0])
        contexts = {
            (scope, context_id): record
            for scope, context_id, record in saved["contexts"]
        }
        sent = {tuple(key) for key in saved["sent"]}
        return contexts, sent, saved["conversations"]

    def save(self, contexts, sent, conversations):
        payload = json.dumps({
            "contexts": [
                [scope, context_id, record]
                for (scope, context_id), record in contexts.items()
            ],
            "sent": list(sent),
            "conversations": conversations,
        }, ensure_ascii=False)

        with closing(sqlite3.connect(str(self.path))) as connection:
            with connection:
                connection.execute(
                    "INSERT OR REPLACE INTO bot_state (id, payload) VALUES (1, ?)",
                    (payload,),
                )
