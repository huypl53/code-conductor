# Requirements: Conductor

**Defined:** 2026-03-11
**Core Value:** A product owner describes a feature, and a self-organizing team of AI coding agents delivers quality, reviewed, tested code — with the human staying in control when they want to be.

## v1.3 Requirements

Requirements for the Orchestrator Intelligence milestone. Each maps to roadmap phases.

### Infrastructure

- [ ] **INFRA-01**: Scheduler exposes `compute_waves()` returning pre-computed dependency wave groups
- [ ] **INFRA-02**: `OrchestratorConfig` model with configurable iteration limits (max_revisions, max_decomposition_retries) replaces hardcoded defaults
- [ ] **MODEL-01**: `ModelProfile` model maps roles (decomposer, reviewer, executor, verifier) to model names with quality/balanced/budget presets

### Execution Pipeline

- [ ] **WAVE-01**: Orchestrator executes tasks in pre-computed waves — all tasks in a wave spawn concurrently, next wave starts when current completes
- [ ] **ROUTE-01**: ACPClient accepts model selection parameter; orchestrator routes model per role using active ModelProfile
- [ ] **LEAN-01**: Agent system prompts pass file paths only (not content), letting agents read their own context for fresh 200k windows

### Agent Communication

- [ ] **STAT-01**: Agents report structured `AgentReport` with status enum (DONE, DONE_WITH_CONCERNS, BLOCKED, NEEDS_CONTEXT), files_changed list, and concerns
- [ ] **STAT-02**: Orchestrator routes based on agent status — DONE proceeds to review, BLOCKED retries with more context or escalates, NEEDS_CONTEXT provides additional info
- [ ] **DEVN-01**: Agent system prompts include deviation classification rules (auto-fix bugs/missing-critical, escalate architectural changes)

### Verification Pipeline

- [ ] **VERI-01**: `TaskVerifier` checks file content is substantive — detects stubs (pass-only, NotImplementedError, TODO markers, empty returns) via regex patterns
- [ ] **VERI-02**: `TaskVerifier` checks wiring — target file is imported/referenced by at least one other file in the project
- [ ] **RVEW-01**: Two-stage review: Stage 1 checks spec compliance (did we build the right thing?), Stage 2 checks code quality (only if Stage 1 passes)

### Smart Decomposition

- [ ] **DCMP-01**: Decomposer scores each task's complexity (1-10) with reasoning and recommended subtask count
- [ ] **DCMP-02**: Tasks scoring above threshold are selectively expanded into sub-tasks with task-specific guidance prompts

## v1.2 Requirements (Completed)

All 7 requirements delivered.

- ✓ **VRFY-01**: File existence gate in revision loop — Phase 24
- ✓ **VRFY-02**: Post-run build command — Phase 25
- ✓ **VRFY-03**: Build command via CLI flag and config.json — Phase 25
- ✓ **QUAL-01**: Structured revision feedback — Phase 24
- ✓ **QUAL-02**: NEEDS_REVISION on exhausted retries — Phase 24
- ✓ **RESM-01**: Review-only exception fallback — Phase 23
- ✓ **RESM-02**: Resume spawn loop hardening — Phase 23

## v1.1 Requirements (Completed)

All 19 requirements delivered. See `.planning/milestones/v1.1-REQUIREMENTS.md`.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Agent-to-agent direct communication | Orchestrator mediates all coordination |
| Custom LLM provider support | ACP-compatible agents only |
| Cost tracking / budget controls | Future enhancement — need token counting infrastructure |
| Prompt template system | Future enhancement — externalized prompt management |
| Pre-decomposition discussion phase | Future enhancement — interactive requirement clarification |
| Failure journal | Future enhancement — structured failure persistence |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 26 | Pending |
| INFRA-02 | Phase 26 | Pending |
| MODEL-01 | Phase 26 | Pending |
| WAVE-01 | Phase 27 | Pending |
| ROUTE-01 | Phase 27 | Pending |
| LEAN-01 | Phase 27 | Pending |
| STAT-01 | Phase 28 | Pending |
| STAT-02 | Phase 28 | Pending |
| DEVN-01 | Phase 28 | Pending |
| VERI-01 | Phase 29 | Pending |
| VERI-02 | Phase 29 | Pending |
| RVEW-01 | Phase 29 | Pending |
| DCMP-01 | Phase 30 | Pending |
| DCMP-02 | Phase 30 | Pending |

**Coverage:**
- v1.3 requirements: 14 total
- Mapped to phases: 14
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-11*
*Last updated: 2026-03-11 after v1.3 milestone started*
