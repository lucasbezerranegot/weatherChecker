import pytest
from unittest.mock import patch, MagicMock

from weatherChecker import send_whatsapp

# --- Dados de Teste ---
# Injetamos destinatários falsos para o teste não depender do ambiente (Secrets)
MOCK_RECIPIENTS = [
    {"phone": "+490000000", "apikey": "CHAVE_TESTE"}
]

def test_send_whatsapp_success():
    """Garante que a função não quebra quando o CallMeBot responde com sucesso real."""
    with patch("weatherChecker.RECIPIENTS", MOCK_RECIPIENTS), \
         patch("weatherChecker.requests.get") as mock_get:
        
        # Simula uma resposta HTTP 200 com texto genérico de sucesso
        mock_response = MagicMock()
        mock_response.text = "Message queued successfully."
        mock_get.return_value = mock_response
        
        # Se a função não levantar SystemExit(1), o teste passa
        try:
            send_whatsapp("Teste de Sucesso")
        except SystemExit:
            pytest.fail("send_whatsapp levantou SystemExit inesperadamente!")


def test_send_whatsapp_paused_account():
    """Garante que a função captura o falso positivo (HTTP 200 + 'Paused') e quebra (Exit 1)."""
    with patch("weatherChecker.RECIPIENTS", MOCK_RECIPIENTS), \
         patch("weatherChecker.requests.get") as mock_get:
        
        # Simula a exata resposta HTML que você recebeu
        mock_response = MagicMock()
        mock_response.text = "<h2>Your Account is <b>Paused</b> due to technical issues.</h2>"
        mock_get.return_value = mock_response
        
        # Verifica se o sys.exit(1) é disparado corretamente
        with pytest.raises(SystemExit) as exc_info:
            send_whatsapp("Teste Conta Pausada")
            
        assert exc_info.value.code == 1