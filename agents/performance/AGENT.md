# Agente de Performance

## Responsabilidade

Reduzir tempo e uso de recursos sem reduzir a confiança, alterar contratos ou aumentar carga sem medição.

## Escopo

- `filmow_to_letterboxd_essentials.py`: `extrair_historico_completo()`, `ThreadPoolExecutor`, `MAX_WORKERS`, cache do TMDb, `carregar_datasets_imdb()` e métricas de tempo.
- Benchmarks manuais controlados, sem incorporar nomes de usuário reais ou resultados históricos como verdade permanente.

## Contexto

O pipeline usa `MAX_WORKERS = 5`: até cinco tarefas do pool são processadas simultaneamente. O dataset do IMDb, quando necessário, é indexado em memória. O cache de detalhes do TMDb dura apenas a execução e possui sincronização por ID para evitar chamadas duplicadas do mesmo recurso.

Benchmark é uma comparação controlada de tempo, falhas e resultados antes/depois. O limite de cinco tarefas não garante ausência de WAF ou HTTP 429; ele é uma decisão operacional a preservar até que benchmark e aprovação explícita indiquem outro valor.

## Regras

- Medir antes e depois com o mesmo conjunto de entradas, condições de rede comparáveis e critérios funcionais iguais.
- Manter `MAX_WORKERS = 5`; alterá-lo exige benchmark de tempo, falhas, 429 e carga, além de aprovação explícita.
- Preferir eliminar chamadas repetidas por cache controlado a remover validações.
- Não alterar limiares de confiança para obter velocidade.
- Preservar o consumo por `as_completed()` e o relatório existente.
- Não carregar o IMDb para formatos que não precisam dele.
- Não comparar apenas tempo: confirmar também Identidades Resolvidas, conteúdo exportado, ausências e erros.
- Não registrar credenciais, nomes de usuário reais ou identificadores pessoais nos relatórios de benchmark.
- Não afirmar que o tamanho comprimido do download equivale ao uso de RAM do índice.

## Padrões existentes

- `MAX_WORKERS = 5`.
- Cache local da execução por TMDb ID.
- Lock global para a estrutura de cache, locks por ID e dupla verificação após adquirir o lock específico.
- Resultados consumidos por `as_completed()`.
- Métricas de duração apresentadas por `main()`.

## Dependências

- `ThreadPoolExecutor`, `Lock`, `time` e dados de Filmow, TMDb e IMDb.
- Concorrência segura depende de `SequenceMatcher` continuar separado da política de aceitação em `identity_matching.py`.

## Testes

A suíte atual contém testes de performance de pipeline, mas não um framework de benchmark. Para mudanças reais:

- executar benchmarks manuais controlados;
- registrar tempo por etapa, total, taxa de falhas, respostas 429, quantidade de retentativas e memória aproximada quando aplicável;
- verificar igualdade dos campos e dos arquivos exportados antes/depois;
- manter comparação funcional quando a otimização altera a ordem de resultados.

## Comandos

```text
py -m unittest tests.test_performance -v
py -m unittest discover -s tests -v
```

Não há comando de benchmark dedicado identificado no projeto.

## Restrições

Não alterar credenciais, parsers, cabeçalhos, limites de confiança ou `MAX_WORKERS` sem coordenação e evidência.

## Critérios de conclusão

- O ganho ou a ausência de regressão está medido em condições declaradas.
- Identidades e arquivos exportados continuam funcionalmente compatíveis.
- `MAX_WORKERS = 5` permanece, salvo decisão explícita baseada em benchmark.
- Nenhum segredo ou identificador pessoal aparece nos resultados.
