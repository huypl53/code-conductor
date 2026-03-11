# Requirements: Conductor

**Defined:** 2026-03-12
**Core Value:** A product owner describes a feature, and a self-organizing team of AI coding agents delivers quality, reviewed, tested code — with the human staying in control when they want to be.

## v2.2 Requirements

Requirements for the Agent Visibility milestone. Each maps to roadmap phases.

### Agent Cells

- [ ] **ACELL-01**: User sees a labeled AgentCell in the transcript when a sub-agent starts working, showing agent name, role, and task title
- [ ] **ACELL-02**: AgentCell updates in real-time as state.json changes (status transitions: working → waiting → done)
- [ ] **ACELL-03**: When an agent completes, its AgentCell shows a completion summary with final status
- [ ] **ACELL-04**: Multiple concurrent AgentCells render independently without interfering with each other

### Orchestrator Status

- [ ] **ORCH-01**: User sees orchestrator status in the transcript when it transitions to planning/delegating (label changes from "Assistant" to "Orchestrator — delegating")
- [ ] **ORCH-02**: When delegation starts, the transcript shows which agents were spawned and what tasks they received

### Stream Interception

- [ ] **STRM-01**: SDK stream tool_use events for conductor_delegate are intercepted and trigger agent visibility updates in the transcript
- [ ] **STRM-02**: Tool-use input (task description, agent config) is accumulated from input_json_delta events before being used to create AgentCells

### State Bridge

- [ ] **BRDG-01**: AgentStateUpdated messages from state.json watcher are forwarded to TranscriptPane (not just AgentMonitorPane)
- [ ] **BRDG-02**: TranscriptPane maintains an _agent_cells registry mapping agent_id to AgentCell for lifecycle management

## Future Requirements

Deferred to a later release. Tracked but not in current roadmap.

### Agent Deep Dive

- **DEEP-01**: User can expand an AgentCell to see detailed tool activity (files read, edited, commands run)
- **DEEP-02**: User can click an AgentCell to open a full sub-agent transcript view

### Advanced Visibility

- **ADVS-01**: Orchestrator planning phase shows decomposition tree before delegation
- **ADVS-02**: Real-time token streaming from individual sub-agents into their AgentCells

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Full sub-agent transcript replay in main view | Interleaved token streams from N concurrent agents is illegible — confirmed anti-feature by Codex RFC |
| Live sub-agent token streaming | Sub-agents run inside DelegationManager.handle_delegate() — not visible to orchestrator's receive_response() loop |
| Replacing AgentMonitorPane | Monitor pane serves a different purpose (collapsible panels); transcript cells complement it |
| Custom agent color themes per role | Defer to visual polish milestone — use accent colors from existing CSS |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| ACELL-01 | - | Pending |
| ACELL-02 | - | Pending |
| ACELL-03 | - | Pending |
| ACELL-04 | - | Pending |
| ORCH-01 | - | Pending |
| ORCH-02 | - | Pending |
| STRM-01 | - | Pending |
| STRM-02 | - | Pending |
| BRDG-01 | - | Pending |
| BRDG-02 | - | Pending |

**Coverage:**
- v2.2 requirements: 10 total
- Mapped to phases: 0
- Unmapped: 10 ⚠️

---
*Requirements defined: 2026-03-12*
*Last updated: 2026-03-12 after initial definition*
