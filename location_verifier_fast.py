from pathlib import Path
import pandas as pd

try:
    from rapidfuzz import process, fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    process = fuzz = None
    RAPIDFUZZ_AVAILABLE = False


class LocationVerifier:
    """Fast location verifier.

    Exact normalized matches are O(1). Fuzzy matching is deliberately limited
    to small batches of unresolved unique values so very large CSVs do not
    spend minutes comparing every row/value.
    """
    FUZZY_MAX_UNIQUE = 5000
    FUZZY_CUTOFF = 94

    def __init__(self, path):
        self.reference = self._load(path)
        self.cache = {}
        self.keys = list(self.reference.keys())
        self.types = set()
        for items in self.reference.values():
            for item in items:
                self.types.add(item["type"])

    def _load(self, path):
        p = Path(path)
        if not p.exists():
            return {}
        df = pd.read_csv(p, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        required = {"name", "type"}
        if not required.issubset(df.columns):
            raise ValueError("reference/locations.csv must contain name,type")
        result = {}
        for row in df.itertuples(index=False):
            row_dict = row._asdict()
            name = str(row_dict.get("name", "")).strip()
            if not name:
                continue
            key = self._norm(name)
            item = {
                "name": name,
                "type": str(row_dict.get("type", "")).strip().lower(),
                "parent_name": str(row_dict.get("parent_name", "")).strip(),
                "country": str(row_dict.get("country", "")).strip(),
            }
            result.setdefault(key, []).append(item)
        return result

    def verify(self, value, expected_type=None, expected_parent=None, expected_country=""):
        key = self._norm(value)
        cache_key = (key, expected_type or "", self._norm(expected_parent), self._norm(expected_country))
        if cache_key in self.cache:
            return self.cache[cache_key]

        candidates = self.reference.get(key, [])
        result = self._select(candidates, value, expected_type, expected_parent, expected_country)
        if result is None and candidates:
            result = {"status": "unknown", "canonical_value": str(value), "detected_type": candidates[0]["type"],
                      "reason": f"Location Type/Hierarchy Mismatch: detected {candidates[0]['type']}"}
        elif result is None:
            result = {"status": "unknown", "canonical_value": str(value), "detected_type": "",
                      "reason": f"Location Not Verified: expected {expected_type}" if expected_type else "Location Not Verified"}
        self.cache[cache_key] = result
        return result

    def verify_many(self, values, expected_type=None, parents=None, countries=None, allow_fuzzy=True):
        """Return a dict keyed by (value,parent,country) for unique input keys."""
        values = pd.Series(values, dtype="string").fillna("").str.strip()
        parents = pd.Series(parents, index=values.index, dtype="string").fillna("").str.strip() if parents is not None else pd.Series("", index=values.index, dtype="string")
        countries = pd.Series(countries, index=values.index, dtype="string").fillna("").str.strip() if countries is not None else pd.Series("", index=values.index, dtype="string")
        keys_df = pd.DataFrame({"value": values, "parent": parents, "country": countries}).drop_duplicates()
        out = {}

        # Exact lookup first: no fuzzy work for known values.
        unresolved = []
        for row in keys_df.itertuples(index=False):
            value, parent, country = str(row.value), str(row.parent), str(row.country)
            if not value:
                continue
            key = (self._norm(value), self._norm(parent), self._norm(country), expected_type or "")
            cached = self.cache.get(key)
            if cached is not None:
                out[(value, parent, country)] = cached
                continue
            candidates = self.reference.get(key[0], [])
            result = self._select(candidates, value, expected_type, parent, country)
            if result is not None:
                self.cache[key] = result
                out[(value, parent, country)] = result
            else:
                unresolved.append((value, parent, country, key))

        # Fuzzy matching only for small unresolved sets. Large datasets skip it
        # intentionally: unresolved values are sent to Unknown instead of
        # making the entire run impractically slow.
        if allow_fuzzy and RAPIDFUZZ_AVAILABLE and unresolved and len(unresolved) <= self.FUZZY_MAX_UNIQUE and self.keys:
            for value, parent, country, cache_key in unresolved:
                match = process.extractOne(self._norm(value), self.keys, scorer=fuzz.ratio, score_cutoff=self.FUZZY_CUTOFF)
                candidates = self.reference.get(match[0], []) if match else []
                result = self._select(candidates, value, expected_type, parent, country)
                if result is None:
                    if candidates:
                        result = {"status": "unknown", "canonical_value": value, "detected_type": candidates[0]["type"],
                                  "reason": f"Location Type/Hierarchy Mismatch: detected {candidates[0]['type']}"}
                    else:
                        result = {"status": "unknown", "canonical_value": value, "detected_type": "",
                                  "reason": f"Location Not Verified: expected {expected_type}" if expected_type else "Location Not Verified"}
                self.cache[cache_key] = result
                out[(value, parent, country)] = result
        else:
            for value, parent, country, cache_key in unresolved:
                result = {"status": "unknown", "canonical_value": value, "detected_type": "",
                          "reason": f"Location Not Verified: expected {expected_type}" if expected_type else "Location Not Verified"}
                self.cache[cache_key] = result
                out[(value, parent, country)] = result

        return out

    def _select(self, candidates, value, expected_type, expected_parent, expected_country):
        for item in candidates:
            if expected_type and item["type"] != expected_type:
                continue
            if expected_parent and item["parent_name"] and self._norm(expected_parent) != self._norm(item["parent_name"]):
                continue
            if expected_country and item["country"] and self._norm(expected_country) != self._norm(item["country"]):
                continue
            return {"status": "valid", "canonical_value": item["name"], "detected_type": item["type"],
                    "parent_name": item["parent_name"], "country": item["country"], "reason": ""}
        return None

    @staticmethod
    def _norm(value):
        return " ".join(str(value).strip().casefold().split())
