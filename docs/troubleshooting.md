# Diagnóstico de problemas

## Antes de começar

Confirme ambiente e sintaxe:

```bash
python --version
python -m pip check
python -m unittest discover -s tests -v
python -m py_compile filmow_to_letterboxd_essentials.py identity_matching.py tmdb_client.py tests/*.py
```

Se os testes acessarem a rede ou pedirem uma chave, interrompa a execução e corrija o teste antes de continuar.

## Dependências ausentes ou incompatíveis

Use um ambiente virtual com Python 3.10 ou mais recente e instale `requirements.txt`:

```bash
python -m pip install -r requirements.txt
python -m pip check
```

Verifique qual interpretador está ativo com `python -c "import sys; print(sys.executable)"`.

## A chave TMDb não é encontrada ou é rejeitada

Confirme a credencial usada pelo seu perfil, sem publicá-la. O arquivo `tmdb_api.txt`, quando usado, deve conter somente a chave e permanecer fora do Git. Se a chave já foi exposta, revogue-a e gere outra. Não coloque uma chave real em log, issue, teste ou documentação.

Erros permanentes de autenticação não são repetidos pelo cliente. Timeouts, 429 e 5xx têm retentativas com espera limitada.

## O histórico não é encontrado

- confirme que a URL do perfil é pública;
- confirme que o usuário digitado corresponde ao identificador público correto;
- confirme que a conta não possui histórico público disponível;
- tente novamente com menos concorrência se houver rate limiting.

Mensagens de HTTP 429 e 5xx normalmente são temporárias. Respostas 4xx diferentes de 429 são tratadas como falha permanente.

## A extração demora ou falha em parte dos filmes

O tempo varia com o tamanho do histórico, latência, WAF e serviços externos. A aplicação processa páginas em paralelo, mas impõe concorrência máxima. Uma falha individual não deve apagar as demais linhas já resolvidas.

Se houver falhas repetidas:

1. aguarde o período de rate limit;
2. execute novamente;
3. revise conectividade e proxy;
4. reduza a concorrência somente ao manter uma configuração local consistente e segura;
5. consulte o relatório para separar falhas de extração de falhas de identidade.

## Nenhum filme foi exportado

Isso ocorre quando não houve linhas resolvidas. Nenhum CSV é criado para uma lista vazia. Verifique:

- histórico público disponível;
- validade da chave TMDb;
- conectividade;
- alterações na estrutura da página;
- mensagens de falha de identidade no relatório.

## A identidade parece errada

O matching é conservador, mas títulos traduzidos, obras collector, remakes, homônimos e metadados incompletos podem enganar a heurística. Compare os IDs e metadados dos dois lados. O relatório indica apenas a origem interna da identidade; ele não substitui uma revisão humana.

## Nota vazia, zero ou inesperada

- `0` é uma nota válida e deve permanecer no CSV;
- ausência ou valor inválido é representado por campo vazio;
- Filmow usa a grade de 0 a 5 em meias estrelas;
- Letterboxd com origem IMDb preserva a escala de 0 a 10;
- Trakt com origem Filmow multiplica a nota por 2 e usa uma casa decimal;
- valores fracionários que não estão na grade Filmow são inválidos.

Confira também se você selecionou Letterboxd ou Trakt, pois a origem escolhida altera o contrato.

## CSV não é aceito pelo importador

Confira:

1. o cabeçalho exato e sua ordem;
2. a origem da nota escolhida;
3. IDs vazios ou linhas com campos inesperados;
4. separador vírgula, UTF-8 e primeira linha de cabeçalho;
5. se o importador espera History e Ratings separados no Trakt;
6. uma amostra pequena antes do lote completo.

Consulte `docs/export-contracts.md` para os contratos atuais. Uma falha do importador externo não é corrigida automaticamente por esta ferramenta.

## Testes ou CI falham

Execute cada etapa separadamente. Verifique a versão de Python, instale `requirements.txt` e rode `unittest` a partir da raiz do repositório. O workflow não deve acessar serviços reais; mocks preservam a suíte offline.

## Limitações conhecidas

- não há importação automática em Letterboxd ou Trakt;
- não há garantia de que toda obra pública será identificada;
- não há suporte oficial a séries: o endpoint TMDb usado é de filmes;
- mudanças no HTML, WAF, APIs ou datasets podem exigir atualização;
- o dataset do IMDb ocupa espaço em disco e pode consumir bastante memória ao ser indexado;
- credenciais, nomes de perfil, CSVs e relatórios são dados sensíveis;
- o software não é uma fonte oficial e deve ser usado com revisão e responsabilidade.
