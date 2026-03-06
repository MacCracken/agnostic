"""Tests for shared/crewai_compat.py — BaseTool fallback."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestBaseToolFallback:
    def test_base_tool_importable(self):
        from shared.crewai_compat import BaseTool

        assert BaseTool is not None

    def test_base_tool_has_name_and_description(self):
        from shared.crewai_compat import BaseTool

        tool = BaseTool()
        assert hasattr(tool, "name")
        assert hasattr(tool, "description")

    def test_base_tool_run_raises(self):
        """The fallback BaseTool._run should raise NotImplementedError."""
        from shared.crewai_compat import BaseTool

        # Only test the fallback class (if crewai is installed, _run may behave differently)
        tool = BaseTool()
        if type(tool).__module__ == "shared.crewai_compat":
            with pytest.raises(NotImplementedError):
                tool._run()

    def test_subclass_can_override_run(self):
        from shared.crewai_compat import BaseTool

        class MyTool(BaseTool):
            name = "my_tool"
            description = "A test tool"

            def _run(self, query: str = ""):
                return f"result: {query}"

        tool = MyTool()
        assert tool.name == "my_tool"
        assert tool._run("hello") == "result: hello"
