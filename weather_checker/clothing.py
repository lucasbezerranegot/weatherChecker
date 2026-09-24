"""Deterministic and explainable clothing recommendations for children."""

from typing import Any

from .config import ChildProfile
from .exceptions import WeatherServiceError

THERMAL_OFFSETS = {
    "cold_sensitive": -3.0,
    "neutral": 0.0,
    "warm_sensitive": 3.0,
}
RAIN_PROBABILITY_THRESHOLD = 50
WIND_GUST_THRESHOLD_KMH = 30
LAYERING_TEMPERATURE_SWING = 8


def clothing_recommendations(
    children: tuple[ChildProfile, ...],
    hourly: dict[str, list[Any]],
    day_uv: float,
    start_index: int,
    end_index: int,
) -> str:
    """Build one recommendation per child for the selected outdoor window."""
    window = slice(start_index, end_index + 1)
    feels = _numbers(hourly["apparent_temperature"][window])
    precipitation = _numbers(hourly["precipitation"][window])
    probabilities = _numbers(hourly["precipitation_probability"][window])
    gusts = _numbers(hourly["wind_gusts_10m"][window])
    if not feels or not precipitation or not probabilities or not gusts:
        raise WeatherServiceError(
            "Previsão sem dados suficientes para recomendar roupas."
        )

    actual_min = min(feels)
    actual_max = max(feels)
    rain_expected = any(value > 0 for value in precipitation) or any(
        value >= RAIN_PROBABILITY_THRESHOLD for value in probabilities
    )
    windy = max(gusts) >= WIND_GUST_THRESHOLD_KMH
    large_swing = actual_max - actual_min >= LAYERING_TEMPERATURE_SWING

    lines = ["👕 *Sugestão de roupas:*"]
    for child in children:
        adjusted_min = actual_min + THERMAL_OFFSETS[child.thermal_profile]
        items = [_base_outfit(adjusted_min)]
        if large_swing:
            items.append("usar camadas fáceis de tirar")
        if windy:
            items.append("levar uma camada corta-vento")
        if rain_expected:
            items.append("levar impermeável, botas e meias extras")
        if day_uv >= 3:
            items.append("chapéu e protetor solar")
        if actual_max >= 25:
            items.append("roupa respirável e garrafa de água")
        if actual_max >= 30:
            items.append("evitar excesso de camadas e sol intenso")
        lines.append(f"• *{child.label}:* {'; '.join(items)}.")
    return "\n".join(lines)


def _base_outfit(adjusted_min: float) -> str:
    if adjusted_min >= 25:
        return "camiseta leve e shorts ou calça leve"
    if adjusted_min >= 20:
        return "camiseta e roupa leve, com casaquinho opcional"
    if adjusted_min >= 15:
        return "manga longa ou camiseta, casaco leve e calça comprida"
    if adjusted_min >= 10:
        return "manga longa, fleece ou moletom e jaqueta de meia-estação"
    if adjusted_min >= 5:
        return "camada-base, fleece, jaqueta quente e gorro"
    if adjusted_min >= 0:
        return "camada térmica, fleece, casaco de inverno, gorro e luvas"
    return "roupa térmica completa, casaco de inverno, calça térmica e botas"


def _numbers(values: list[Any]) -> list[float]:
    return [float(value) for value in values if value is not None]
