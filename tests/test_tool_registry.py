"""Tests for tool_registry — registration, queries, schema management, and
execute_tool core dispatch.

Scope
-----
This file covers the *registration and query* side of tool_registry.py:

    register / register_tool / get_tool / get_all_tools /
    get_tool_schemas / get_schemas_for_categories /
    all_categories / list_by_category /
    Tool.to_api_schema /
    execute_tool (unknown tool, success, exception)

The *audit log* and *confirmation gate* features of execute_tool are tested
separately in tests/test_tool_registry_audit.py.  Both suites manipulate the
module-level _TOOLS dict, so they use disjoint tool-name prefixes:
    • test_tool_registry_audit.py  →  "_test_level*", "_audit_*"
    • this file                    →  "_tr_*"
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure the repo root is importable regardless of working directory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_registry():
    """Save and restore module-level state around every test.

    This prevents test-tool registrations from leaking into other tests and
    ensures the schema cache is always reset to a known state.
    """
    import tool_registry

    # Save state
    saved_tools = dict(tool_registry._TOOLS)
    saved_schemas = tool_registry._CACHED_SCHEMAS
    saved_gate = tool_registry._confirmation_gate

    # Remove any pre-existing _tr_ test tools that survived a previous run
    for key in list(tool_registry._TOOLS.keys()):
        if key.startswith("_tr_"):
            del tool_registry._TOOLS[key]
    tool_registry._CACHED_SCHEMAS = None

    yield

    # Restore state
    tool_registry._TOOLS.clear()
    tool_registry._TOOLS.update(saved_tools)
    tool_registry._CACHED_SCHEMAS = saved_schemas
    tool_registry._confirmation_gate = saved_gate


def _noop_handler(**kwargs) -> str:
    return "ok"


def _register_tr(name: str, category: str = "core", safety_level: int = 1) -> None:
    """Register a minimal test tool with the _tr_ prefix."""
    import tool_registry

    tool_registry.register(
        name=f"_tr_{name}",
        description=f"Test tool {name}",
        parameters={"type": "object", "properties": {}},
        handler=_noop_handler,
        category=category,
        safety_level=safety_level,
    )


# ---------------------------------------------------------------------------
# Tool dataclass
# ---------------------------------------------------------------------------


class TestToolDataclass:
    """Tool.to_api_schema() must produce the exact Anthropic schema format."""

    def test_to_api_schema_keys_present(self):
        import tool_registry

        t = tool_registry.Tool(
            name="my_tool",
            description="Does something",
            parameters={"type": "object", "properties": {}},
            handler=_noop_handler,
        )
        schema = t.to_api_schema()
        assert "name" in schema
        assert "description" in schema
        assert "input_schema" in schema

    def test_to_api_schema_name_matches(self):
        import tool_registry

        t = tool_registry.Tool(
            name="my_tool",
            description="desc",
            parameters={},
            handler=_noop_handler,
        )
        assert t.to_api_schema()["name"] == "my_tool"

    def test_to_api_schema_description_matches(self):
        import tool_registry

        t = tool_registry.Tool(
            name="t",
            description="The description",
            parameters={},
            handler=_noop_handler,
        )
        assert t.to_api_schema()["description"] == "The description"

    def test_to_api_schema_input_schema_is_parameters(self):
        import tool_registry

        params = {"type": "object", "properties": {"x": {"type": "string"}}}
        t = tool_registry.Tool(name="t", description="d", parameters=params, handler=_noop_handler)
        assert t.to_api_schema()["input_schema"] is params

    def test_default_safety_level_is_1(self):
        import tool_registry

        t = tool_registry.Tool(name="t", description="d", parameters={}, handler=_noop_handler)
        assert t.safety_level == 1

    def test_default_category_is_core(self):
        import tool_registry

        t = tool_registry.Tool(name="t", description="d", parameters={}, handler=_noop_handler)
        assert t.category == "core"


# ---------------------------------------------------------------------------
# register() and register_tool() alias
# ---------------------------------------------------------------------------


class TestRegistration:
    """register() stores tools; register_tool() is a transparent alias."""

    def test_register_stores_tool(self):
        import tool_registry

        _register_tr("alpha")
        assert tool_registry.get_tool("_tr_alpha") is not None

    def test_register_tool_alias_stores_tool(self):
        """register_tool() must behave identically to register()."""
        import tool_registry

        tool_registry.register_tool(
            name="_tr_alias",
            description="alias test",
            parameters={},
            handler=_noop_handler,
        )
        assert tool_registry.get_tool("_tr_alias") is not None

    def test_registered_tool_has_correct_name(self):
        import tool_registry

        _register_tr("beta")
        t = tool_registry.get_tool("_tr_beta")
        assert t.name == "_tr_beta"

    def test_registered_tool_has_correct_description(self):
        import tool_registry

        tool_registry.register(
            name="_tr_desc_test",
            description="A very specific description",
            parameters={},
            handler=_noop_handler,
        )
        t = tool_registry.get_tool("_tr_desc_test")
        assert t.description == "A very specific description"

    def test_registered_tool_has_correct_category(self):
        import tool_registry

        _register_tr("cattest", category="file")
        assert tool_registry.get_tool("_tr_cattest").category == "file"

    def test_registered_tool_has_correct_safety_level(self):
        import tool_registry

        _register_tr("lvltest", safety_level=3)
        assert tool_registry.get_tool("_tr_lvltest").safety_level == 3

    def test_register_default_safety_level_is_1(self):
        import tool_registry

        _register_tr("defaultlvl")
        assert tool_registry.get_tool("_tr_defaultlvl").safety_level == 1

    def test_register_default_category_is_core(self):
        import tool_registry

        _register_tr("defaultcat")
        assert tool_registry.get_tool("_tr_defaultcat").category == "core"

    def test_register_overwrites_existing_tool(self):
        """Re-registering under the same name replaces the previous entry."""
        import tool_registry

        tool_registry.register("_tr_overwrite", "first", {}, lambda: "first_result")
        tool_registry.register("_tr_overwrite", "second", {}, lambda: "second_result")
        t = tool_registry.get_tool("_tr_overwrite")
        assert t.description == "second"

    def test_register_invalidates_schema_cache(self):
        """Registering a new tool must clear _CACHED_SCHEMAS."""
        import tool_registry

        # Prime the cache
        _ = tool_registry.get_tool_schemas()
        assert tool_registry._CACHED_SCHEMAS is not None

        # Registering a new tool must invalidate it
        _register_tr("cache_bust")
        assert tool_registry._CACHED_SCHEMAS is None

    def test_register_handler_is_stored(self):
        """The handler callable stored must be the exact object passed in."""
        import tool_registry

        def my_handler(**kwargs):
            return "specific"

        tool_registry.register("_tr_handler", "h", {}, my_handler)
        assert tool_registry.get_tool("_tr_handler").handler is my_handler


# ---------------------------------------------------------------------------
# get_tool / get_all_tools
# ---------------------------------------------------------------------------


class TestQueryFunctions:
    """get_tool, get_all_tools return correct data."""

    def test_get_tool_returns_none_for_unknown(self):
        import tool_registry

        assert tool_registry.get_tool("_tr_does_not_exist") is None

    def test_get_tool_returns_tool_object(self):
        import tool_registry

        _register_tr("found")
        result = tool_registry.get_tool("_tr_found")
        import tool_registry as tr

        assert isinstance(result, tr.Tool)

    def test_get_all_tools_includes_registered_tool(self):
        import tool_registry

        _register_tr("list_me")
        names = [t.name for t in tool_registry.get_all_tools()]
        assert "_tr_list_me" in names

    def test_get_all_tools_returns_list(self):
        import tool_registry

        result = tool_registry.get_all_tools()
        assert isinstance(result, list)

    def test_get_all_tools_includes_multiple_tools(self):
        import tool_registry

        _register_tr("multi_a")
        _register_tr("multi_b")
        names = [t.name for t in tool_registry.get_all_tools()]
        assert "_tr_multi_a" in names
        assert "_tr_multi_b" in names


# ---------------------------------------------------------------------------
# Schema functions
# ---------------------------------------------------------------------------


class TestSchemaFunctions:
    """get_tool_schemas, get_schemas_for_categories, caching behavior."""

    def test_get_tool_schemas_returns_list(self):
        import tool_registry

        result = tool_registry.get_tool_schemas()
        assert isinstance(result, list)

    def test_get_tool_schemas_includes_registered_tool(self):
        import tool_registry

        _register_tr("schema_check")
        schemas = tool_registry.get_tool_schemas()
        names = [s["name"] for s in schemas]
        assert "_tr_schema_check" in names

    def test_get_tool_schemas_schema_format(self):
        """Each schema dict must have name, description, and input_schema keys."""
        import tool_registry

        _register_tr("fmt_check")
        schemas = tool_registry.get_tool_schemas()
        tr_schema = next(s for s in schemas if s["name"] == "_tr_fmt_check")
        assert "name" in tr_schema
        assert "description" in tr_schema
        assert "input_schema" in tr_schema

    def test_get_tool_schemas_is_cached(self):
        """Second call must return the same list object (cache hit)."""
        import tool_registry

        first = tool_registry.get_tool_schemas()
        second = tool_registry.get_tool_schemas()
        assert first is second

    def test_get_tool_schemas_cache_rebuilt_after_register(self):
        """Cache must be regenerated after a new registration."""
        import tool_registry

        first = tool_registry.get_tool_schemas()
        _register_tr("rebuild")
        second = tool_registry.get_tool_schemas()
        # New list object (cache was invalidated and rebuilt)
        assert first is not second

    def test_get_schemas_for_categories_filters_by_category(self):
        import tool_registry

        _register_tr("cat_a1", category="web")
        _register_tr("cat_b1", category="shell")
        web_schemas = tool_registry.get_schemas_for_categories({"web"})
        web_names = [s["name"] for s in web_schemas]
        assert "_tr_cat_a1" in web_names
        assert "_tr_cat_b1" not in web_names

    def test_get_schemas_for_categories_empty_set_returns_no_tr_tools(self):
        import tool_registry

        _register_tr("no_cat")
        result = tool_registry.get_schemas_for_categories(set())
        names = [s["name"] for s in result]
        assert "_tr_no_cat" not in names

    def test_get_schemas_for_categories_multiple_categories(self):
        import tool_registry

        _register_tr("multi_web", category="web")
        _register_tr("multi_git", category="git")
        _register_tr("multi_shell", category="shell")
        schemas = tool_registry.get_schemas_for_categories({"web", "git"})
        names = [s["name"] for s in schemas]
        assert "_tr_multi_web" in names
        assert "_tr_multi_git" in names
        assert "_tr_multi_shell" not in names


# ---------------------------------------------------------------------------
# all_categories / list_by_category
# ---------------------------------------------------------------------------


class TestCategoryFunctions:
    """all_categories and list_by_category return correct groupings."""

    def test_all_categories_includes_registered_category(self):
        import tool_registry

        _register_tr("catcheck", category="mycat")
        assert "mycat" in tool_registry.all_categories()

    def test_all_categories_returns_set(self):
        import tool_registry

        result = tool_registry.all_categories()
        assert isinstance(result, set)

    def test_all_categories_multiple_categories(self):
        import tool_registry

        _register_tr("c1", category="alpha")
        _register_tr("c2", category="beta")
        cats = tool_registry.all_categories()
        assert "alpha" in cats
        assert "beta" in cats

    def test_list_by_category_groups_tools(self):
        import tool_registry

        _register_tr("grp_a", category="grpcat")
        _register_tr("grp_b", category="grpcat")
        by_cat = tool_registry.list_by_category()
        grp_names = [t.name for t in by_cat.get("grpcat", [])]
        assert "_tr_grp_a" in grp_names
        assert "_tr_grp_b" in grp_names

    def test_list_by_category_returns_dict(self):
        import tool_registry

        result = tool_registry.list_by_category()
        assert isinstance(result, dict)

    def test_list_by_category_tools_are_tool_objects(self):
        import tool_registry

        _register_tr("typecheck", category="tcat")
        by_cat = tool_registry.list_by_category()
        for tool in by_cat.get("tcat", []):
            assert isinstance(tool, tool_registry.Tool)


# ---------------------------------------------------------------------------
# execute_tool core dispatch (audit/gate tested in test_tool_registry_audit.py)
# ---------------------------------------------------------------------------


class TestExecuteToolDispatch:
    """execute_tool unknown-tool path, success, and exception handling."""

    def test_unknown_tool_returns_error_string(self):
        import tool_registry

        result = tool_registry.execute_tool("_tr_nonexistent_xyz", {})
        assert result.startswith("Error")

    def test_unknown_tool_error_mentions_tool_name(self):
        import tool_registry

        result = tool_registry.execute_tool("_tr_nosuchname", {})
        assert "_tr_nosuchname" in result

    def test_success_returns_handler_output(self):
        import tool_registry

        tool_registry.register("_tr_exec_ok", "ok", {}, lambda: "handler_output", safety_level=1)

        with patch("tool_registry._get_audit_log") as mock_log:
            mock_log.return_value = MagicMock()
            result = tool_registry.execute_tool("_tr_exec_ok", {})

        assert result == "handler_output"

    def test_handler_receives_tool_input_kwargs(self):
        """execute_tool must unpack the input dict as **kwargs to the handler."""
        import tool_registry

        received = {}

        def capturing_handler(**kwargs):
            received.update(kwargs)
            return "done"

        tool_registry.register("_tr_kwargs_test", "kw", {}, capturing_handler, safety_level=1)

        with patch("tool_registry._get_audit_log") as mock_log:
            mock_log.return_value = MagicMock()
            tool_registry.execute_tool("_tr_kwargs_test", {"x": 1, "y": "hello"})

        assert received == {"x": 1, "y": "hello"}

    def test_exception_in_handler_returns_error_string(self):
        import tool_registry

        def boom():
            raise ValueError("intentional failure")

        tool_registry.register("_tr_boom", "boom", {}, boom, safety_level=1)

        with patch("tool_registry._get_audit_log") as mock_log:
            mock_log.return_value = MagicMock()
            result = tool_registry.execute_tool("_tr_boom", {})

        assert result.startswith("Error")

    def test_exception_message_included_in_error_string(self):
        import tool_registry

        def explode():
            raise RuntimeError("specific error message")

        tool_registry.register("_tr_explode", "explode", {}, explode, safety_level=2)

        with patch("tool_registry._get_audit_log") as mock_log:
            mock_log.return_value = MagicMock()
            result = tool_registry.execute_tool("_tr_explode", {})

        assert "specific error message" in result

    def test_error_string_convention_starts_with_Error(self):
        """Callers distinguish success from failure by checking startswith('Error')."""
        import tool_registry

        result = tool_registry.execute_tool("_tr_absent_tool_convention", {})
        # Both unknown-tool and handler-exception paths must follow this convention
        assert result.startswith("Error")

    def test_execute_tool_success_does_not_start_with_error(self):
        import tool_registry

        tool_registry.register("_tr_noerr", "noerr", {}, lambda: "good result", safety_level=1)

        with patch("tool_registry._get_audit_log") as mock_log:
            mock_log.return_value = MagicMock()
            result = tool_registry.execute_tool("_tr_noerr", {})

        assert not result.startswith("Error")
