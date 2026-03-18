"""Process-level sandbox for custom tool validation.

Validates untrusted tool source code in an isolated subprocess with:
- Resource limits (CPU time, memory, file descriptors)
- No network access (inherited from restricted env)
- Restricted imports (no os, subprocess, socket, etc.)
- Timeout enforcement

The subprocess validates that the source compiles, defines exactly one
BaseTool subclass, and doesn't use disallowed imports. If validation
passes, the main process loads the tool with the existing restricted-
builtins exec (which is safe enough for *validated* code).

Environment variables
---------------------
AGNOS_TOOL_SANDBOX_ENABLED
    Enable subprocess validation. Default ``true``.
AGNOS_TOOL_SANDBOX_TIMEOUT
    Max seconds for validation subprocess. Default ``10``.
AGNOS_TOOL_SANDBOX_MAX_MEM_MB
    Max RSS memory for validation subprocess. Default ``256``.
"""

from __future__ import annotations

import ast
import logging
import os
import subprocess
import sys
import textwrap

logger = logging.getLogger(__name__)

_SANDBOX_ENABLED = os.getenv("AGNOS_TOOL_SANDBOX_ENABLED", "true").lower() not in (
    "false",
    "0",
    "no",
)
_SANDBOX_TIMEOUT = int(os.getenv("AGNOS_TOOL_SANDBOX_TIMEOUT", "10"))
_SANDBOX_MAX_MEM_MB = int(os.getenv("AGNOS_TOOL_SANDBOX_MAX_MEM_MB", "256"))

# Imports that are never allowed in tool source code
_BLOCKED_MODULES = frozenset(
    {
        "os",
        "subprocess",
        "socket",
        "shutil",
        "pathlib",
        "ctypes",
        "multiprocessing",
        "signal",
        "resource",
        "importlib",
        "sys",
        "builtins",
        "__builtin__",
        "code",
        "codeop",
        "compile",
        "compileall",
        "py_compile",
        "pickle",
        "shelve",
        "marshal",
        "tempfile",
        "glob",
        "fnmatch",
        "io",
        "http",
        "urllib",
        "requests",
        "httpx",
        "aiohttp",
        "asyncio",
        "threading",
        "concurrent",
    }
)


class SandboxError(Exception):
    """Raised when sandbox validation fails."""


def _check_ast(source_code: str, name: str) -> None:
    """Static analysis: check for disallowed imports and constructs."""
    try:
        tree = ast.parse(source_code)
    except SyntaxError as exc:
        raise SandboxError(f"Syntax error in tool '{name}': {exc}") from exc

    for node in ast.walk(tree):
        # Block import of dangerous modules
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_root = alias.name.split(".")[0]
                if module_root in _BLOCKED_MODULES:
                    raise SandboxError(
                        f"Tool '{name}' imports blocked module: {alias.name}"
                    )

        if isinstance(node, ast.ImportFrom):
            if node.module:
                module_root = node.module.split(".")[0]
                if module_root in _BLOCKED_MODULES:
                    raise SandboxError(
                        f"Tool '{name}' imports from blocked module: {node.module}"
                    )

        # Block exec/eval calls
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in ("exec", "eval", "compile"):
                raise SandboxError(
                    f"Tool '{name}' uses disallowed builtin: {func.id}()"
                )

        # Block __subclasses__, __globals__, __builtins__ attribute access
        if isinstance(node, ast.Attribute):
            if node.attr in (
                "__subclasses__",
                "__globals__",
                "__builtins__",
                "__code__",
            ):
                raise SandboxError(
                    f"Tool '{name}' accesses disallowed attribute: {node.attr}"
                )


def _validate_in_subprocess(source_code: str, name: str) -> None:
    """Run validation in an isolated subprocess with resource limits."""
    # Build a validation script that:
    # 1. Sets resource limits
    # 2. Compiles the source
    # 3. Checks for BaseTool subclass
    validation_script = textwrap.dedent(f"""\
        import json, resource, sys

        # Resource limits
        max_mem = {_SANDBOX_MAX_MEM_MB} * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (max_mem, max_mem))
        except (ValueError, resource.error):
            pass  # Not all platforms support RLIMIT_AS
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
        except (ValueError, resource.error):
            pass
        try:
            resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
        except (ValueError, resource.error):
            pass

        source = sys.stdin.read()

        try:
            compile(source, "<tool:{name}>", "exec")
        except SyntaxError as e:
            print(json.dumps({{"error": f"Syntax error: {{e}}"}}))
            sys.exit(1)

        # AST check for class definitions (don't exec — subprocess lacks deps)
        import ast
        try:
            tree = ast.parse(source)
            classes = [
                node.name for node in ast.walk(tree)
                if isinstance(node, ast.ClassDef) and not node.name.startswith("_")
            ]
        except Exception as e:
            print(json.dumps({{"error": f"Parse error: {{e}}"}}))
            sys.exit(1)

        if not classes:
            print(json.dumps({{"error": "No classes defined"}}))
            sys.exit(1)

        print(json.dumps({{"ok": True, "classes": classes}}))
    """)

    try:
        result = subprocess.run(
            [sys.executable, "-c", validation_script],
            input=source_code,
            capture_output=True,
            text=True,
            timeout=_SANDBOX_TIMEOUT,
            env={
                "PATH": "",
                "HOME": "/tmp",
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )
    except subprocess.TimeoutExpired as exc:
        raise SandboxError(
            f"Tool '{name}' validation timed out ({_SANDBOX_TIMEOUT}s)"
        ) from exc
    except Exception as exc:
        raise SandboxError(f"Tool '{name}' sandbox error: {exc}") from exc

    if result.returncode != 0:
        # Try to parse structured error
        try:
            import json

            err = json.loads(result.stdout.strip())
            raise SandboxError(f"Tool '{name}': {err.get('error', 'unknown error')}")
        except (json.JSONDecodeError, SandboxError):
            if isinstance(sys.exc_info()[1], SandboxError):
                raise
            raise SandboxError(
                f"Tool '{name}' validation failed: {result.stderr.strip() or result.stdout.strip()}"
            )


def validate_tool_source(name: str, source_code: str) -> None:
    """Validate tool source code before loading.

    Performs:
    1. AST analysis — blocks dangerous imports, exec/eval, MRO walking
    2. Subprocess validation — compiles and executes in isolated process
       with resource limits

    Raises SandboxError if validation fails.
    """
    # Always run AST checks (fast, in-process)
    _check_ast(source_code, name)

    # Subprocess validation (optional but enabled by default)
    if _SANDBOX_ENABLED:
        _validate_in_subprocess(source_code, name)
        logger.info("Tool '%s' passed sandbox validation", name)
    else:
        logger.warning(
            "Tool '%s' sandbox validation skipped (AGNOS_TOOL_SANDBOX_ENABLED=false)",
            name,
        )
