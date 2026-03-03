# Plano Executavel por Issues - Addon Print Toolbox

Data: 2026-03-03
Escopo: estabilizacao tecnica e base para funcionalidades inteligentes

## Como usar este plano
- Cada issue tem ID unico, escopo, dependencias e criterio de aceite objetivo.
- Ordem recomendada: E1 -> E2 -> E3 -> E4.
- Uma issue so pode ser fechada quando todos os criterios de aceite forem verificados.

## Epic E1 - Estabilidade Operacional

### E1-I01: Introduzir infraestrutura de estado por Scene
Tipo: Refactor
Dependencias: nenhuma
Descricao:
- Criar um armazenamento de estado em `Scene.print3d_toolbox_runtime` para substituir variaveis globais de runtime.
- Estado minimo: `report_items` e `advisor_suggestions`.
Criterios de aceite:
- `report.py` nao usa mais estado global mutavel para dados de execucao.
- `operators/advisor.py` nao usa mais lista global `_suggestions`.
- Limpar estado ao trocar cena/ao limpar relatorio.

### E1-I02: Padronizar tratamento de erro e log
Tipo: Refactor
Dependencias: E1-I01
Descricao:
- Criar utilitario central de erro/log (camada `core/runtime.py`).
- Remover `print(...)` em caminhos criticos e substituir por `report(...)` + log tecnico.
Criterios de aceite:
- Caminhos criticos em analyze/export/edit nao usam `print` para erro operacional.
- Mensagens para usuario sao curtas e acionaveis.

### E1-I03: Consolidar compatibilidade de operadores/exporters
Tipo: Refactor
Dependencias: nenhuma
Descricao:
- Extrair `operator_exists` e checks de 3MF para modulo unico (`core/compat.py`).
- Reusar em `preferences.py` e `operators/export.py`.
Criterios de aceite:
- Nao existe duplicacao da funcao de check 3MF.
- Fluxo de export 3MF continua funcional com fallback.

## Epic E2 - Qualidade Automatizada

### E2-I01: Criar smoke test headless
Tipo: Test
Dependencias: E1-I01
Descricao:
- Criar `tests/smoke_headless.py` para validar registro do addon, check geometrico e limpeza de estado.
- Script deve rodar com `blender --background --python tests/smoke_headless.py`.
Criterios de aceite:
- Script termina com codigo 0 no cenario feliz.
- Script falha com codigo != 0 quando um passo critico quebra.

### E2-I02: Documentar execucao de testes
Tipo: Docs
Dependencias: E2-I01
Descricao:
- Adicionar secao no README com comando e pre-requisitos para smoke test.
Criterios de aceite:
- README contem comando pronto de execucao.
- Explica limitacao (requer Blender instalado).

## Epic E3 - Base Arquitetural para Inteligencia

### E3-I01: Definir schema de snapshot de analise
Tipo: Feature
Dependencias: E1-I01
Descricao:
- Criar `core/models.py` com dataclasses:
  - `AnalysisMetric`
  - `AnalysisSnapshot`
  - `AdvisorSuggestion`
- Snapshot deve ser serializavel para JSON (estrutura simples).
Criterios de aceite:
- Existe funcao de serializacao/deserializacao.
- Snapshot e salvo no runtime state apos `Check All`.

### E3-I02: Persistir snapshot da ultima execucao
Tipo: Feature
Dependencias: E3-I01
Descricao:
- Salvar snapshot no runtime da scene apos analise.
- Disponibilizar API para leitura pelo Advisor.
Criterios de aceite:
- Advisor usa snapshot quando disponivel.
- Quando snapshot nao existe, fluxo continua com fallback.

## Epic E4 - Advisor Confiavel

### E4-I01: Explicabilidade de sugestoes
Tipo: Feature
Dependencias: E3-I01
Descricao:
- Adicionar `reason` e `evidence` em cada sugestao do Advisor.
- Mostrar no painel UI.
Criterios de aceite:
- Toda sugestao exibida possui motivo tecnico claro.
- Sem regressao de botoes "Apply Suggestion".

### E4-I02: Priorizacao deterministica
Tipo: Feature
Dependencias: E4-I01
Descricao:
- Ordenar sugestoes por prioridade e severidade de evidencia.
Criterios de aceite:
- Ordem de sugestoes e estavel entre execucoes com mesmo input.

## Sequenciamento de execucao recomendado
1. E1-I01
2. E1-I03
3. E1-I02
4. E2-I01
5. E2-I02
6. E3-I01
7. E3-I02
8. E4-I01
9. E4-I02

## Definicao de pronto (DoD)
- Codigo passa em smoke test headless.
- Mudancas documentadas no README quando relevante.
- Sem duplicacao de utilitarios de compatibilidade.
- Sem uso de estado global mutavel para report/suggestions.
