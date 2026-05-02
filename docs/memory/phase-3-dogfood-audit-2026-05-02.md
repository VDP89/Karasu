# Phase 3 dogfood audit — 2026-05-02

## 1) F9/F10/F11 correctness

### Veredicto binario
- **F9: SÍ (correcto)**
- **F10: SÍ (correcto, con una limitación conocida aceptable en Phase 3)**
- **F11: SÍ (correcto)**

### Razón corta
- F9 corrige la causa raíz real: `karasu chat` depende de `JobQueue`, y ese componente vive en el extra `[job-queue]` de `python-telegram-bot`.
- F10 corrige el síntoma operativo observado (warnings por solapamiento de jobs) y mantiene el invariante de no concurrencia del reader.
- F11 cubre específicamente el patrón de atomic write observado en Notepad (`*.tmp.*`) sin romper los defaults previos de ruido.

### Edge cases encontrados
- F9: si un operador instala sin resolver extras (entorno roto/manual), seguirá fallando; no es bug de código, sí riesgo de packaging/documentación.
- F10: con latencias muy altas de Telegram, `coalesce=True` puede condensar ejecuciones y generar burst de envío posterior; no pierde eventos (el tail conserva offset), pero puede aumentar demora percibida.
- F11: otros editores podrían usar sufijos distintos (`.~tmp`, `#file#`, etc.); no contradice F11, pero no queda universal.

---

## 2) Findings faltantes (forward-look)

### 2.1 Persistir `priority` efectiva en `agent_response`

### Veredicto binario
- **SÍ, conviene agregarlo como mejora (no blocker).**

### Razón corta
- Hoy la evidencia de override quedó indirecta (“Claude lo verbalizó”). Persistir la prioridad efectiva en metadatos de respuesta mejora auditabilidad sin cambiar semántica de F3.

### Riesgo con contratos congelados
- **No rompe F3** si se mantiene intacto: “solo hay `agent_response` cuando hubo trabajo real”.
- Debe implementarse como enriquecimiento de `data` en respuestas existentes, no como nuevo evento ni heartbeat.

### 2.2 `trust_level=2` ejecuta autónomo

### Veredicto binario
- **SÍ, requiere guardrail explícito de docs (y opcionalmente de código).**

### Razón corta
- El dogfood probó edición autónoma real sobre `sample.py`; está dentro de contrato, pero merece advertencia operativa visible para evitar sorpresas en despliegues nuevos.

### Guardrail recomendado
- Documentar en `local-dogfood`/runbook una sección “`trust_level=2` puede modificar archivos sin aprobación humana”.
- Nice-to-have de código: log estructurado destacado al iniciar adapter con `trust_level>=2`.

### 2.3 Cap por `originating file_change.id`

### Veredicto binario
- **SÍ, es una limitación real; NO blocker en Phase 3.**

### Razón corta
- El cap actual controla spam sobre un mismo origin (cumple objetivo de stop-rule local), pero no limita loops distribuidos en múltiples origins consecutivos.

### Clasificación
- **Finding nuevo (P2/P3 de robustez operativa)** para Phase 3+.
- Aceptable mantenerlo ahora por invariante single-worker + freeze de contratos.

---

## 3) Convención `sessions/` + bitácora

### Veredicto binario
- **SÍ, tiene sentido y está bien diseñada.**

### Razón corta
- Separa snapshot (`current-state`), índice (`session-log`) y narrativa profunda por sesión (`sessions/YYYY-MM-DD-*.md`), que es exactamente lo que se necesita para auditoría reproducible.

### Ajustes sugeridos
- Requerido: ninguno.
- Nice-to-have: plantilla mínima (`docs/memory/sessions/_template.md`) para reducir variación de estructura entre operadores.

---

## 4) Readiness para Phase 3+ archive

### Veredicto binario
- **SÍ, listos para abrir Phase 3+** (webhook/A2A/handoff), **con 2 tareas cortas de hardening recomendadas en paralelo**.

### Razón corta
- El loop crítico quedó validado en vivo, los 3 findings del día están mergeados y los invariants/frozen contracts quedaron explícitos.

### Hardening antes o en paralelo al primer chunk 3+
- Registrar “priority efectiva aplicada” en `agent_response.data` para observabilidad del loop.
- Añadir guardrail documental explícito sobre `trust_level=2` y, si entra en scope, warning de arranque.

---

## Cambios REQUERIDOS vs NICE-TO-HAVE

### REQUERIDOS
1. **Documentar explícitamente** que `trust_level=2` habilita edición autónoma (riesgo operativo directo).
2. **Abrir issue formal** por limitación de cap local por origin (no global), para que no quede como deuda tácita.

### NICE-TO-HAVE
1. Persistir `priority` efectiva en `agent_response.data` (auditabilidad fuerte del override).
2. Plantilla de bitácora en `docs/memory/sessions/_template.md`.
3. Warning estructurado en startup cuando `trust_level>=2`.
