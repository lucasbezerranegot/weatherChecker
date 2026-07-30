import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Importa as duas funções do seu script principal
from weatherChecker import get_kita_forecast, send_whatsapp

# ==========================================
# 1. DADOS FALSOS E PREPARAÇÃO (MOCKS)
# ==========================================

# Destinatários falsos para não depender das variáveis de ambiente no teste
MOCK_RECIPIENTS = [
    {"phone": "+490000000", "apikey": "CHAVE_TESTE"}
]

def create_mock_weather_data(target_date_str):
    """Gera um JSON falso idêntico ao do Open-Meteo para testar a lógica."""
    hourly_times = [f"{target_date_str}T{str(i).zfill(2)}:00" for i in range(24)]
    
    # Temperaturas: 10 graus o dia todo, com pico de 30 graus ao meio-dia
    temperatures = [10.0] * 24
    temperatures[12] = 30.0 
    
    # Chuva: tudo seco, exceto 5.5mm às 02:00 da manhã
    precipitation = [0.0] * 24
    precipitation[2] = 5.5 

    return {
        "hourly": {
            "time": hourly_times,
            "temperature_2m": temperatures,
            "apparent_temperature": temperatures, 
            "precipitation": precipitation,
            "weather_code": [0] * 24, 
            "wind_gusts_10m": [15.0] * 24
        },
        "daily": {
            "time": [target_date_str],
            "uv_index_max": [7.5] # UV Alto
        }
    }


# ==========================================
# 2. TESTES DE INTEGRAÇÃO (WHATSAPP)
# ==========================================

def test_send_whatsapp_success():
    """Garante que a função não quebra quando o CallMeBot responde com sucesso real."""
    with patch("weatherChecker.RECIPIENTS", MOCK_RECIPIENTS), \
         patch("weatherChecker.requests.get") as mock_get:
        
        # Simula resposta HTTP 200 normal
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
        
        # Simula a exata resposta HTML de erro disfarçado
        mock_response = MagicMock()
        mock_response.text = "<h2>Your Account is <b>Paused</b> due to technical issues.</h2>"
        mock_get.return_value = mock_response
        
        # Verifica se o sys.exit(1) é acionado para falhar o GitHub Actions
        with pytest.raises(SystemExit) as exc_info:
            send_whatsapp("Teste Conta Pausada")
            
        assert exc_info.value.code == 1


# ==========================================
# 3. TESTES DE LÓGICA DE NEGÓCIO (CLIMA)
# ==========================================

@patch("weatherChecker.send_whatsapp") # Impede o envio de mensagem real
@patch("weatherChecker.requests.get")  # Impede o download de dados reais
def test_night_mode_detects_rain_and_high_uv(mock_get, mock_send_whatsapp):
    """Testa se o modo noturno processa corretamente a chuva e o alerta UV."""
    
    # Prepara a data de "amanhã" respeitando o fuso da Alemanha
    munich_tz = ZoneInfo("Europe/Berlin")
    now = datetime.now(munich_tz)
    tomorrow_str = (now.date() + timedelta(days=1)).strftime("%Y-%m-%d")
    
    # Entrega o JSON falso que criamos lá em cima
    mock_response = MagicMock()
    mock_response.json.return_value = create_mock_weather_data(tomorrow_str)
    mock_get.return_value = mock_response
    
    # Executa a função
    get_kita_forecast(mode="night")
    
    # Analisa a mensagem final montada pelo script
    args, kwargs = mock_send_whatsapp.call_args
    sent_message = args[0]
    
    # Validações estruturais do relatório
    assert "TRAILER / BIKES" in sent_message
    assert "5.5mm" in sent_message
    assert "Máx: 30.0°C" in sent_message
    assert "Alerta UV" in sent_message
    assert "7.5" in sent_message
