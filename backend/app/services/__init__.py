"""Business logic and data access.

Services own queries and rules but never the transaction: the request-scoped
session dependency commits once, after the handler returns."""
