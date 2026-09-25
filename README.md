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

## Instalação no Windows

### 1. Escolha uma pasta para o projeto

Abra o PowerShell e escolha uma pasta dedicada para guardar o projeto. O caminho pode ser qualquer um disponível na sua máquina.

Este exemplo cria uma pasta dentro da sua pasta de usuário:

```powershell
$Projeto = "$HOME\MeusProjetos\filmow_to_letterboxd_essentials"
New-Item -ItemType Directory -Path $Projeto
Set-Location $Projeto
```

Se você já possui uma pasta de projetos, pode usá-la. Evite escolher uma pasta que contenha arquivos importantes ou outro projeto.

### 2. Obtenha o projeto

Com o PowerShell dentro da pasta escolhida, clone o repositório:

```powershell
git clone https://github.com/jhojhocraazy/filmow_to_letterboxd_essentials.git .
```

O ponto final `.` instala o projeto diretamente na pasta escolhida.

Confirme que os arquivos foram copiados:

```powershell
Test-Path requirements.txt
Test-Path filmow_to_letterboxd_essentials.py
```

Os dois comandos devem retornar `True`. Se retornarem `False`, verifique se o PowerShell está na pasta correta.

### 3. Crie o ambiente virtual

O ambiente virtual é uma pasta isolada chamada `.venv` que guarda as bibliotecas usadas pelo projeto. Ele deve ser criado dentro da pasta do projeto:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

O prompt normalmente passa a mostrar `(.venv)`. Se a ativação for bloqueada pelo PowerShell, não é necessário alterar a política do sistema: use o Python do ambiente diretamente.

### 4. Instale as dependências

Se a ativação funcionou:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Se a ativação não funcionou, use:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 5. Confirme a instalação

Execute da pasta do projeto:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

O primeiro comando não deve relatar dependências quebradas. O segundo deve terminar com `OK`.

## Se a pasta ainda não tiver o projeto

Este é um caso de recuperação, não uma etapa normal da instalação. Se `Test-Path requirements.txt` retornar `False`, escolha uma nova pasta e execute novamente:

```powershell
$Projeto = "$HOME\MeusProjetos\filmow_to_letterboxd_essentials-novo"
New-Item -ItemType Directory -Path $Projeto
Set-Location $Projeto
git clone https://github.com/jhojhocraazy/filmow_to_letterboxd_essentials.git .
```

Não remova pastas automaticamente. Se a pasta já contiver um ambiente virtual, dados ou outro projeto, escolha outro destino ou faça uma revisão manual antes de qualquer comando destrutivo.

## Como executar

Depois da instalação, execute com o ambiente virtual ativo:

```powershell
python filmow_to_letterboxd_essentials.py
```

Se a ativação não estiver disponível:

```powershell
.\.venv\Scripts\python.exe filmow_to_letterboxd_essentials.py
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
