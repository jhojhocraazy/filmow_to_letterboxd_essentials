# Contexto compactado — ETL Filmow → Letterboxd/Trakt

## Finalidade

Este documento conserva o contexto público, estável e didático do projeto para retomada futura. Ele não contém credenciais, conteúdo de `tmdb_api.txt`, nomes de usuário reais, IDs de sessão ou outros identificadores pessoais.

## Objetivo

Manter um ETL Python — extração, transformação e carregamento — que obtém o histórico público do Filmow, resolve a identidade de filmes no TMDb, busca sob demanda a nota pública do IMDb quando necessária e gera arquivos compatíveis com Letterboxd e Trakt, sem reduzir a confiança da identificação.

## Estado arquitetural

A aplicação começou como uma CLI monolítica e hoje está parcialmente modularizada:

- `filmow_to_letterboxd_essentials.py`: orquestração da CLI e do ETL, scraping do Filmow, fluxo de menu, exportação e métricas.
- `identity_matching.py`: regras puras de normalização, similaridade e pontuação de confiança.
- `tmdb_client.py`: API do TMDb, tempo limite, retentativas e normalização de metadados.
- `tests/`: testes unitários e de integração com `unittest`.
- `agents/`: instruções documentais para confiança, integrações, resiliência, performance, exportação, validação e UX.
- `AGENT.md`: regras globais, contratos, arquitetura e critérios de conclusão.

Fluxo de dados vigente:

1. Obter as páginas do histórico público do Filmow.
2. Extrair título, ano, direção, nota pessoal e ID quando disponível.
3. Auditar o ID encontrado com os metadados do TMDb.
4. Quando a auditoria direta não for suficiente, buscar candidatos de filmes e aplicar fallback com limiar próprio.
5. Usar a nota pública do IMDb somente quando o contrato escolhido precisar dela.
6. Preparar e publicar os CSV do formato selecionado e o relatório da execução.

## Termos técnicos

- **TMDb:** banco público de metadados cinematográficos usado para confirmar a identidade e obter IDs, títulos, ano, país e diretores.
- **IMDb:** fonte da nota pública usada pela exportação Analítica e pelas escolhas de origem IMDb.
- **JSON-LD:** formato de dados estruturados incorporado no HTML do Filmow; um ID encontrado ali é uma pista e ainda precisa passar pela auditoria de confiança.
- **Fallback:** busca alternativa quando o ID direto não é aceito. O resultado também passa por `calculate_confidence()` e pelo limiar de fallback.
- **Cache:** armazenamento temporário que evita trabalho repetido. O cache de detalhes do TMDb existe apenas durante a execução.
- **Lock:** trava de coordenação que controla acesso concorrente. O lock por TMDb ID serializa apenas consultas ao mesmo ID; IDs diferentes podem continuar em paralelo.
- **WAF:** *Web Application Firewall*, barreira que pode limitar ou recusar acesso automatizado e responder com HTTP 429 ou erros temporários.
- **RAM:** memória volátil do processo. O download comprimido do IMDb e o índice que permanece em RAM são recursos diferentes.

## Decisões de produção vigentes

### Fluxo formato → origem condicional → confirmação

1. O menu principal aceita:
   - `1` — Analítica;
   - `2` — Sintética;
   - `3` — Letterboxd;
   - `4` — Trakt;
   - `H` — ajuda, em qualquer caixa;
   - `0` — sair.
2. A origem das notas só é perguntada quando a seleção realmente depende dela:
   - Analítica usa Filmow + IMDb e não pede uma escolha adicional;
   - Sintética exporta somente IDs e não usa nota;
   - Letterboxd pergunta Filmow ou IMDb;
   - Trakt pergunta Filmow ou IMDb para o arquivo Ratings.
3. A CLI solicita o usuário público do Filmow e apresenta um resumo com formato, origem efetiva, colunas, conversão e arquivos esperados. A confirmação exige ação explícita antes de carregar o IMDb ou coletar o histórico.
4. Na confirmação, `1` inicia, `2` volta ao menu e `0` cancela. Cancelar ou voltar antes dessa ação não gera arquivo nem coleta dados.
5. Entrada inválida produz mensagem em português e mantém o usuário na etapa atual.
6. A ajuda abre uma nova tela e retorna ao menu. As transições usam `limpar_para_menu()`, que chama `limpar_tela()` sem transformar falha de limpeza em falha da exportação.

A inicialização da CLI pode carregar a credencial TMDb do armazenamento local, solicitar sua digitação se ausente e criar a sessão HTTP. Essas ações locais antecedem o menu, mas não equivalem a baixar o IMDb, consultar o histórico ou exportar arquivos.

