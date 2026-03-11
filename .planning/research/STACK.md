# Stack Research

**Domain:** Interactive chat TUI additions — v1.1 milestone (Conductor)
**Researched:** 2026-03-11
**Confidence:** HIGH

---

## Existing Stack (Validated in v1.0 — Do Not Re-research)

| Technology | Version | Role |
|------------|---------|------|
| `claude-agent-sdk` | `>=0.1.48` | ACP comms, agent spawning |
| `rich` | `>=13` | Terminal display, Live tables |
| `typer` | `>=0.12` | CLI command routing |
| `asyncio` | stdlib | Async event loop |
| `pydantic v2` | `>=2.10` | Data models |
| `fastapi` + `uvicorn` | `>=0.135` / `>=0.41` | Dashboard API server |
| `watchfiles` | `>=1.1` | File watching |

Current input handling (`input_loop.py`) uses `asyncio.to_thread(input, "> ")`. This works for the current command-dispatch loop but cannot support readline history, multiline input, or a stable prompt line that survives concurrent Rich output printing above it.

---

## New Stack Additions for v1.1

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `prompt_toolkit` | `3.0.52` | Interactive terminal input with history, multiline, and concurrent-output safety | The standard for Python TUI input — used by IPython, pgcli, Poetry shell, and Claude Code's own CLI. Provides `PromptSession.prompt_async()` which awaits without blocking the event loop (unlike `asyncio.to_thread(input)`). `patch_stdout()` context manager intercepts all writes to stdout and redraws the prompt correctly when Rich or async code prints mid-turn — this is the critical capability that prevents garbled output when streaming tokens appear alongside an active input line. `FileHistory` persists command history to disk across restarts. |
| `ClaudeSDKClient` (already in `claude-agent-sdk 0.1.48`) | — (no new dep) | Multi-turn conversation with persistent session state | `query()` (used today) creates a fresh Claude Code session each call — no memory of previous turns. `ClaudeSDKClient` reuses the same session across turns, maintains full conversation context, supports `interrupt()` to stop mid-stream, and is the correct API for an interactive chat loop. Already in the existing SDK at the pinned version — no new package needed. |
| `include_partial_messages=True` (SDK option on `ClaudeAgentOptions`) | — (no new dep) | Token-by-token streaming output | Causes the SDK to emit `StreamEvent` messages containing raw `content_block_delta` / `text_delta` events as tokens arrive, before the complete `AssistantMessage` is assembled. Required for the "response streams in real-time" experience that Claude Code and Codex CLI deliver. Without this, the user sees nothing until Claude finishes the entire response. Already in the existing SDK — a one-field change to `ClaudeAgentOptions`. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `prompt_toolkit.history.FileHistory` | bundled in `prompt_toolkit` | Persist chat prompts across sessions | Always — store at `~/.conductor_history` so `Up` arrow recalls previous prompts across restarts |
| `prompt_toolkit.patch_stdout` | bundled | Route concurrent Rich output through prompt redraw | Always in chat mode — without it, streaming token output and Rich status messages overwrite the input line |
| `rich.markdown.Markdown` | bundled in `rich>=13` | Render Claude's markdown responses in the terminal | Use when printing assistant text responses — headings, code fences, bullet lists render correctly; already a zero-cost dep |
| `rich.syntax.Syntax` | bundled in `rich>=13` | Syntax-highlight code blocks in streamed output | For detected code blocks in chat responses; already present |

### Development Tools

No new dev tools needed — `pytest-asyncio` with `asyncio_mode = "auto"` already configured handles async test coverage for the new chat loop.

---

## Installation

```bash
# Single new runtime dependency
uv add "prompt-toolkit>=3.0.52"

# No other new deps:
# - ClaudeSDKClient is already in claude-agent-sdk>=0.1.48
# - include_partial_messages is a ClaudeAgentOptions field, not a new package
# - rich.markdown / rich.syntax are already in rich>=13
```

---

## Integration Pattern: How New Stack Fits the Existing Code

### 1. Replace `_ainput()` in `input_loop.py`

Current code:
```python
async def _ainput(prompt: str = "") -> str:
    return await asyncio.to_thread(input, prompt)
```

