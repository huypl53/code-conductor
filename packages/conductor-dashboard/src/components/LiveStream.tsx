/**
 * LiveStream component — real-time event log filtered by agent.
 *
 * Renders a terminal-like scrollable list of DeltaEvents for a specific agent.
 * Auto-scrolls to the bottom when new events arrive.
 */
import { useEffect, useRef } from "react";
import type { DeltaEvent } from "../types/conductor";

interface LiveStreamProps {
  agentId: string;
  events: DeltaEvent[];
}

const EVENT_TYPE_COLORS: Record<string, string> = {
  task_assigned: "text-blue-400",
  task_status_changed: "text-yellow-400",
  task_completed: "text-green-400",
  task_failed: "text-red-400",
  agent_registered: "text-purple-400",
  agent_status_changed: "text-cyan-400",
  intervention_needed: "text-orange-400",
};

export function LiveStream({ agentId, events }: LiveStreamProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  const agentEvents = events.filter((e) => e.agent_id === agentId);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [agentEvents.length]);

  if (agentEvents.length === 0) {
    return (
      <div className="bg-gray-900 rounded p-3 max-h-64 overflow-y-auto">
        <p className="text-gray-500 font-mono text-xs">No events yet</p>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="bg-gray-900 rounded p-3 max-h-64 overflow-y-auto"
    >
      <ul className="space-y-1">
        {agentEvents.map((event, index) => {
          const colorClass = EVENT_TYPE_COLORS[event.type] ?? "text-gray-400";
          return (
            <li key={index} className="font-mono text-xs flex gap-2">
              <span className="text-gray-600 flex-shrink-0">{String(index).padStart(3, "0")}</span>
              <span className={`flex-shrink-0 ${colorClass}`}>{event.type}</span>
              {event.task_id && (
                <span className="text-gray-400">{event.task_id}</span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
