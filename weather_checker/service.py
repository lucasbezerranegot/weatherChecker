"""Forecast message construction and multi-household orchestration."""

from datetime import datetime, timedelta
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from .clothing import clothing_recommendations
from .config import (
    ApplicationConfig,
    ChildProfile,
    Household,
    Recipient,
    load_application_config,
)
from .delivery import CallMeBotClient
from .exceptions import WeatherServiceError
from .weather import LAT, LON, OpenMeteoClient, get_weather_description

PLAYGROUND_RAIN_MM_THRESHOLD = 0.0
PLAYGROUND_RAIN_PROBABILITY_THRESHOLD = 50
DEFAULT_HOUSEHOLD = Household(
    household_id="family_1",
    latitude=LAT,
    longitude=LON,
    timezone="Europe/Berlin",
    children=(
        ChildProfile("child_1", "Criança 1"),
        ChildProfile("child_2", "Criança 2"),
    ),
)


def _time_index(values: list[str], value: str) -> int:
    try:
        return values.index(value)
    except ValueError as exc:
        raise WeatherServiceError(
            f"Open-Meteo não retornou o horário necessário: {value}."
        ) from exc


def _playground_advice(
    hourly: dict[str, list[Any]],
    start_index: int,
    end_index: int,
) -> str:
    window = slice(start_index, end_index + 1)
    precipitation = hourly["precipitation"][window]
    probabilities = hourly["precipitation_probability"][window]
    rain_expected = any(
        value is not None and value > PLAYGROUND_RAIN_MM_THRESHOLD
        for value in precipitation
    ) or any(
        value is not None and value >= PLAYGROUND_RAIN_PROBABILITY_THRESHOLD
        for value in probabilities
    )

    if rain_expected:
        return "☔ *Parquinho:* Hoje não tem parquinho — há chuva prevista."
    return "🛝 *Parquinho:* Hoje tem parquinho — previsão seca."


def build_forecast_message(
    data: dict[str, Any],
    mode: str,
    now: datetime | None = None,
    household: Household | None = None,
    children: tuple[ChildProfile, ...] | None = None,
) -> str:
    if mode not in {"morning", "night"}:
        raise ValueError("mode deve ser 'morning' ou 'night'.")

    configured_household = household or DEFAULT_HOUSEHOLD
    configured_children = children or configured_household.children
    local_timezone = ZoneInfo(configured_household.timezone)
    current = now or datetime.now(local_timezone)
    if current.tzinfo is None:
        current = current.replace(tzinfo=local_timezone)
    else:
        current = current.astimezone(local_timezone)

    target_date = current.date() + timedelta(days=1) if mode == "night" else current.date()
    day_label = "Amanhã" if mode == "night" else "Hoje"
    target_date_str = target_date.strftime("%Y-%m-%d")
    is_weekend = target_date.weekday() >= 5
    hourly, daily = data["hourly"], data["daily"]

    night_alert = ""
    if mode == "night":
        idx_now = _time_index(hourly["time"], current.strftime("%Y-%m-%dT%H:00"))
        idx_tomorrow_0700 = _time_index(
            hourly["time"], f"{target_date_str}T07:00"
        )
        night_precip = hourly["precipitation"][idx_now : idx_tomorrow_0700 + 1]
        valid_precip = [value for value in night_precip if value is not None]
        if any(value > 0.0 for value in valid_precip):
            night_alert = (
                "🚨 *TRAILER / BIKES:* Vai chover até "
                f"{max(valid_precip)}mm na madrugada. Guardar!\n\n"
            )
        else:
            night_alert = "🌙 *Trailer:* Madrugada seca. Pode deixar fora.\n\n"

    day_idx = _time_index(daily["time"], target_date_str)
    uv_max = daily["uv_index_max"][day_idx]
    uv_alert = (
        f"⚠️ *UV Alto ({uv_max})* - Protetor!"
        if uv_max >= 6.0
        else f"☀️ UV: {uv_max} (OK)"
    )
    clothing_start = _time_index(hourly["time"], f"{target_date_str}T08:00")
    clothing_end = _time_index(
        hourly["time"], f"{target_date_str}T{configured_household.playground_end}"
    )
    clothing = clothing_recommendations(
        configured_children,
        hourly,
        uv_max,
        clothing_start,
        clothing_end,
    )
    message = night_alert

    if is_weekend:
        message += (
            f"🌳 *Fim de Semana em Família!* "
            f"({day_label} - {target_date.strftime('%d/%m')})\n\n"
        )
        message += (
            f"📈 Máx: {daily['temperature_2m_max'][day_idx]}°C | "
            f"📉 Mín: {daily['temperature_2m_min'][day_idx]}°C\n"
        )
        message += f"{uv_alert}\n\n"
        idx_0900 = _time_index(hourly["time"], f"{target_date_str}T09:00")
        idx_1700 = _time_index(hourly["time"], f"{target_date_str}T17:00")
        day_precip = hourly["precipitation"][idx_0900 : idx_1700 + 1]
        if any(value > 0.5 for value in day_precip if value is not None):
            message += "☔ *Plano A: Brincadeiras em casa!* Tem chuva prevista para o dia."
        else:
            message += "🛴 *Parquinho liberado!* Dia seco, perfeito para gastar energia lá fora."
        return f"{message}\n\n{clothing}"

    idx_0800 = clothing_start
    idx_1600 = _time_index(hourly["time"], f"{target_date_str}T16:00")
    kita_slice = slice(idx_0800, idx_1600 + 1)
    temps = hourly["temperature_2m"][kita_slice]
    feels = hourly["apparent_temperature"][kita_slice]

    message += (
        f"🧥 *Roupas do Kita* ({day_label} - {target_date.strftime('%d/%m')})\n\n"
    )
    message += "🚲 *Ida (08:00):*\n"
    message += (
        f"🌡️ {hourly['temperature_2m'][idx_0800]}°C "
        f"(Sens: {hourly['apparent_temperature'][idx_0800]}°C) | "
        f"💨 {hourly['wind_gusts_10m'][idx_0800]} km/h\n"
    )
    message += f"{get_weather_description(hourly['weather_code'][idx_0800])}\n\n"
    message += "🎒 *No Kita (08:00 - 16:00):*\n"
    message += f"📈 Máx: {max(temps)}°C (Sens: {max(feels)}°C)\n"
    message += f"📉 Mín: {min(temps)}°C (Sens: {min(feels)}°C)\n"
    message += f"{uv_alert}\n\n"
    message += "🚲 *Volta (16:00):*\n"
    message += (
        f"🌡️ {hourly['temperature_2m'][idx_1600]}°C "
        f"(Sens: {hourly['apparent_temperature'][idx_1600]}°C) | "
        f"💨 {hourly['wind_gusts_10m'][idx_1600]} km/h\n"
    )
    message += get_weather_description(hourly["weather_code"][idx_1600])
    if mode == "morning":
        playground_start = _time_index(
            hourly["time"],
            f"{target_date_str}T{configured_household.playground_start}",
        )
        playground_end = _time_index(
            hourly["time"],
            f"{target_date_str}T{configured_household.playground_end}",
        )
        message += f"\n\n{_playground_advice(hourly, playground_start, playground_end)}"
    return f"{message}\n\n{clothing}"


