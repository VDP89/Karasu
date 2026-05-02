# Phase 3 dogfood audit — 2026-05-02

Forward-look audit returned by ChatGPT after the live dogfood
(see [`sessions/2026-05-02-phase-3-dogfood.md`](sessions/2026-05-02-phase-3-dogfood.md)
and the closed tracking issue #39).

The audit reviewed:
- The 5 Phase 3 PRs merged earlier the same day (#34, #35, #36, #37, #38).
- The 3 dogfood-derived F-PRs (#40 F9, #41 F10, #42 F11).
- The closure docs (#43, #44).
- The Phase 3 invariants and frozen contracts in `decision-log.md`.

## 1) F9 / F10 / F11 correctness

```text
Veredicto binario:
  F9: SÍ (correcto)
  F10: SÍ (correcto, con una limitación conocida aceptable en Phase 3)
  F11: SÍ (correcto)

Razón corta:
  - F9 corrige la causa raíz real: karasu chat depende de JobQueue,
    y ese componente vive en el extra [job-queue] de
    python-telegram-bot.
  - F10 corrige el síntoma operativo observado (warnings por
    solapamiento de jobs) y mantiene el invariante de no
    concurrencia del reader.
  - F11 cubre específicamente el patrón de atomic write observado
    en Notepad (*.tmp.*) sin romper los defaults previos de ruido.

Edge cases identificados:
  - F9: si un operador instala sin resolver extras (entorno roto/
    manual), seguirá fallando; no es bug de código, sí riesgo de
    packaging/documentación.
  - F10: con latencias muy altas de Telegram, coalesce=True puede
    condensar ejecuciones y generar burst de envío posterior; no
    pierde eventos (el tail conserva offset), pero puede aumentar
    demora percibida.
  - F11: otros editores podrían usar sufijos distintos (.~tmp,
    #file#, etc.); no contradice F11, pero no queda universal.
```

## 2) Findings faltantes (forward-look)

### 2.1 Persistir priority efectiva en agent_response

```text
Veredicto: SÍ, conviene agregarlo como mejora (no blocker).

Razón corta:
  Hoy la evidencia de override quedó indirecta ("Claude lo verbalizó").
  Persistir la prioridad efectiva en metadatos de respuesta mejora
  auditabilidad sin cambiar semántica de F3.

Riesgo con contratos congelados:
  No rompe F3 si se mantiene intacto: "solo hay agent_response cuando
  hubo trabajo real". Debe implementarse como enriquecimiento de
  data en respuestas existentes, no como nuevo evento ni heartbeat.
```

### 2.2 trust_level=2 ejecuta autónomo

```text
Veredicto: SÍ, requiere guardrail explícito de docs (y opcionalmente
de código).

Razón corta:
  El dogfood probó edición autónoma real sobre sample.py; está dentro
  de contrato, pero merece advertencia operativa visible para evitar
  sorpresas en despliegues nuevos.

Guardrail recomendado:
  - Documentar en local-dogfood / runbook una sección
    "trust_level=2 puede modificar archivos sin aprobación humana".
  - Nice-to-have de código: log estructurado destacado al iniciar
    adapter con trust_level >= 2.
```

### 2.3 Cap por originating file_change.id

```text
Veredicto: SÍ, es una limitación real; NO blocker en Phase 3.

Razón corta:
  El cap actual controla spam sobre un mismo origin (cumple objetivo
  de stop-rule local), pero no limita loops distribuidos en
  múltiples origins consecutivos.

Clasificación:
  - Finding nuevo (P2/P3 de robustez operativa) para Phase 3+.
  - Aceptable mantenerlo ahora por invariante single-worker + freeze
    de contratos.
```

## 3) Convención sessions/ + bitácora

```text
Veredicto: SÍ, tiene sentido y está bien diseñada.

Razón corta:
  Separa snapshot (current-state), índice (session-log) y narrativa
  profunda por sesión (sessions/YYYY-MM-DD-*.md), que es exactamente
  lo que se necesita para auditoría reproducible.

Ajustes sugeridos:
  - Requerido: ninguno.
  - Nice-to-have: plantilla mínima (docs/memory/sessions/_template.md)
    para reducir variación de estructura entre operadores.
```

## 4) Readiness para Phase 3+ archive

```text
Veredicto: SÍ, listos para abrir Phase 3+ (webhook / A2A / handoff),
con 2 tareas cortas de hardening recomendadas en paralelo.

Razón corta:
  El loop crítico quedó validado en vivo, los 3 findings del día
  están mergeados y los invariants/frozen contracts quedaron
  explícitos.

Hardening antes o en paralelo al primer chunk 3+:
  - Registrar "priority efectiva aplicada" en agent_response.data
    para observabilidad del loop.
  - Añadir guardrail documental explícito sobre trust_level=2 y, si
    entra en scope, warning de arranque.
```

## REQUERIDOS vs NICE-TO-HAVE

```text
REQUERIDOS:
  1. Documentar explícitamente que trust_level=2 habilita edición
     autónoma (riesgo operativo directo).
  2. Abrir issue formal por limitación de cap local por origin
     (no global), para que no quede como deuda tácita.

NICE-TO-HAVE:
  1. Persistir priority efectiva en agent_response.data
     (auditabilidad fuerte del override).
  2. Plantilla de bitácora en docs/memory/sessions/_template.md.
  3. Warning estructurado en startup cuando trust_level >= 2.
```

## Aplicación post-audit

Tracked in this PR / commit history:

| Item | Tipo | Estado |
|---|---|---|
| Trust=2 autonomous-execution warning in docs | REQUERIDO #1 | Aplicado en este PR (`docs/local-dogfood.md` + `docs/decisions.md`) |
| Issue formal por cap-local-per-origin | REQUERIDO #2 | Issue abierto post-merge |
| Persistir priority en agent_response | NICE-TO-HAVE #1 | Queued para Phase 3+ chunk de hardening |
| Plantilla `_template.md` para sessions/ | NICE-TO-HAVE #2 | Aplicado en este PR |
| Warning estructurado en startup trust>=2 | NICE-TO-HAVE #3 | Queued junto con #1 |

Next step apunta a Phase 3+ archive pre-mortem doc-only PR. Las dos
tareas de hardening (NICE-TO-HAVE #1 y #3) pueden ir en paralelo al
primer chunk Phase 3+ o resolverse antes — no bloquean el design.
