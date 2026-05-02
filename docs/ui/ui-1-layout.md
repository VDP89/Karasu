# Karasu UI-1 Layout

## Entry Flow
1. Login
2. Project selection
3. Dashboard

## Header
Karasu UI | Project selector | Crow state | User

## Layout
Header
Live Map and Event Detail
Timeline

## Sections
Live Map: Usuario, Karasu, Claude, Codex, GitHub
Event Detail: content, success, requires_human, metadata
Timeline: file_change, agent_response, human_decision

## Crow State
idle, processing, waiting, error
Priority: error > waiting > processing > idle

## Rules
UI does not execute pipeline
UI does not dispatch agents
UI does not apply scars

## Project Model
Each project has event_log, scars, config
UI only switches context
