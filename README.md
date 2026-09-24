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

## Testes

```bash
pytest -q
```