The problem: `asyncio.to_thread(input)` blocks the OS thread until Enter is pressed and cannot be cancelled cleanly. It has no readline history and its prompt line is overwritten when Rich or streaming tokens write to stdout.

Replace with `PromptSession.prompt_async()` for the new chat command. The existing `_ainput` and `_input_loop` in `input_loop.py` serve the `conductor run` batch-mode command-dispatch loop and should remain unchanged. The new chat loop lives in a separate module.

```python
# cli/chat.py (new module)
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout
from pathlib import Path

_session = PromptSession(
    history=FileHistory(str(Path.home() / ".conductor_history"))
)

async def chat_loop(repo_path: Path) -> None:
    with patch_stdout():  # all print()/Rich output redraws the prompt safely
        async with ClaudeSDKClient(options=_build_options(repo_path)) as client:
            while True:
                try:
                    text = await _session.prompt_async("conductor> ")
                except (KeyboardInterrupt, EOFError):
                    break
                if not text.strip():
                    continue
                await _send_and_stream(client, text)
```

`patch_stdout()` wraps stdout so that when streaming token output or Rich `console.print()` calls fire during the `await`, they print above the prompt line and the prompt redraws below — the same mechanism used by IPython, Poetry, and similar async CLI tools.

### 2. Switch from `query()` to `ClaudeSDKClient` for chat mode

`conductor run "..."` (batch mode) keeps `query()` — correct for one-shot tasks.

New `conductor` (no args, chat mode) uses `ClaudeSDKClient`:

```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, AssistantMessage, ResultMessage
from claude_agent_sdk.types import StreamEvent

def _build_options(repo_path: Path) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        include_partial_messages=True,   # streaming tokens
        permission_mode="acceptEdits",   # direct tool use
        cwd=str(repo_path),
    )

async def _send_and_stream(client: ClaudeSDKClient, prompt: str) -> None:
    await client.query(prompt)
    in_tool = False
    async for message in client.receive_response():
        if isinstance(message, StreamEvent):
            event = message.event
            etype = event.get("type")
            if etype == "content_block_start":
                block = event.get("content_block", {})
                if block.get("type") == "tool_use":
                    print(f"\n[{block.get('name')}...]", end="", flush=True)
                    in_tool = True
            elif etype == "content_block_delta":
                delta = event.get("delta", {})
                if delta.get("type") == "text_delta" and not in_tool:
                    print(delta.get("text", ""), end="", flush=True)
            elif etype == "content_block_stop" and in_tool:
                print(" done", flush=True)
                in_tool = False
        elif isinstance(message, ResultMessage):
            print()  # final newline after streamed response
```

The `ClaudeSDKClient` session retains full conversation context across turns for the lifetime of the `async with` block — the orchestrator remembers what was said earlier in the same `conductor` invocation.

### 3. Typer entrypoint: route no-args to chat

Current `__init__.py` sets `no_args_is_help=True`. Change to route no-args invocation to the new chat command:

```python
# cli/__init__.py
app = typer.Typer(
    name="conductor",
    help="Conductor: AI agent orchestration",
    invoke_without_command=True,   # changed from no_args_is_help=True
)

@app.callback(invoke_without_command=True)
def default(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        asyncio.run(_chat_async())

app.command("run")(run)
app.command("status")(status)
```

`conductor run "..."` continues to work unchanged. `conductor` (no args) opens the interactive chat TUI.

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| `prompt_toolkit` | Keep `asyncio.to_thread(input)` | Only acceptable if no streaming output, no readline history, and no concurrent Rich printing needed. All three are needed for the chat TUI. |
| `prompt_toolkit` | `readline` (stdlib) | `readline` has no async support and cannot coexist with Rich Live or concurrent async prints. Avoid. |
| `prompt_toolkit` | `Textual` | Textual is better when building a full TUI application with panels, widgets, and mouse events. Overkill here — it would require rewriting the entire display layer. Rich + prompt_toolkit achieves the target UX with ~1 new dependency. |
| `ClaudeSDKClient` | `query()` with manual history | Would require serializing and replaying conversation turns as context every call — brittle, loses tool-use history context, and doesn't support `interrupt()`. `ClaudeSDKClient` handles session continuity natively. |
| `include_partial_messages=True` | Wait for complete `AssistantMessage` | Complete messages only arrive after Claude finishes all thinking and tool execution — no streaming feel, defeats the primary UX goal. |

