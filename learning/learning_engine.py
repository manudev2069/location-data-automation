from pathlib import Path
import csv
from datetime import datetime


class LearningEngine:
    """Lightweight feedback learning layer with bulk lookup support."""
    FIELDS = ["field", "original", "corrected", "source", "approved", "times_seen", "first_seen", "last_seen"]

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = {}
        self.loaded = 0
        self.reused = 0
        self.new_learned = 0
        self._load()

    @staticmethod
    def _norm(value):
        return " ".join(str(value).strip().casefold().split())

    def _key(self, field, original):
        return (str(field).strip().casefold(), self._norm(original))

    def _load(self):
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                if str(row.get("approved", "yes")).strip().lower() != "yes":
                    continue
                key = self._key(row.get("field", ""), row.get("original", ""))
                if key[1]:
                    self.data[key] = row
        self.loaded = len(self.data)

    def lookup(self, field, original):
        row = self.data.get(self._key(field, original))
        if row:
            self.reused += 1
            return row.get("corrected", "")
        return None

    def lookup_many(self, field, series):
        """Vector-friendly lookup. Returns normalized-key -> corrected mapping."""
        out = {}
        for value in pd_unique(series):
            row = self.data.get(self._key(field, value))
            if row:
                out[value] = row.get("corrected", "")
        self.reused += len(out)
        return out

    def learn(self, field, original, corrected, source="auto"):
        original = str(original)
        corrected = str(corrected)
        if not original.strip() or original == corrected:
            return False
        key = self._key(field, original)
        now = datetime.now().isoformat(timespec="seconds")
        if key in self.data:
            row = self.data[key]
            row["corrected"] = corrected
            row["times_seen"] = str(int(row.get("times_seen", "1") or 1) + 1)
            row["last_seen"] = now
            return False
        self.data[key] = {
            "field": str(field), "original": original, "corrected": corrected,
            "source": source, "approved": "yes", "times_seen": "1",
            "first_seen": now, "last_seen": now
        }
        self.new_learned += 1
        return True

    def learn_many(self, field, pairs, source="auto"):
        for original, corrected in pairs:
            self.learn(field, original, corrected, source)

    def save(self):
        with self.path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.FIELDS)
            writer.writeheader()
            for row in sorted(self.data.values(), key=lambda x: (x["field"].lower(), x["original"].lower())):
                writer.writerow({k: row.get(k, "") for k in self.FIELDS})

    def stats(self):
        return {"learned_total": len(self.data), "new_learned": self.new_learned, "reused": self.reused}


def pd_unique(series):
    # Small helper avoids importing pandas into the learning module.
    return set(str(v) for v in series if str(v).strip())
