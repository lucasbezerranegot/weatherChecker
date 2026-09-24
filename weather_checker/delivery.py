"""WhatsApp delivery through CallMeBot."""

import requests

from .config import Recipient
from .exceptions import DeliveryError

CALLMEBOT_URL = "https://api.callmebot.com/whatsapp.php"


def mask_phone(phone: str) -> str:
    return f"***{phone[-4:]}" if len(phone) >= 4 else "***"


class CallMeBotClient:
    def __init__(
        self,
        session: requests.Session | None = None,
        timeout: tuple[float, float] = (5.0, 20.0),
    ) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout

    def send(self, message: str, recipients: list[Recipient]) -> None:
        self.send_many([(recipient, message) for recipient in recipients])

    def send_many(self, deliveries: list[tuple[Recipient, str]]) -> None:
        """Send recipient-specific messages and aggregate all failures."""
        if not deliveries:
            raise DeliveryError("Nenhum destinatário configurado.")

        failures: list[str] = []
        for recipient, message in deliveries:
            masked_phone = mask_phone(recipient.phone)
            try:
                response = self.session.get(
                    CALLMEBOT_URL,
                    params={
                        "phone": recipient.phone,
                        "text": message,
                        "apikey": recipient.apikey,
                    },
                    timeout=self.timeout,
                )
                response.raise_for_status()
                body = response.text.lower()
                if "paused" in body or "resume" in body:
                    failures.append(f"{masked_phone}: conta pausada")
                    print(f"❌ Falha para {masked_phone}: conta pausada no CallMeBot.")
                else:
                    print(f"✅ Mensagem enviada para {masked_phone}.")
            except requests.RequestException as exc:
                failures.append(f"{masked_phone}: {type(exc).__name__}")
                print(f"❌ Falha de rede para {masked_phone}: {type(exc).__name__}.")

        if failures:
            raise DeliveryError(
                f"Falha no envio para {len(failures)} de {len(deliveries)} "
                f"destinatário(s): {'; '.join(failures)}."
            )
