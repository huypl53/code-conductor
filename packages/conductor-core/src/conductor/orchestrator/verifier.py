"""VERI-01/02: TaskVerifier — stub detection and wiring checks.

Verifies that agent output is substantive (not stubs) and properly wired
into the project by at least one other file referencing the target basename.
"""
from __future__ import annotations

import asyncio
import re
import subprocess
from pathlib import Path

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Default stub patterns
# ---------------------------------------------------------------------------

DEFAULT_STUB_PATTERNS: list[str] = [
    r"^\s*pass\s*$",                  # pass-only line
    r"raise\s+NotImplementedError",   # NotImplementedError raise
    r"#\s*TODO",                      # TODO markers
    r"^\s*return\s+None\s*$",         # explicit return None
    r"^\s*return\s*$",                # bare return
    r"\.\.\.\s*$",                    # ellipsis body
]


# ---------------------------------------------------------------------------
# VerificationResult model
# ---------------------------------------------------------------------------


class VerificationResult(BaseModel):
    """Three-level result from TaskVerifier.verify()."""

    exists: bool
    substantive: bool
    wired: bool
    stub_matches: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# TaskVerifier
# ---------------------------------------------------------------------------


def _count_substantive_lines(content: str) -> int:
    """Count non-empty, non-comment lines of code."""
    count = 0
    for line in content.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            count += 1
    return count


class TaskVerifier:
    """Verifies agent output files for existence, substance, and project wiring."""

    def __init__(
        self,
        repo_path: str,
        stub_patterns: list[str] | None = None,
    ) -> None:
        self._repo_path = repo_path
        patterns = stub_patterns if stub_patterns is not None else DEFAULT_STUB_PATTERNS
        self._compiled = [
            re.compile(p, re.MULTILINE | re.IGNORECASE)
            for p in patterns
        ]
        self._raw_patterns = patterns

    async def verify(self, target_file: str) -> VerificationResult:
        """Verify target_file for existence, substance, and wiring.

        Args:
            target_file: Relative path to the file under repo_path.

        Returns:
            VerificationResult with exists, substantive, wired, stub_matches.
        """
        target_path = Path(self._repo_path) / target_file

        # Existence check
        try:
            content = await asyncio.to_thread(
                target_path.read_text, encoding="utf-8"
            )
        except FileNotFoundError:
            return VerificationResult(
                exists=False, substantive=False, wired=False
            )

        # Stub detection: check each compiled pattern
        stub_matches: list[str] = []
        for i, compiled in enumerate(self._compiled):
            if compiled.search(content):
                stub_matches.append(self._raw_patterns[i])

        # Substantive heuristic: stub patterns matched AND low line count
        substantive_line_count = _count_substantive_lines(content)
        if stub_matches and substantive_line_count < 10:
            substantive = False
        else:
            substantive = True

        # Wiring check via grep — use stem (no extension) so "mymodule.py" matches
        # both `import mymodule` and `from src.mymodule import ...`
        target_stem = target_path.stem
        wired = await asyncio.to_thread(
            self._check_wiring, target_stem, str(target_path)
        )

        return VerificationResult(
            exists=True,
            substantive=substantive,
            wired=wired,
            stub_matches=stub_matches,
        )

    def _check_wiring(self, target_stem: str, target_full_path: str) -> bool:
        """Use grep to find files that reference target_stem (filename without extension).

        Searching by stem (e.g. "mymodule") catches `import mymodule`,
        `from pkg.mymodule import ...`, and string references like "mymodule".

        Returns True if at least one file other than target itself references it.
        """
        result = subprocess.run(
            [
                "grep",
                "-rl",
                "--include=*.py",
                "--include=*.ts",
                "--include=*.js",
                target_stem,
                self._repo_path,
            ],
            capture_output=True,
            text=True,
        )
        # Filter out the target file itself
        referencing_files = [
            f for f in result.stdout.splitlines()
            if f and f != target_full_path
        ]
        return len(referencing_files) > 0
