# Agente do Projeto Filmow Export

## Responsabilidade

Manter mudanças corretas e compatíveis no ETL que extrai o histórico público do Filmow, resolve identidades cinematográficas no TMDb, obtém notas públicas do IMDb e gera arquivos para Letterboxd e Trakt.

## Escopo

- `filmow_to_letterboxd_essentials.py`: CLI, ETL, integrações, resolução de identidade e exportação.
- `identity_matching.py`: normalização de texto, similaridade e pontuação de confiança.
- `tmdb_client.py`: comunicação com a API do TMDb, retentativas e normalização de metadados.
- `requirements.txt`: dependências externas.
- `README.md`: instalação, operação e visão arquitetural.
- `agents/`: instruções documentais dos agentes especializados.
- `.gitignore`: proteção de credenciais, conjuntos de dados e artefatos gerados.
- Artefatos locais ignorados, quando existirem: `tmdb_api.txt` e `title.ratings.tsv.gz`.
- Não editar `.git/`.

## Contexto técnico

- A aplicação é uma CLI predominantemente modular e procedural. O módulo principal orquestra o ETL; `identity_matching.py` isola regras puras; `tmdb_client.py` isola a integração com o TMDb.
- O pipeline coleta as páginas do histórico público do Filmow, extrai título, ano, direção e nota pessoal, resolve IDs no TMDb, consulta a nota pública do IMDb quando o contrato precisa dela e grava os arquivos de saída.
- A extração concorrente usa `ThreadPoolExecutor` com `MAX_WORKERS = 5`, isto é, no máximo cinco tarefas submetidas ao pool por vez. Esse limite preserva contenção de carga, mas não garante por si só que o WAF nunca responderá com bloqueio ou HTTP 429.
- WAF (*Web Application Firewall*) é uma barreira de proteção do serviço que pode recusar ou limitar requisições automatizadas. `cloudscraper` cria a sessão usada para acessar o Filmow; `BeautifulSoup` faz a análise do HTML; `requests` atende ao acesso HTTP; `rich` apresenta a interface.
- A API externa do TMDb é a versão 3, e a credencial local é carregada por `carregar_credencial()`. A credencial não deve aparecer em código, documentação, logs, URLs ou respostas.
- As notas públicas vêm de `title.ratings.tsv.gz`, obtido de `datasets.imdbws.com` quando necessário e ausente localmente. O índice fica somente na memória durante a execução.
- Fallback é uma alternativa de resolução usada quando o ID obtido diretamente não passa na auditoria. Cache é armazenamento temporário que evita repetir uma operação; neste projeto, o cache do TMDb dura uma execução. Lock é um mecanismo de coordenação que serializa acesso ao recurso protegido.
- O projeto não contém frontend, banco de dados ou processos de longa duração; o CI público está em `.github/workflows/tests.yml`.

## Agentes especializados

- `agents/confidence/`: auditoria de identidade e redução de falsos positivos.
- `agents/integrations/`: TMDb, IMDb, credenciais e contratos HTTP.
- `agents/resilience/`: scraping, WAF, retentativas e paginação.
- `agents/performance/`: concorrência, cache, tempo e uso de memória.
- `agents/export/`: CSV, nomes de arquivos, notas e relatório.
- `agents/validation/`: estratégia de testes e validação, sem inventar infraestrutura.
- `agents/ux/`: menus interativos, origem condicional, confirmação, ajuda e limpeza de tela.

## Decisões de produção

As decisões a seguir são o padrão público a preservar; alterá-las exige pedido explícito.

### Fluxo da CLI

O fluxo é sequencial: **formato → origem condicional → confirmação**.

1. **Formato:** o menu aceita `1` Analítica, `2` Sintética, `3` Letterboxd, `4` Trakt, `H` para ajuda (aceita em qualquer caixa) e `0` para sair.
2. **Origem condicional:** só é solicitada quando a escolha altera a nota exportada. Analítica usa as duas fontes (Filmow + IMDb) por contrato; Sintética não exporta notas; Letterboxd e Trakt pedem explicitamente Filmow ou IMDb.
3. **Usuário e confirmação:** depois da origem aplicável, a CLI solicita o usuário público do Filmow, mostra formato, origem efetiva, colunas, conversão e arquivos esperados, e exige confirmação. Na confirmação, `1` inicia, `2` volta ao menu e `0` cancela a execução.

