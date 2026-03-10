/**
 * AgentCard component showing a collapsed summary of an agent's current state.
 *
 * Three expansion levels:
 *   collapsed - header only (name, role, task, status badge)
 *   detail    - expands to show recent actions placeholder
 *   stream    - expands further to show live stream placeholder
 *
 * Defaults to collapsed (DASH-05).
 */
import { useState } from "react";
import type {
  AgentRecord,
  Task,
  DeltaEvent,
  InterventionCommand,
  ExpansionLevel,
} from "../types/conductor";
import { StatusBadge } from "./StatusBadge";

interface AgentCardProps {
  agent: AgentRecord;
  tasks: Task[];
  events: DeltaEvent[];
  onIntervene?: (command: InterventionCommand) => void;
}

export function AgentCard({ agent, tasks }: AgentCardProps) {
  const [expansion, setExpansion] = useState<ExpansionLevel>("collapsed");

  const currentTask = agent.current_task_id
    ? tasks.find((t) => t.id === agent.current_task_id)
    : null;

  const taskTitle = currentTask ? currentTask.title : "No task assigned";

  function toggleExpansion() {
    setExpansion((prev) => (prev === "collapsed" ? "detail" : "collapsed"));
  }

  const isExpanded = expansion !== "collapsed";

  return (
    <div className="rounded-lg border border-gray-200 bg-white shadow-sm transition-all duration-200">
      {/* Collapsed header (always visible) */}
      <button
        type="button"
        onClick={toggleExpansion}
        className="w-full flex items-center gap-3 px-4 py-3 text-left"
        aria-expanded={isExpanded}
      >
        {/* Chevron icon */}
        <svg
          className={`w-4 h-4 flex-shrink-0 text-gray-400 transition-transform duration-200 ${isExpanded ? "rotate-90" : ""}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>

        {/* Agent name and role */}
        <div className="flex-1 min-w-0">
          <div className="font-medium text-gray-900 truncate">{agent.name}</div>
          <div className="text-xs text-gray-500 truncate">{agent.role}</div>
        </div>

        {/* Task title */}
        <div className="text-sm text-gray-600 truncate max-w-[40%]">{taskTitle}</div>

        {/* Status badge */}
        <StatusBadge status={agent.status} />
      </button>

      {/* Detail section */}
      {expansion !== "collapsed" && (
        <div className="px-4 pb-4 border-t border-gray-100">
          <div className="pt-3">
            <p className="text-sm text-gray-500">Recent actions</p>
            <button
              type="button"
              onClick={() => setExpansion("stream")}
              className="mt-2 text-xs text-blue-600 hover:underline"
            >
              Show live stream
            </button>
          </div>
        </div>
      )}

      {/* Stream section */}
      {expansion === "stream" && (
        <div className="px-4 pb-4">
          <p className="text-sm text-gray-500">Live stream</p>
        </div>
      )}
    </div>
  );
}
