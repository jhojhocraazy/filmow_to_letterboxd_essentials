# Filmow to Letterboxd & Trakt Essentials

Um motor de extração, transformação e carga (ETL - *Extract, Transform, Load*) de alta performance arquitetado para migrar históricos do portal Filmow para plataformas de registro de consumo. O sistema opera com processamento concorrente (Multithreading) e inteligência offline para contornar firewalls e latência de rede.

## Arquitetura e Lógica Operacional

A arquitetura foi projetada para resolver omissões crônicas de banco de dados, purificar o histórico e aplicar evasão contra bloqueios automatizados (WAF) do Cloudflare.

*   **Processamento Concorrente:** A extração utiliza `ThreadPoolExecutor` para raspar até 5 obras simultaneamente. O limite de instâncias é ajustado para maximizar a extração sem acionar as travas de negação de serviço (*Rate Limit 429*) da plataforma.
*   **Inteligência Offline (Zero-Network Data):** O motor baixa o arquivo de despejo oficial de avaliações do IMDb (`title.ratings.tsv.gz`) e constrói um índice de busca na memória RAM (~30MB). Isso elimina as requisições *web* à Amazon para coletar a nota pública, derrubando o tempo de execução em mais de 80%.
*   **Filtro Cinematográfico Estrito:** O Filmow frequentemente cataloga séries de TV e documentários episódicos na aba de filmes. O motor força o mapeamento exclusivamente para o endpoint `/movie` do TMDb. Qualquer ID televisivo é reprovado matematicamente e expurgado da exportação, prevenindo falhas de importação no Letterboxd.
*   **Via Expressa (Fast-Track JSON-LD) com Auditoria:** O roteador intercepta metadados estruturados injetados invisivelmente na tag `<script type="application/ld+json">`. Para evitar a colisão de falsos positivos (ex: sequências compartilhando o ID do primeiro filme), o script cruza o ano de lançamento e o diretor. Se reprovado, a via expressa é abortada.
*   **Mecanismo de Contingência (Fallback):** Quando o ID matriz falha na auditoria, o script despacha uma busca semântica livre na API do TMDb. A resolução de identidade só é validada se o cálculo de similaridade atingir grau de confiança estrutural (Score > 100).

## Estrutura de Exportação Dinâmica

O menu interativo formata o empacotamento dos dados para garantir que nenhum importador parceiro rejeite o documento:

1.  **Analítica:** Exporta um inventário contendo IDs do IMDb e TMDb, título nacional, título original, ano, diretores e notas. Utilizado para auditar discrepâncias de metadados.
2.  **Sintética:** Uma base minimalista contendo as chaves primárias e a nota global do IMDb (`Rating10`).
3.  **Letterboxd Essencial:** Padrão estrito de importação da plataforma Letterboxd. Isola a nota fracionada dada pelo usuário no Filmow para espelhar o histórico perfeitamente.
4.  **Trakt.tv:** Divide a saída em dois arquivos independentes (`History` para registrar a visualização e `Ratings` para credenciar a nota pública do IMDb). Padroniza a tipologia de todos os itens como `movie`.

## Dependências e Instalação

O ambiente exige o interpretador Python instalado localmente e bibliotecas externas para evasão de firewall e renderização do painel de telemetria.

1. Clone o repositório para o disco local via CLI.
2. Instale os pacotes requeridos executando `pip install -r requirements.txt`. Se o sistema operacional retornar erro de comando, utilize o roteamento do Python Launcher: `py -m pip install -r requirements.txt`.
3. Inicie o orquestrador executando `python filmow_to_letterboxd_essentials.py` ou `py filmow_to_letterboxd_essentials.py`.

Durante a inicialização, o motor armazenará a sua chave de API do TMDb v3 em um documento de texto plano local. A credencial ficará protegida pelas regras ativas de bloqueio do repositório (`.gitignore`).