/**
 * TypeScript types mirroring backend Pydantic models exactly.
 *
 * Source of truth: packages/conductor-core/src/conductor/state/models.py
 *                  packages/conductor-core/src/conductor/dashboard/events.py
 *
 * Keep in sync with backend models manually.
 */

// ---------------------------------------------------------------------------
// Enums (mirroring StrEnum values from backend)
// ---------------------------------------------------------------------------

export type TaskStatus =
  | "pending"
  | "in_progress"
  | "completed"
  | "failed"
  | "blocked";

export type ReviewStatus = "pending" | "approved" | "needs_revision";

export type AgentStatus = "idle" | "working" | "waiting" | "done";

export type EventType =
  | "task_assigned"
  | "task_status_changed"
  | "task_completed"
  | "task_failed"
  | "agent_registered"
  | "agent_status_changed"
  | "intervention_needed";

// ---------------------------------------------------------------------------
// Core models (mirroring conductor.state.models)
// ---------------------------------------------------------------------------

export interface Task {
  id: string;
  title: string;
  description: string;
  status: TaskStatus;
  assigned_agent: string | null;
  outputs: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  requires: string[];
  produces: string[];
  target_file: string;
  material_files: string[];
  review_status: ReviewStatus;
  revision_count: number;
}

export interface AgentRecord {
  id: string;
  name: string;
  role: string;
  current_task_id: string | null;
  status: AgentStatus;
  registered_at: string;
  session_id: string | null;
  memory_file: string | null;
  started_at: string | null;
}

export interface Dependency {
  task_id: string;
  depends_on: string;
}

export interface ConductorState {
  version: string;
  tasks: Task[];
  agents: AgentRecord[];
  dependencies: Dependency[];
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Event models (mirroring conductor.dashboard.events)
// ---------------------------------------------------------------------------

export interface DeltaEvent {
  type: EventType;
  task_id: string | null;
  agent_id: string | null;
  payload: Record<string, unknown>;
  is_smart_notification: boolean;
}

// ---------------------------------------------------------------------------
// Dashboard-specific types
// ---------------------------------------------------------------------------

/** Intervention commands sent from dashboard to backend over WebSocket. */
export interface InterventionCommand {
  action: "cancel" | "redirect" | "feedback";
  agent_id: string;
  message?: string;
}

/** UI expansion state for task/agent cards. */
export type ExpansionLevel = "collapsed" | "detail" | "stream";

/** Top-level dashboard reactive state. */
export interface DashboardState {
  conductorState: ConductorState | null;
  events: DeltaEvent[];
  connected: boolean;
}
