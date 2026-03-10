"""ORCH-01: TaskDecomposer — structured decomposition via SDK query()."""
from __future__ import annotations

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

from conductor.orchestrator.errors import DecompositionError
from conductor.orchestrator.models import TaskPlan

# ---------------------------------------------------------------------------
# Decomposition prompt template
# ---------------------------------------------------------------------------

DECOMPOSE_PROMPT_TEMPLATE = """\
You are a software architect and project coordinator. \
You do not write code. Your only job is to decompose a feature description \
into a structured task plan that can be assigned to coding agents.

Analyse the feature description below and produce a TaskPlan JSON object.
Each task must specify exactly one target_file that the agent will modify.
Tasks may declare file dependencies using the requires field (list of other task IDs).

<feature_description>
{feature_description}
</feature_description>

Return a valid TaskPlan JSON object according to the provided schema.
"""

_MAX_TURNS = 3


class TaskDecomposer:
    """Decomposes a feature description into a TaskPlan via SDK structured output.

    Uses the Claude SDK query() function with an output_format schema so the
    model is constrained to return a valid TaskPlan JSON object.

    Raises:
        DecompositionError: If the SDK fails to produce a valid structured
            output after max retries, or returns no result at all.
    """

    async def decompose(self, feature_description: str) -> TaskPlan:
        """Decompose *feature_description* into a TaskPlan.

        Args:
            feature_description: Natural language description of the feature
                to be implemented.

        Returns:
            A validated TaskPlan containing task specs for the feature.

        Raises:
            DecompositionError: On schema retry exhaustion, empty response,
                or None structured output.
        """
        prompt = DECOMPOSE_PROMPT_TEMPLATE.format(
            feature_description=feature_description
        )
        options = ClaudeAgentOptions(
            output_format={
                "type": "json_schema",
                "schema": TaskPlan.model_json_schema(),
            },
            max_turns=_MAX_TURNS,
        )

        result: ResultMessage | None = None

        async for message in query(prompt=prompt, options=options):
            if isinstance(message, ResultMessage):
                if message.subtype == "error_max_structured_output_retries":
                    raise DecompositionError(
                        "Decomposition failed: max structured output "
                        "retry limit reached"
                    )
                result = message
                break  # first ResultMessage is the final result

        if result is None:
            raise DecompositionError(
                "No result received from decomposition query"
            )

        if result.structured_output is None:
            raise DecompositionError(
                "No structured output in decomposition result"
            )

        return TaskPlan.model_validate(result.structured_output)
