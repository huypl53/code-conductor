/**
 * NotificationProvider component and useSmartNotifications hook.
 *
 * Wraps Sonner's Toaster and provides smart toast notifications for
 * task_completed, task_failed, and intervention_needed events.
 */
import { useEffect, useRef } from "react";
import { Toaster, toast } from "sonner";
import type { DeltaEvent, EventType } from "../types/conductor";

// ---------------------------------------------------------------------------
// NotificationProvider component
// ---------------------------------------------------------------------------

/**
 * Renders the Sonner Toaster at top-right. Place once near the root of the app.
 */
export function NotificationProvider() {
  return <Toaster position="top-right" />;
}

// ---------------------------------------------------------------------------
// useSmartNotifications hook
// ---------------------------------------------------------------------------

const SMART_NOTIFICATION_TYPES: Set<EventType> = new Set([
  "task_completed",
  "task_failed",
  "intervention_needed",
]);

/**
 * Processes new DeltaEvents and fires Sonner toasts for smart notification events.
 *
 * Tracks a lastProcessed index to avoid re-firing toasts for already-seen events.
 * Call this once in the App component body, passing the events array from useConductorSocket.
 */
export function useSmartNotifications(events: DeltaEvent[]): void {
  const lastProcessed = useRef<number>(0);

  useEffect(() => {
    const unprocessed = events.slice(lastProcessed.current);

    for (const event of unprocessed) {
      if (!event.is_smart_notification) continue;
      if (!SMART_NOTIFICATION_TYPES.has(event.type)) continue;

      if (event.type === "task_completed") {
        toast.success(`Task completed: ${event.task_id}`);
      } else if (event.type === "task_failed") {
        toast.error(`Task failed: ${event.task_id}`);
      } else if (event.type === "intervention_needed") {
        toast.warning(`Agent ${event.agent_id} needs intervention`, {
          duration: Infinity,
        });
      }
    }

    lastProcessed.current = events.length;
  }, [events]);
}
