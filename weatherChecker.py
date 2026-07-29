import argparse
import os
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# --- Configurações ---
LAT = 48.137154  # Munich Ramersdorf
LON = 11.576124

RECIPIENTS = [
    {"phone": os.getenv("PHONE_1"), "apikey": os.getenv("APIKEY_1")},
    {"phone": os.getenv("PHONE_2"), "apikey": os.getenv("APIKEY_2")}
]

def get_weather_description(wmo_code):
    codes = {
        0: "☀️ Céu limpo", 1: "🌤️ Maiormente limpo", 2: "⛅ Parcialmente nublado", 3: "☁️ Nublado",
        45: "🌫️ Neblina", 48: "🌫️ Névoa",
        51: "🌧️ Garoa leve", 53: "🌧️ Garoa moderada", 55: "🌧️ Garoa forte",
        61: "☔ Chuva leve", 63: "☔ Chuva moderada", 65: "☔ Chuva forte",
        68: "🌨️💧 Schneeregen leve", 69: "🌨️💧 Schneeregen forte",
        71: "❄️ Neve leve", 73: "❄️ Neve moderada", 75: "❄️ Neve forte",
        80: "🌦️ Pancadas", 81: "🌦️ Pancadas fortes",
        95: "⛈️ Trovoada"
    }
    return codes.get(wmo_code, f"❓ {wmo_code}")

def send_whatsapp(message):
    for person in RECIPIENTS:
        if not person.get("phone") or not person.get("apikey"):
            print(f"⚠️ Chaves ausentes para um contato. Pulando.")
            continue
        url = "https://api.callmebot.com/whatsapp.php"
        try:
            requests.get(url, params={"phone": person["phone"], "text": message, "apikey": person["apikey"]})
        except Exception as e:
            print(f"Erro ao enviar para {person['phone']}: {e}")

def get_kita_forecast(mode):
    munich_tz = ZoneInfo("Europe/Berlin")
    now = datetime.now(munich_tz)
    
    # O CI/CD define a regra, o Python apenas executa
    if mode == "night":
        target_date = now.date() + timedelta(days=1)
        day_label = "Amanhã"
    else:
        target_date = now.date()
        day_label = "Hoje"

    target_date_str = target_date.strftime("%Y-%m-%d")

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": LAT, "longitude": LON,
        "hourly": "temperature_2m,apparent_temperature,precipitation,weather_code,wind_gusts_10m",
        "daily": "uv_index_max",
        "timezone": "Europe/Berlin"
    }
    
    data = requests.get(url, params=params).json()
    hourly, daily = data["hourly"], data["daily"]

    # --- LÓGICA DO TRAILER E BIKES (Só roda se o modo for "night") ---
    night_alert = ""
    if mode == "night":
        current_hour_str = now.strftime("%Y-%m-%dT%H:00")
        try:
            idx_now = hourly["time"].index(current_hour_str)
            idx_tomorrow_0700 = hourly["time"].index(f"{target_date_str}T07:00")
            night_precip = hourly["precipitation"][idx_now : idx_tomorrow_0700 + 1]
            
            if any(p > 0.0 for p in night_precip if p is not None):
                max_rain = max(p for p in night_precip if p is not None)
                night_alert = f"🚨 *TRAILER / BIKES:* Vai chover até {max_rain}mm na madrugada. Guardar!\n\n"
            else:
                night_alert = f"🌙 *Trailer:* Madrugada seca. Pode deixar fora.\n\n"
        except ValueError:
            night_alert = "⚠️ Erro ao calcular previsão da madrugada.\n\n"

    # --- LÓGICA DAS ROUPAS (Ida, Kita, Volta) ---
    idx_0800 = hourly["time"].index(f"{target_date_str}T08:00")
    idx_1600 = hourly["time"].index(f"{target_date_str}T16:00")
    kita_slice = slice(idx_0800, idx_1600 + 1)
    
    temps = hourly["temperature_2m"][kita_slice]
    feels = hourly["apparent_temperature"][kita_slice]
    
    day_idx = daily["time"].index(target_date_str)
    uv_max = daily["uv_index_max"][day_idx]
    uv_alert = f"⚠️ *UV Alto ({uv_max})* - Protetor!" if uv_max >= 6.0 else f"☀️ UV: {uv_max} (OK)"

    # --- MONTAGEM DA MENSAGEM ---
    message = night_alert  
    message += f"🧥 *Roupas do Kita* ({day_label} - {target_date.strftime('%d/%m')})\n\n"
    
    message += f"🚲 *Ida (08:00):*\n"
    message += f"🌡️ {hourly['temperature_2m'][idx_0800]}°C (Sens: {hourly['apparent_temperature'][idx_0800]}°C) | 💨 {hourly['wind_gusts_10m'][idx_0800]} km/h\n"
    message += f"{get_weather_description(hourly['weather_code'][idx_0800])}\n\n"

    message += f"🎒 *No Kita (08:00 - 16:00):*\n"
    message += f"📈 Máx: {max(temps)}°C (Sens: {max(feels)}°C)\n"
    message += f"📉 Mín: {min(temps)}°C (Sens: {min(feels)}°C)\n"
    message += f"{uv_alert}\n\n"

    message += f"🚲 *Volta (16:00):*\n"
    message += f"🌡️ {hourly['temperature_2m'][idx_1600]}°C (Sens: {hourly['apparent_temperature'][idx_1600]}°C) | 💨 {hourly['wind_gusts_10m'][idx_1600]} km/h\n"
    message += f"{get_weather_description(hourly['weather_code'][idx_1600])}"

    send_whatsapp(message)

if __name__ == "__main__":
    # Configura o script para aceitar argumentos via terminal (ou CI/CD)
    parser = argparse.ArgumentParser(description="Script de previsão do tempo para o Kita")
    parser.add_argument("--mode", choices=["morning", "night"], required=True, help="Define o tipo de relatório")
    args = parser.parse_args()
    
    get_kita_forecast(args.mode)