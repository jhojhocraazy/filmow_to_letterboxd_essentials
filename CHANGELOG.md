# Changelog

Todas as mudanças relevantes deste projeto são registradas neste arquivo.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o versionamento segue [Semantic Versioning](https://semver.org/lang/pt-BR/).

## [Não publicado]

Nenhuma mudança publicada além da versão inicial.

## [0.1.0] - 2026-09-25

### Adicionado

- Primeira versão pública da ETL para extrair o histórico público do Filmow.
- Resolução e auditoria de identidades de filmes com dados do TMDb e regras de confiança.
- Exportações analítica, sintética, Letterboxd e Trakt.
- Exportação Trakt separada em History e Ratings, com conversão opcional de notas do Filmow.
- Cache de metadados do TMDb, retentativas para falhas transitórias e escrita atômica de CSV e relatório.
- Suíte de testes `unittest` offline cobrindo extração, matching, integrações, resiliência e exportação.
- Documentação de uso, arquitetura, contratos de exportação, segurança e diagnóstico de problemas.