Regras do fluxo:

- Não antecipar perguntas de etapas que não se aplicam.
- Não baixar ou indexar o IMDb, acessar o histórico ou gravar CSV antes da confirmação final. A leitura local da credencial, seu prompt seguro e a criação da sessão ocorrem na inicialização da CLI, mas não são coleta de dados nem exportação.
- Voltar ou cancelar antes da confirmação não produz arquivo nem coleta de dados.
- Entrada inválida mantém o usuário na etapa atual, com mensagem em português e sem efeito colateral.
- A ajuda `H` abre a documentação e retorna ao menu; `0` no menu encerra com sucesso.
- A transição de telas usa `limpar_para_menu()`, que delega a `limpar_tela()`. Falhas de limpeza não devem impedir a operação.

### Opções e arquivos de exportação

Há **quatro opções de formato** e **cinco arquivos CSV possíveis** em uma execução: um arquivo para cada opção, exceto Trakt, que gera dois arquivos separados. O contrato de Letterboxd também possui dois cabeçalhos condicionais, pois a origem escolhida determina a coluna de nota.

| Opção | Arquivo | Contrato e origem |
|---|---|---|
| Analítica | `exportacao_analitica_<user>_<timestamp>.csv` | `imdbID`, `tmdbID`, `tmdbTitle`, `tmdbYear`, `tmdbCountry`, `tmdbDirectors`, `filmowTitle`, `filmowYear`, `filmowRating`, `Rating10`; nota pessoal do Filmow + nota pública do IMDb |
| Sintética | `exportacao_sintetica_<user>_<timestamp>.csv` | `imdbID`, `tmdbID`; sem notas |
| Letterboxd Essencial | `exportacao_letterboxd_<user>_<timestamp>.csv` | Filmow → `imdbID`, `tmdbID`, `Rating`; IMDb → `imdbID`, `tmdbID`, `Rating10` |
| Trakt | `exportacao_history_trakt_<user>_<timestamp>.csv` | `imdb_id`, `tmdb_id`, `type`; sem nota |
| Trakt | `exportacao_ratings_trakt_<user>_<timestamp>.csv` | `imdb_id`, `tmdb_id`, `type`, `rating`; Filmow ×2 ou IMDb original |

Regras dos contratos:

- `type` é sempre `movie`; a resolução permanece restrita a filmes.
- `Rating` e `filmowRating` representam a nota pessoal do Filmow na escala original 0–5. `Rating10` e `rating` na origem IMDb representam a nota pública original na escala 0–10.
- Em Letterboxd não há conversão: Filmow usa `Rating` e IMDb usa `Rating10`, sempre com o valor válido original.
- Em Trakt Ratings, a origem Filmow é a única conversão contratada: uma nota válida em meia estrela, de 0 a 5, é multiplicada por 2 e gravada na escala 0–10. A origem IMDb preserva o valor público original. Valores ausentes, não numéricos, fora da escala ou fora da grade de meias estrelas são inválidos para o exportador.
- History não contém nota. History e Ratings contêm as linhas resolvidas selecionadas para a execução, inclusive linhas cuja nota de Ratings seja vazia; Ratings não é um subconjunto que exclua ausência ou invalidez.
- Ausência ou invalidez de nota é gravada como **campo vazio**, nunca como zero, `None`, `null` ou texto substituto. Zero é preservado quando for uma nota válida.
- Os IDs e demais campos válidos são gravados sem conversão. A afirmação “valores originais” não exclui a conversão Filmow ×2 explicitamente contratada para Trakt Ratings.
- `csv.DictWriter` com `extrasaction="ignore"` impede que campos internos, como `idOrigin`, vazem para os CSV.
- A publicação dos CSV é atômica: cada arquivo temporário é finalizado e substituído somente quando está completo.

