"""Async input loop for interactive conductor CLI sessions.

Reads commands from the terminal concurrently with agent question events from
the human_out queue.  Commands are dispatched to orchestrator methods.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from rich.console import Console

from conductor.cli.display import _build_table

if TYPE_CHECKING:
    from conductor.state.manager import StateManager


async def _ainput(prompt: str = "") -> str:
    """Async wrapper around blocking input() using asyncio.to_thread."""
    return await asyncio.to_thread(input, prompt)


async def _dispatch_command(
    line: str,
    orchestrator: object,
    state_manager: StateManager | None = None,
    console: Console | None = None,
) -> bool:
    """Parse and dispatch a single CLI command line.

    Returns True if the loop should exit (quit/exit), False otherwise.
    """
    if console is None:
        console = Console(stderr=True)

    tokens = line.strip().split()
    if not tokens:
        return False

    cmd = tokens[0].lower()

    if cmd == "cancel":
        if len(tokens) < 2:
            console.print("[red]Usage: cancel <agent_id>[/]")
            return False
        agent_id = tokens[1]
        await orchestrator.cancel_agent(agent_id)  # type: ignore[union-attr]
        console.print(f"[green]Cancelled agent {agent_id}[/]")

    elif cmd == "feedback":
        if len(tokens) < 3:
            console.print("[red]Usage: feedback <agent_id> <message...>[/]")
            return False
        agent_id = tokens[1]
        message = " ".join(tokens[2:])
        await orchestrator.inject_guidance(agent_id, message)  # type: ignore[union-attr]
        console.print(f"[green]Sent feedback to agent {agent_id}[/]")

    elif cmd == "redirect":
        if len(tokens) < 3:
            console.print("[red]Usage: redirect <agent_id> <new_instructions...>[/]")
            return False
        agent_id = tokens[1]
        new_instructions = " ".join(tokens[2:])
        await orchestrator.cancel_agent(agent_id, new_instructions=new_instructions)  # type: ignore[union-attr]
        console.print(f"[green]Redirected agent {agent_id}[/]")

    elif cmd == "status":
        if state_manager is None:
            console.print("No state manager available")
        else:
            state = await asyncio.to_thread(state_manager.read_state)
            console.print(_build_table(state))

    elif cmd in ("quit", "exit"):
        return True

    else:
        console.print(
            f"Unknown command: {cmd}. Available: cancel, feedback, redirect, status, quit"
        )

    return False


async def _input_loop(
    human_out: asyncio.Queue,  # type: ignore[type-arg]
    human_in: asyncio.Queue,  # type: ignore[type-arg]
    orchestrator: object,
    state_manager: StateManager | None = None,
    console: Console | None = None,
) -> None:
    """Concurrent input loop: reads typed commands and agent questions simultaneously.

    Uses asyncio.wait(FIRST_COMPLETED) to race terminal input against incoming
    HumanQuery objects from the orchestrator.

    Exits when:
    - The user types quit/exit.
    - The coroutine is cancelled (e.g. when asyncio.gather finishes).
    """
    if console is None:
        console = Console(stderr=True)

    input_task: asyncio.Task[str] = asyncio.create_task(_ainput("> "))
    queue_task: asyncio.Task[object] = asyncio.create_task(human_out.get())

    try:
        while True:
            done, pending = await asyncio.wait(
                {input_task, queue_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            if queue_task in done:
                # An agent has a question for the human
                query = queue_task.result()
                console.print(f"\n[bold yellow]Agent question:[/] {query.question}")
                answer = await _ainput("Your answer: ")
                await human_in.put(answer)
                # Recreate queue task for next question
                queue_task = asyncio.create_task(human_out.get())

            if input_task in done:
                # User typed a command
                line = input_task.result().strip()
                if line:
                    should_exit = await _dispatch_command(
                        line, orchestrator, state_manager=state_manager, console=console
                    )
                    if should_exit:
                        break
                # Recreate input task for next command
                input_task = asyncio.create_task(_ainput("> "))

    except asyncio.CancelledError:
        # Normal shutdown — gather was cancelled when orchestrator finished
        pass
    finally:
        # Cancel any pending tasks on exit
        for task in (input_task, queue_task):
            if not task.done():
                task.cancel()
