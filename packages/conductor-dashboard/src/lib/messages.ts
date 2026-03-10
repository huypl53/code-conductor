/**
 * WebSocket message parsing and intervention command serialization utilities.
 *
 * The backend sends two kinds of messages over WebSocket:
 *   1. Snapshots: full ConductorState objects — detected by presence of "version" field
 *   2. Deltas: DeltaEvent objects — detected by presence of "type" field
 *
 * The dashboard sends InterventionCommand objects to the backend.
 */
import type { ConductorState, DeltaEvent, InterventionCommand } from "../types/conductor";

// ---------------------------------------------------------------------------
// Message parsing
// ---------------------------------------------------------------------------

export type ParsedMessage =
  | { kind: "snapshot"; state: ConductorState }
  | { kind: "delta"; event: DeltaEvent }
  | { kind: "error" };

/**
 * Parse a raw WebSocket message string into a typed message.
 *
 * Detection strategy:
 *   - "version" field present -> snapshot (ConductorState)
 *   - "type" field present    -> delta (DeltaEvent)
 *   - otherwise / parse error -> error
 */
export function parseMessage(data: string): ParsedMessage {
  try {
    const parsed = JSON.parse(data) as Record<string, unknown>;
    if ("version" in parsed) {
      return { kind: "snapshot", state: parsed as unknown as ConductorState };
    }
    if ("type" in parsed) {
      return { kind: "delta", event: parsed as unknown as DeltaEvent };
    }
    return { kind: "error" };
  } catch {
    return { kind: "error" };
  }
}

// ---------------------------------------------------------------------------
// Intervention serialization
// ---------------------------------------------------------------------------

/**
 * Serialize an intervention command to a JSON string for sending over WebSocket.
 */
export function serializeIntervention(command: InterventionCommand): string {
  return JSON.stringify(command);
}
