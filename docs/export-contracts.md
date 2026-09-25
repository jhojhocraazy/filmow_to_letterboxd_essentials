# Contratos de exportação

## Regras comuns

Os CSV usam UTF-8, vírgula como delimitador e includeem uma linha de cabeçalho. A ordem das colunas é parte do contrato público e deve ser preservada. Campos desconhecidos do dicionário interno são descartados na exportação.

A escrita usa um arquivo temporário no mesmo diretório, `fsync` e substituição atômica. Uma escrita interrompida não deve publicar um CSV final truncado. O nome padrão é:

```text
exportacao_<formato>_<perfil>_<AAAAMMDD_HHMMSS>.csv
```

Para Trakt, há dois nomes:

```text
exportacao_history_trakt_<perfil>_<AAAAMMDD_HHMMSS>.csv
exportacao_ratings_trakt_<perfil>_<AAAAMMDD_HHMMSS>.csv
```

O perfil aparece no nome do arquivo e deve ser considerado dado pessoal.

## Analítica

Modo interno: `analitica`. Não pergunta a origem da nota e usa o dataset público do IMDb.

Cabeçalho exato, nesta ordem:

```csv
imdbID,tmdbID,tmdbTitle,tmdbYear,tmdbCountry,tmdbDirectors,filmowTitle,filmowYear,filmowRating,Rating10
```

- `imdbID`: ID IMDb com prefixo `tt` quando disponível.
- `tmdbID`: ID numérico do TMDb convertido para texto.
- campos `tmdb*`: metadados normalizados.
- `filmowTitle` e `filmowYear`: dados extraídos da página de origem.
- `filmowRating`: nota de 0 a 5; aceita a grade de meias estrelas.
- `Rating10`: nota pública do IMDb de 0 a 10.

Ausência ou valor inválido de nota resulta em campo vazio. O valor zero é uma nota válida e não deve ser convertido em vazio.

## Sintética

Modo interno: `sintetica`. Não usa o dataset de notas do IMDb.

```csv
imdbID,tmdbID
```

Este formato preserva as linhas resolvidas, mas não exporta nota nem metadados.

## Letterboxd

Letterboxd exige escolha explícita de `filmow` ou `imdb`.

### Origem Filmow

```csv
imdbID,tmdbID,Rating
```

`Rating` mantém a escala original de 0 a 5. Valores fora da grade de meias estrelas são considerados inválidos e exportados como vazio.

### Origem IMDb

```csv
imdbID,tmdbID,Rating10
```

`Rating10` mantém a escala pública de 0 a 10. Valores ausentes, não numéricos, infinitos ou fora do intervalo são exportados como vazio.

O nome e a escala da coluna mudam conforme a origem; consumidores não devem assumir o cabeçalho `Rating` para toda exportação Letterboxd.

## Trakt

Trakt exige escolha explícita de `filmow` ou `imdb` e sempre gera dois arquivos.

### History

```csv
imdb_id,tmdb_id,type
```

`type` é sempre `movie`. Nenhuma nota é exportada nesse arquivo.

### Ratings

```csv
imdb_id,tmdb_id,type,rating
```

`type` é sempre `movie`.

- Com origem `filmow`, a nota válida de 0 a 5 é multiplicada por 2 usando `Decimal` e exportada com uma casa decimal, por exemplo `4.5` vira `9.0`. Apenas valores da grade de meia estrela são aceitos.
- Com origem `imdb`, a nota válida de 0 a 10 é preservada.
- Valores ausentes ou inválidos produzem campo vazio, mas a linha continua presente.
- Zero é preservado: `0.0` para Filmow convertido e `0` para IMDb.

## Compatibilidade e evolução

Mudanças de nome, ordem ou escala exigem atualização de código, testes e deste documento. Um novo formato deve ter um contrato próprio, sem reaproveitar silenciosamente um cabeçalho existente.
