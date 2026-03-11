/**
 * InterventionPanel component — cancel, redirect, and feedback controls.
 *
 * Provides three action buttons for operator interventions.
 * Cancel fires immediately; Feedback and Redirect open inline inputs.
 */
import { useState } from "react";
import type { InterventionCommand } from "../types/conductor";

interface InterventionPanelProps {
  agentId: string;
  onIntervene: (command: InterventionCommand) => void;
}

type ActiveInput = "feedback" | "redirect" | "pause" | null;

export function InterventionPanel({ agentId, onIntervene }: InterventionPanelProps) {
  const [activeInput, setActiveInput] = useState<ActiveInput>(null);
  const [message, setMessage] = useState("");

  function handleCancel() {
    onIntervene({ action: "cancel", agent_id: agentId });
  }

  function handleToggle(type: "feedback" | "redirect" | "pause") {
    if (activeInput === type) {
      setActiveInput(null);
      setMessage("");
    } else {
      setActiveInput(type);
      setMessage("");
    }
  }

  function handleSend() {
    if (!activeInput || !message.trim()) return;
    onIntervene({ action: activeInput, agent_id: agentId, message });
    setActiveInput(null);
    setMessage("");
  }

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <button
          type="button"
          onClick={handleCancel}
          className="px-3 py-1.5 text-xs font-medium rounded bg-red-100 text-red-700 hover:bg-red-200 transition-colors"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={() => handleToggle("feedback")}
          className={`px-3 py-1.5 text-xs font-medium rounded transition-colors ${
            activeInput === "feedback"
              ? "bg-blue-600 text-white"
              : "bg-blue-100 text-blue-700 hover:bg-blue-200"
          }`}
        >
          Feedback
        </button>
        <button
          type="button"
          onClick={() => handleToggle("redirect")}
          className={`px-3 py-1.5 text-xs font-medium rounded transition-colors ${
            activeInput === "redirect"
              ? "bg-amber-600 text-white"
              : "bg-amber-100 text-amber-700 hover:bg-amber-200"
          }`}
        >
          Redirect
        </button>
        <button
          type="button"
          onClick={() => handleToggle("pause")}
          className={`px-3 py-1.5 text-xs font-medium rounded transition-colors ${
            activeInput === "pause"
              ? "bg-purple-600 text-white"
              : "bg-purple-100 text-purple-700 hover:bg-purple-200"
          }`}
        >
          Pause
        </button>
      </div>

      {activeInput !== null && (
        <div className="flex gap-2 transition-all">
          <input
            type="text"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder={
              activeInput === "feedback"
                ? "Send feedback to agent..."
                : activeInput === "redirect"
                ? "New instructions for agent..."
                : "Question for the human..."
            }
            onKeyDown={(e) => {
              if (e.key === "Enter" && message.trim()) handleSend();
            }}
            className="flex-1 text-xs px-3 py-1.5 rounded border border-gray-300 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
          <button
            type="button"
            onClick={handleSend}
            disabled={!message.trim()}
            className="px-3 py-1.5 text-xs font-medium rounded bg-gray-800 text-white hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Send
          </button>
        </div>
      )}
    </div>
  );
}
