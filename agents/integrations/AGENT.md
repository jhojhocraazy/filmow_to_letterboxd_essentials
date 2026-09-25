# Agente de Integrações Externas

## Responsabilidade

Manter as integrações confiáveis com TMDb, dataset público do IMDb e armazenamento seguro da credencial, respeitando a política de identidade.

## Escopo

- `tmdb_client.py`: `fetch_tmdb()` e `get_tmdb_details()`.
- `filmow_to_letterboxd_essentials.py`: `carregar_credencial()`, `carregar_datasets_imdb()`, wrappers `fetch_tmdb()`/`get_tmdb_details()` e `resolve_tmdb_by_search()`.
- `tmdb_api.txt`, quando existir, é credencial local ignorada; seu conteúdo não deve ser lido para fins documentais.
- `title.ratings.tsv.gz`, quando existir, é conjunto local ignorado.

## Contexto

A API do TMDb é a versão 3. `tmdb_client.py` encapsula comunicação, tempo limite, retentativas e normalização; wrappers, isto é, funções de compatibilidade no módulo principal preservam a interface e a injeção da chave. As notas do IMDb vêm de `datasets.imdbws.com` e são indexadas em RAM somente quando o contrato efetivo precisa delas.

A camada de integração fornece dados; ela não aceita nem rejeita uma identidade por conta própria. `calculate_confidence()` e a política de fallback permanecem no agente de confiança.

## Regras

- Preservar a injeção da chave como parâmetro da requisição, sem imprimi-la nem incluí-la em URL persistida, log ou erro.
- Preservar timeouts, retentativas e tratamento de respostas inválidas existentes.
- Não alterar endpoint, formato do dataset ou nomes de arquivos sem evidência na tarefa.
- Não baixar nem indexar o IMDb para Sintética ou quando a origem efetiva for Filmow.
- Analítica, Letterboxd com IMDb e Trakt com IMDb exigem o dataset; erros de obtenção devem ser explícitos e recuperáveis.
- Tratar a credencial ausente ou vazia por meio do fluxo seguro existente, sem registrá-la.
- Manter integração separada da regra de decisão de confiança.
- Não registrar nomes de usuário reais, IDs de sessão ou identificadores pessoais.

## Padrões existentes

- Dependências declaradas em `requirements.txt`.
- Arquivos sensíveis e artefatos gerados protegidos por `.gitignore`.
- Dicionário IMDb mantido em memória durante a execução e reutilizável entre formatos compatíveis.

## Dependências

- `requests`, `cloudscraper`, `pathlib`, `gzip` e `json`.

## Testes

Validar sem rede:

- credencial ausente ou vazia pelo caminho seguro;
- dataset já presente e ausência de download redundante;
- leitura do gzip e índice sob demanda;
- resposta TMDb vazia ou inválida;
- HTTP 429, 5xx, exceções e JSON inválido conforme a política existente;
- ausência de nota pública sem confundi-la com zero;
- injeção da chave sem exposição.

## Comandos

```text
py -m unittest tests.test_tmdb_client -v
py -m unittest tests.test_integrations -v
py -m unittest discover -s tests -v
```

## Critérios de conclusão

- A chave permanece protegida e não é exposta.
- O dataset só é obtido quando o contrato exige nota pública.
- Falhas de rede permanecem tratáveis segundo a política existente.
- A integração não toma decisões de confiança.
