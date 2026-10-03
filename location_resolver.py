class LocationResolver:
    """O(1) hierarchy resolver built from the incoming CSV.

    The incoming dataset itself is used as a consistency reference. This is
    intentionally separate from the optional external reference file so the
    automation can handle large master datasets without fuzzy-searching every
    row.
    """
    def __init__(self):
        self.cities = set()
        self.states = set()
        self.countries = set()
        self.city_triples = set()
        self.state_pairs = set()

    @staticmethod
    def norm(value):
        return " ".join(str(value).strip().casefold().split())

    def fit(self, cities=None, states=None, countries=None):
        cities = list(cities or [])
        states = list(states or [])
        countries = list(countries or [])
        self.cities = {self.norm(x) for x in cities if self.norm(x)}
        self.states = {self.norm(x) for x in states if self.norm(x)}
        self.countries = {self.norm(x) for x in countries if self.norm(x)}
        self.state_pairs = set()
        self.city_triples = set()
        for city, state, country in zip(cities, states, countries):
            c, s, k = self.norm(city), self.norm(state), self.norm(country)
            if s and k:
                self.state_pairs.add((s, k))
            if c and s and k:
                self.city_triples.add((c, s, k))
        return self