### Dataset do IMDb sob demanda

- `title.ratings.tsv.gz` só é baixado, quando ausente, e indexado quando o contrato selecionado precisa da nota pública do IMDb.
- Analítica sempre precisa do IMDb. Sintética, Letterboxd com origem Filmow e Trakt com origem Filmow não dependem dele; Letterboxd ou Trakt com origem IMDb dependem.
- O download é condicional à existência do arquivo local. O índice permanece em memória e pode ser reutilizado quando o usuário alterna entre formatos compatíveis durante a mesma execução; não é persistido entre execuções.
- Falha ao obter a base é erro explícito e recuperável, sem publicar arquivo parcial.

### Separação entre identidade, nota e exportação

- **Identidade:** resolve o filme (Filmow → TMDb), aplica limiares e fallback; não conhece formatos de saída.
- **Nota:** conhece a origem e a escala de cada avaliação e valida o valor apenas para o contrato de destino; não escolhe o formato.
- **Exportação:** transforma linhas já resolvidas em registros e escreve CSV e relatório; não consulta rede nem redecide identidade.

Regras:

- Nenhuma responsabilidade deve reimplementar a decisão de outra.
- O dicionário intermediário pode manter aliases, isto é, nomes alternativos dos campos (`imdbID`/`imdb_id`, `tmdbID`/`tmdb_id`, `Rating`/`rating`) para atender exportadores distintos, mas cada alias deve ter significado consistente no contexto.
- Mudança em uma área exige validar as outras duas por passagem de contrato.
- Trakt é o ponto em que a camada de nota/exportação aplica a conversão contratada; “sem conversão” só vale para Letterboxd e para a origem IMDb em Trakt.

## Padrões existentes

- Funções procedurais com docstrings que descrevem função, motivo e restrições.
- Constantes de configuração no topo de `filmow_to_letterboxd_essentials.py`.
- Integração HTTP com tempo de espera, retentativas e tratamento específico para HTTP 429 e falhas do WAF.
- Logs de progresso e telemetria via `rich.console.Console`.
- Arquivos CSV gerados na pasta atual, com timestamp `YYYYMMDD_HHMMSS`.
- Thread pool executado por página, com resultados consumidos por `as_completed()`.
- Menus e painéis construídos com `rich.console.Console` e `Panel`, entrada via `input()` e mensagens em português.
- Relatório derivado das métricas da execução e das linhas já exportadas, sem recomputar decisões.

## Dependências

- `cloudscraper>=1.2.71`: criação de sessão para o Filmow.
- `requests>=2.31.0`: dataset do IMDb e API do TMDb.
- `beautifulsoup4>=4.12.0`: análise do HTML do Filmow.
- `rich>=13.7.0`: menus, painéis, mensagens e telemetria.

Não atualizar versões ou adicionar dependências sem necessidade explícita.

## Regras obrigatórias

- Alterar apenas arquivos necessários; não refatorar código, README ou testes sem solicitação.
- Preservar as quatro opções, os cinco arquivos possíveis, a ordem e a ordem das colunas dos CSV.
- Preservar o fluxo formato → origem condicional → confirmação, a ajuda `H`, a saída `0` e a limpeza entre telas.
- Manter Analítica com Filmow + IMDb, Sintética somente com IDs, Letterboxd com o contrato condicional correto e Trakt com History sem nota e Ratings conforme a origem escolhida.
- Tratar ausência ou invalidez de nota como campo vazio e preservar zero válido.
- Não alegar “sem conversão” de forma absoluta: Trakt Ratings com origem Filmow aplica multiplicação por 2.
- Obter o dataset do IMDb apenas quando o contrato selecionado depender dele.
- Não misturar identidade, notas e exportação; validar as áreas conectadas por passagem de contrato.
- Preservar a resolução restrita a filmes e os limiares atuais: JSON-LD validado com score `>= 40` e fallback com score `>= 100`, salvo pedido explícito.
- Preservar `MAX_WORKERS = 5`; outro valor exige benchmark comparativo e aprovação explícita.
- Não reutilizar ID do fallback ou da busca do TMDb sem a auditoria de `calculate_confidence()`.
- Manter extração compatível com os seletores HTML e o JSON-LD atualmente consumidos.
- Preservar timeouts, intervalos, número de tentativas e limites de busca, salvo pedido explícito.
- Não introduzir frameworks, bancos, camadas, ferramentas ou suítes adicionais sem solicitação ou evidência.
- Não criar pastas ou arquivos de infraestrutura artificialmente.

