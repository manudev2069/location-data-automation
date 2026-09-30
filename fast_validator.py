import pandas as pd

class FastValidator:
    OUTPUT = {
        "Unknown", "Unknown_Columns", "Unknown_Reasons",
        "Validation_Status", "Correction_Status"
    }

    EXPECTED = {
        "id","uuid","parent_id","location_level","location_type",
        "name","short_name","slug","code","alternate_name","description",
        "latitude","longitude","timezone","postal_code","materialized_path",
        "status","city_rank","metadata","created_at","updated_at"
    }

    NUMERIC = {
        "id","parent_id","location_level","city_rank",
        "latitude","longitude"
    }

    DATE = {"created_at", "updated_at"}

    LOCATION = {
        "city":"city","town":"city","district":"city",
        "state":"state","province":"state",
        "country":"country","nation":"country"
    }

    def __init__(self, verifier):
        self.verifier = verifier

    def process(self, df, progress_callback=None):
        data = df.copy().fillna("")
        n = len(data)

        unknown = pd.Series("", index=data.index, dtype="object")
        unknown_cols = pd.Series("", index=data.index, dtype="object")
        reasons = pd.Series("", index=data.index, dtype="object")
        corrected = pd.Series(False, index=data.index)

        # Unknown/new columns
        for col in list(data.columns):
            name = str(col).strip()
            if name in self.OUTPUT or name in self.EXPECTED:
                continue

            s = data[col].astype("string").fillna("")
            bad = s.str.strip().ne("")
            if bad.any():
                self._issue(
                    unknown, unknown_cols, reasons, bad,
                    name, s, "Unknown/New Column"
                )
                data.loc[bad, col] = ""

        cols = [
            c for c in data.columns
            if str(c).strip() in self.EXPECTED
        ]

        total_cols = max(len(cols), 1)

        for idx, col in enumerate(cols, 1):
            name = str(col).strip()
            s = data[col].astype("string").fillna("")
            nonempty = s.str.strip().ne("")

            if not nonempty.any():
                self._progress(
                    progress_callback, idx, total_cols, n,
                    f"Checking: {name}"
                )
                continue

            # Encoding corruption
            garbled = nonempty & s.str.contains(
                r"Ã|Â|à¤|â|�", regex=True, na=False
            )

            if garbled.any():
                self._issue(
                    unknown, unknown_cols, reasons,
                    garbled, name, s, "Encoding/Garbled Text"
                )
                data.loc[garbled, col] = ""

            remaining = nonempty & ~garbled

            # Numeric
            if name.lower() in self.NUMERIC:
                numeric = pd.to_numeric(
                    s.where(remaining, ""), errors="coerce"
                )
                bad = remaining & numeric.isna()

                if bad.any():
                    self._issue(
                        unknown, unknown_cols, reasons,
                        bad, name, s,
                        "Invalid Type: Expected numeric value"
                    )
                    data.loc[bad, col] = ""

                self._progress(
                    progress_callback, idx, total_cols, n,
                    f"Validating numeric: {name}"
                )
                continue

            # Date
            if name.lower() in self.DATE:
                parsed = pd.to_datetime(
                    s.where(remaining, ""),
                    errors="coerce",
                    dayfirst=True,
                    format="mixed"
                )
                bad = remaining & parsed.isna()

                if bad.any():
                    self._issue(
                        unknown, unknown_cols, reasons,
                        bad, name, s, "Invalid Date/Time"
                    )
                    data.loc[bad, col] = ""

                self._progress(
                    progress_callback, idx, total_cols, n,
                    f"Validating date: {name}"
                )
                continue

            # Semantic location verification
            expected = self._location_type(name)

            if expected:
                vals = s[remaining]
                mapping = {}
                bad_reasons = {}

                for value in vals.drop_duplicates().tolist():
                    result = self.verifier.verify(value, expected)
                    if result["status"] == "valid":
                        mapping[value] = result["canonical_value"]
                    else:
                        bad_reasons[value] = result["reason"]

                if mapping:
                    mask = remaining & s.isin(mapping.keys())
                    data.loc[mask, col] = s[mask].map(mapping)

                if bad_reasons:
                    bad = remaining & s.isin(bad_reasons.keys())
                    if bad.any():
                        self._issue_series(
                            unknown, unknown_cols, reasons,
                            bad, name, s, s[bad].map(bad_reasons)
                        )
                        data.loc[bad, col] = ""

                unresolved = (
                    remaining
                    & ~s.isin(mapping.keys())
                    & ~s.isin(bad_reasons.keys())
                )

                if unresolved.any():
                    self._issue(
                        unknown, unknown_cols, reasons,
                        unresolved, name, s,
                        f"Location Not Verified: expected {expected}"
                    )
                    data.loc[unresolved, col] = ""

                self._progress(
                    progress_callback, idx, total_cols, n,
                    f"Verifying {expected}: {name}"
                )
                continue

            # Fast generic text cleaning.
            cleaned = (
                s.str.replace(
                    r"[^A-Za-z0-9\s\.,'’\-\(\)/&\+:%_\u0900-\u097F]",
                    "",
                    regex=True
                )
                .str.replace(r"\s+", " ", regex=True)
                .str.strip()
            )

            changed = remaining & cleaned.ne(s)

            if changed.any():
                self._issue(
                    unknown, unknown_cols, reasons,
                    changed, name, s,
                    "Auto-Corrected: Removed invalid character(s)"
                )
                data.loc[changed, col] = cleaned[changed]
                corrected.loc[changed] = True

            empty = (
                remaining
                & data[col].astype("string").str.strip().eq("")
            )

            if empty.any():
                self._issue(
                    unknown, unknown_cols, reasons,
                    empty, name, s, "Unknown/Empty After Cleaning"
                )

            self._progress(
                progress_callback, idx, total_cols, n,
                f"Cleaning text: {name}"
            )

        data["Unknown"] = unknown
        data["Unknown_Columns"] = unknown_cols
        data["Unknown_Reasons"] = reasons

        has_issue = reasons.str.len().gt(0)

        data["Validation_Status"] = has_issue.map(
            {True:"Unknown", False:"Valid"}
        )

        data["Correction_Status"] = "No Correction"
        data.loc[corrected & ~has_issue, "Correction_Status"] = "Auto-Corrected"
        data.loc[corrected & has_issue, "Correction_Status"] = (
            "Partially Corrected - Review Required"
        )

        valid = data.loc[~has_issue].copy()
        unknown_df = data.loc[has_issue].copy()

        summary = {
            "total_rows": n,
            "valid_rows": len(valid),
            "unknown_rows": len(unknown_df),
            "valid_percentage": round(
                len(valid) * 100 / n, 2
            ) if n else 0,
            "unknown_percentage": round(
                len(unknown_df) * 100 / n, 2
            ) if n else 0
        }

        if progress_callback:
            progress_callback(n, n, "Validation complete. Writing output...")

        return valid, unknown_df, summary

    @staticmethod
    def _issue(u, uc, r, mask, name, series, reason):
        FastValidator._append(
            u, mask, name + "=" + series.astype("string")
        )
        FastValidator._append(
            uc, mask, pd.Series(name, index=series.index)
        )
        FastValidator._append(
            r, mask, pd.Series(reason, index=series.index)
        )

    @staticmethod
    def _issue_series(u, uc, r, mask, name, series, reasons):
        FastValidator._append(
            u, mask, name + "=" + series.astype("string")
        )
        FastValidator._append(
            uc, mask, pd.Series(name, index=series.index)
        )
        FastValidator._append(r, mask, reasons)

    @staticmethod
    def _append(target, mask, values):
        old = target.loc[mask]
        vals = values.loc[mask].astype("string")
        target.loc[mask] = old.where(old.eq(""), old + " | ") + vals

    @staticmethod
    def _location_type(name):
        low = name.lower()
        for hint, kind in FastValidator.LOCATION.items():
            if hint in low:
                return kind
        return None

    @staticmethod
    def _progress(callback, idx, total_cols, n, status):
        if callback:
            callback(
                int(idx * n / total_cols),
                n,
                status
            )
