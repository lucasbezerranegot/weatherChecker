# Weather Checker

Envia previsões personalizadas pelo CallMeBot para várias famílias. Cada família
pode ter localização, fuso horário, crianças, perfis térmicos e janela de
parquinho próprios.

## Configuração familiar

Copie `households.example.json` para `households.json` e ajuste os dados. O
arquivo real é ignorado pelo Git. Depois, execute com:

```bash
export HOUSEHOLDS_CONFIG_PATH=households.json
python3 weatherChecker.py --mode morning
```

Também é possível colocar o JSON completo em `HOUSEHOLDS_CONFIG_JSON`. No
GitHub Actions, esse valor deve ser criado como um repository secret com esse
nome.

Cada entrada de `recipients` usa um slot numérico. As credenciais podem vir de
`PHONE_<slot>` e `APIKEY_<slot>` ou, para uma configuração privada em arquivo ou
secret, dos campos `phone` e `apikey` do próprio destinatário. Variáveis de
ambiente têm prioridade.

```json
"recipients": {
  "1": {"household": "family_1"},
  "4": {
    "household": "another_family",
    "phone": "+49000000000",
    "apikey": "callmebot-key"
  }
}
```

Por padrão, um destinatário recebe recomendações para todas as crianças da sua
família. Para selecionar apenas algumas:

```json
"4": {
  "household": "family_1",
  "children": ["child_2"]
}
```

Perfis térmicos aceitos:

- `cold_sensitive`: escolhe aproximadamente uma faixa de roupa mais quente;
- `neutral`: usa a sensação térmica prevista;
- `warm_sensitive`: escolhe aproximadamente uma faixa mais leve.

Se `HOUSEHOLDS_CONFIG_PATH` e `HOUSEHOLDS_CONFIG_JSON` não forem definidos, a
configuração padrão mantém os slots 1 e 2 na família principal e o slot 3 em
uma família independente, todos na localização atual de Munique.

## Execução local com Docker

1. Copie `households.example.json` para `households.json` e personalize famílias,
   crianças e destinatários.
2. Copie `.env.example` para `.env` e preencha as credenciais do CallMeBot.
3. Confira todas as mensagens sem enviá-las:

```bash
HOUSEHOLDS_CONFIG_FILE=./households.json docker compose run --rm \
  weather-checker python weatherChecker.py --mode morning --dry-run
HOUSEHOLDS_CONFIG_FILE=./households.json docker compose run --rm \
  weather-checker python weatherChecker.py --mode night --dry-run
```

4. Somente depois da conferência, inicie o scheduler:

```bash
HOUSEHOLDS_CONFIG_FILE=./households.json docker compose up -d --build
docker compose logs -f weather-checker
```

O processo agenda os relatórios todos os dias às **07:00** e **20:00** no fuso
`Europe/Berlin`. O horário continua sendo o horário local após as mudanças de
verão/inverno. Jobs atrasados em até 30 minutos são consolidados e executados
uma vez; execuções simultâneas são bloqueadas.

Se uma consulta meteorológica ou qualquer envio falhar, a execução termina com
erro e o health check do container fica `unhealthy` até uma execução completa
ter sucesso. Antes do primeiro horário agendado, o container é considerado
saudável.

Para parar sem apagar configuração:

```bash
docker compose down
```

O workflow operacional do GitHub fica disponível apenas para disparos manuais de
contingência. Eventos enviados pelo cron-job.org não iniciam mais relatórios,
evitando mensagens duplicadas com o scheduler local.

## CI

O workflow `CI` roda em cada push e pull request. Ele executa todos os testes,
valida o Compose e constrói a imagem Docker.

## Testes

```bash
python -m pip install -r requirements-dev.txt
pytest -q
```
