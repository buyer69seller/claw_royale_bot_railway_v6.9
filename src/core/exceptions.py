# src/core/exceptions.py
"""Custom exceptions untuk bot"""

class ClawRoyaleError(Exception):
    """Base exception"""
    pass

class ConfigurationError(ClawRoyaleError):
    """Missing atau invalid konfigurasi"""
    pass

class VersionMismatchError(ClawRoyaleError):
    """API version mismatch (426)"""
    pass

class AgentDeadError(ClawRoyaleError):
    """Agent mati dalam game"""
    pass

class TargetDeadError(ClawRoyaleError):
    """Target sudah mati - retryable"""
    pass

class ResumeTargetDeadError(ClawRoyaleError):
    """Resume target dead (1013) - re-dial required"""
    pass

class AuthenticationError(ClawRoyaleError):
    """Auth gagal"""
    pass

class RateLimitError(ClawRoyaleError):
    """Rate limit exceeded"""
    pass

class NotSelectedError(ClawRoyaleError):
    """Not selected for game"""
    pass

class GameError(ClawRoyaleError):
    """General game error"""
    pass

class AgentTokenRequiredError(ClawRoyaleError):
    """Agent token required"""
    pass

class AccountBlockedError(ClawRoyaleError):
    """Account is blocked"""
    pass