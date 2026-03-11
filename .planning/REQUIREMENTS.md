# Requirements: Conductor

**Defined:** 2026-03-11
**Core Value:** A product owner describes a feature, and a self-organizing team of AI coding agents delivers quality, reviewed, tested code — with the human staying in control when they want to be.

## v1.2 Requirements

Requirements for the Task Verification & Build Safety milestone. Each maps to roadmap phases.

### Task Verification

- [ ] **VRFY-01**: When a task has `target_file` set and the file does not exist on disk after review, the orchestrator retries via the revision loop instead of marking COMPLETED
- [ ] **VRFY-02**: After all tasks complete, if `build_command` is configured, the orchestrator runs it and reports pass/fail with stderr output
- [ ] **VRFY-03**: User can set `build_command` via `--build-command` CLI flag or `.conductor/config.json`

### Quality Assurance

- [ ] **QUAL-01**: Reviewer returns structured feedback; agent receives revision instructions and resubmits within a configurable maximum number of rounds
- [ ] **QUAL-02**: When revision attempts are exhausted, the task is marked NEEDS_REVISION with the reason, not silently completed

### Resume Robustness

- [ ] **RESM-01**: When `review_only` review fails with an exception, the orchestrator falls back to best-effort approval instead of crashing
- [ ] **RESM-02**: The resume spawn loop correctly handles completed tasks from `get_ready()`, retrieves task exceptions, and uses `marked_done` flag to avoid premature loop exit

## v1.1 Requirements (Completed)

All 19 requirements delivered. See `.planning/milestones/v1.1-REQUIREMENTS.md` for details.

### Chat Interface — CHAT-01 through CHAT-08 (8 requirements)
### Smart Delegation — DELG-01 through DELG-04 (4 requirements)
### Session Management — SESS-01 through SESS-05 (5 requirements)
### Sub-Agent Visibility — VISB-01, VISB-02 (2 requirements)

## v1.3+ Requirements

Deferred to future release. Tracked but not in current roadmap.

### Concurrency

- **CONC-01**: Multiple concurrent chat sessions with session-scoped state namespacing

### Enhanced Display

- **DISP-01**: Inline diff review in TUI for file changes
- **DISP-02**: Per-task GSD scope flexibility display in chat

### Input

- **INPT-01**: Voice input support

### Infrastructure

- **INFR-01**: Git worktree isolation per agent for large parallel workloads
- **INFR-02**: CI integration — auto-fix failing builds by spawning agents

## Out of Scope

| Feature | Reason |
|---------|--------|
| Automatic error remediation from build output | Future enhancement — v1.2 reports errors, does not auto-fix |
| Per-file syntax checking | Language-specific, complex; build command covers this |
| Integration/runtime testing | Beyond scope of file existence + build verification |
| Parsing build output to map errors to tasks | Future enhancement for targeted remediation |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| VRFY-01 | Phase 24 | Pending |
| VRFY-02 | Phase 25 | Pending |
| VRFY-03 | Phase 25 | Pending |
| QUAL-01 | Phase 24 | Pending |
| QUAL-02 | Phase 24 | Pending |
| RESM-01 | Phase 23 | Pending |
| RESM-02 | Phase 23 | Pending |

**Coverage:**
- v1.2 requirements: 7 total
- Mapped to phases: 7
- Unmapped: 0

---
*Requirements defined: 2026-03-11*
