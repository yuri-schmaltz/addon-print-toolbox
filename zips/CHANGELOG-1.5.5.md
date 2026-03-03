# Changelog — 3D Print Toolbox v1.5.4

**Data:** 2026-03-03

## Visão geral
Versão de manutenção com melhorias de infraestrutura, testes automatizados, persistência de snapshots e aprimoramentos no mecanismo de sugestões do Advisor.

## Melhorias implementadas

- **E1-I01 — Infraestrutura de estado por Scene**: adição de `report_items` e `advisor_suggestions` para isolar estado por cena e permitir múltiplas execuções independentes.
- **E1-I02 — Padronização de erros/log**: tratamento e formato de logs padronizados em caminhos críticos para facilitar diagnóstico.
- **E1-I03 — Compatibilidade de operadores/exporters (3MF)**: consolidação de compatibilidade com operadores e suporte a 3MF quando disponível no Blender.
- **E2-I01 — Smoke test headless**: inclusão de `tests/smoke_headless.py` para validação rápida em CI/ambientes headless.
- **E2-I02 — Documentação do smoke test**: instruções adicionadas no `README.md` para execução local do smoke test.
- **E3-I01 — Schema de snapshot**: definição de schema em `core/models.py` para snapshots de análise.
- **E3-I02 — Persistência e consumo de snapshot no Advisor**: gravação e leitura de snapshots para permitir reanálises e rastreabilidade das sugestões.
- **E4-I01 — Explicabilidade nas sugestões**: adição de `reason/evidence` nas sugestões do Advisor para melhor transparência.
- **E4-I02 — Priorização determinística**: ordenação determinística das sugestões para reprodutibilidade.

## Validação

- Validação sintática local: `python -m compileall -q .`
- Smoke test executado no Blender 5.0.1 (build 2025-12-16) — `Smoke test passed` e export STL validado.

## Observações

- Risco residual: serialização de índices do report em `StringProperty` pode crescer em malhas muito grandes — monitorar casos extremos.

---
Arquivo gerado automaticamente e empacotado como `addon-print-toolbox-1.5.4.zip`.
