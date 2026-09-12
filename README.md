# Filmow to Letterboxd Essentials

Ferramenta CLI nativa para extração de catálogos do Filmow com reconciliação matemática de metadados na API do TMDb e validação cruzada de confiabilidade. 

**Instalação**
Execute o instalador de pacotes no terminal:
`pip install -r requirements.txt`

Se o sistema retornar erro de comando não reconhecido (comum no Windows), force a instalação acionando o módulo através do executável principal da linguagem:
`python -m pip install -r requirements.txt`

**Uso Interativo**
Execute o script sem argumentos para acionar a interface visual (Rich):
`python filmow_to_letterboxd_essentials.py`

**Uso em Automação (Headless)**
A omissão da interface ocorre automaticamente ao inserir o nome do usuário na execução. 

Parâmetros suportados na linha de comando:
* `usuario`: O nome do perfil público. Atua como gatilho de automação; sua presença ignora o menu interativo e inicia a raspagem imediatamente.
* `--modo`: Define a estrutura de colunas do arquivo CSV gerado. Aceita os valores `analitica` (padrão), `sintetica` ou `letterboxd`.
* `--delay`: Controla o intervalo em segundos entre requisições ao Filmow para mitigar bloqueios de taxa de rede (Rate Limit). O valor padrão é `1.0`, aceitando valores fracionados.

Exemplo de execução acionando todos os parâmetros simultaneamente:
`python filmow_to_letterboxd_essentials.py seunomedeusuario --modo letterboxd --delay 2.5`