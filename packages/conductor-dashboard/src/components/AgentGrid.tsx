/**
 * AgentGrid component — responsive grid layout for all agent cards.
 *
 * Renders one AgentCard per agent in a responsive CSS grid.
 * Shows an empty state message when no agents are registered.
 */
import type {
  AgentRecord,
  Task,
  DeltaEvent,
  InterventionCommand,
} from "../types/conductor";
import { AgentCard } from "./AgentCard";

interface AgentGridProps {
  agents: AgentRecord[];
  tasks: Task[];
  events: DeltaEvent[];
  onIntervene?: (command: InterventionCommand) => void;
}

export function AgentGrid({ agents, tasks, events, onIntervene }: AgentGridProps) {
  if (agents.length === 0) {
    return (
      <div className="flex items-center justify-center py-16 text-gray-400">
        <p className="text-lg">No agents running</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      {agents.map((agent) => (
        <AgentCard
          key={agent.id}
          agent={agent}
          tasks={tasks}
          events={events}
          onIntervene={onIntervene}
        />
      ))}
    </div>
  );
}
