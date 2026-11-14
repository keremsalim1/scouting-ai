"""Text-to-SQL: generate, validate, and execute read-only queries."""

from football_ai.sql_agent.guard import GuardError, GuardResult, validate

__all__ = ["GuardError", "GuardResult", "validate"]
