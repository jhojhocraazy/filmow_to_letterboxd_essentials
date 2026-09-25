# Agente de UX e Fluxo de Interação

## Responsabilidade

Preservar a operação interativa na ordem **formato → origem condicional → confirmação** e apresentar mensagens claras, sem executar ações exportadoras antes da aprovação.

## Escopo

- `filmow_to_letterboxd_essentials.py`: `exibir_menu_e_obter_selecao()`, `exibir_documentacao()`, `obter_origem_nota()`, `confirmar_configuracao_exportacao()`, `main()`, `limpar_tela()` e `limpar_para_menu()`.
- Contratos apresentados: Analítica, Sintética, Letterboxd Essencial e Trakt.
- `README.md` somente quando a tarefa exigir alterar a documentação da operação.

## Contexto

A CLI opera em laço. O menu principal oferece quatro formatos, ajuda `H` e saída `0`. A origem só aparece quando a escolha altera a nota exportada. Depois da escolha aplicável e do usuário público, a CLI mostra um resumo e exige confirmação.

A criação inicial da sessão e o carregamento seguro da credencial TMDb são preparação local. A confirmação, porém, antecede o download/indexação do IMDb, a leitura do histórico e a publicação de CSV.

## Fluxo público

| Entrada | Formato | Origem | Próxima etapa |
|---|---|---|---|
| `1` | Analítica | ambas: Filmow + IMDb | usuário e confirmação |
| `2` | Sintética | nenhuma | usuário e confirmação |
| `3` | Letterboxd | escolha explícita: Filmow ou IMDb | usuário e confirmação |
| `4` | Trakt | escolha explícita: Filmow ou IMDb | usuário e confirmação |
| `H` | ajuda | não se aplica | documentação e retorno ao menu |
| `0` | sair | não se aplica | encerramento |

Na etapa de origem, `0` volta ao menu. Na confirmação, `1` inicia, `2` volta ao menu e `0` cancela a execução.

## Regras

- Manter a ordem formato → origem condicional → confirmação.
- Omitir a pergunta de origem para Analítica e Sintética; não exibir uma pergunta neutra.
- Não baixar ou indexar o IMDb, varrer o histórico ou gravar CSV antes da confirmação explícita.
- Voltar ou cancelar antes de iniciar não deve produzir arquivo nem coleta de dados.
- Entrada inválida mantém o usuário na etapa atual, com mensagem curta em português.
- Preservar `H` em qualquer caixa e `0` para sair; a numeração exibida deve corresponder ao mapeamento interno.
- Usar `limpar_para_menu()` nas transições de tela; ela delega a `limpar_tela()` e não deve fazer a operação falhar se o shell não aceitar o comando.
- Não exibir credenciais, nomes de usuário reais, IDs de sessão ou outros identificadores pessoais em menu, painel, confirmação, relatório ou erro.
- Não acoplar a origem ao agente de confiança: origem da nota não decide qual filme é o mesmo.
- Não alterar nomes, cabeçalhos ou significado das notas apenas na apresentação.

## Resumo de confirmação

A confirmação deve informar:

- usuário público informado;
- formato;
- origem efetiva: ambas, nenhuma, Filmow ou IMDb;
- colunas do contrato;
- conversão aplicável, inclusive Filmow ×2 em Trakt;
- arquivos esperados, lembrando que Trakt gera History e Ratings.

## Padrões existentes

- Menus, painéis e relatórios usam `rich.console.Console` e `Panel`.
- Entrada do usuário usa `input()`.
- Limpeza de tela usa `limpar_tela()` por meio de `limpar_para_menu()`.
- Mensagens e documentação rápida são em português.

## Dependências

- `rich` e `input()`. Não introduzir dependência nova apenas para apresentação.

## Testes

Validar offline, sem rede:

- `1` a `4` retornam os formatos esperados e `H` abre a ajuda;
- `0` encerra pelo menu e as ações de confirmação têm o significado indicado;
- origem é perguntada somente em Letterboxd e Trakt e aceita Filmow/IMDb;
- entradas inválidas não encerram a CLI;
- confirmação resume formato, origem, colunas e conversão;
- voltar ou cancelar não coleta nem grava;
- `limpar_para_menu()` chama a limpeza de tela;
- nenhuma credencial ou informação sensível é renderizada.

## Comandos

```text
py -m unittest tests.test_cli_export_flow -v
py -m unittest discover -s tests -v
python filmow_to_letterboxd_essentials.py
```

## Critérios de conclusão

- Formato → origem condicional → confirmação está íntegro.
- `H`, `0` e as transições de tela permanecem claros.
- Nenhuma pergunta irrelevante ou ação exportadora prematura aparece.
- Nenhum segredo ou identificador pessoal é exibido.
