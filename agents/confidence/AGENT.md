# Agente de Confiança e Qualidade

## Responsabilidade

Garantir que cada obra exportada corresponda ao filme correto e reduzir falsos positivos.

## Escopo

- `identity_matching.py`: `normalize_text()`, `similarity()` e `calculate_confidence()`.
- `filmow_to_letterboxd_essentials.py`: `processar_filme()` e `resolve_tmdb_by_search()`.
- Aceitar, rejeitar ou encaminhar um candidato ao fallback.

## Contexto

A normalização, a similaridade e a pontuação estão isoladas no módulo puro `identity_matching.py`. O pipeline trata o ID de JSON-LD como pista, mas só o aceita após comparar título, ano e diretores. O fallback, isto é, a busca alternativa quando o ID direto é rejeitado, usa `/search/movie`, e o resultado também passa por `calculate_confidence()` antes de ser aceito.

## Regras

- Não aceitar ID apenas porque apareceu no HTML ou no JSON-LD.
- Preservar a auditoria de título, ano e diretor antes de confirmar candidato.
- Preservar os limiares atuais: JSON-LD validado com score `>= 40` e fallback com score `>= 100`, salvo pedido explícito.
- Registrar ou controlar origem e pontuação sem incluir credenciais ou identificadores pessoais.
- Tratar empates e divergências como falhas de transformação e encaminhá-los ao fallback, não como confirmação automática.
- Não aceitar séries, programas de TV ou outros tipos que não sejam filmes.
- Não remover validações para melhorar velocidade; otimizações devem preservar resultados e falsos positivos conhecidos.
- Não decidir nomes de arquivos, prioridades de concorrência ou política de exportação.

## Padrões existentes

- `SequenceMatcher` participa da similaridade.
- A busca do TMDb usa `/search/movie`; detalhes usam a API `/movie`.
- O dicionário final contém aliases de IDs para exportadores diferentes.
- A origem interna do ID não é campo público dos CSV.

## Dependências

- Dados extraídos do Filmow.
- Metadados retornados pelo TMDb.
- `identity_matching.py`, quando a extração ou os testes forem alterados.

## Testes

Validar título exato, título alternativo, diferença de ano, divergência de direção, ID incorreto, fallback, limiares e rejeição de tipos que não sejam filmes.

## Comandos

```text
py -m unittest tests.test_confidence -v
py -m unittest tests.test_identity_matching -v
py -m unittest discover -s tests -v
```

## Critérios de conclusão

- Nenhum resultado fraco é apresentado como resolvido.
- ID direto e fallback continuam submetidos à auditoria.
- A origem da decisão continua distinguível apenas em dados internos e relatórios.
- A exportação permanece restrita a filmes.
