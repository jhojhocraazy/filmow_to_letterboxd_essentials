# Filmow to Letterboxd & Trakt Essentials

Um motor de extração, transformação e carga (ETL - *Extract, Transform, Load*) de alta performance arquitetado para migrar históricos do portal Filmow para o Letterboxd e Trakt.tv. O sistema opera com processamento concorrente (Multithreading) e inteligência offline para contornar firewalls e latência de rede.

## Arquitetura e Lógica Operacional

A arquitetura foi projetada para resolver omissões crônicas de banco de dados e aplicar evasão contra bloqueios automatizados (WAF) do Cloudflare, entregando varreduras integrais de perfis em minutos, não horas.

*   **Processamento Concorrente:** A extração utiliza `ThreadPoolExecutor` para raspar múltiplas páginas do Filmow simultaneamente. O limite de instâncias (*workers*) é ajustado para maximizar a extração sem acionar as travas de negação de serviço (*Rate Limit 429*) da plataforma.
*   **Inteligência Offline (Zero-Network Data):** O motor baixa o arquivo de despejo oficial de avaliações do IMDb (`title.ratings.tsv.gz`) e constrói um índice de busca instantânea na memória RAM. Isso elimina a necessidade de fazer requisições *web* à Amazon para coletar a nota pública das obras.
*   **Via Expressa (Fast-Track JSON-LD):** O roteador intercepta metadados estruturados injetados invisivelmente na tag `<script type="application/ld+json">` do código-fonte do Filmow. Se o ID oficial do IMDb for localizado na chave `sameAs`, a validação de identidade é aprovada instantaneamente.
*   **Mecanismo de Contingência Semântica (Fallback):** Quando o ID matriz está ausente no Filmow, o script extrai atributos secundários (título, ano e diretor) e despacha uma busca matemática cruzada na API do TMDb. A resolução de identidade só é validada se o cálculo de similaridade atingir grau de confiança estrutural (Score > 100).

## Estrutura de Exportação Dinâmica

O menu interativo permite direcionar o empacotamento dos dados para diferentes finalidades, garantindo que nenhum importador parceiro rejeite o documento:

1.  **Analítica:** Exporta um inventário contendo IDs do IMDb e TMDb, título nacional, título original, ano, diretores e as notas originais e públicas. Utilizado para auditar discrepâncias de metadados.
2.  **Sintética:** Uma base minimalista contendo as chaves primárias e a nota global do IMDb (`Rating10`).
3.  **Letterboxd Essencial:** Padrão estrito de importação da plataforma Letterboxd. Isola a nota fracionada dada pelo usuário no Filmow para espelhar o histórico perfeitamente.
4.  **Trakt.tv:** Divide a saída em dois arquivos independentes (`History` para registrar a visualização e `Ratings` para credenciar a nota pública). Identifica topologias cruzadas automaticamente, marcando filmes como `movie` e minisséries como `show` para prevenir falhas no importador nativo do Trakt.

## Dependências e Instalação

O ambiente exige o interpretador Python instalado localmente e bibliotecas externas para evasão de firewall e renderização do painel de telemetria.

1. Clone o repositório para o disco local via CLI.
2. Instale os pacotes requeridos executando `pip install -r requirements.txt`. Se o sistema operacional retornar erro de comando, utilize o roteamento do Python Launcher: `py -m pip install -r requirements.txt`.
3. Inicie o orquestrador executando `python filmow_to_letterboxd_essentials.py` ou `py filmow_to_letterboxd_essentials.py`.

Durante a inicialização, o motor armazenará a sua chave de API do TMDb v3 em um documento de texto plano local. A credencial ficará protegida pelas regras ativas de bloqueio do repositório (`.gitignore`).