# Arquitetura

## Visão geral

A solução é uma aplicação de console local, dividida em três módulos Python:

```text
filmow_to_letterboxd_essentials.py  -> orquestração, scraping, ETL e exportação
identity_matching.py                -> regras puras de comparação de identidade
tmdb_client.py                      -> cliente TMDb, retry e normalização
```

Os testes ficam em `tests/` e usam `unittest` com respostas e E/S simuladas.

## Fluxo principal

1. A CLI exibe o menu e coleta formato, origem das notas, quando aplicável, e perfil público.
2. A sessão HTTP resilientemente lê as páginas paginadas do histórico.
3. Cada página é processada com até cinco tarefas concorrentes.
4. Para cada filme, o HTML fornece título, ano, direção, nota e possível ID IMDb por JSON-LD.
5. O ID é auditado no TMDb. Se não houver evidência suficiente, uma busca semântica restrita a filmes procura candidatos.
6. `identity_matching.py` calcula confiança com títulos normalizados, ano e direção.
7. O dicionário interno enriquecido é entregue às funções de exportação.
8. CSV e relatório são escritos em arquivos temporários e publicados por substituição atômica.

## Separação de responsabilidades

### Módulo principal

Concentra a interação com o usuário, a leitura do histórico, a orquestração concorrente, o carregamento opcional do dataset do IMDb e a preparação dos formatos públicos. Também mantém wrappers para preservar a interface histórica do aplicativo.

### Cliente TMDb

`tmdb_client.py` envia requisições com timeout, repete respostas 429 e 5xx, respeita `Retry-After` quando numérico e limita a espera. Apenas payload de filmes é consultado, reduzindo o risco de tratar séries como filmes. A chave é recebida por argumento e não deve ser registrada.

### Matching

`identity_matching.py` não faz E/S. Recebe dicionários já extraídos e retorna somente uma pontuação. Títulos são normalizados para ignorar acentos, caixa e certos numerais romanos editoriais; ano e direção funcionam como evidências cruzadas.

O caminho principal aceita pontuação a partir de 40. O fallback semântico exige pelo menos 100 e também um ID IMDb, uma condição conservadora para reduzir falsos positivos.

## Concorrência e cache

- O histórico é dividido por páginas para limitar o pico de trabalho.
- `MAX_WORKERS` limita as requisições simultâneas.
- Resultados são reordenados pelo índice original antes de avançar, portanto a ordem do CSV não depende da conclusão das threads.
- Falhas de uma obra são isoladas e contabilizadas.
- Detalhes do TMDb são cacheados por ID. Locks por ID evitam consultas duplicadas para o mesmo recurso, enquanto IDs diferentes podem ser buscados em paralelo.
- O dataset do IMDb é carregado apenas para a analítica ou quando a origem escolhida é IMDb em Letterboxd/Trakt.

## Validação e escrita

A preparação de linhas cria somente os campos do contrato solicitado. Notas usam `Decimal` e validação de faixa. O zero é preservado; ausência e valores inválidos viram vazio. `csv.DictWriter` ignora campos internos extras.

Escrita e relatório usam temporário, flush, `fsync` e `os.replace`, com limpeza do temporário em caso de exceção.

## Decisões e limites

- A aplicação é um ETL, não um importador automático de Letterboxd ou Trakt.
- Não há banco de dados; datasets e cache são em memória e o dataset IMDb é mantido em arquivo local.
- A confiança é heurística e não elimina ambiguidade de títulos ou metadados.
- O código depende do HTML público do Filmow e dos contratos do TMDb/IMDb; mudanças externas podem quebrar a coleta.
- Os testes validam lógica e integração com mocks, mas não comprovam disponibilidade ou termos de uso dos serviços.
