class StateCodeMapper:
    """Fast source-derived state-code mapper.

    Learns code -> state relationships from the current dataset.
    Supports known alternate names such as Pondicherry/Puducherry.
    Ambiguous codes remain unresolved unless they are known aliases.
    """

    STATE_ALIASES = {
        "pondicherry": "puducherry",
        "puducherry": "puducherry",
    }

    CODE_ALIASES = {
        "py": "puducherry",
    }

    def __init__(self):
        self.mapping = {}

    @classmethod
    def norm(cls, value):
        value = " ".join(str(value).strip().casefold().split())
        return cls.STATE_ALIASES.get(value, value)

    def fit(self, codes, states):
        self.mapping = {}

        for code, state in zip(codes, states):
            c = str(code).strip().casefold()
            s = self.norm(state)

            if c and s:
                self.mapping.setdefault(c, set()).add(s)

        # Apply known code aliases
        for alias_code, canonical_state in self.CODE_ALIASES.items():
            self.mapping.setdefault(alias_code, set()).add(canonical_state)

        return self

    def resolve(self, code):
        c = str(code).strip().casefold()

        # Known code alias
        if c in self.CODE_ALIASES:
            return self.CODE_ALIASES[c]

        values = self.mapping.get(c, set())

        if len(values) == 1:
            return next(iter(values))

        return ""

    def is_unambiguous(self, code):
        c = str(code).strip().casefold()

        if c in self.CODE_ALIASES:
            return True

        return len(self.mapping.get(c, set())) == 1