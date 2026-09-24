"""Configuration for households, children, recipients, and locations."""

import json
from dataclasses import dataclass
from datetime import time
from os import environ
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .exceptions import ConfigurationError

THERMAL_PROFILES = {"cold_sensitive", "neutral", "warm_sensitive"}

DEFAULT_CONFIGURATION: dict[str, Any] = {
    "households": {
        "family_1": {
            "location": {
                "latitude": 48.137154,
                "longitude": 11.576124,
                "timezone": "Europe/Berlin",
            },
            "children": {
                "child_1": {"label": "Criança 1", "thermal_profile": "neutral"},
                "child_2": {"label": "Criança 2", "thermal_profile": "neutral"},
            },
            "playground": {"start": "16:00", "end": "19:00"},
        },
        "friend_family": {
            "location": {
                "latitude": 48.137154,
                "longitude": 11.576124,
                "timezone": "Europe/Berlin",
            },
            "children": {
                "child_3": {"label": "Criança 3", "thermal_profile": "neutral"}
            },
            "playground": {"start": "16:00", "end": "19:00"},
        },
    },
    "recipients": {
        "1": {"household": "family_1"},
        "2": {"household": "family_1"},
        "3": {"household": "friend_family"},
    },
}


@dataclass(frozen=True)
class ChildProfile:
    child_id: str
    label: str
    thermal_profile: str = "neutral"


@dataclass(frozen=True)
class Household:
    household_id: str
    latitude: float
    longitude: float
    timezone: str
    children: tuple[ChildProfile, ...]
    playground_start: str = "16:00"
    playground_end: str = "19:00"

    def child(self, child_id: str) -> ChildProfile:
        for child in self.children:
            if child.child_id == child_id:
                return child
        raise ConfigurationError(
            f"Criança '{child_id}' não existe na família '{self.household_id}'."
        )

    @property
    def location_key(self) -> tuple[float, float, str]:
        return (self.latitude, self.longitude, self.timezone)


@dataclass(frozen=True)
class Recipient:
    phone: str
    apikey: str
    slot: int = 0
    household_id: str = "family_1"
    child_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ApplicationConfig:
    households: dict[str, Household]
    recipients: tuple[Recipient, ...]


def load_application_config(
    environment: Mapping[str, str] | None = None,
    configuration: str | Mapping[str, Any] | None = None,
) -> ApplicationConfig:
    """Load configuration from JSON, a file, or the safe built-in default."""
    values = environ if environment is None else environment
    raw_configuration: str | Mapping[str, Any]

    if configuration is not None:
        raw_configuration = configuration
    elif values.get("HOUSEHOLDS_CONFIG_JSON", "").strip():
        raw_configuration = values["HOUSEHOLDS_CONFIG_JSON"]
    elif values.get("HOUSEHOLDS_CONFIG_PATH", "").strip():
        path = Path(values["HOUSEHOLDS_CONFIG_PATH"])
        try:
            raw_configuration = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigurationError(
                f"Não foi possível ler a configuração familiar em '{path}'."
            ) from exc
    else:
        raw_configuration = DEFAULT_CONFIGURATION

    payload = _decode_configuration(raw_configuration)
    households = _parse_households(payload.get("households"))
    recipients = _parse_recipients(payload.get("recipients"), households, values)
    return ApplicationConfig(households=households, recipients=recipients)


def load_recipients(
    environment: Mapping[str, str] | None = None,
    required_count: int = 3,
) -> list[Recipient]:
    """Backward-compatible strict loading for a fixed number of recipients."""
    values = environ if environment is None else environment
    recipients: list[Recipient] = []
    invalid: list[int] = []

    for number in range(1, required_count + 1):
        phone = values.get(f"PHONE_{number}", "").strip()
        apikey = values.get(f"APIKEY_{number}", "").strip()
        if not phone or not apikey:
            invalid.append(number)
            continue
        recipients.append(Recipient(phone=phone, apikey=apikey, slot=number))

    if invalid:
        _raise_missing_credentials(invalid)
    return recipients


def _decode_configuration(
    configuration: str | Mapping[str, Any],
) -> dict[str, Any]:
    if isinstance(configuration, str):
        try:
            payload = json.loads(configuration)
        except json.JSONDecodeError as exc:
            raise ConfigurationError("HOUSEHOLDS_CONFIG_JSON contém JSON inválido.") from exc
    else:
        payload = dict(configuration)
    if not isinstance(payload, dict):
        raise ConfigurationError("A configuração familiar precisa ser um objeto JSON.")
    return payload