### Opções, arquivos e contratos

Há quatro opções de formato e cinco arquivos CSV possíveis: Analítica, Sintética e Letterboxd geram um arquivo por execução; Trakt gera dois. Letterboxd possui dois cabeçalhos condicionais, mas apenas um deles é gerado em cada execução.

| Formato | Arquivo | Colunas, na ordem | Origem das notas |
|---|---|---|---|
| Analítica | `exportacao_analitica_<user>_<timestamp>.csv` | `imdbID`, `tmdbID`, `tmdbTitle`, `tmdbYear`, `tmdbCountry`, `tmdbDirectors`, `filmowTitle`, `filmowYear`, `filmowRating`, `Rating10` | Filmow + IMDb |
| Sintética | `exportacao_sintetica_<user>_<timestamp>.csv` | `imdbID`, `tmdbID` | nenhuma |
| Letterboxd — Filmow | `exportacao_letterboxd_<user>_<timestamp>.csv` | `imdbID`, `tmdbID`, `Rating` | Filmow original 0–5 |
| Letterboxd — IMDb | `exportacao_letterboxd_<user>_<timestamp>.csv` | `imdbID`, `tmdbID`, `Rating10` | IMDb original 0–10 |
| Trakt History | `exportacao_history_trakt_<user>_<timestamp>.csv` | `imdb_id`, `tmdb_id`, `type` | nenhuma |
| Trakt Ratings — Filmow | `exportacao_ratings_trakt_<user>_<timestamp>.csv` | `imdb_id`, `tmdb_id`, `type`, `rating` | Filmow ×2 para a escala 0–10 |
| Trakt Ratings — IMDb | `exportacao_ratings_trakt_<user>_<timestamp>.csv` | `imdb_id`, `tmdb_id`, `type`, `rating` | IMDb original 0–10 |

Regras comuns:

- `type` é sempre `movie`; séries e programas de TV não entram na exportação.
- `Rating` e `filmowRating` são notas do Filmow na escala 0–5. `Rating10` e `rating` quando associados ao IMDb são notas públicas na escala 0–10.
- Letterboxd preserva o valor original e o cabeçalho determinado pela origem.
- Trakt Ratings é a única conversão contratada: a origem Filmow multiplica por 2. A origem IMDb não converte. Portanto, a afirmação “sem conversão” deve ficar restrita às rotas que de fato não convertem.
- Trakt History não contém nota. History e Ratings recebem as linhas selecionadas para a execução; uma linha sem nota válida continua em Ratings com o campo `rating` vazio.
- Valores ausentes, não numéricos, fora da escala ou fora da grade de meias estrelas são inválidos para o exportador de nota e ficam vazios. Zero é uma nota válida e não significa ausência.
- IDs e demais valores válidos são preservados. A conversão Filmow ×2 do Trakt não se aplica aos outros contratos.
- `csv.DictWriter` usa `extrasaction="ignore"`; aliases (nomes alternativos) e campos internos como `idOrigin` não vazam para os CSV.
- A escrita é atômica: um CSV é publicado por substituição somente após ser finalizado, evitando arquivo final truncado.

### Dataset do IMDb sob demanda

- Analítica sempre depende do IMDb.
- Sintética, Letterboxd com Filmow e Trakt Ratings com Filmow não dependem do IMDb.
- Letterboxd e Trakt Ratings com origem IMDb dependem dele.
- Quando necessário e ausente localmente, `title.ratings.tsv.gz` é baixado de `datasets.imdbws.com` e indexado em memória.
- O índice pode ser reutilizado na mesma execução ao alternar entre formatos compatíveis, mas não é persistido entre execuções.
- Falha na obtenção é explícita e recuperável; nenhum CSV deve ser publicado parcialmente.

### Separação de responsabilidades

- **Identidade:** título, ano, diretores, comparação de metadados, limiares e fallback; não conhece o destino de saída.
- **Nota:** origem, escala, conversão Trakt e validação para o contrato; não escolhe o formato.
- **Exportação:** seleção de campos, ordenação, CSV e relatório; não consulta rede nem redecide identidade.

Mudança em uma área deve ser verificada nas demais por passagem de contrato. O dicionário intermediário aceita aliases como `imdbID`/`imdb_id`, `tmdbID`/`tmdb_id` e `Rating`/`rating`, mas o significado deve permanecer coerente no uso de cada exportador.

## Concorrência, cache e resiliência

