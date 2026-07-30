import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Importa as duas funções do seu script principal
from weatherChecker import get_kita_forecast, send_whatsapp

# ==========================================
# 1. DADOS FALSOS E PREPARAÇÃO (MOCKS)
# ==========================================

# Variável de contatos falsos para os testes do CallMeBot
MOCK_RECIPIENTS = [
    {"phone": "+490000000", "apikey": "CHAVE_TESTE"}
]

def create_mock_weather_data(today_str, tomorrow_str):
    """Gera um JSON falso com 48 horas (hoje e amanhã) para o teste não quebrar a busca de 'agora'."""
    hourly_times = [f"{today_str}T{str(i).zfill(2)}:00" for i in range(24)] + \
                   [f"{tomorrow_str}T{str(i).zfill(2)}:00" for i in range(24)]
    
    temperatures = [10.0] * 48
    temperatures[36] = 30.0 
    
    precipitation = [0.0] * 48
    precipitation[26] = 5.5 

    return {
        "hourly": {
            "time": hourly_times,
            "temperature_2m": temperatures,
            "apparent_temperature": temperatures, 
            "precipitation": precipitation,
            "weather_code": [0] * 48, 
            "wind_gusts_10m": [15.0] * 48
        },
        "daily": {
            "time": [today_str, tomorrow_str],
            "uv_index_max": [3.0, 7.5] 
        }
    }

# ==========================================
# 2. TESTES DE INTEGRAÇÃO (WHATSAPP)
# ==========================================

def test_send_whatsapp_success():
    """Garante que a função não quebra quando o CallMeBot responde com sucesso real."""
    with patch("weatherChecker.RECIPIENTS", MOCK_RECIPIENTS), \
         patch("weatherChecker.requests.get") as mock_get:
        
        mock_response = MagicMock()
        mock_response.text = "Message queued successfully."
        mock_get.return_value = mock_response
        
        try:
            send_whatsapp("Teste de Sucesso")
        except SystemExit:
            pytest.fail("A função levantou SystemExit inesperadamente num cenário de sucesso!")


def test_send_whatsapp_paused_account():
    """Garante que a função captura o falso positivo (HTTP 200 + 'Paused') e quebra o pipeline."""
    with patch("weatherChecker.RECIPIENTS", MOCK_RECIPIENTS), \
         patch("weatherChecker.requests.get") as mock_get:
        
        mock_response = MagicMock()
        mock_response.text = "<h2>Your Account is <b>Paused</b> due to technical issues.</h2>"
        mock_get.return_value = mock_response
        
        with pytest.raises(SystemExit) as exc_info:
            send_whatsapp("Teste Conta Pausada")
            
        assert exc_info.value.code == 1


# ==========================================
# 3. TESTES DE LÓGICA DE NEGÓCIO (CLIMA)
# ==========================================

@patch("weatherChecker.send_whatsapp") 
@patch("weatherChecker.requests.get")  
def test_night_mode_detects_rain_and_high_uv(mock_get, mock_send_whatsapp):
    """Testa se o modo noturno processa corretamente a chuva e o alerta UV."""
    
    munich_tz = ZoneInfo("Europe/Berlin")
    now = datetime.now(munich_tz)
    today_str = now.strftime("%Y-%m-%d")
    tomorrow_str = (now.date() + timedelta(days=1)).strftime("%Y-%m-%d")
    
    mock_response = MagicMock()
    mock_response.json.return_value = create_mock_weather_data(today_str, tomorrow_str)
    mock_get.return_value = mock_response
    
    get_kita_forecast(mode="night")
    
    args, kwargs = mock_send_whatsapp.call_args
    sent_message = args[0]
    
    assert "TRAILER / BIKES" in sent_message
    assert "5.5mm" in sent_message
    assert "Máx: 30.0°C" in sent_message
    
    # CORREÇÃO: Procurando pela string exata que o seu script monta
    assert "UV Alto" in sent_message 
    assert "7.5" in sent_message