from datetime import datetime, timedelta
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
import requests

from weatherChecker import main
from weather_checker.config import Recipient, load_recipients
from weather_checker.delivery import CallMeBotClient
from weather_checker.exceptions import (
    ConfigurationError,
    DeliveryError,
    WeatherServiceError,
)
from weather_checker.service import build_forecast_message, run_forecast
from weather_checker.weather import OpenMeteoClient

MUNICH_TZ = ZoneInfo("Europe/Berlin")
FIXED_NOW = datetime(2026, 9, 24, 20, 0, tzinfo=MUNICH_TZ)


def create_mock_weather_data(now: datetime = FIXED_NOW) -> dict:
    today = now.date()
    dates = [today + timedelta(days=offset) for offset in range(3)]
    hourly_times = [
        f"{day:%Y-%m-%d}T{hour:02d}:00"
        for day in dates
        for hour in range(24)
    ]
    size = len(hourly_times)
    temperatures = [10.0] * size
    precipitation = [0.0] * size

    tomorrow_noon = hourly_times.index(f"{dates[1]:%Y-%m-%d}T12:00")
    tomorrow_0200 = hourly_times.index(f"{dates[1]:%Y-%m-%d}T02:00")
    temperatures[tomorrow_noon] = 30.0
    precipitation[tomorrow_0200] = 5.5

    return {
        "hourly": {
            "time": hourly_times,
            "temperature_2m": temperatures,
            "apparent_temperature": temperatures.copy(),
            "precipitation": precipitation,
            "precipitation_probability": [0] * size,
            "weather_code": [0] * size,
            "wind_gusts_10m": [15.0] * size,
        },
        "daily": {
            "time": [f"{day:%Y-%m-%d}" for day in dates],
            "uv_index_max": [3.0, 7.5, 4.0],
            "temperature_2m_max": [16.0, 30.0, 18.0],
            "temperature_2m_min": [8.0, 10.0, 9.0],
        },
    }


def make_response(payload=None, text="OK") -> MagicMock:
    response = MagicMock()
    response.text = text
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def make_http_error(status: int) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status
    return requests.HTTPError(response=response)


def three_recipients() -> list[Recipient]:
    return [
        Recipient(phone=f"+49000000{number}", apikey=f"key-{number}")
        for number in range(1, 4)
    ]


def test_loads_all_three_required_recipients():
    environment = {
        "PHONE_1": "+491",
        "APIKEY_1": "key-1",
        "PHONE_2": "+492",
        "APIKEY_2": "key-2",
        "PHONE_3": "+493",
        "APIKEY_3": "key-3",
    }

    recipients = load_recipients(environment)

    assert [recipient.phone for recipient in recipients] == ["+491", "+492", "+493"]


@pytest.mark.parametrize(
    "environment, missing",
    [
        ({}, "1, 2, 3"),
        (
            {
                "PHONE_1": "+491",
                "APIKEY_1": "key-1",
                "PHONE_2": "+492",
                "APIKEY_2": "key-2",
                "PHONE_3": "+493",
            },
            "3",
        ),
    ],
)
def test_missing_recipient_configuration_is_an_error(environment, missing):
    with pytest.raises(ConfigurationError, match=missing):
        load_recipients(environment)


def test_delivery_succeeds_only_after_all_three_recipients_receive():
    session = MagicMock()
    session.get.side_effect = [make_response(), make_response(), make_response()]

    CallMeBotClient(session=session).send("Teste", three_recipients())

    assert session.get.call_count == 3
    for call in session.get.call_args_list:
        assert call.kwargs["timeout"] == (5.0, 20.0)


def test_delivery_reports_partial_failure_and_still_attempts_every_recipient():
    session = MagicMock()
    failed = make_response()
    failed.raise_for_status.side_effect = make_http_error(500)
    session.get.side_effect = [make_response(), failed, make_response()]

    with pytest.raises(DeliveryError, match="1 de 3"):
        CallMeBotClient(session=session).send("Teste", three_recipients())

    assert session.get.call_count == 3


def test_delivery_treats_paused_account_as_failure():
    session = MagicMock()
    session.get.side_effect = [
        make_response(),
        make_response(text="Your account is Paused. Click to resume."),
        make_response(),
    ]

    with pytest.raises(DeliveryError, match="conta pausada"):
        CallMeBotClient(session=session).send("Teste", three_recipients())


def test_delivery_timeout_is_failure_without_retrying_send():
    session = MagicMock()
    session.get.side_effect = [
        requests.Timeout("timeout"),
        make_response(),
        make_response(),
    ]

    with pytest.raises(DeliveryError, match="1 de 3"):
        CallMeBotClient(session=session).send("Teste", three_recipients())

    assert session.get.call_count == 3


def test_delivery_rejects_empty_recipient_list():
    with pytest.raises(DeliveryError, match="Nenhum destinatário"):
        CallMeBotClient(session=MagicMock()).send("Teste", [])


def test_weather_client_retries_timeout_then_succeeds():
    session = MagicMock()
    session.get.side_effect = [
        requests.Timeout("timeout"),
        make_response(create_mock_weather_data()),
    ]
    sleeper = MagicMock()
    client = OpenMeteoClient(session=session, sleeper=sleeper)

    result = client.get_forecast()

    assert result["hourly"]["time"]
    assert session.get.call_count == 2
    sleeper.assert_called_once_with(0.5)


