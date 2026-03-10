/**
 * Status badge component showing a colored dot and status text.
 * Used in agent cards to indicate current agent status at a glance.
 */
import type { AgentStatus } from "../types/conductor";

const COLOR_MAP: Record<AgentStatus, string> = {
  idle: "bg-gray-400",
  working: "bg-green-500",
  waiting: "bg-yellow-500",
  done: "bg-blue-500",
};

interface StatusBadgeProps {
  status: AgentStatus;
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const dotColor = COLOR_MAP[status];

  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`rounded-full w-2 h-2 flex-shrink-0 ${dotColor}`} />
      <span className="text-sm text-gray-700">{status}</span>
    </span>
  );
}
