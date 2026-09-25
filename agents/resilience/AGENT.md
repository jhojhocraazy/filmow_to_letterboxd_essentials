# Agente de Resiliência e Scraping

## Responsabilidade

Manter a coleta do histórico do Filmow estável diante de WAF, limites de requisição, paginação e mudanças de HTML.

## Escopo

- `filmow_to_letterboxd_essentials.py`: `obter_pagina_blindada()`, `extrair_historico_completo()` e a extração de HTML/JSON-LD em `processar_filme()`.
- Criação da sessão `cloudscraper` em `criar_sessao_filmow()`.
- Timeouts, espera entre requisições, `Retry-After` e política de retentativas existentes.

## Contexto

O scraper usa seletores CSS do Filmow, JSON-LD e paginação `?pagina=`. WAF é a barreira de proteção do serviço e pode responder com HTTP 429 ou erros temporários 5xx, incluindo 502, 503, 504, 520, 521, 522 e 524. A resposta não deve ser interpretada automaticamente como conteúdo útil nem convertida em campo inventado.

## Regras

- Preservar timeouts, `Retry-After` e espera exponencial existentes, salvo alteração solicitada.
- Não aumentar a frequência de requisições nem `MAX_WORKERS` sem benchmark explícito.
- Preservar a identificação do histórico público e a contagem de páginas.
- Ao alterar seletores, validar título, ano, diretores, nota e link, todos consumidos posteriormente.
- JSON-LD inválido ou ausente não pode gerar ID confiável por acidente.
- Não decidir se uma identidade é confiável; encaminhar os dados ao agente de confiança.
- Não expor credenciais, nomes de usuário reais ou identificadores pessoais em mensagens de falha.
- Tratar falhas transitórias conforme a política existente e distinguish-las de ausência real de campo.
- Não afirmar que `MAX_WORKERS = 5` elimina WAF ou 429; ele limita a concorrência, enquanto as respostas do serviço precisam de tratamento e medição.

## Padrões existentes

- Itens extraídos por `#movies-list li.movie_list_item` e `a.tip-movie[href]`.
- ID IMDb procurado em scripts JSON-LD e URLs `imdb.com/title/tt...`.
- Sessão criada em um ponto injetável, o que facilita isolamento nos testes.
- `MAX_WORKERS = 5` pertence à orquestração por página.

## Dependências

- `cloudscraper`, `requests`, `beautifulsoup4`, `re`, `time` e `urljoin`.

## Testes

A suíte atual contém testes de resiliência. Validar respostas simuladas para:

- página vazia e histórico inexistente;
- paginação e número de páginas;
- JSON-LD ausente ou inválido;
- HTML sem algum campo;
- HTTP 429 e 5xx, incluindo `Retry-After` quando aplicável;
- exaustão de tentativas, sem exceder o limite de `MAX_WORKERS`.

Não usar rede real na validação padrão.

## Comandos

```text
py -m unittest tests.test_resilience -v
py -m unittest discover -s tests -v
```

## Critérios de conclusão

- Falhas transitórias continuam sendo tratadas conforme a política existente.
- A extração não perde páginas e não inventa campos ausentes.
- Mudanças de parser preservam a estrutura usada pelo pipeline.
- O limite de concorrência permanece `MAX_WORKERS = 5`.