## Segurança

- Nunca reproduzir o conteúdo de `tmdb_api.txt` em código, documentação, logs, commits ou respostas.
- Preservar `tmdb_api.txt`, `*.csv`, `*.tsv.gz` e `relatorio_filmow_*.txt` sob as regras atuais do `.gitignore`.
- Não registrar a API key em mensagens de erro, URLs, saída do console ou artefatos.
- Preservar o armazenamento local da credencial em `carregar_credencial()` e seu prompt interativo, salvo pedido explícito.
- Não incorporar nomes de usuário reais, IDs de sessão ou outros identificadores pessoais em documentação pública.

## Testes e validação

- A suíte atual usa `unittest` e está em `tests/`, incluindo confiança e módulo puro, cliente TMDb, integrações, resiliência, performance, exportação e fluxo da CLI.
- Comando da suíte: `py -m unittest discover -s tests -v`.
- Compilação sintática: `py -m py_compile filmow_to_letterboxd_essentials.py identity_matching.py tmdb_client.py`.
- Lint, type checking, formatação automatizada, cobertura e infraestrutura de benchmark não estão identificados; não inventar resultados.
- Ao alterar parsing, validar estruturas representativas e os campos título, ano, diretores, nota e link.
- Ao alterar identidade, validar título exato, alternativo, diferença de ano, divergência de direção, ID incorreto, fallback e ausência de nota.
- Ao alterar exportação, validar cabeçalho, ordem, aliases internos, origem de cada nota, conversão Trakt, zero válido, ausência vazia, UTF-8, timestamp, escrita atômica e arquivos Trakt separados.
- Ao alterar rede, validar tempo limite, retentativas, 429, falhas temporárias e `MAX_WORKERS`.
- Ao alterar a CLI, validar `H`/`0`, ordem formato → origem condicional → confirmação, omissão de pergunta, entrada inválida, cancelamento, limpeza de tela e ausência de coleta antes da confirmação.

## Comandos

Instalação:

```text
py -m pip install -r requirements.txt
```

Execução:

```text
python filmow_to_letterboxd_essentials.py
py filmow_to_letterboxd_essentials.py
```

A execução pode acessar a rede, solicitar a credencial do TMDb e o usuário do Filmow, percorrer as três etapas, obter o IMDb sob demanda quando necessário e gravar artefatos locais. A suíte disponível é executada com `py -m unittest discover -s tests -v`.

## Limitações

- Versão mínima ou suportada de Python: Python 3.10 ou mais recente, declarada no `pyproject.toml`.
- Banco de dados e migrações: não identificados.
- Ambiente de teste automatizado e CI: `unittest` e `.github/workflows/tests.yml`; lint e type checking não estão configurados.
- Não presumir serviços, variáveis de ambiente, endpoints ou comandos que não estejam no projeto.

## Critérios de conclusão

- A tarefa foi atendida sem alterações fora dos arquivos documentais autorizados.
- Contratos, notas, escalas, ausência vazia e arquivos Trakt permanecem coerentes.
- O fluxo formato → origem condicional → confirmação, `H`/`0` e a limpeza de tela estão íntegros.
- O IMDb só é obtido quando o contrato precisa dele.
- `MAX_WORKERS = 5`, limiares, retentativas e tempos-limite continuam coerentes com a intenção da mudança.
- A documentação cita apenas testes, ferramentas e resultados efetivamente presentes ou verificados.
- Nenhuma credencial, nome de usuário real, ID de sessão ou outro identificador pessoal foi incorporado.
