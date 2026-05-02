# Karasu UI — Phase UI Design

UI = surface, not orchestrator

## Source

.karasu/events.jsonl

## Timeline

Mostrar eventos:
- file_change
- agent_response
- human_decision

Campos:
- timestamp
- type
- path
- agent

## Event detail

Para agent_response:
- content
- success
- requires_human

## Actions

Permitir:
- marcar como revisado
- marcar como irrelevante

NO permitir:
- ejecutar pipeline
- re-dispatch
- aplicar scars
