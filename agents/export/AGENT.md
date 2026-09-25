# Agente de Exportação e Compatibilidade

## Responsabilidade

Preservar os CSV consumidos por Letterboxd e Trakt, suas origens de nota e a coerência entre o fluxo da CLI e os arquivos publicados.

## Escopo

- `filmow_to_letterboxd_essentials.py`: constantes de colunas, `modo_precisa_imdb()`, `colunas_exportacao()`, `preparar_linha_exportacao()`, `converter_rating_filmow_para_trakt()`, `exportar_linhas()` e escrita do relatório.
- `README.md` somente quando a tarefa exigir atualizar a operação documentada.
- A política de confiança, o scraper e a resolução de identidade pertencem a outros agentes.

## Contexto

A CLI oferece quatro formatos, que podem gerar cinco arquivos CSV: Analítica, Sintética e Letterboxd geram um arquivo; Trakt gera History e Ratings separados. Letterboxd tem cabeçalhos condicionais, mas só um arquivo é criado por execução.

## Contratos atuais

| Formato | Colunas, na ordem | Nota |
|---|---|---|
| Analítica | `imdbID`, `tmdbID`, `tmdbTitle`, `tmdbYear`, `tmdbCountry`, `tmdbDirectors`, `filmowTitle`, `filmowYear`, `filmowRating`, `Rating10` | Filmow + IMDb |
| Sintética | `imdbID`, `tmdbID` | nenhuma |
| Letterboxd, origem Filmow | `imdbID`, `tmdbID`, `Rating` | Filmow original 0–5 |
| Letterboxd, origem IMDb | `imdbID`, `tmdbID`, `Rating10` | IMDb original 0–10 |
| Trakt History | `imdb_id`, `tmdb_id`, `type` | nenhuma |
| Trakt Ratings, origem Filmow | `imdb_id`, `tmdb_id`, `type`, `rating` | Filmow ×2 para 0–10 |
| Trakt Ratings, origem IMDb | `imdb_id`, `tmdb_id`, `type`, `rating` | IMDb original 0–10 |

Regras:

- `type` é sempre `movie` e a resolução permanece restrita a filmes.
- Letterboxd não converte o valor. O nome público é **Filmow**; o valor técnico interno `filmow` permanece inalterado.
- Trakt Ratings é a única conversão: uma nota Filmow válida em meia estrela é multiplicada por 2. IMDb permanece original. Portanto, “sem conversão” não descreve todo o fluxo Trakt.
- Trakt History recebe as linhas selecionadas sem campo de nota. Trakt Ratings também recebe essas linhas; nota ausente ou inválida resulta em `rating` vazio, não em exclusão da linha.
- Zero é uma nota válida. Ausência, texto não numérico, valor fora da escala ou nota Filmow fora da grade de meias estrelas resulta em campo vazio.
- `csv.DictWriter` mantém `extrasaction="ignore"`; `idOrigin` e aliases internos não podem vazar.
- A escrita de cada CSV é atômica: um arquivo final só substitui o destino após ser gravado por completo.
- O dataset do IMDb é obtido somente quando o contrato efetivo precisa dele.

## Regras

- Preservar nomes, timestamp `YYYYMMDD_HHMMSS`, cabeçalhos, ordem, UTF-8 e separação dos arquivos Trakt.
- Preservar `MAX_WORKERS = 5`; este agente não altera concorrência.
- Não misturar identidade, origem da nota e escrita do arquivo.
- Não registrar credenciais ou identificadores pessoais.
- Não afirmar que cinco trabalhadores é um limite seguro por si só. Ele limita a concorrência, enquanto respostas do WAF e 429 são riscos operacionais a medir.
- Não confundir o tamanho comprimido do IMDb com o uso de RAM: o download e o índice em memória são recursos distintos.

## Dependências

- `csv`, `datetime`, `Decimal`, `os`, `pathlib` e os dicionários produzidos pelo pipeline.
- Para uma origem IMDb efetiva, o índice público do IMDb; para origem Filmow, apenas a nota pessoal já extraída.

## Testes

Validar com `unittest`:

- Analítica com metadados, `filmowRating` e `Rating10`.
- Sintética limitada a `imdbID,tmdbID`, mesmo quando não houver nota válida.
- Letterboxd Filmow → `Rating` e IMDb → `Rating10`, sem conversão e com ausências vazias.
- Trakt History sem nota e Trakt Ratings com Filmow ×2 ou IMDb original.
- Zero preservado; ausência, texto inválido e valores fora da escala vazios.
- Cabeçalho, ordem, escaping, aliases internos, timestamp, escrita atômica e arquivos Trakt separados.
- Pergunta de origem apenas em Letterboxd e Trakt; ausência de download IMDb quando a origem efetiva é Filmow ou o formato é Sintético.

## Comandos

```text
py -m unittest tests.test_export -v
py -m unittest tests.test_cli_export_flow -v
py -m unittest discover -s tests -v
```

## Critérios de conclusão

- Os quatro formatos continuam válidos e o Trakt continua gerando dois arquivos.
- Cada nota mantém a origem, a escala e a conversão correta; ausência e invalidez ficam vazias.
- Nenhum campo interno, segredo ou identificador pessoal entra nos artefatos.
