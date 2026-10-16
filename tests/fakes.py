"""Test doubles shared across test modules."""


class FakeDriver:
    """Stand-in for neo4j.Driver: records queries and answers them with a responder function.

    responder(query, parameters) returns a list of dict records, or raises to simulate a failure.
    """

    def __init__(self, responder=None):
        self.queries = []
        self.closed = False
        self._responder = responder or (lambda query, parameters: [])

    def execute_query(self, query, parameters=None, **kwargs):
        """Record the query and return (records, summary, keys) like neo4j's EagerResult."""
        self.queries.append((query, parameters, kwargs))
        records = self._responder(query, parameters)
        return records, None, list(records[0].keys()) if records else []

    def close(self):
        """Mark the driver closed."""
        self.closed = True


class FakeSummary:
    """Stand-in for neo4j.ResultSummary: the query type and server notifications."""

    def __init__(self, query_type="r", notifications=None):
        self.query_type = query_type
        self.notifications = notifications or []


class FakeRecord(dict):
    """Stand-in for neo4j.Record."""

    def data(self):
        """Return the record as a plain dict."""
        return dict(self)


class FakeResult:
    """Stand-in for neo4j.Result, built from an answer dict: rows, query_type, notifications."""

    def __init__(self, answer):
        self._rows = [FakeRecord(row) for row in answer.get("rows", [])]
        self._summary = FakeSummary(answer.get("query_type", "r"), answer.get("notifications"))

    def fetch(self, n):
        """Return at most n records."""
        return self._rows[:n]

    def consume(self):
        """Return the summary."""
        return self._summary


class FakeSession:
    """Stand-in for neo4j.Session. session_responder(query, parameters) returns an answer dict or raises."""

    def __init__(self, driver, config):
        self._driver = driver
        self.config = config

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, query, parameters=None):
        """Record the query (its text if it is a neo4j.Query) and answer it."""
        text = getattr(query, "text", query)
        self._driver.session_queries.append((text, parameters, self.config, getattr(query, "timeout", None)))
        return FakeResult(self._driver.session_responder(text, parameters))


class FakeSessionDriver(FakeDriver):
    """FakeDriver that also opens sessions, for code using driver.session() (the agent's guardrails)."""

    def __init__(self, responder=None, session_responder=None):
        super().__init__(responder)
        self.session_queries = []
        self.session_responder = session_responder or (lambda query, parameters: {"rows": []})

    def session(self, **config):
        """Open a fake session with the given config."""
        return FakeSession(self, config)
