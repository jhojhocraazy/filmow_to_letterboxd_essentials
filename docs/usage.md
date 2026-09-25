# Uso

## O que a ferramenta faz

A aplicação executa uma ETL local. Ela lê o histórico **público** de filmes de um perfil do Filmow, tenta resolver a identidade de cada obra com evidências do TMDb, opcionalmente consulta notas públicas do IMDb e gera CSV para análise ou importação.

A ferramenta não importa diretamente em Letterboxd ou Trakt. A importação dos arquivos gerados é uma etapa manual e deve ser conferida.

## Requisitos

- Python 3.10, 3.11, 3.12 ou 3.13;
- acesso à internet na execução real;
- uma chave de API da TMDb, fornecida somente na máquina do usuário;
- um perfil Filmow com histórico público.

Dependências atuais:

| Pacote | Versão mínima |
| --- | --- |
| `cloudscraper` | 1.2.71 |
| `requests` | 2.31.0 |
| `beautifulsoup4` | 4.12.0 |
| `rich` | 13.7.0 |

Essas versões mínimas são as declaradas em `requirements.txt` e `pyproject.toml`. O fluxo usa apenas a biblioteca padrão `unittest` para testes.

## Instalação

No diretório do projeto, crie um ambiente virtual:

```bash
python -m venv .venv
```

Ative-o:

```bash
# Linux/macOS
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Instale as dependências atuais:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Opcionalmente, instale também o comando de console do projeto:

```bash
python -m pip install .
```

## Primeira execução

Execute:

```bash
python filmow_to_letterboxd_essentials.py
```

Ou, após `python -m pip install .`:

```bash
filmow-to-letterboxd-essentials
```

Na primeira execução, a aplicação solicita uma chave de API da TMDb. A chave pode ser salva em `tmdb_api.txt` para reutilização. Mantenha esse arquivo fora do versionamento; se o repositório ainda não o ignora, não o adicione e configure sua instância local corretamente.

Depois:

1. escolha um formato no menu;
2. para Letterboxd ou Trakt, escolha a origem das notas;
3. informe o **nome do perfil público** do Filmow quando solicitado;
4. confira o resumo e as colunas;
5. confirme para iniciar a coleta;
6. aguarde a extração e verifique o relatório antes de importar os CSV.

O tempo depende do tamanho do histórico, das respostas dos serviços, dos rate limits e da carga de rede. A concorrência interna é limitada para reduzir pressão sobre o Filmow.

## Escolhas de exportação

- **Analítica:** IDs, metadados do TMDb/Filmow e notas das duas origens.
- **Sintética:** somente IDs IMDb e TMDb.
- **Letterboxd com Filmow:** mantém a escala original de 0 a 5 na coluna `Rating`.
- **Letterboxd com IMDb:** mantém a escala pública de 0 a 10 na coluna `Rating10`.
- **Trakt com Filmow:** gera History e Ratings; multiplica notas de meia estrela por 2 para a escala 0–10.
- **Trakt com IMDb:** gera History e Ratings mantendo a nota pública de 0 a 10.

Os cabeçalhos exatos e as regras de validação estão em [contratos de exportação](export-contracts.md).

## Testes locais

A suíte foi projetada para ser offline e não deve acessar Filmow, TMDb ou IMDb:

```bash
python -m pip check
python -m unittest discover -s tests -v
python -m py_compile filmow_to_letterboxd_essentials.py identity_matching.py tmdb_client.py tests/*.py
```

Não execute a CLI nem forneça uma chave real aoRodar testes.

## Boas práticas

- confira uma amostra de títulos, IDs e notas antes de importar;
- preserve os CSV e o relatório fora do repositório público;
- não envie chave, dados pessoais ou artefatos de uma execução real em issue ou pull request;
- compare o resultado com a página de origem quando uma identidade parecer errada;
- consulte as [limitações](troubleshooting.md#limitações-conhecidas) antes de tratar o resultado como definitivo.
