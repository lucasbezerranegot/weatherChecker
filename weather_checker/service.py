"""Forecast message construction and application orchestration."""

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .config import Recipient, load_recipients
from .delivery import CallMeBotClient
from .exceptions import WeatherServiceError
from .weather import OpenMeteoClient, get_weather_description

MUNICH_TZ = ZoneInfo("Europe/Berlin")
PLAYGROUND_RAIN_MM_THRESHOLD = 0.0
PLAYGROUND_RAIN_PROBABILITY_THRESHOLD = 50


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
) -> str:
    if mode not in {"morning", "night"}:
        raise ValueError("mode deve ser 'morning' ou 'night'.")

    current = now or datetime.now(MUNICH_TZ)
    if current.tzinfo is None:
        current = current.replace(tzinfo=MUNICH_TZ)
    else:
        current = current.astimezone(MUNICH_TZ)

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
            message += "☔ *Plano A: Brincadeiras em casa!* Tem chuva prevista para o dia.\n"
        else:
            message += "🛴 *Parquinho liberado!* Dia seco, perfeito para gastar energia lá fora.\n"
        return message

    idx_0800 = _time_index(hourly["time"], f"{target_date_str}T08:00")
    idx_1600 = _time_index(hourly["time"], f"{target_date_str}T16:00")
    idx_1900 = _time_index(hourly["time"], f"{target_date_str}T19:00")
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
        message += f"\n\n{_playground_advice(hourly, idx_1600, idx_1900)}"
    return message


def run_forecast(
    mode: str,
    weather_client: OpenMeteoClient | None = None,
    delivery_client: CallMeBotClient | None = None,
    recipients: list[Recipient] | None = None,
    now: datetime | None = None,
) -> str:
    configured_recipients = load_recipients() if recipients is None else recipients
    weather = weather_client or OpenMeteoClient()
    delivery = delivery_client or CallMeBotClient()
    message = build_forecast_message(weather.get_forecast(), mode, now=now)
    delivery.send(message, configured_recipients)
    return message
