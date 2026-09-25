# Como contribuir

Agradecemos contribuições responsible e reproduzíveis. Este projeto é escrito em Python e usa a biblioteca padrão `unittest`.

## Antes de começar

1. Faça uma issue ou discuta a alteração proposta, especialmente quando ela mudar um cabeçalho CSV ou uma regra dematching.
2. Crie um branch descritivo a partir da branch principal.
3. Não inclua chaves de API, cookies, dados pessoais, arquivos de sessão, exportações reais ou relatórios gerados.

## Ambiente local

Requer Python 3.10 ou mais recente.

```bash
python -m venv .venv
```

Ative o ambiente e instale as dependências:

```bash
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell
.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Para instalar o projeto e o comando de console em um ambiente virtual:

```bash
python -m pip install .
```

## Antes de enviar alterações

Execute a validação completa:

```bash
python -m pip check
python -m unittest discover -s tests -v
python -m py_compile filmow_to_letterboxd_essentials.py identity_matching.py tmdb_client.py tests/*.py
```

Em Windows, se o último comando não expandir `tests/*.py`, use a forma explícita do Python 3.10+:

```bash
python -c "import pathlib, py_compile; [py_compile.compile(str(p), doraise=True) for p in pathlib.Path('tests').glob('*.py')]"
```

Os testes são offline: mantenha as chamadas externas simuladas e não execute a CLI durante a validação automatizada.

## Padrões de contribuição

- Mantha alterações pequenas, focadas e compatíveis com Python 3.10+.
- Siga o estilo existente: quatro espaços, linhas curtas quando possível e nomes descritivos.
- Não adicione dependências sem explicar necessidade, impacto e atualização de `requirements.txt` e `pyproject.toml`.
- Documente novos campos e modification de CSV em `docs/export-contracts.md`.
- Adicione testes `unittest` para regressões e casos de falha.
- Preserve escrita atômica, validação de notas, ordem determinística e a não exposição de credenciais.
- Atualize `CHANGELOG.md` quando a mudança for relevante para usuários.

## Commits e pull requests

Use mensagens curtas no imperativo e explique no pull request:

- o problema resolvido;
- a abordagem adotada;
- riscos e limitações;
- comandos de validação executados;
- mudanças de documentação ou contrato.

Não abra um pull request se a suíte offline falhar. Problemas de segurança não devem ser detalhados em issue pública; siga `SECURITY.md`.