def generate_forecasts(
    mode: str,
    weather_client: OpenMeteoClient | None = None,
    application_config: ApplicationConfig | None = None,
    environment: Mapping[str, str] | None = None,
    now: datetime | None = None,
    require_credentials: bool = True,
) -> tuple[dict[int, str], list[tuple[Recipient, str]]]:
    """Build every recipient-specific message without sending anything."""
    config = application_config or load_application_config(
        environment,
        require_credentials=require_credentials,
    )
    weather = weather_client or OpenMeteoClient()
    weather_cache: dict[tuple[float, float, str], dict[str, Any]] = {}
    message_cache: dict[tuple[str, tuple[str, ...]], str] = {}
    deliveries: list[tuple[Recipient, str]] = []
    messages: dict[int, str] = {}

    for recipient in config.recipients:
        household = config.households[recipient.household_id]
        weather_data = weather_cache.get(household.location_key)
        if weather_data is None:
            weather_data = weather.get_forecast(
                latitude=household.latitude,
                longitude=household.longitude,
                timezone=household.timezone,
            )
            weather_cache[household.location_key] = weather_data

        message_key = (household.household_id, recipient.child_ids)
        message = message_cache.get(message_key)
        if message is None:
            selected_children = tuple(
                household.child(child_id) for child_id in recipient.child_ids
            )
            message = build_forecast_message(
                weather_data,
                mode,
                now=now,
                household=household,
                children=selected_children,
            )
            message_cache[message_key] = message

        messages[recipient.slot] = message
        deliveries.append((recipient, message))

    return messages, deliveries


def run_forecast(
    mode: str,
    weather_client: OpenMeteoClient | None = None,
    delivery_client: CallMeBotClient | None = None,
    application_config: ApplicationConfig | None = None,
    environment: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> dict[int, str]:
    messages, deliveries = generate_forecasts(
        mode,
        weather_client=weather_client,
        application_config=application_config,
        environment=environment,
        now=now,
    )
    (delivery_client or CallMeBotClient()).send_many(deliveries)
    return messages