- `MAX_WORKERS = 5` limita a concorrência do `ThreadPoolExecutor` por página.
- Resultados são consumidos por `as_completed()` à medida que as tarefas terminam.
- O cache de detalhes do TMDb usa sincronização para impedir chamadas duplicadas do mesmo ID durante uma execução, sem impedir o paralelismo entre IDs diferentes.
- Timeouts, intervalos, número de tentativas e tratamento de HTTP 429/5xx e WAF fazem parte do comportamento operacional e só devem mudar com justificativa.
- A extração do Filmow depende de seletores HTML, JSON-LD e paginação; mudanças devem ser validadas contra estruturas representativas.

## Testes atuais

A suíte usa apenas `unittest` e está em `tests/`. Os arquivos atuais são:

- `tests/test_confidence.py`;
- `tests/test_identity_matching.py`;
- `tests/test_tmdb_client.py`;
- `tests/test_integrations.py`;
- `tests/test_resilience.py`;
- `tests/test_performance.py`;
- `tests/test_export.py`;
- `tests/test_cli_export_flow.py`.

Comandos disponíveis:

```powershell
py -m unittest discover -s tests -v
py -m py_compile filmow_to_letterboxd_essentials.py identity_matching.py tmdb_client.py
```

O contexto antigo continha contagens de testes, tempos e resultados de benchmark. Esses números não são contratos e não são repetidos aqui sem uma nova execução controlada. Também não há suíte automatizada específica de benchmark real. Lint, type checking e cobertura percentual não estão configurados; o CI público executa a suíte `unittest` em `.github/workflows/tests.yml`.

Os testes atuais cobrem, conforme os arquivos presentes:

- confiança e limiares de JSON-LD/fallback;
- funções puras de normalização e similaridade;
- cliente TMDb e políticas de retentativa;
- integrações e resiliência;
- concorrência e métricas de pipeline;
- contratos, notas, conversão, ausência vazia e escrita CSV;
- menu, `H`/`0`, origem condicional, confirmação e cancelamento.

## Estado atual resumido

- O fluxo formato → origem condicional → confirmação está implementado.
- O dataset do IMDb é obtido somente quando o contrato selecionado precisa dele.
- Os contratos atuais estão implementados, inclusive Letterboxd condicional e os dois arquivos Trakt.
- A lógica de confiança e o cliente TMDb estão separados em módulos.
- O cache TMDb e a concorrência usam o limite vigente `MAX_WORKERS = 5`.
- A suíte atual existe; este documento não afirma uma contagem ou um resultado histórico sem verificação da execução correspondente.
- Não há afirmação de benchmark real novo, commit específico ou estado de execução presumido neste contexto público.

## Limitações conhecidas

- O cache TMDb não é persistido entre execuções.
- O índice do IMDb pode ocupar bastante memória; o tamanho do arquivo comprimido não representa o uso de RAM do índice.
- Não há métricas detalhadas permanentes para HTTP 429, respostas 5xx, retentativas e tempo total de espera.
- Não há teste automatizado para um benchmark real completo.
- A identificação depende dos dados públicos e da estabilidade do Filmow, do TMDb e do IMDb.
- A execução sem restrição de páginas percorre todo o histórico.

## Próximos passos sujeitos a validação

Antes de alterar redes, observabilidade ou performance:

1. Medir tempo, falhas, respostas 429/5xx, retentativas e memória com o mesmo conjunto de entradas.
2. Isolar falhas individuais sem transformar uma falha local em perda das demais linhas.
3. Preservar timeouts, `Retry-After`, espera exponencial e parsing validado.
4. Manter `MAX_WORKERS = 5` até que benchmark e aprovação explícita indiquem outro valor.
5. Avaliar cache de busca normalizada apenas com uma chave segura que inclua ano e diretores.
6. Rodar a suíte e a compilação após cada mudança e revisar o diff completo.
7. Confirmar que credenciais, conjuntos de dados e artefatos continuam ignorados antes de qualquer commit.

## Critérios de preservação

Uma mudança futura só deve ser considerada validada quando:

- os testes existentes e os novos testes relevantes passarem;
- o Python continuar compilando;
- fluxo, `H`/`0`, confirmação, limpeza e origem condicional permanecerem coerentes;
- cabeçalhos, ordem, arquivos, origens, escalas e conversão Trakt permanecerem corretos;
- nota ausente ou inválida continuar vazia e zero válido continuar preservado;
- o dataset do IMDb continuar sendo obtido apenas quando necessário;
- credenciais e identificadores pessoais não aparecerem em logs, documentação, commits ou respostas;
- o fallback continuar aceitando os mesmos casos válidos e rejeitando falsos positivos conhecidos;
- qualquer ganho de performance tiver comparação válida com o baseline e sem regressão funcional.
