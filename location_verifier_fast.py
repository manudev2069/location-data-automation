from pathlib import Path
import pandas as pd

try:
    from rapidfuzz import process, fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    from difflib import SequenceMatcher
    RAPIDFUZZ_AVAILABLE = False


class LocationVerifier:
    def __init__(self, path):
        self.reference = self._load(path)
        self.cache = {}
        self.keys = list(self.reference.keys())

    def _load(self, path):
        p = Path(path)
        if not p.exists():
            return {}

        df = pd.read_csv(
            p,
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig"
        )

        if not {"name", "type"}.issubset(df.columns):
            raise ValueError(
                "reference/locations.csv must contain name,type"
            )

        result = {}
        for _, row in df.iterrows():
            name = str(row["name"]).strip()
            if name:
                result[self._norm(name)] = {
                    "name": name,
                    "type": str(row["type"]).strip().lower()
                }
        return result

    def verify(self, value, expected_type=None):
        key = self._norm(value)

        if key in self.cache:
            return self._match(
                self.cache[key], expected_type
            )

        # Fast exact lookup first.
        if key in self.reference:
            item = self.reference[key]
            result = {
                "status": "valid",
                "canonical_value": item["name"],
                "detected_type": item["type"],
                "reason": ""
            }
            self.cache[key] = result
            return self._match(result, expected_type)

        # Fuzzy lookup only for unique values not found exactly.
        result = None

        if RAPIDFUZZ_AVAILABLE and self.keys:
            match = process.extractOne(
                key,
                self.keys,
                scorer=fuzz.ratio,
                score_cutoff=94
            )
            if match:
                item = self.reference[match[0]]
                result = {
                    "status": "valid",
                    "canonical_value": item["name"],
                    "detected_type": item["type"],
                    "reason": ""
                }

        elif self.keys:
            # Dependency-free fallback. Exact matching remains fast;
            # fuzzy fallback is only used when rapidfuzz is unavailable.
            best_key = None
            best_score = 0

            for ref_key in self.keys:
                score = SequenceMatcher(
                    None, key, ref_key
                ).ratio()

                if score > best_score:
                    best_score = score
                    best_key = ref_key

            if best_key is not None and best_score >= 0.94:
                item = self.reference[best_key]
                result = {
                    "status": "valid",
                    "canonical_value": item["name"],
                    "detected_type": item["type"],
                    "reason": ""
                }

        if result is not None:
            self.cache[key] = result
            return self._match(result, expected_type)

        result = {
            "status": "unknown",
            "canonical_value": str(value),
            "detected_type": "",
            "reason": (
                f"Location Not Verified: expected {expected_type}"
                if expected_type
                else "Location Not Verified"
            )
        }

        self.cache[key] = result
        return result

    @staticmethod
    def _match(result, expected_type):
        if not expected_type:
            return result

        if result["detected_type"] == expected_type:
            return result

        return {
            "status": "unknown",
            "canonical_value": result["canonical_value"],
            "detected_type": result["detected_type"],
            "reason": (
                "Location Type Mismatch: detected "
                f"{result['detected_type']}, expected {expected_type}"
            )
        }

    @staticmethod
    def _norm(value):
        return " ".join(
            str(value).strip().casefold().split()
        )
