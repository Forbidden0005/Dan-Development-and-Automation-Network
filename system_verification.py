#!/usr/bin/env python3
"""Manual system verification helpers for Dan.

This script is a smoke check, not a certification of production readiness.
Use scripts/repo_health.py for the standard automated repository audit.
"""

import os
import time
from contextlib import contextmanager


@contextmanager
def timer(description):
    start = time.perf_counter()
    yield
    elapsed = time.perf_counter() - start
    print(f"  {description}: {elapsed * 1000:.2f}ms")


def test_authentication_system():
    """Exercise authentication import and optional credential validation."""
    print("=== AUTHENTICATION SYSTEM TEST ===")

    try:
        admin_key = os.environ.get("DAN_VERIFICATION_API_KEY", "").strip()
        if not admin_key:
            print("  SKIP: Set DAN_VERIFICATION_API_KEY to run authentication check")
            print("  Auth state was not opened.")
            return

        with timer("Auth system import"):
            from auth_system import get_auth_manager

        with timer("Get auth manager"):
            auth = get_auth_manager()

        with timer("Authentication check"):
            session = auth.authenticate(admin_key)

        if session:
            print(f"  SUCCESS: Authenticated as {session.username}")

            with timer("Permission check"):
                has_admin = auth.check_permission(session, "*")

            print(f"  Admin permissions: {has_admin}")
        else:
            print("  ERROR: Authentication failed")

        print(f"  Total users: {len(auth.users)}")
        print("  AUTH SYSTEM: CHECK COMPLETED")

    except Exception as e:
        print(f"  AUTH SYSTEM ERROR: {e}")


def test_tool_registry_performance():
    """Exercise tool registry schema cache behavior."""
    print("\n=== TOOL REGISTRY PERFORMANCE TEST ===")

    try:
        with timer("Tool registry import"):
            import tool_registry

        with timer("First schema generation"):
            schemas1 = tool_registry.get_tool_schemas()

        with timer("Cached schema access (2nd call)"):
            schemas2 = tool_registry.get_tool_schemas()

        with timer("Cached schema access (3rd call)"):
            tool_registry.get_tool_schemas()

        print(f"  Schema count: {len(schemas1)}")
        print(f"  Cache working: {schemas1 is schemas2}")
        print("  TOOL REGISTRY: CHECK COMPLETED")

    except Exception as e:
        print(f"  TOOL REGISTRY ERROR: {e}")


def test_provider_optimizations():
    """Exercise provider key rotation behavior with a dummy local key."""
    print("\n=== PROVIDER OPTIMIZATIONS TEST ===")

    try:
        with timer("Provider import"):
            from providers import KeyRotator

        os.environ["TEST_API_KEY"] = "test_key"  # pragma: allowlist secret

        try:
            with timer("KeyRotator init"):
                rotator = KeyRotator("TEST_API_KEY")

            with timer("10 key selections"):
                for _ in range(10):
                    rotator.next()

            print(f"  Key rotation interval: {rotator.HOLD_SECONDS}s")
            print(f"  Keys loaded: {rotator.count}")
            print("  PROVIDER: CHECK COMPLETED")
        finally:
            os.environ.pop("TEST_API_KEY", None)

    except Exception as e:
        print(f"  PROVIDER ERROR: {e}")


def test_image_tools_lazy_loading():
    """Exercise image tool import path."""
    print("\n=== IMAGE TOOLS LAZY LOADING TEST ===")

    try:
        with timer("Image tools import"):
            import image_tools  # noqa: F401

        print("  Image tools imported")
        print("  LAZY LOADING: CHECK COMPLETED")

    except Exception as e:
        print(f"  IMAGE TOOLS ERROR: {e}")


def test_ml_tools_integration():
    """Exercise ML tool import and registry visibility."""
    print("\n=== ML TOOLS INTEGRATION TEST ===")

    try:
        with timer("ML tools import"):
            import ml_tools  # noqa: F401

        with timer("Tool registry check"):
            import tool_registry

            all_tools = tool_registry.get_all_tools()
            ml_tools_list = [t for t in all_tools if t.category == "ml"]

        print(f"  ML tools registered: {len(ml_tools_list)}")
        for tool in ml_tools_list:
            print(f"    - {tool.name}")
        print("  ML INTEGRATION: CHECK COMPLETED")

    except Exception as e:
        print(f"  ML TOOLS ERROR: {e}")


def test_complete_system():
    """Exercise tool registration across the active tool bundles."""
    print("\n=== COMPLETE SYSTEM TEST ===")

    try:
        with timer("Complete tool registration"):
            import actions
            import image_tools  # noqa: F401
            import knowledge
            import ml_tools  # noqa: F401
            import skills
            import tools
            import web
            import workers

            tools.register_core_tools()
            knowledge.register_knowledge_tools()
            web.register_web_tools()
            workers.register_worker_tools()
            actions.register_action_tools()
            skills.register_skill_tools()

        with timer("Get all tools"):
            import tool_registry

            all_tools = tool_registry.get_all_tools()
            categories = tool_registry.list_by_category()

        print(f"  Total tools: {len(all_tools)}")
        print(f"  Categories: {len(categories)}")
        for cat, tools_list in categories.items():
            print(f"    {cat}: {len(tools_list)} tools")

        print("  COMPLETE SYSTEM: CHECK COMPLETED")

    except Exception as e:
        print(f"  SYSTEM ERROR: {e}")


def performance_summary():
    """Print measured areas without claiming unverified improvement ratios."""
    print("\n=== PERFORMANCE SUMMARY ===")
    print("- Authentication import and optional authentication check were timed above.")
    print("- Tool schema cache behavior was checked above.")
    print("- Provider key rotation behavior was exercised above.")
    print("- Image and ML imports were attempted above.")
    print("- Treat this as a local smoke check; benchmark separately for performance claims.")


def security_summary():
    """Print security areas exercised without overstating coverage."""
    print("\n=== SECURITY SUMMARY ===")
    print("- Authentication and permission checks run only when DAN_VERIFICATION_API_KEY is set.")
    print("- Tool registration and dependency imports were exercised above.")
    print("- This script does not replace tests, Bandit, detect-secrets, or repo_health.")
    print("- Review failures and skipped checks above before drawing conclusions.")


def main():
    """Run the manual smoke-check suite."""
    print("Dan AI Agent - Manual System Smoke Check")
    print("=" * 60)

    start_time = time.time()

    test_authentication_system()
    test_tool_registry_performance()
    test_provider_optimizations()
    test_image_tools_lazy_loading()
    test_ml_tools_integration()
    test_complete_system()

    total_time = time.time() - start_time

    print("\n=== VERIFICATION COMPLETE ===")
    print(f"Total test time: {total_time:.2f} seconds")
    print("Smoke checks finished. Review ERROR and SKIP lines above.")

    performance_summary()
    security_summary()

    print("\nSuggested next check: python scripts/repo_health.py")


if __name__ == "__main__":
    main()
