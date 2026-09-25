# Segurança

## Versão com suporte

A série `0.1.x` recebe correções de segurança compatíveis com a API existente. Como o projeto está em uma versão inicial, não há uma LTS separada.

## Relato de vulnerabilidade

Não publique detalhes sensíveis em issue, discussion ou pull request público. Abra um reporte privado no mecanismo de segurança do repositório GitHub e inclua:

- descrição do problema e impacto;
- passos mínimos de reprodução;
- versão ou commit afetado;
- versão de Python e sistema operacional;
- mitigação já testada.

Não envie uma chave real. Substitua-a por um valor fictício e remova dados pessoais e arquivos exportados.

## Tratamento de segredos

- A chave da TMDb é solicitada pela CLI e pode ser salva localmente em `tmdb_api.txt`. Esse arquivo nunca deve ser versionado, anexado ou compartilhado.
- Caso a chave tenha sido exposta, revogue-a no painel da TMDb e gere outra imediatamente.
- Não coloque credenciais em URLs, logs, relatórios, CSVs, variáveis versionadas ou exemplos desta documentação.
- O nome de usuário do Filmow usado em uma execução local aparece no nome de arquivos exportados e no relatório. Trate esses artefatos como dados pessoais e não os versione.
- A ferramenta trabalha com histórico público, mas os resultados podem revelar hábitos de consumo e notas pessoais.

## Segurança operacional

- Use uma conta e uma chave TMDb com o menor privilégio necessário.
- Execute com um usuário de sistema sem privilégios administrativos e mantenha Python e dependências atualizadas.
- A extração acessa Filmow, TMDb e, quando necessário, datasets do IMDb. Respeite termos de uso, limites de requisição e políticas de cada serviço.
- Revise arquivos CSV antes de importá-los em outra plataforma: eles podem conter histórico e avaliações.
- O código tenta evitar publicação parcial de arquivos, mas uma falha do sistema de arquivos ou do processo sempre deve ser tratada como falha da exportação.

## Limites de segurança

O matching reduz falsos positivos por heurística, mas não transforma os resultados em identidade sob prova. Revise amostras, especialmente títulos ambíguos, traduções, filmes-remakes, coletâneas e obras com dados incompletos. A integração direta com Letterboxd ou Trakt não é executada pelo projeto: os CSV precisam ser conferidos antes da importação.
