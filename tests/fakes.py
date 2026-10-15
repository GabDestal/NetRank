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
