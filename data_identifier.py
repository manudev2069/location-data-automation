from dataclasses import dataclass
from typing import Dict, List

import pandas as pd

from schema_engine import AdaptiveSchemaEngine, ColumnProfile


@dataclass
class IdentificationResult:
    profiles: List[ColumnProfile]
    role_columns: Dict[str, str]


class DataIdentifier:
    """Adaptive data identifier used before row validation.

    It turns a CSV's unknown column layout into a small set of semantic roles.
    It deliberately keeps ambiguous roles unresolved instead of guessing.
    """

    LOCATION_ROLES = {"CITY", "STATE", "COUNTRY", "AREA"}

    def __init__(self, verifier=None):
        self.schema_engine = AdaptiveSchemaEngine(verifier)

    def identify(self, df: pd.DataFrame) -> IdentificationResult:
        profiles = self.schema_engine.infer(df)
        role_columns: Dict[str, str] = {}

        # Prefer the strongest profile for each role. Ties are resolved by
        # confidence and then by the first occurrence in the CSV.
        for profile in profiles:
            role = profile.detected_category
            if not role or role == "UNIDENTIFIED":
                continue
            current = role_columns.get(role)
            if current is None:
                role_columns[role] = profile.column_name
                continue
            old = next((p for p in profiles if p.column_name == current), None)
            if old and profile.confidence > old.confidence:
                role_columns[role] = profile.column_name

        return IdentificationResult(profiles=profiles, role_columns=role_columns)

    @staticmethod
    def normalize_role(role: str) -> str:
        return str(role or "").strip().upper()
