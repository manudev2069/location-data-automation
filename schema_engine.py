import re
from dataclasses import dataclass, asdict
from typing import Dict, List

import pandas as pd


@dataclass
class ColumnProfile:
    column_name: str
    detected_type: str
    detected_category: str
    confidence: float
    verification_status: str
    reason: str

    def as_dict(self):
        return asdict(self)


class AdaptiveSchemaEngine:
    """Generic CSV schema inference.

    It does not require one fixed column layout. It combines header hints,
    sample values, value patterns and optional location reference evidence.
    Ambiguous columns are reported instead of being guessed as a business field.
    """

    LOCATION_ALIASES = {
        "CITY": ["city", "cityname", "city_name", "locationcity", "location_city", "town", "municipality"],
        "STATE": ["state", "statename", "state_name", "statefullname", "state_full_name", "locationstate", "location_state", "province", "region"],
        "STATE_CODE": ["statecode", "state_code", "stateshortcode", "state_short_code", "stateabbr", "state_abbr", "stateiso"],
        "COUNTRY": ["country", "countryname", "country_name", "locationcountry", "location_country", "nation"],
        "AREA": ["area", "areaname", "area_name", "locationarea", "location_area", "locality", "neighborhood", "district"],
    }

    SPECIAL_ALIASES = {
        "ID": ["id", "recordid", "record_id", "rowid", "uuid", "guid", "area_id", "city_id", "state_id", "country_id"],
        "POSTAL_CODE": ["postalcode", "postal_code", "pincode", "pin", "zip", "zipcode", "zip_code"],
        "LATITUDE": ["latitude", "lat"],
        "LONGITUDE": ["longitude", "long", "lng", "lon"],
        "RANK": ["rank", "cityrank", "city_rank", "ranking", "priority"],
        "EMAIL": ["email", "emailaddress", "email_address", "mail"],
        "PHONE": ["phone", "phonenumber", "phone_number", "mobile", "mobile_number", "contactnumber", "contact_number"],
        "URL": ["url", "website", "web", "sourceurl", "source_url"],
        "DATE": ["date", "createdat", "created_at", "updatedat", "updated_at", "timestamp", "datetime", "time"],
        "BOOLEAN": ["active", "enabled", "isactive", "is_active", "status_flag"],
    }

    def __init__(self, verifier=None):
        self.verifier = verifier
        self.location_vocab = self._build_location_vocab(verifier)

    @staticmethod
    def normalize_header(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", str(value).strip().casefold())

    @staticmethod
    def _nonempty(series: pd.Series) -> pd.Series:
        return series.astype("string").fillna("").str.strip()

    def _build_location_vocab(self, verifier):
        vocab = {"CITY": set(), "STATE": set(), "STATE_CODE": set(), "COUNTRY": set(), "AREA": set()}
        if not verifier:
            return vocab
        for candidates in verifier.reference.values():
            if not isinstance(candidates, list):
                candidates = [candidates]
            for item in candidates:
                typ = str(item.get("type", "")).upper()
                if typ == "TOWN":
                    typ = "CITY"
                if typ in vocab:
                    vocab[typ].add(self.normalize_header(item.get("name", "")))
        return vocab

    def infer(self, df: pd.DataFrame) -> List[ColumnProfile]:
        profiles = []
        for col in df.columns:
            profiles.append(self._infer_column(str(col), df[col]))
        return profiles

    def _infer_column(self, column: str, series: pd.Series) -> ColumnProfile:
        s = self._nonempty(series)
        nonempty = s[s.ne("")]
        header = self.normalize_header(column)

        if len(nonempty) == 0:
            return ColumnProfile(column, "EMPTY", "UNIDENTIFIED", 0.0, "Unverified", "Column contains no non-empty sample values")

        category, header_score = self._header_category(header)
        detected_type, type_score = self._value_type(nonempty)

        # Strong semantic aliases win over generic type inference.
        if category:
            # Semantic headers provide a stronger type signal than a small or
            # mixed sample. This lets fields such as Rank, Email and Latitude
            # validate correctly even when a few rows are bad.
            semantic_type = {
                "ID": "NUMBER" if detected_type == "NUMBER" else detected_type,
                "POSTAL_CODE": "TEXT",
                "LATITUDE": "NUMBER",
                "LONGITUDE": "NUMBER",
                "RANK": "NUMBER",
                "EMAIL": "EMAIL",
                "PHONE": "TEXT",
                "URL": "TEXT",
                "DATE": "DATE/TIME",
                "BOOLEAN": "BOOLEAN",
            }.get(category, detected_type)
            confidence = min(0.99, 0.60 + 0.35 * header_score + 0.05 * type_score)
            verification = self._verification_for(category, nonempty)
            reason = "Category inferred from column name and value pattern"
            return ColumnProfile(column, semantic_type, category, round(confidence, 2), verification, reason)

        # Value-only semantic identification using the reference vocabulary.
        value_category, value_score = self._value_category(nonempty)
        if value_category:
            confidence = round(min(0.95, 0.50 + value_score), 2)
            verification = self._verification_for(value_category, nonempty)
            return ColumnProfile(column, detected_type, value_category, confidence, verification, "Category inferred from reference/value evidence")

        # Generic columns are still identifiable by data type; they are not
        # forced into a made-up business category.
        if detected_type != "UNKNOWN":
            confidence = round(max(0.55, type_score), 2)
            return ColumnProfile(column, detected_type, "TEXT" if detected_type == "TEXT" else detected_type, confidence, "Not Required", "Generic type inferred from sample values")

        return ColumnProfile(column, "UNKNOWN", "UNIDENTIFIED", 0.0, "Unverified", "Unable to infer a reliable type/category")

    def _header_category(self, header):
        for category, aliases in {**self.LOCATION_ALIASES, **self.SPECIAL_ALIASES}.items():
            aliases_norm = {self.normalize_header(x) for x in aliases}
            if header in aliases_norm:
                return category, 1.0
        # Token/substring fallback for names such as primary_city_name.
        checks = [
            ("CITY", ["city", "town", "municipality"]),
            ("STATE", ["state", "province"]),
            ("STATE_CODE", ["statecode", "stateabbr", "stateshortcode"]),
            ("COUNTRY", ["country", "nation"]),
            ("AREA", ["area", "locality", "neighborhood", "district"]),
            ("POSTAL_CODE", ["postal", "pincode", "zipcode", "zip"]),
            ("LATITUDE", ["latitude"]),
            ("LONGITUDE", ["longitude"]),
            ("EMAIL", ["email"]),
            ("PHONE", ["phone", "mobile", "contactnumber"]),
            ("URL", ["url", "website"]),
            ("DATE", ["date", "timestamp", "datetime", "createdat", "updatedat"]),
            ("RANK", ["rank", "ranking"]),
        ]
        for category, tokens in checks:
            if any(token in header for token in tokens):
                return category, 0.85
        return None, 0.0

    def _value_type(self, s):
        sample = s.head(1000)
        lower = sample.str.casefold()
        numeric = pd.to_numeric(sample, errors="coerce").notna().mean()
        datetime_rate = pd.to_datetime(sample, errors="coerce", format="mixed").notna().mean()
        email_rate = lower.str.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$").mean()
        uuid_rate = lower.str.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$").mean()
        bool_rate = lower.isin(["true", "false", "yes", "no", "y", "n", "0", "1"]).mean()

        if uuid_rate >= 0.8:
            return "UUID", 0.98
        if email_rate >= 0.8:
            return "EMAIL", 0.97
        if bool_rate >= 0.95:
            return "BOOLEAN", 0.95
        if numeric >= 0.50:
            return "NUMBER", round(min(0.96, 0.60 + numeric * 0.36), 2)
        if datetime_rate >= 0.90 and numeric < 0.90:
            return "DATE/TIME", 0.93
        if sample.str.len().median() > 0:
            return "TEXT", 0.75
        return "UNKNOWN", 0.0

    def _value_category(self, s):
        normalized = {self.normalize_header(v) for v in s.head(1000)}
        for category in ["CITY", "STATE", "STATE_CODE", "COUNTRY", "AREA"]:
            vocab = self.location_vocab.get(category, set())
            if vocab:
                overlap = len(normalized & vocab) / max(1, len(normalized))
                if overlap >= 0.70:
                    return category, min(0.40, overlap * 0.40)
        return None, 0.0

    def _verification_for(self, category, values):
        if category not in self.location_vocab:
            return "Not Required"
        if not self.location_vocab.get(category):
            return "Unverified"
        normalized = {self.normalize_header(v) for v in values if str(v).strip()}
        known = len(normalized & self.location_vocab[category])
        return "Verified" if known == len(normalized) else "Partially Verified"

    def as_dataframe(self, profiles):
        return pd.DataFrame([p.as_dict() for p in profiles])
