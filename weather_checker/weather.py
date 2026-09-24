"""Open-Meteo client and weather-code presentation."""

import time
from collections.abc import Callable
from typing import Any

import requests

from .exceptions import WeatherServiceError

LAT = 48.137154
LON = 11.576124
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def get_weather_description(wmo_code: int) -> str:
    codes = {
        0: "☀️ Céu limpo",
        1: "🌤️ Majoritariamente limpo",
        2: "⛅ Parcialmente nublado",
        3: "☁️ Nublado",
        45: "🌫️ Neblina",
        48: "🌫️ Névoa",
        51: "🌧️ Garoa leve",
        53: "🌧️ Garoa moderada",
        55: "🌧️ Garoa forte",
        61: "☔ Chuva leve",
        63: "☔ Chuva moderada",
        65: "☔ Chuva forte",
        68: "🌨️💧 Schneeregen leve",
        69: "🌨️💧 Schneeregen forte",
        71: "❄️ Neve leve",
        73: "❄️ Neve moderada",
        75: "❄️ Neve forte",
        80: "🌦️ Pancadas",
        81: "🌦️ Pancadas fortes",
        95: "⛈️ Trovoada",
    }
    return codes.get(wmo_code, f"❓ {wmo_code}")


class OpenMeteoClient:
    def __init__(
        self,
        session: requests.Session | None = None,
        timeout: tuple[float, float] = (5.0, 15.0),
        max_attempts: int = 3,
        backoff_seconds: float = 0.5,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds
        self.sleeper = sleeper

    def get_forecast(self) -> dict[str, Any]:
        params = {
            "latitude": LAT,
            "longitude": LON,
            "hourly": (
                "temperature_2m,apparent_temperature,precipitation,"
                "precipitation_probability,weather_code,wind_gusts_10m"
            ),
            "daily": "uv_index_max,temperature_2m_max,temperature_2m_min",
            "timezone": "Europe/Berlin",
        }

        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.session.get(
                    OPEN_METEO_URL,
                    params=params,
                    timeout=self.timeout,
                )
                response.raise_for_status()
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status in RETRYABLE_STATUS_CODES and attempt < self.max_attempts:
                    self._wait_before_retry(attempt)
                    continue
                raise WeatherServiceError(
                    f"Open-Meteo respondeu com HTTP {status or 'desconhecido'}."
                ) from exc
            except requests.RequestException as exc:
                if attempt < self.max_attempts:
                    self._wait_before_retry(attempt)
                    continue
                raise WeatherServiceError(
                    f"Falha de rede ao consultar Open-Meteo após {attempt} tentativas."
                ) from exc

            try:
                data = response.json()
            except ValueError as exc:
                raise WeatherServiceError("Open-Meteo retornou JSON inválido.") from exc

            self._validate_payload(data)
            return data

        raise WeatherServiceError("Não foi possível consultar Open-Meteo.")

    def _wait_before_retry(self, attempt: int) -> None:
        self.sleeper(self.backoff_seconds * (2 ** (attempt - 1)))

    @staticmethod
    def _validate_payload(data: Any) -> None:
        required = {
            "hourly": {
                "time",
                "temperature_2m",
                "apparent_temperature",
                "precipitation",
                "precipitation_probability",
                "weather_code",
                "wind_gusts_10m",
            },
            "daily": {
                "time",
                "uv_index_max",
                "temperature_2m_max",
                "temperature_2m_min",
            },
        }
        if not isinstance(data, dict):
            raise WeatherServiceError("Resposta do Open-Meteo não é um objeto JSON.")

        for section, fields in required.items():
            content = data.get(section)
            if not isinstance(content, dict):
                raise WeatherServiceError(
                    f"Resposta do Open-Meteo sem a seção '{section}'."
                )
            missing = sorted(fields.difference(content))
            if missing:
                raise WeatherServiceError(
                    f"Resposta do Open-Meteo incompleta em '{section}': "
                    f"{', '.join(missing)}."
                )
            if any(not isinstance(content[field], list) for field in fields):
                raise WeatherServiceError(
                    f"Resposta do Open-Meteo contém dados inválidos em '{section}'."
                )
            lengths = {len(content[field]) for field in fields}
            if not lengths or 0 in lengths or len(lengths) != 1:
                raise WeatherServiceError(
                    f"Resposta do Open-Meteo contém séries vazias ou desalinhadas "
                    f"em '{section}'."
                )
