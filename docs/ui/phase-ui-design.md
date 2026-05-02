# Karasu UI — Phase UI Design v2

## Principle

UI = surface, not orchestrator

---

## Source of truth

.karasu/events.jsonl

---

## Core UI (MVP)

### 1. Live Map (Primary View)

Visualización de dominios:

- Usuario
- Karasu
- Claude
- Codex
- GitHub

Reglas:

- Cada dominio es un nodo
- Los eventos generan flujo entre nodos
- El cuervo representa el mensaje en tránsito

Ejemplos:

- Usuario → Claude → cuervo vuela hacia Claude
- Claude → Codex → cuervo cambia dirección
- Codex → Usuario → cuervo vuelve

Regla obligatoria:

> No hay animación sin evento real

---

### 2. Decision Moment

Cuando:

requires_human = true

La UI debe:

- enfocar ese evento
- resaltar visualmente
- pausar el contexto visual
- mostrar acción clara

Acciones:

- marcar como revisado
- marcar como irrelevante
- preparar corrección (draft)

---

### 3. Crow State (System State)

El cuervo representa el estado del sistema:

- Idle → posado
- Processing → volando
- Waiting → mirando / quieto
- Error → agitado

No es decoración. Es indicador operativo.

---

## Secondary Modules

### 4. Token Monitor

Mostrar por agente:

- uso relativo (%)
- barra visual

Ejemplo:

Claude  ████████░░ 80%  
Codex   █████░░░░░ 52%

Alertas:

- 80% → warning
- 95% → crítico

Regla:

> Solo observación (no bloquear ejecución)

---

### 5. Voice Input (Draft Mode)

Función:

- dictado por voz
- transcripción
- traducción ES ↔ EN

Flujo:

Usuario habla  
↓  
Karasu transcribe  
↓  
Karasu muestra draft  
↓  
Usuario confirma envío  

Configuración:

Settings → Language

- Español
- English

Regla:

> Voz nunca ejecuta directo

---

## Timeline (Supporting View)

Lista de eventos:

- file_change
- agent_response
- human_decision

Campos:

- timestamp
- tipo
- path
- agent

---

## Event Detail

Para agent_response:

- content
- success
- requires_human
- metadata

---

## Constraints (MANDATORY)

- no llamar pipeline
- no re-dispatch
- no aplicar scars
- no mutar AgentResponse
- UI solo observa y registra

---

## Success Criteria

- El usuario entiende el sistema en <10s
- El usuario identifica decisiones pendientes
- El usuario puede actuar sin leer logs

---
UI design v2 draft
