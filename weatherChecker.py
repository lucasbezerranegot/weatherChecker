"""Backward-compatible CLI entry point for the weather checker."""

import argparse
import sys

from weather_checker.config import load_recipients
from weather_checker.delivery import CallMeBotClient
from weather_checker.exceptions import WeatherCheckerError
from weather_checker.service import generate_forecasts, run_forecast
from weather_checker.weather import get_weather_description


def send_whatsapp(message: str) -> None:
    CallMeBotClient().send(message, load_recipients())


def get_kita_forecast(mode: str) -> dict[int, str]:
    return run_forecast(mode)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Script de previsão do tempo para o Kita"
    )
    parser.add_argument(
        "--mode",
        choices=["morning", "night"],
        required=True,
        help="Define o tipo de relatório",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Gera e exibe os relatórios sem enviar mensagens",
    )
    args = parser.parse_args(argv)

    try:
        if args.dry_run:
            messages, _ = generate_forecasts(args.mode, require_credentials=False)
            for slot, message in messages.items():
                print(f"\n===== Destinatário {slot} =====\n{message}")
        else:
            get_kita_forecast(args.mode)
    except WeatherCheckerError as exc:
        print(f"🚨 {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