def _parse_households(raw_households: Any) -> dict[str, Household]:
    if not isinstance(raw_households, dict) or not raw_households:
        raise ConfigurationError("A configuração precisa conter pelo menos uma família.")

    households: dict[str, Household] = {}
    for household_id, raw_household in raw_households.items():
        if not isinstance(household_id, str) or not household_id.strip():
            raise ConfigurationError("Toda família precisa de um identificador válido.")
        if not isinstance(raw_household, dict):
            raise ConfigurationError(f"Família '{household_id}' possui configuração inválida.")

        location = raw_household.get("location")
        if not isinstance(location, dict):
            raise ConfigurationError(f"Família '{household_id}' não possui localização.")
        latitude = _number(location.get("latitude"), "latitude", household_id)
        longitude = _number(location.get("longitude"), "longitude", household_id)
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ConfigurationError(f"Localização inválida para família '{household_id}'.")
        timezone = str(location.get("timezone", "")).strip()
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ConfigurationError(
                f"Fuso horário inválido para família '{household_id}': '{timezone}'."
            ) from exc

        children = _parse_children(raw_household.get("children"), household_id)
        playground = raw_household.get("playground", {})
        if not isinstance(playground, dict):
            raise ConfigurationError(
                f"Configuração de parquinho inválida para família '{household_id}'."
            )
        playground_start = str(playground.get("start", "16:00"))
        playground_end = str(playground.get("end", "19:00"))
        if _time_minutes(playground_start) >= _time_minutes(playground_end):
            raise ConfigurationError(
                f"Janela de parquinho inválida para família '{household_id}'."
            )

        households[household_id] = Household(
            household_id=household_id,
            latitude=latitude,
            longitude=longitude,
            timezone=timezone,
            children=children,
            playground_start=playground_start,
            playground_end=playground_end,
        )
    return households


def _parse_children(raw_children: Any, household_id: str) -> tuple[ChildProfile, ...]:
    if not isinstance(raw_children, dict) or not raw_children:
        raise ConfigurationError(
            f"Família '{household_id}' precisa conter pelo menos uma criança."
        )
    children: list[ChildProfile] = []
    for child_id, raw_child in raw_children.items():
        if not isinstance(raw_child, dict):
            raise ConfigurationError(
                f"Configuração inválida para criança '{child_id}'."
            )
        label = str(raw_child.get("label", child_id)).strip()
        profile = str(raw_child.get("thermal_profile", "neutral")).strip()
        if not label:
            raise ConfigurationError(f"Criança '{child_id}' precisa de um label.")
        if profile not in THERMAL_PROFILES:
            raise ConfigurationError(
                f"Perfil térmico inválido para criança '{child_id}': '{profile}'."
            )
        children.append(
            ChildProfile(child_id=child_id, label=label, thermal_profile=profile)
        )
    return tuple(children)


def _parse_recipients(
    raw_recipients: Any,
    households: dict[str, Household],
    environment: Mapping[str, str],
) -> tuple[Recipient, ...]:
    if not isinstance(raw_recipients, dict) or not raw_recipients:
        raise ConfigurationError(
            "A configuração precisa conter pelo menos um destinatário."
        )

    recipients: list[Recipient] = []
    missing_credentials: list[int] = []
    for raw_slot, raw_recipient in raw_recipients.items():
        try:
            slot = int(raw_slot)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(
                f"Slot de destinatário inválido: '{raw_slot}'."
            ) from exc
        if slot <= 0 or not isinstance(raw_recipient, dict):
            raise ConfigurationError(f"Destinatário '{raw_slot}' é inválido.")

        household_id = str(raw_recipient.get("household", "")).strip()
        household = households.get(household_id)
        if household is None:
            raise ConfigurationError(
                f"Destinatário {slot} referencia família inexistente '{household_id}'."
            )

        raw_child_ids = raw_recipient.get("children")
        if raw_child_ids is None:
            child_ids = tuple(child.child_id for child in household.children)
        elif isinstance(raw_child_ids, list) and raw_child_ids:
            child_ids = tuple(str(child_id) for child_id in raw_child_ids)
        else:
            raise ConfigurationError(
                f"Lista de crianças inválida para destinatário {slot}."
            )
        for child_id in child_ids:
            household.child(child_id)

        phone = environment.get(f"PHONE_{slot}", "").strip() or _optional_string(
            raw_recipient.get("phone")
        )
        apikey = environment.get(f"APIKEY_{slot}", "").strip() or _optional_string(
            raw_recipient.get("apikey")
        )
        if not phone or not apikey:
            missing_credentials.append(slot)
            continue
        recipients.append(
            Recipient(
                slot=slot,
                phone=phone,
                apikey=apikey,
                household_id=household_id,
                child_ids=child_ids,
            )
        )

    if missing_credentials:
        _raise_missing_credentials(sorted(missing_credentials))
    return tuple(sorted(recipients, key=lambda recipient: recipient.slot))


def _number(value: Any, field: str, household_id: str) -> float:
    if isinstance(value, bool):
        raise ConfigurationError(f"{field} inválida para família '{household_id}'.")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(
            f"{field} inválida para família '{household_id}'."
        ) from exc


def _optional_string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _time_minutes(value: str) -> int:
    try:
        parsed = time.fromisoformat(value)
    except ValueError as exc:
        raise ConfigurationError(f"Horário inválido: '{value}'. Use HH:00.") from exc
    if parsed.minute != 0 or parsed.second != 0 or parsed.microsecond != 0:
        raise ConfigurationError(f"Horário inválido: '{value}'. Use horas inteiras.")
    return parsed.hour * 60


def _raise_missing_credentials(slots: list[int]) -> None:
    indexes = ", ".join(str(slot) for slot in slots)
    raise ConfigurationError(
        f"Configuração incompleta para destinatário(s): {indexes}. "
        "Cada destinatário precisa de PHONE_n e APIKEY_n."
    )
