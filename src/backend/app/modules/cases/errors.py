"""Chyby stavového automatu zakázky sdílené moduly nad cases."""


class CaseActionError(ValueError):
    """Business-rule violation during a case action (maps to HTTP 409)."""