---

## What NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `aioconsole` | Provides async `ainput()` but no history, completion, or `patch_stdout` equivalent — same fundamental limitation as the current code | `prompt_toolkit` |
| `Textual` | Full TUI framework — compelling but requires rewriting the display layer. Rich + prompt_toolkit achieves the chat TUI with far less disruption to existing code. | Rich (existing) + prompt_toolkit (new) |
| `anthropic` Python SDK (direct) | Bypasses the Claude Agent SDK, loses ACP compatibility, tool execution, and the orchestrator's existing permission model | `claude-agent-sdk` (existing) |
| Any conversation-history store (SQLite, JSON file, etc.) | `ClaudeSDKClient` manages session state internally per-invocation. Cross-session "memory" is already handled by the `.memory/` folder convention from v1.0 | Existing `.memory/` pattern |
| `click` directly | Already have Typer (which wraps Click). Double-dependency confusion. | Typer (already present) |

---

## Stack Patterns by Mode

**Chat mode (`conductor` with no args — NEW):**
- `ClaudeSDKClient` (persistent session across turns) + `include_partial_messages=True`
- `PromptSession.prompt_async()` inside `patch_stdout()` context
- Stream `text_delta` chunks to stdout; show `[tool_name...]` indicator during tool calls
- `FileHistory("~/.conductor_history")` for cross-session prompt history

**Batch mode (`conductor run "..."` — UNCHANGED):**
- Keep existing `query()` + `_display_loop` + `_input_loop` as-is
- No `prompt_toolkit` needed — batch mode is command-dispatch, not a chat prompt

**Smart delegation (orchestrator logic — NOT a stack decision):**
- No new library — the system prompt on `ClaudeSDKClient` instructs the orchestrator when to handle directly vs. spawn sub-agents
- Sub-agent spawning when delegating reuses the existing `Orchestrator` class unchanged

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| `prompt-toolkit==3.0.52` | Python 3.12/3.13, `rich>=13` | No known conflicts. `patch_stdout()` uses stdout wrapping that is compatible with Rich's `Console`. Latest release: 2025-08-27. |
| `claude-agent-sdk>=0.1.48` (current: 0.1.48, released 2026-03-07) | Python 3.12/3.13 | `ClaudeSDKClient` and `include_partial_messages` both confirmed in official docs for this version. |
| `typer>=0.12` with `invoke_without_command=True` | Typer 0.12+ | `@app.callback(invoke_without_command=True)` pattern is stable in Typer 0.12. |

---

## Sources

- [Agent SDK reference - Python](https://platform.claude.com/docs/en/agent-sdk/python) — `ClaudeSDKClient` API, `query()` vs `ClaudeSDKClient` comparison, session continuity — HIGH confidence (official Anthropic docs, verified 2026-03-11)
- [Stream responses in real-time](https://platform.claude.com/docs/en/agent-sdk/streaming-output) — `include_partial_messages`, `StreamEvent`, `text_delta` pattern, streaming UI example — HIGH confidence (official Anthropic docs, verified 2026-03-11)
- [PyPI: claude-agent-sdk](https://pypi.org/project/claude-agent-sdk/) — confirmed current version 0.1.48, released 2026-03-07 — HIGH confidence
- [PyPI: prompt-toolkit](https://pypi.org/project/prompt-toolkit/) — confirmed current version 3.0.52, released 2025-08-27 — HIGH confidence
- [prompt_toolkit docs: Asking for input](https://python-prompt-toolkit.readthedocs.io/en/stable/pages/asking_for_input.html) — `prompt_async()`, `patch_stdout()`, `FileHistory`, `PromptSession` API — HIGH confidence (official docs, verified 2026-03-11)
- [prompt_toolkit asyncio docs](https://python-prompt-toolkit.readthedocs.io/en/master/pages/advanced_topics/asyncio.html) — event loop integration — HIGH confidence (official docs)

---
*Stack research for: Conductor v1.1 — interactive chat TUI additions*
*Researched: 2026-03-11*
