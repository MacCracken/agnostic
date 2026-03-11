"""Tests for shared/crewai_compat.py — BaseTool fallback."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestBaseToolFallback:
    def test_base_tool_importable(self):
        from shared.crewai_compat import BaseTool

        assert BaseTool is not None

    def test_base_tool_has_name_and_description(self):
        from shared.crewai_compat import BaseTool

        # When crewai is installed, BaseTool is abstract — check class attrs exist
        assert hasattr(BaseTool, "name") or "name" in getattr(
            BaseTool, "model_fields", {}
        )
        assert hasattr(BaseTool, "description") or "description" in getattr(
            BaseTool, "model_fields", {}
        )

    def test_subclass_can_override_run(self):
        from shared.crewai_compat import BaseTool

        class MyTool(BaseTool):
            name: str = "my_tool"
            description: str = "A test tool"

            def _run(self, query: str = ""):
                return f"result: {query}"

        tool = MyTool()
        assert tool.name == "my_tool"
        assert tool._run("hello") == "result: hello"
