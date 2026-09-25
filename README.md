# Filmow to Letterboxd & Trakt Essentials

Ferramenta de linha de comando para transformar um histórico público do Filmow em arquivos CSV compatíveis com Letterboxd e Trakt.

O programa consulta o histórico público, compara cada filme com o TMDb, preserva apenas identidades cinematográficas suficientemente seguras e oferece diferentes formatos de exportação.

## O que você pode exportar

| Opção | O que contém | Origem das notas |
|---|---|---|
| Analítica | IDs, metadados e notas para auditoria | Filmow e IMDb |
| Sintética | Apenas IDs IMDb e TMDb | Nenhuma |
| Letterboxd + Filmow | IDs e `Rating` | Nota pessoal do Filmow |
| Letterboxd + IMDb | IDs e `Rating10` | Nota pública do IMDb |
| Trakt History | IDs e `type=movie` | Sem notas |
| Trakt Ratings | IDs, tipo e `rating` | Filmow convertido para 0–10 ou IMDb original |

O relatório analítico é o formato indicado para conferir se os títulos, anos, diretores e IDs foram identificados corretamente.

## Requisitos

- Python 3.10 ou mais recente;
- acesso à internet;
- uma chave da API TMDb v3;
- um perfil público do Filmow.

A chave é solicitada na primeira execução e salva localmente em `tmdb_api.txt`. Esse arquivo é ignorado pelo Git e nunca deve ser enviado para o repositório.

## Instalação

### 1. Obter o projeto

O comando abaixo clona o código dentro da pasta atual. O ponto final (`.`) é importante: ele evita criar uma subpasta com outro nome.

```powershell
cd C:\\Users\\Administrator\\Downloads\\Teste
git clone https://github.com/jhojhocraazy/filmow_to_letterboxd_essentials.git .
```

Confirme que os arquivos necessários estão presentes:

```powershell
Test-Path requirements.txt
Test-Path filmow_to_letterboxd_essentials.py
```

Os dois comandos devem retornar `True`. Se você criou o ambiente virtual antes de clonar o projeto, remova apenas o `.venv`, clone o repositório e crie o ambiente novamente:

```powershell
deactivate
Remove-Item -Recurse -Force .venv
git clone https://github.com/jhojhocraazy/filmow_to_letterboxd_essentials.git .
```

### 2. Criar o ambiente virtual

O ambiente virtual fica dentro da pasta do projeto, mas não contém o código-fonte. Por isso, `requirements.txt` e `filmow_to_letterboxd_essentials.py` devem existir antes de executar a instalação.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

O prompt deve mostrar `(.venv)`. Se a ativação for bloqueada pelo PowerShell, execute o Python diretamente pelo ambiente:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Se a ativação funcionar, os comandos equivalentes são:

```powershell
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
```

### 3. Validar a instalação

```powershell
py -m unittest discover -s tests -v
py -m pip check
```

## Como executar

Depois da instalação, execute com o ambiente virtual ativo:

```powershell
py filmow_to_letterboxd_essentials.py
```

O menu usa esta ordem:

1. escolha o formato;
2. escolha a origem das notas, quando ela for necessária;
3. informe o usuário público do Filmow;
4. confirme a operação;
5. aguarde o processamento e a geração dos arquivos.

Para sair, escolha `0`. A ajuda não inicia uma exportação e pode ser aberta com `H`.

## Escolha das notas

- **Filmow:** nota pessoal, normalmente de 0 a 5.
- **IMDb:** nota pública, normalmente de 0 a 10.
- A escolha é única para a execução atual.
- Nota ausente ou inválida fica vazia; ela não é transformada em zero.
- O zero é uma nota válida e é preservado.
- No Trakt com origem Filmow, a nota é convertida de 0–5 para 0–10 multiplicando por 2.
- No Trakt com origem IMDb, a nota é mantida na escala original.

O relatório analítico sempre mantém `filmowRating` e `Rating10` separados, sem escolha do usuário.

## Arquivos gerados

Os arquivos são gravados na pasta de trabalho atual.

- `exportacao_analitica_<usuario>_<timestamp>.csv`
- `exportacao_sintetica_<usuario>_<timestamp>.csv`
- `exportacao_letterboxd_<usuario>_<timestamp>.csv`
- `exportacao_history_trakt_<usuario>_<timestamp>.csv`
- `exportacao_ratings_trakt_<usuario>_<timestamp>.csv`
- `relatorio_filmow_<timestamp>.txt`

O relatório mostra o formato escolhido, a origem das notas, métricas de resolução, falhas, campos sem nota e arquivos produzidos.

## Como funciona, em linguagem simples

1. O programa lê as páginas públicas do histórico.
2. Para cada item, procura um ID do IMDb e consulta o TMDb.
3. O programa compara título, ano e direção.
4. Se o ID encontrado não for confiável, procura uma alternativa no TMDb restrita a filmes.
5. Só são exportados filmes que passam pela verificação de confiança.
6. A nota escolhida é aplicada somente na etapa final de exportação.

A escolha da nota não altera a identidade do filme.

## Segurança e privacidade

- `tmdb_api.txt` é local e ignorado pelo Git.
- CSVs, relatórios, datasets e arquivos temporários são ignorados pelo Git.
- Não coloque API keys, exports ou relatórios em issues públicas.
- O dataset público do IMDb é baixado apenas quando o formato precisa da nota pública.
- O índice do IMDb é mantido em memória durante a execução.

Leia também `SECURITY.md`.

## Testes e desenvolvimento

A suíte é offline e usa `unittest`:

```powershell
py -m unittest discover -s tests -v
```

Compilação dos módulos principais:

```powershell
py -m py_compile filmow_to_letterboxd_essentials.py identity_matching.py tmdb_client.py
```

Veja `CONTRIBUTING.md` para o processo de alteração e `CHANGELOG.md` para o histórico da versão.

## Limitações

- O acesso depende da disponibilidade e do HTML público do Filmow, TMDb e IMDb.
- Mudanças no layout do Filmow podem exigir atualização do parser.
- O dataset IMDb ocupa memória durante a execução.
- O programa processa o histórico selecionado; a primeira página não é um modo separado da CLI.
- A correspondência nunca deve ser interpretada como uma prova absoluta; por isso o programa registra falhas e omissões.

## Documentação adicional

- `docs/usage.md`: passo a passo para usuários;
- `docs/export-contracts.md`: colunas e regras dos CSV;
- `docs/architecture.md`: organização interna;
- `docs/troubleshooting.md`: solução de problemas;
- `agents/`: instruções de manutenção e responsabilidades das áreas do projeto.
