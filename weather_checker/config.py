"""Environment-backed application configuration."""

from dataclasses import dataclass
from os import environ
from typing import Mapping

from .exceptions import ConfigurationError


@dataclass(frozen=True)
class Recipient:
    phone: str
    apikey: str


def load_recipients(
    environment: Mapping[str, str] | None = None,
    required_count: int = 3,
) -> list[Recipient]:
    """Load all required recipients or fail before attempting delivery."""
    values = environ if environment is None else environment
    recipients: list[Recipient] = []
    invalid: list[int] = []

    for number in range(1, required_count + 1):
        phone = values.get(f"PHONE_{number}", "").strip()
        apikey = values.get(f"APIKEY_{number}", "").strip()
        if not phone or not apikey:
            invalid.append(number)
            continue
        recipients.append(Recipient(phone=phone, apikey=apikey))

    if invalid:
        indexes = ", ".join(str(number) for number in invalid)
        raise ConfigurationError(
            f"Configuração incompleta para destinatário(s): {indexes}. "
            "Cada destinatário precisa de PHONE_n e APIKEY_n."
        )

    return recipients

