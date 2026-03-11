"""VERI-01/02 tests: TaskVerifier stub detection and wiring checks."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from conductor.orchestrator.verifier import (
    DEFAULT_STUB_PATTERNS,
    TaskVerifier,
    VerificationResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(tmp_path: Path, rel_path: str, content: str) -> Path:
    """Write content to a relative path inside tmp_path, creating parents."""
    full = tmp_path / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content)
    return full


# ---------------------------------------------------------------------------
# VerificationResult model
# ---------------------------------------------------------------------------


class TestVerificationResult:
    """VerificationResult has three bool fields plus stub_matches list."""

    def test_has_exists_field(self) -> None:
        r = VerificationResult(exists=True, substantive=True, wired=True)
        assert r.exists is True

    def test_has_substantive_field(self) -> None:
        r = VerificationResult(exists=True, substantive=False, wired=False)
        assert r.substantive is False

    def test_has_wired_field(self) -> None:
        r = VerificationResult(exists=True, substantive=True, wired=False)
        assert r.wired is False

    def test_has_stub_matches_default_empty(self) -> None:
        r = VerificationResult(exists=True, substantive=True, wired=True)
        assert r.stub_matches == []

    def test_stub_matches_populated(self) -> None:
        r = VerificationResult(
            exists=True, substantive=False, wired=False, stub_matches=["pass"]
        )
        assert "pass" in r.stub_matches


# ---------------------------------------------------------------------------
# DEFAULT_STUB_PATTERNS exported
# ---------------------------------------------------------------------------


class TestDefaultStubPatterns:
    """DEFAULT_STUB_PATTERNS is a non-empty list of strings."""

    def test_is_list(self) -> None:
        assert isinstance(DEFAULT_STUB_PATTERNS, list)

    def test_is_nonempty(self) -> None:
        assert len(DEFAULT_STUB_PATTERNS) >= 4

    def test_all_strings(self) -> None:
        assert all(isinstance(p, str) for p in DEFAULT_STUB_PATTERNS)


# ---------------------------------------------------------------------------
# Missing file
# ---------------------------------------------------------------------------


class TestVerifyMissingFile:
    """verify() returns all-False when file does not exist."""

    @pytest.mark.asyncio
    async def test_missing_file_all_false(self, tmp_path: Path) -> None:
        verifier = TaskVerifier(repo_path=str(tmp_path))
        result = await verifier.verify("nonexistent/file.py")
        assert result.exists is False
        assert result.substantive is False
        assert result.wired is False


# ---------------------------------------------------------------------------
# Stub pattern detection
# ---------------------------------------------------------------------------


class TestStubDetection:
    """verify() returns substantive=False for stub files matching known patterns."""

    @pytest.mark.asyncio
    async def test_pass_only_function(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "src/stub.py",
            "def my_func():\n    pass\n",
        )
        verifier = TaskVerifier(repo_path=str(tmp_path))
        result = await verifier.verify("src/stub.py")
        assert result.exists is True
        assert result.substantive is False

    @pytest.mark.asyncio
    async def test_not_implemented_error(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "src/stub.py",
            "def my_func():\n    raise NotImplementedError\n",
        )
        verifier = TaskVerifier(repo_path=str(tmp_path))
        result = await verifier.verify("src/stub.py")
        assert result.exists is True
        assert result.substantive is False

    @pytest.mark.asyncio
    async def test_todo_marker(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "src/stub.py",
            "def my_func():\n    # TODO: implement\n    pass\n",
        )
        verifier = TaskVerifier(repo_path=str(tmp_path))
        result = await verifier.verify("src/stub.py")
        assert result.exists is True
        assert result.substantive is False

    @pytest.mark.asyncio
    async def test_return_none_only(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "src/stub.py",
            "def my_func():\n    return None\n",
        )
        verifier = TaskVerifier(repo_path=str(tmp_path))
        result = await verifier.verify("src/stub.py")
        assert result.exists is True
        assert result.substantive is False

    @pytest.mark.asyncio
    async def test_bare_return(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "src/stub.py",
            "def my_func():\n    return\n",
        )
        verifier = TaskVerifier(repo_path=str(tmp_path))
        result = await verifier.verify("src/stub.py")
        assert result.exists is True
        assert result.substantive is False

    @pytest.mark.asyncio
    async def test_ellipsis_body(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "src/stub.py",
            "def my_func():\n    ...\n",
        )
        verifier = TaskVerifier(repo_path=str(tmp_path))
        result = await verifier.verify("src/stub.py")
        assert result.exists is True
        assert result.substantive is False

    @pytest.mark.asyncio
    async def test_stub_matches_populated_on_stub(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "src/stub.py",
            "def my_func():\n    pass\n",
        )
        verifier = TaskVerifier(repo_path=str(tmp_path))
        result = await verifier.verify("src/stub.py")
        assert len(result.stub_matches) > 0


# ---------------------------------------------------------------------------
# Substantive file detection
# ---------------------------------------------------------------------------


class TestSubstantiveDetection:
    """verify() returns substantive=True for real implementations."""

    @pytest.mark.asyncio
    async def test_real_implementation(self, tmp_path: Path) -> None:
        content = "\n".join(
            [
                "import os",
                "import sys",
                "",
                "",
                "def authenticate(username: str, password: str) -> bool:",
                "    if not username or not password:",
                "        return False",
                "    hashed = hash_password(password)",
                "    user = db.get_user(username)",
                "    if user is None:",
                "        return False",
                "    return user.password_hash == hashed",
                "",
                "",
                "def hash_password(password: str) -> str:",
                "    import hashlib",
                "    return hashlib.sha256(password.encode()).hexdigest()",
            ]
        )
        _write(tmp_path, "src/auth.py", content)
        verifier = TaskVerifier(repo_path=str(tmp_path))
        result = await verifier.verify("src/auth.py")
        assert result.exists is True
        assert result.substantive is True


# ---------------------------------------------------------------------------
# Wiring check
# ---------------------------------------------------------------------------


class TestWiringCheck:
    """verify() checks if another file imports/references target file basename."""

    @pytest.mark.asyncio
    async def test_wired_when_imported(self, tmp_path: Path) -> None:
        # Target file with real implementation
        content = "\n".join(
            [
                "import os",
                "",
                "def do_something():",
                "    x = os.path.join('a', 'b')",
                "    y = x.upper()",
                "    return y + 'extra'",
                "",
                "def helper():",
                "    return do_something().strip()",
                "",
                "class MyClass:",
                "    def method(self):",
                "        return 42",
            ]
        )
        _write(tmp_path, "src/mymodule.py", content)
        # Another file that imports the target
        _write(tmp_path, "src/main.py", "from src.mymodule import do_something\n")

        verifier = TaskVerifier(repo_path=str(tmp_path))
        result = await verifier.verify("src/mymodule.py")
        assert result.wired is True

    @pytest.mark.asyncio
    async def test_not_wired_when_not_imported(self, tmp_path: Path) -> None:
        content = "\n".join(
            [
                "import os",
                "",
                "def do_something():",
                "    x = os.path.join('a', 'b')",
                "    y = x.upper()",
                "    return y + 'extra'",
                "",
                "def helper():",
                "    return do_something().strip()",
                "",
                "class MyClass:",
                "    def method(self):",
                "        return 42",
            ]
        )
        _write(tmp_path, "src/isolated.py", content)
        # No other file references it

        verifier = TaskVerifier(repo_path=str(tmp_path))
        result = await verifier.verify("src/isolated.py")
        assert result.wired is False

    @pytest.mark.asyncio
    async def test_wired_via_string_reference(self, tmp_path: Path) -> None:
        """wired=True even if referenced as string (e.g. config file)."""
        content = "\n".join(
            [
                "import os",
                "",
                "def do_something():",
                "    x = os.path.join('a', 'b')",
                "    y = x.upper()",
                "    return y + 'extra'",
                "",
                "class MyClass:",
                "    def method(self):",
                "        return 42",
                "",
                "def more():",
                "    pass",
            ]
        )
        _write(tmp_path, "src/service.py", content)
        # A JS file references it
        _write(tmp_path, "src/loader.js", 'require("./service")\n')

        verifier = TaskVerifier(repo_path=str(tmp_path))
        result = await verifier.verify("src/service.py")
        assert result.wired is True


# ---------------------------------------------------------------------------
# Custom stub patterns
# ---------------------------------------------------------------------------


class TestCustomStubPatterns:
    """TaskVerifier accepts custom stub_patterns list."""

    @pytest.mark.asyncio
    async def test_custom_pattern_triggers_stub(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "src/stub.py",
            "def my_func():\n    STUB_ME_OUT = True\n",
        )
        verifier = TaskVerifier(
            repo_path=str(tmp_path), stub_patterns=["STUB_ME_OUT"]
        )
        result = await verifier.verify("src/stub.py")
        assert result.substantive is False

    @pytest.mark.asyncio
    async def test_default_patterns_used_when_none_given(
        self, tmp_path: Path
    ) -> None:
        _write(tmp_path, "src/stub.py", "def f():\n    pass\n")
        verifier = TaskVerifier(repo_path=str(tmp_path))
        result = await verifier.verify("src/stub.py")
        # Default patterns include pass-only, should catch this
        assert result.substantive is False