def test_weather_client_fails_after_three_network_attempts():
    session = MagicMock()
    session.get.side_effect = requests.Timeout("timeout")
    sleeper = MagicMock()

    with pytest.raises(WeatherServiceError, match="após 3 tentativas"):
        OpenMeteoClient(session=session, sleeper=sleeper).get_forecast()

    assert session.get.call_count == 3
    assert sleeper.call_args_list[0].args == (0.5,)
    assert sleeper.call_args_list[1].args == (1.0,)


def test_weather_client_does_not_retry_non_retryable_http_error():
    session = MagicMock()
    response = make_response()
    response.raise_for_status.side_effect = make_http_error(400)
    session.get.return_value = response

    with pytest.raises(WeatherServiceError, match="HTTP 400"):
        OpenMeteoClient(session=session, sleeper=MagicMock()).get_forecast()

    assert session.get.call_count == 1


def test_weather_client_retries_temporary_http_error():
    session = MagicMock()
    unavailable = make_response()
    unavailable.raise_for_status.side_effect = make_http_error(503)
    session.get.side_effect = [unavailable, make_response(create_mock_weather_data())]

    result = OpenMeteoClient(session=session, sleeper=MagicMock()).get_forecast()

    assert result["daily"]["time"]
    assert session.get.call_count == 2


def test_weather_client_rejects_invalid_json():
    session = MagicMock()
    response = make_response()
    response.json.side_effect = ValueError("bad json")
    session.get.return_value = response

    with pytest.raises(WeatherServiceError, match="JSON inválido"):
        OpenMeteoClient(session=session).get_forecast()


def test_weather_client_rejects_incomplete_payload():
    session = MagicMock()
    session.get.return_value = make_response({"hourly": {}, "daily": {}})

    with pytest.raises(WeatherServiceError, match="incompleta"):
        OpenMeteoClient(session=session).get_forecast()


def test_weather_client_rejects_misaligned_series():
    session = MagicMock()
    payload = create_mock_weather_data()
    payload["hourly"]["temperature_2m"] = []
    session.get.return_value = make_response(payload)

    with pytest.raises(WeatherServiceError, match="vazias ou desalinhadas"):
        OpenMeteoClient(session=session).get_forecast()


def test_night_message_preserves_rain_and_high_uv_logic():
    message = build_forecast_message(
        create_mock_weather_data(),
        mode="night",
        now=FIXED_NOW,
    )

    assert "TRAILER / BIKES" in message
    assert "5.5mm" in message
    assert "Máx: 30.0°C" in message
    assert "UV Alto (7.5)" in message


def test_weekend_message_from_github_is_preserved():
    saturday = datetime(2026, 9, 26, 7, 0, tzinfo=MUNICH_TZ)
    payload = create_mock_weather_data(saturday)
    noon = payload["hourly"]["time"].index("2026-09-26T12:00")
    payload["hourly"]["precipitation"][noon] = 0.6

    message = build_forecast_message(payload, mode="morning", now=saturday)

    assert "Fim de Semana em Família" in message
    assert "Brincadeiras em casa" in message


def test_weekday_morning_reports_no_playground_when_rain_is_forecast():
    payload = create_mock_weather_data()
    after_kita = payload["hourly"]["time"].index("2026-09-24T17:00")
    payload["hourly"]["precipitation"][after_kita] = 0.1

    message = build_forecast_message(payload, mode="morning", now=FIXED_NOW)

    assert "Hoje não tem parquinho" in message


def test_weekday_morning_uses_rain_probability_for_playground():
    payload = create_mock_weather_data()
    evening = payload["hourly"]["time"].index("2026-09-24T19:00")
    payload["hourly"]["precipitation_probability"][evening] = 50

    message = build_forecast_message(payload, mode="morning", now=FIXED_NOW)

    assert "Hoje não tem parquinho" in message


def test_weekday_morning_reports_playground_when_forecast_is_dry():
    message = build_forecast_message(
        create_mock_weather_data(),
        mode="morning",
        now=FIXED_NOW,
    )

    assert "Hoje tem parquinho" in message


def test_weekday_playground_advice_appears_after_kita_return():
    message = build_forecast_message(
        create_mock_weather_data(),
        mode="morning",
        now=FIXED_NOW,
    )

    assert message.index("Volta (16:00)") < message.index("Parquinho:")


def test_weekday_night_report_does_not_include_playground_advice():
    message = build_forecast_message(
        create_mock_weather_data(),
        mode="night",
        now=FIXED_NOW,
    )

    assert "Parquinho:" not in message


def test_run_forecast_delivers_built_message_to_all_recipients():
    weather_client = MagicMock()
    weather_client.get_forecast.return_value = create_mock_weather_data()
    delivery_client = MagicMock()
    recipients = three_recipients()

    message = run_forecast(
        "morning",
        weather_client=weather_client,
        delivery_client=delivery_client,
        recipients=recipients,
        now=FIXED_NOW,
    )

    delivery_client.send.assert_called_once_with(message, recipients)


def test_cli_returns_error_when_configuration_is_missing(monkeypatch, capsys):
    for number in range(1, 4):
        monkeypatch.delenv(f"PHONE_{number}", raising=False)
        monkeypatch.delenv(f"APIKEY_{number}", raising=False)

    assert main(["--mode", "morning"]) == 1
    assert "Configuração incompleta" in capsys.readouterr().err
