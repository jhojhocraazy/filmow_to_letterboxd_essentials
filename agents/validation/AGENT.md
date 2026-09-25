# Agente de Validação e Testes

## Responsabilidade

Planejar e aplicar validações reproduzíveis para parsing, identidade, integrações, resiliência, performance, exportação e UX.

## Escopo

- Suíte existente em `tests/`.
- Testes ou scripts novos somente quando solicitados ou necessários para uma mudança aprovada.
- `README.md` somente para documentar um comando novo realmente adicionado.

## Contexto

A suíte atual usa `unittest` e é executada no CI definido em `.github/workflows/tests.yml`. Os arquivos existentes cobrem confiança, `identity_matching.py`, cliente TMDb, integrações, resiliência, performance, exportação e fluxo da CLI. Lint, type checking e cobertura percentual não estão configurados.

Testes de rede devem simular respostas ou isolar integrações. Validação com dados reais depende de credencial TMDb, usuário do Filmow e disponibilidade dos serviços; ela não é a validação padrão da suíte.

## Regras

- Não declarar cobertura além dos arquivos e cenários efetivamente verificados.
- Não afirmar contagem de testes ou resultado histórico sem executar a suíte correspondente.
- Não inventar benchmark, lint, cobertura ou ferramenta inexistente.
- Preferir respostas simuladas e dados locais para validar lógica sem chamadas reais.
- Não acessar rede, ler credenciais ou usar nomes de usuário reais na validação offline.
- Validar sucesso, rejeição, falha de rede, nota ausente/inválida, zero válido e compatibilidade de CSV.
- Não adicionar dependência de teste sem solicitação explícita ou necessidade aprovada.
- Ao alterar parsing, testar campos título, ano, diretores, nota e link.
- Ao alterar identidade, testar título exato, alternativo, diferença de ano, divergência de direção, ID incorreto e fallback.
- Ao alterar exportação, testar todos os cabeçalhos, ordem, origem, escala, conversão Trakt, ausência vazia, zero, timestamp, aliases internos e arquivos separados.
- Ao alterar CLI, testar `H`/`0`, ordem formato → origem condicional → confirmação, entrada inválida, cancelamento e limpeza de tela.

## Testes atuais

Arquivos presentes em `tests/`:

- `test_confidence.py`;
- `test_identity_matching.py`;
- `test_tmdb_client.py`;
- `test_integrations.py`;
- `test_resilience.py`;
- `test_performance.py`;
- `test_export.py`;
- `test_cli_export_flow.py`.

A presença de um arquivo não deve ser convertida em uma afirmação de que todos os cenários passaram; execute a suíte antes de relatar resultado.

## Comandos

```text
py -m unittest discover -s tests -v
py -m py_compile filmow_to_letterboxd_essentials.py identity_matching.py tmdb_client.py
```

## Critérios de conclusão

- Existe cenário reproduzível para a mudança.
- Suíte relevante e compilação foram executadas quando exigidas, ou a limitação foi declarada claramente.
- Falhas conhecidas são diferenciadas de regressões.
- A documentação afirma apenas o que foi verificado e não contém identificadores pessoais.
