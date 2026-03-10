/**
 * AgentCard component showing a collapsed summary of an agent's current state.
 *
 * Three expansion levels:
 *   collapsed - header only (name, role, task, status badge)
 *   detail    - expands to show recent actions, files modified, intervention controls
 *   stream    - expands further to show live event stream
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
import { InterventionPanel } from "./InterventionPanel";
import { LiveStream } from "./LiveStream";

interface AgentCardProps {
  agent: AgentRecord;
  tasks: Task[];
  events: DeltaEvent[];
  onIntervene?: (command: InterventionCommand) => void;
}

const MAX_RECENT_EVENTS = 10;

export function AgentCard({ agent, tasks, events, onIntervene }: AgentCardProps) {
  const [expansion, setExpansion] = useState<ExpansionLevel>("collapsed");

  const currentTask = agent.current_task_id
    ? tasks.find((t) => t.id === agent.current_task_id)
    : null;

  const taskTitle = currentTask ? currentTask.title : "No task assigned";

  const agentEvents = events
    .filter((e) => e.agent_id === agent.id)
    .slice(-MAX_RECENT_EVENTS);

  function toggleExpansion() {
    setExpansion((prev) => (prev === "collapsed" ? "detail" : "collapsed"));
  }

  function toggleStream() {
    setExpansion((prev) => (prev === "stream" ? "detail" : "stream"));
  }

  const isExpanded = expansion !== "collapsed";

  // No-op intervention handler if none provided
  const handleIntervene = onIntervene ?? (() => {});

  return (
    <div className="rounded-lg border border-gray-200 bg-white shadow-sm transition-all duration-200">
      {/* Collapsed header (always visible) */}
      <button
        type="button"
        onClick={toggleExpansion}
        className="w-full flex items-center gap-3 px-4 py-3 text-left"
        aria-expanded={isExpanded}
        aria-label={agent.name}
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

      {/* Detail section (visible when not collapsed) */}
      {expansion !== "collapsed" && (
        <div className="px-4 pb-4 border-t border-gray-100 space-y-4">
          {/* Recent Actions */}
          <div className="pt-3">
            <h3 className="text-xs font-semibold text-gray-700 uppercase tracking-wide mb-2">
              Recent Actions
            </h3>
            {agentEvents.length === 0 ? (
              <p className="text-xs text-gray-400">No recent activity</p>
            ) : (
              <ul className="space-y-1">
                {agentEvents.map((event, index) => (
                  <li key={index} className="text-xs text-gray-600">
                    <span className="font-mono">{event.type}</span>
                    {event.task_id && (
                      <span className="text-gray-400 ml-1">task: {event.task_id}</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Files */}
          <div>
            <h3 className="text-xs font-semibold text-gray-700 uppercase tracking-wide mb-2">
              Files
            </h3>
            {currentTask ? (
              <ul className="space-y-1">
                {currentTask.target_file && (
                  <li className="text-xs font-mono text-gray-600">{currentTask.target_file}</li>
                )}
                {currentTask.material_files.map((file) => (
                  <li key={file} className="text-xs font-mono text-gray-400">
                    {file}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-gray-400">No files</p>
            )}
          </div>

          {/* Intervention Controls */}
          <InterventionPanel agentId={agent.id} onIntervene={handleIntervene} />

          {/* Live stream toggle */}
          <button
            type="button"
            onClick={toggleStream}
            className="text-xs text-blue-600 hover:underline"
          >
            {expansion === "stream" ? "Hide live stream" : "Show live stream"}
          </button>
        </div>
      )}

      {/* Stream section */}
      {expansion === "stream" && (
        <div className="px-4 pb-4">
          <LiveStream agentId={agent.id} events={events} />
        </div>
      )}
    </div>
  );
}
