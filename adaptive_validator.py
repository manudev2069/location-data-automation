import pandas as pd
from data_identifier import DataIdentifier
from state_code_mapper import StateCodeMapper
from location_resolver import LocationResolver


class AdaptiveValidator:
    OUTPUT = {
        "Unknown",
        "Unknown_Columns",
        "Unknown_Reasons",
        "Validation_Status",
        "Correction_Status",
    }

    LOCATION_CATEGORIES = {
        "CITY",
        "STATE",
        "STATE_CODE",
        "COUNTRY",
        "AREA",
    }

    def __init__(self, verifier, learning=None):
        self.verifier = verifier
        self.learning = learning
        self.identifier = DataIdentifier(verifier)

    def process(self, df, progress_callback=None):
        data = df.copy().fillna("")
        n = len(data)

        if n == 0:
            for c in [
                "Unknown",
                "Unknown_Columns",
                "Unknown_Reasons",
            ]:
                data[c] = ""

            data["Validation_Status"] = "Valid"
            data["Correction_Status"] = "No Correction"

            profiles = self.identifier.identify(data).profiles

            return (
                data.copy(),
                data.copy(),
                self._summary(
                    0,
                    0,
                    0,
                    self.identifier.schema_engine.as_dataframe(profiles),
                ),
                self.identifier.schema_engine.as_dataframe(profiles),
            )

        unknown = pd.Series("", index=data.index, dtype="string")
        unknown_cols = pd.Series("", index=data.index, dtype="string")
        reasons = pd.Series("", index=data.index, dtype="string")

        corrected = pd.Series(False, index=data.index)
        learned_reused = pd.Series(False, index=data.index)

        # ---------------------------------------------------------
        # Phase 0: Adaptive Schema Identification
        # ---------------------------------------------------------
        identified = self.identifier.identify(data)

        profiles = identified.profiles
        profile_map = {p.column_name: p for p in profiles}

        schema_df = self.identifier.schema_engine.as_dataframe(
            profiles
        )

        role_columns = {}

        for p in profiles:
            if (
                p.detected_category in self.LOCATION_CATEGORIES
                and p.confidence >= 0.70
            ):
                old = role_columns.get(p.detected_category)

                if old is None or p.confidence > old.confidence:
                    role_columns[p.detected_category] = p

        self._active_roles = role_columns

        # ---------------------------------------------------------
        # Phase 1: Cleaning / Learning
        # ---------------------------------------------------------
        columns = [str(c).strip() for c in data.columns]
        total_cols = max(1, len(columns))

        for idx, col in enumerate(columns, start=1):

            if col in self.OUTPUT or col not in data.columns:
                continue

            p = profile_map[col]

            s = (
                data[col]
                .astype("string")
                .fillna("")
            )

            nonempty = s.str.strip().ne("")

            # -----------------------------------------------------
            # Learned corrections
            # -----------------------------------------------------
            if self.learning and nonempty.any():

                values = pd.unique(
                    s.loc[nonempty]
                )

                learned_map = self.learning.lookup_many(
                    col,
                    values
                )

                if learned_map:

                    mapped = s.map(learned_map)

                    mask = (
                        nonempty
                        & mapped.notna()
                        & mapped.ne(s)
                    )

                    if mask.any():

                        data.loc[mask, col] = mapped.loc[mask]

                        learned_reused.loc[mask] = True
                        corrected.loc[mask] = True

                        s = (
                            data[col]
                            .astype("string")
                            .fillna("")
                        )

                        nonempty = s.str.strip().ne("")

            # -----------------------------------------------------
            # Empty columns
            # -----------------------------------------------------
            if p.detected_type == "EMPTY":
                continue

            category = p.detected_category

            # -----------------------------------------------------
            # Location columns
            # -----------------------------------------------------
            if category in self.LOCATION_CATEGORIES:

                cleaned = self._clean_text(s)

                changed = nonempty & cleaned.ne(s)

                if changed.any():

                    self._audit_correction(
                        unknown,
                        unknown_cols,
                        reasons,
                        changed,
                        col,
                        s,
                        "Auto-Corrected: Removed invalid character(s)",
                    )

                    if self.learning:

                        pairs = (
                            pd.DataFrame(
                                {
                                    "original": s.loc[changed],
                                    "corrected": cleaned.loc[changed],
                                }
                            )
                            .drop_duplicates()
                            .itertuples(
                                index=False,
                                name=None,
                            )
                        )

                        self.learning.learn_many(
                            col,
                            pairs,
                            "safe_character_cleanup",
                        )

                    data.loc[changed, col] = cleaned.loc[changed]

                    corrected.loc[changed] = True

                self._progress(
                    progress_callback,
                    idx,
                    total_cols,
                    n,
                    f"Cleaning: {col}",
                )

                continue

            # -----------------------------------------------------
            # Numeric validation
            # -----------------------------------------------------
            if (
                category in {
                    "NUMBER",
                    "LATITUDE",
                    "LONGITUDE",
                    "RANK",
                }
                or p.detected_type == "NUMBER"
            ):

                numeric = pd.to_numeric(
                    s,
                    errors="coerce",
                )

                bad = nonempty & numeric.isna()

                if bad.any():

                    self._issue(
                        unknown,
                        unknown_cols,
                        reasons,
                        bad,
                        col,
                        s,
                        "Invalid Numeric Value",
                    )

                    data.loc[bad, col] = ""

                continue

            # -----------------------------------------------------
            # Date validation
            # -----------------------------------------------------
            if (
                category == "DATE"
                or p.detected_type == "DATE/TIME"
            ):

                parsed = pd.to_datetime(
                    s,
                    errors="coerce",
                    format="mixed",
                )

                bad = nonempty & parsed.isna()

                if bad.any():

                    self._issue(
                        unknown,
                        unknown_cols,
                        reasons,
                        bad,
                        col,
                        s,
                        "Invalid Date/Time",
                    )

                    data.loc[bad, col] = ""

                continue

            # -----------------------------------------------------
            # UUID validation
            # -----------------------------------------------------
            if p.detected_type == "UUID":

                bad = nonempty & ~s.str.match(
                    r"^[0-9a-fA-F]{8}-"
                    r"[0-9a-fA-F]{4}-"
                    r"[1-5][0-9a-fA-F]{3}-"
                    r"[89abAB][0-9a-fA-F]{3}-"
                    r"[0-9a-fA-F]{12}$",
                    na=False,
                )

                if bad.any():

                    self._issue(
                        unknown,
                        unknown_cols,
                        reasons,
                        bad,
                        col,
                        s,
                        "Invalid UUID",
                    )

                    data.loc[bad, col] = ""

            # -----------------------------------------------------
            # Email validation
            # -----------------------------------------------------
            elif p.detected_type == "EMAIL":

                bad = nonempty & ~s.str.match(
                    r"^[^\s@]+@[^\s@]+\.[^\s@]+$",
                    na=False,
                )

                if bad.any():

                    self._issue(
                        unknown,
                        unknown_cols,
                        reasons,
                        bad,
                        col,
                        s,
                        "Invalid Email",
                    )

                    data.loc[bad, col] = ""

            # -----------------------------------------------------
            # Garbled / encoding text
            # -----------------------------------------------------
            s = (
                data[col]
                .astype("string")
                .fillna("")
            )

            nonempty = s.str.strip().ne("")

            garbled = (
                nonempty
                & s.str.contains(
                    r"Ã|Â|à¤|â|�",
                    regex=True,
                    na=False,
                )
            )

            if garbled.any():

                self._issue(
                    unknown,
                    unknown_cols,
                    reasons,
                    garbled,
                    col,
                    s,
                    "Garbled/Encoding Text",
                )

                data.loc[garbled, col] = ""

                s = (
                    data[col]
                    .astype("string")
                    .fillna("")
                )

                nonempty = s.str.strip().ne("")

            # -----------------------------------------------------
            # Unknown schema/data pattern
            # -----------------------------------------------------
            if p.detected_type == "UNKNOWN":

                self._issue(
                    unknown,
                    unknown_cols,
                    reasons,
                    nonempty,
                    col,
                    s,
                    "Unidentified Column/Data Pattern",
                )

                data.loc[nonempty, col] = ""

            self._progress(
                progress_callback,
                idx,
                total_cols,
                n,
                f"Cleaning: {col}",
            )

        # ---------------------------------------------------------
        # Phase 2: Build source hierarchy
        # ---------------------------------------------------------
        ctx = self._build_hierarchy(
            data,
            role_columns,
        )

        self._update_schema_verification(
            schema_df,
            role_columns,
            ctx,
        )

        # ---------------------------------------------------------
        # Phase 3: Validate location hierarchy
        # ---------------------------------------------------------
        for category in [
            "COUNTRY",
            "STATE_CODE",
            "STATE",
            "CITY",
            "AREA",
        ]:

            p = role_columns.get(category)

            if not p or p.column_name not in data.columns:
                continue

            col = p.column_name

            s = (
                data[col]
                .astype("string")
                .fillna("")
            )

            nonempty = s.str.strip().ne("")

            if not nonempty.any():
                continue

            if category == "COUNTRY":

                self._validate_country(
                    data,
                    col,
                    s,
                    nonempty,
                    ctx,
                    unknown,
                    unknown_cols,
                    reasons,
                )

            elif category == "STATE_CODE":

                self._validate_state_code(
                    data,
                    col,
                    s,
                    nonempty,
                    ctx,
                    unknown,
                    unknown_cols,
                    reasons,
                )

            elif category == "STATE":

                self._validate_state(
                    data,
                    col,
                    s,
                    nonempty,
                    ctx,
                    unknown,
                    unknown_cols,
                    reasons,
                )

            elif category == "CITY":

                self._validate_city(
                    data,
                    col,
                    s,
                    nonempty,
                    ctx,
                    unknown,
                    unknown_cols,
                    reasons,
                )

            elif category == "AREA":

                if "area" in getattr(
                    self.verifier,
                    "types",
                    set(),
                ):

                    self._validate_with_reference(
                        data,
                        col,
                        s,
                        nonempty,
                        "area",
                        unknown,
                        unknown_cols,
                        reasons,
                    )

            self._progress(
                progress_callback,
                n,
                n,
                n,
                f"Verified: {col}",
            )

        # ---------------------------------------------------------
        # Final validation fields
        # ---------------------------------------------------------
        data["Unknown"] = unknown

        data["Unknown_Columns"] = self._dedupe_pipe(
            unknown_cols
        )

        data["Unknown_Reasons"] = self._dedupe_pipe(
            reasons
        )

        unresolved = (
            data["Unknown_Reasons"]
            .astype("string")
            .str.replace(
                r"(?:^| \| )Auto-Corrected: [^|]+",
                "",
                regex=True,
            )
            .str.strip(" |")
        )

        has_issue = unresolved.str.len().gt(0)

        data["Validation_Status"] = has_issue.map(
            {
                True: "Unknown",
                False: "Valid",
            }
        )

        data["Correction_Status"] = "No Correction"

        data.loc[
            corrected
            & ~learned_reused
            & ~has_issue,
            "Correction_Status",
        ] = "Auto-Corrected / Learned"

        data.loc[
            learned_reused
            & ~has_issue,
            "Correction_Status",
        ] = "Learned Correction Applied"

        data.loc[
            corrected
            & has_issue,
            "Correction_Status",
        ] = "Partially Corrected - Review Required"

        valid = data.loc[
            ~has_issue
        ].copy()

        unknown_df = data.loc[
            has_issue
        ].copy()

        summary = self._summary(
            n,
            len(valid),
            len(unknown_df),
            schema_df,
        )

        summary.update(
            {
                "learned_total":
                    self.learning.stats()["learned_total"]
                    if self.learning
                    else 0,

                "new_learned":
                    self.learning.stats()["new_learned"]
                    if self.learning
                    else 0,

                "learned_reused":
                    self.learning.stats()["reused"]
                    if self.learning
                    else 0,
            }
        )

        if progress_callback:

            progress_callback(
                n,
                n,
                "Validation complete. Writing output...",
            )

        if self.learning:
            self.learning.save()

        return (
            valid,
            unknown_df,
            summary,
            schema_df,
        )

    # =============================================================
    # NORMALIZATION
    # =============================================================

    @staticmethod
    def _norm(value):
        return " ".join(
            str(value)
            .strip()
            .casefold()
            .split()
        )

    # =============================================================
    # TEXT CLEANING
    # =============================================================

    @staticmethod
    def _clean_text(s):

        return (
            s.astype("string")
            .fillna("")
            .str.replace(
                r"[^A-Za-z0-9\s\.,'’\-\(\)/&\+:%_\u0900-\u097F]",
                "",
                regex=True,
            )
            .str.replace(
                r"\s+",
                " ",
                regex=True,
            )
            .str.strip()
        )

    # =============================================================
    # BUILD SOURCE HIERARCHY
    # =============================================================

    def _build_hierarchy(
        self,
        data,
        roles,
    ):

        def vals(role):

            p = roles.get(role)

            if (
                p
                and p.column_name in data.columns
            ):

                return (
                    data[p.column_name]
                    .astype("string")
                    .fillna("")
                )

            return pd.Series(
                "",
                index=data.index,
                dtype="string",
            )

        city = vals("CITY")
        state = vals("STATE")
        code = vals("STATE_CODE")
        country = vals("COUNTRY")

        resolver = LocationResolver().fit(
            city.tolist(),
            state.tolist(),
            country.tolist(),
        )

        code_mapper = StateCodeMapper().fit(
            code.tolist(),
            state.tolist(),
        )

        city_n = city.map(self._norm)
        state_n = state.map(self._norm)
        code_n = code.map(self._norm)
        country_n = country.map(self._norm)

        # ---------------------------------------------------------
        # Normalize alternate state names
        # ---------------------------------------------------------
        state_aliases = {
            "pondicherry": "puducherry",
            "puducherry": "puducherry",
        }

        state_n = state_n.map(
            lambda x: state_aliases.get(x, x)
        )

        # ---------------------------------------------------------
        # Normalize source mapper mapping as well
        # ---------------------------------------------------------
        normalized_code_mapping = {}

        for code_key, states in code_mapper.mapping.items():

            normalized_states = {
                state_aliases.get(
                    self._norm(state_value),
                    self._norm(state_value),
                )
                for state_value in states
            }

            normalized_code_mapping[
                self._norm(code_key)
            ] = normalized_states

        state_pairs = set(
            zip(
                state_n[state_n.ne("")],
                country_n[state_n.ne("")],
            )
        )

        code_pairs = set(
            zip(
                code_n[code_n.ne("")],
                state_n[code_n.ne("")],
            )
        )

        code_to_state = {}

        for c, s in code_pairs:

            if c and s:

                code_to_state.setdefault(
                    c,
                    set(),
                ).add(s)

        # Merge normalized mapper values
        for c, states in normalized_code_mapping.items():

            code_to_state.setdefault(
                c,
                set(),
            ).update(states)

        city_triples = set(
            zip(
                city_n[city_n.ne("")],
                state_n[city_n.ne("")],
                country_n[city_n.ne("")],
            )
        )

        countries = set(
            country_n[
                country_n.ne("")
            ]
        )

        states = set(
            state_n[
                state_n.ne("")
            ]
        )

        cities = set(
            city_n[
                city_n.ne("")
            ]
        )

        return {
            "state_pairs": state_pairs,
            "code_to_state": code_to_state,
            "city_triples": city_triples,
            "countries": countries,
            "states": states,
            "cities": cities,
            "has_city": bool(city_triples),
            "has_state": bool(
                state_pairs or states
            ),
            "has_country": bool(countries),
        }

    # =============================================================
    # SCHEMA VERIFICATION
    # =============================================================

    def _update_schema_verification(
        self,
        schema_df,
        roles,
        ctx,
    ):

        if schema_df.empty:
            return

        for category in self.LOCATION_CATEGORIES:

            p = roles.get(category)

            if not p:
                continue

            mask = schema_df[
                "column_name"
            ].eq(
                p.column_name
            )

            if category == "AREA":

                status = (
                    "Verified"
                    if "area"
                    in getattr(
                        self.verifier,
                        "types",
                        set(),
                    )
                    else "Identified / Unverified"
                )

                reason = (
                    "Area identified; no authoritative area reference available"
                    if status != "Verified"
                    else "Verified against area reference"
                )

            elif category == "CITY":

                status = (
                    "Verified (Source Hierarchy)"
                    if ctx["has_city"]
                    else "Unverified"
                )

                reason = (
                    "City verified using City + State + Country combinations present in the source dataset"
                    if ctx["has_city"]
                    else "No usable city hierarchy found"
                )

            elif category == "STATE_CODE":

                status = (
                    "Verified (Source Mapping)"
                    if ctx["code_to_state"]
                    else "Unverified"
                )

                reason = (
                    "State code mapped to state name from source rows"
                    if ctx["code_to_state"]
                    else "No usable state-code mapping found"
                )

            elif category == "STATE":

                status = (
                    "Verified (Source Hierarchy)"
                    if ctx["has_state"]
                    else "Unverified"
                )

                reason = (
                    "State verified using State + Country combinations present in the source dataset"
                    if ctx["has_state"]
                    else "No usable state hierarchy found"
                )

            else:

                status = (
                    "Verified (Source Values)"
                    if ctx["has_country"]
                    else "Unverified"
                )

                reason = (
                    "Country values are internally consistent in the source dataset"
                    if ctx["has_country"]
                    else "No country values available"
                )

            schema_df.loc[
                mask,
                "verification_status",
            ] = status

            schema_df.loc[
                mask,
                "reason",
            ] = reason

    # =============================================================
    # COUNTRY VALIDATION
    # =============================================================

    def _validate_country(
        self,
        data,
        col,
        s,
        nonempty,
        ctx,
        u,
        uc,
        r,
    ):

        known_ref = set()

        for key, items in getattr(
            self.verifier,
            "reference",
            {},
        ).items():

            for item in items:

                if (
                    str(
                        item.get(
                            "type",
                            "",
                        )
                    ).lower()
                    == "country"
                ):

                    known_ref.add(
                        self._norm(
                            item.get(
                                "name",
                                "",
                            )
                        )
                    )

        normalized = s.map(
            self._norm
        )

        if known_ref:

            ref_bad = (
                nonempty
                & ~normalized.isin(
                    known_ref
                )
            )

            if (
                ref_bad.any()
                and not set(
                    normalized[nonempty]
                ).issubset(
                    known_ref
                )
            ):

                bad = pd.Series(
                    False,
                    index=data.index,
                )

                reason = ""

            else:

                bad = ref_bad

                reason = (
                    "Country Not Verified Against Reference"
                )

        else:

            bad = (
                nonempty
                & ~normalized.isin(
                    ctx["countries"]
                )
            )

            reason = (
                "Country Not Supported By Source Values"
            )

        if bad.any():

            self._issue(
                u,
                uc,
                r,
                bad,
                col,
                s,
                reason,
            )

            data.loc[
                bad,
                col,
            ] = ""

    # =============================================================
    # STATE CODE VALIDATION
    # =============================================================

    def _validate_state_code(
        self,
        data,
        col,
        s,
        nonempty,
        ctx,
        u,
        uc,
        r,
    ):

        state_col = self._role_col(
            "STATE"
        )

        normalized_code = s.map(
            self._norm
        )

        mapped = normalized_code.map(
            lambda x:
                next(
                    iter(
                        ctx[
                            "code_to_state"
                        ].get(
                            x,
                            set(),
                        )
                    ),
                    "",
                )
        )

        # ---------------------------------------------------------
        # Known alternate state names
        # ---------------------------------------------------------
        state_aliases = {
            "pondicherry": "puducherry",
            "puducherry": "puducherry",
        }

        normalized_mapped = mapped.map(
            lambda x:
                state_aliases.get(
                    x,
                    x,
                )
        )

        if state_col is None:

            bad = (
                nonempty
                & normalized_mapped.eq("")
            )

        else:

            state_values = (
                data[state_col]
                .astype("string")
                .fillna("")
                .map(self._norm)
            )

            normalized_state = state_values.map(
                lambda x:
                    state_aliases.get(
                        x,
                        x,
                    )
            )

            bad = (
                nonempty
                & (
                    normalized_mapped.eq("")
                    |
                    (
                        normalized_state.ne("")
                        & normalized_state.ne(
                            normalized_mapped
                        )
                    )
                )
            )

        if bad.any():

            self._issue(
                u,
                uc,
                r,
                bad,
                col,
                s,
                "State Code does not match State Name",
            )

            data.loc[
                bad,
                col,
            ] = ""

    # =============================================================
    # STATE VALIDATION
    # =============================================================

    def _validate_state(
        self,
        data,
        col,
        s,
        nonempty,
        ctx,
        u,
        uc,
        r,
    ):

        normalized = s.map(
            self._norm
        )

        # Alternate state names
        state_aliases = {
            "pondicherry": "puducherry",
            "puducherry": "puducherry",
        }

        normalized = normalized.map(
            lambda x:
                state_aliases.get(
                    x,
                    x,
                )
        )

        country_col = self._role_col(
            "COUNTRY"
        )

        if country_col:

            country = (
                data[country_col]
                .astype("string")
                .fillna("")
                .map(self._norm)
            )

        else:

            country = pd.Series(
                "",
                index=data.index,
                dtype="string",
            )

        pairs = pd.Series(
            list(
                zip(
                    normalized,
                    country,
                )
            ),
            index=data.index,
        )

        bad = (
            nonempty
            & ~pairs.isin(
                ctx["state_pairs"]
            )
        )

        if bad.any():

            self._issue(
                u,
                uc,
                r,
                bad,
                col,
                s,
                "State + Country combination not verified",
            )

            data.loc[
                bad,
                col,
            ] = ""

    # =============================================================
    # CITY VALIDATION
    # =============================================================

    def _validate_city(
        self,
        data,
        col,
        s,
        nonempty,
        ctx,
        u,
        uc,
        r,
    ):

        normalized = s.map(
            self._norm
        )

        state_col = self._role_col(
            "STATE"
        )

        country_col = self._role_col(
            "COUNTRY"
        )

        if state_col:

            state = (
                data[state_col]
                .astype("string")
                .fillna("")
                .map(self._norm)
            )

        else:

            state = pd.Series(
                "",
                index=data.index,
                dtype="string",
            )

        if country_col:

            country = (
                data[country_col]
                .astype("string")
                .fillna("")
                .map(self._norm)
            )

        else:

            country = pd.Series(
                "",
                index=data.index,
                dtype="string",
            )

        # Normalize state aliases
        state_aliases = {
            "pondicherry": "puducherry",
            "puducherry": "puducherry",
        }

        state = state.map(
            lambda x:
                state_aliases.get(
                    x,
                    x,
                )
        )

        triples = pd.Series(
            list(
                zip(
                    normalized,
                    state,
                    country,
                )
            ),
            index=data.index,
        )

        # Normalize hierarchy reference before comparison
        normalized_city_triples = set()

        for city_value, state_value, country_value in ctx[
            "city_triples"
        ]:

            normalized_city_triples.add(
                (
                    city_value,
                    state_aliases.get(
                        state_value,
                        state_value,
                    ),
                    country_value,
                )
            )

        bad = (
            nonempty
            & ~triples.isin(
                normalized_city_triples
            )
        )

        if bad.any():

            self._issue(
                u,
                uc,
                r,
                bad,
                col,
                s,
                "City + State + Country combination not verified",
            )

            data.loc[
                bad,
                col,
            ] = ""

    # =============================================================
    # REFERENCE VALIDATION
    # =============================================================

    def _validate_with_reference(
        self,
        data,
        col,
        s,
        nonempty,
        expected,
        u,
        uc,
        r,
    ):

        results = self.verifier.verify_many(
            s.loc[nonempty],
            expected,
            allow_fuzzy=True,
        )

        key_map = {
            str(k): v
            for k, v in results.items()
        }

        status = s.map(
            lambda x:
                key_map.get(
                    str(x),
                    {},
                ).get(
                    "status",
                    "unknown",
                )
        )

        bad = (
            nonempty
            & status.ne("valid")
        )

        if bad.any():

            self._issue(
                u,
                uc,
                r,
                bad,
                col,
                s,
                "Location Not Verified Against Reference",
            )

            data.loc[
                bad,
                col,
            ] = ""

    # =============================================================
    # ROLE COLUMN
    # =============================================================

    def _role_col(self, category):

        return (
            getattr(
                self,
                "_active_roles",
                {},
            )
            .get(category)
            .column_name
            if getattr(
                self,
                "_active_roles",
                {},
            ).get(category)
            else None
        )

    # =============================================================
    # DEDUPLICATE REASONS
    # =============================================================

    @staticmethod
    def _dedupe_pipe(s):

        def f(v):

            parts = [
                x.strip()
                for x in str(v).split(" | ")
                if x.strip()
            ]

            seen = []

            for x in parts:

                if x not in seen:
                    seen.append(x)

            return " | ".join(seen)

        return s.map(f)

    # =============================================================
    # SUMMARY
    # =============================================================

    @staticmethod
    def _summary(
        n,
        valid,
        unknown,
        schema_df,
    ):

        return {
            "total_rows": n,

            "valid_rows": valid,

            "unknown_rows": unknown,

            "valid_percentage":
                round(
                    valid * 100 / n,
                    2,
                )
                if n
                else 0,

            "unknown_percentage":
                round(
                    unknown * 100 / n,
                    2,
                )
                if n
                else 0,

            "schema_columns":
                len(schema_df),

            "identified_columns":
                int(
                    (
                        schema_df[
                            "detected_type"
                        ]
                        != "UNKNOWN"
                    ).sum()
                )
                if not schema_df.empty
                else 0,

            "verified_columns":
                int(
                    schema_df[
                        "verification_status"
                    ]
                    .astype(str)
                    .str.startswith(
                        "Verified"
                    )
                    .sum()
                )
                if not schema_df.empty
                else 0,
        }

    # =============================================================
    # ISSUE HANDLING
    # =============================================================

    @staticmethod
    def _issue(
        u,
        uc,
        r,
        mask,
        name,
        series,
        reason,
    ):

        AdaptiveValidator._append(
            u,
            mask,
            name
            + "="
            + series.astype("string"),
        )

        AdaptiveValidator._append(
            uc,
            mask,
            pd.Series(
                name,
                index=series.index,
                dtype="string",
            ),
        )

        vals = (
            reason.astype("string")
            if isinstance(
                reason,
                pd.Series,
            )
            else pd.Series(
                reason,
                index=series.index,
                dtype="string",
            )
        )

        AdaptiveValidator._append(
            r,
            mask,
            vals,
        )

    # =============================================================
    # CORRECTION AUDIT
    # =============================================================

    @staticmethod
    def _audit_correction(
        u,
        uc,
        r,
        mask,
        name,
        series,
        reason,
    ):

        AdaptiveValidator._append(
            u,
            mask,
            name
            + "="
            + series.astype("string"),
        )

        AdaptiveValidator._append(
            uc,
            mask,
            pd.Series(
                name,
                index=series.index,
                dtype="string",
            ),
        )

        AdaptiveValidator._append(
            r,
            mask,
            pd.Series(
                reason,
                index=series.index,
                dtype="string",
            ),
        )

    # =============================================================
    # APPEND VALUES
    # =============================================================

    @staticmethod
    def _append(
        target,
        mask,
        values,
    ):

        old = target.loc[mask]

        vals = (
            values.loc[mask]
            .astype("string")
        )

        target.loc[mask] = (
            old.where(
                old.eq(""),
                old + " | ",
            )
            + vals
        )

    # =============================================================
    # PROGRESS
    # =============================================================

    @staticmethod
    def _progress(
        callback,
        done,
        total,
        rows,
        status,
    ):

        if callback:

            callback(
                int(
                    done
                    * rows
                    / max(
                        1,
                        total,
                    )
                ),
                rows,
                status,
            )