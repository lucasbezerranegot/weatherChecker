"""Application-specific exceptions."""


class WeatherCheckerError(Exception):
    """Base exception for expected application failures."""


class ConfigurationError(WeatherCheckerError):
    """Raised when required environment configuration is missing."""


class WeatherServiceError(WeatherCheckerError):
    """Raised when the weather service cannot provide usable data."""


class DeliveryError(WeatherCheckerError):
    """Raised when one or more recipients do not receive the message."""

