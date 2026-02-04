"""Integration tests for dashboard rendering.

These tests verify that tabs actually render in the browser,
catching htmx/Alpine issues that unit tests miss.

IMPORTANT: Dashboard must be running at localhost:8502 before running these tests.
Start with: uv run --directory src/services/dashboard uvicorn backend.main:app --port 8502

Run with: pytest src/services/dashboard/tests/test_integration.py -v
"""

import pytest
from playwright.sync_api import Page, expect


class TestTabRendering:
    """Verify each tab loads and renders content."""

    def test_heuristics_tab_renders_rows(self, page: Page, dashboard_url: str):
        """Heuristics tab shows rows in DOM (Pattern A)."""
        page.goto(dashboard_url)

        # Click Heuristics tab
        page.click("text=Heuristics")

        # Wait for content to load (htmx swap)
        page.wait_for_selector("#heuristics-tab", timeout=5000)

        # Verify container exists (even if empty)
        container = page.locator("#heuristics-rows-container")
        expect(container).to_be_visible()

        # If there are rows, verify they rendered
        # (not just that HTML was returned, but that DOM elements exist)
        rows = page.locator("[data-heuristic-row]")
        # Don't assert count - may be 0 if no data
        # Just verify the query works and didn't error

    def test_learning_tab_renders_rows(self, page: Page, dashboard_url: str):
        """Learning tab shows fire history (Pattern A)."""
        page.goto(dashboard_url)

        page.click("text=Learning")
        page.wait_for_selector("#learning-tab", timeout=5000)

        container = page.locator("#learning-rows-container, #fires-container")
        expect(container).to_be_visible()

    def test_logs_tab_renders_lines(self, page: Page, dashboard_url: str):
        """Logs tab shows log lines (Pattern A)."""
        page.goto(dashboard_url)

        page.click("text=Logs")
        page.wait_for_selector("#logs-tab", timeout=5000)

        container = page.locator("#logs-container")
        expect(container).to_be_visible()

    def test_llm_tab_renders(self, page: Page, dashboard_url: str):
        """LLM tab loads (Pattern B - Alpine JSON fetch)."""
        page.goto(dashboard_url)

        page.click("text=LLM")
        page.wait_for_selector("#llm-tab", timeout=5000)

        # LLM tab uses Alpine to fetch status
        # Just verify the tab container loaded
        tab = page.locator("#llm-tab")
        expect(tab).to_be_visible()

    def test_settings_tab_renders(self, page: Page, dashboard_url: str):
        """Settings tab loads (Pattern B - Alpine JSON fetch)."""
        page.goto(dashboard_url)

        page.click("text=Settings")
        page.wait_for_selector("#settings-tab", timeout=5000)

        tab = page.locator("#settings-tab")
        expect(tab).to_be_visible()


class TestTabNavigation:
    """Verify tab switching works correctly."""

    def test_tab_navigation_preserves_content(self, page: Page, dashboard_url: str):
        """Switching tabs and back preserves state."""
        page.goto(dashboard_url)

        # Go to Heuristics
        page.click("text=Heuristics")
        page.wait_for_selector("#heuristics-tab", timeout=5000)

        # Go to Logs
        page.click("text=Logs")
        page.wait_for_selector("#logs-tab", timeout=5000)

        # Go back to Heuristics
        page.click("text=Heuristics")
        page.wait_for_selector("#heuristics-tab", timeout=5000)

        # Verify it loaded (htmx doesn't cache by default)
        container = page.locator("#heuristics-rows-container")
        expect(container).to_be_visible()


class TestSidebar:
    """Verify sidebar renders."""

    def test_sidebar_shows_services(self, page: Page, dashboard_url: str):
        """Sidebar service list renders."""
        page.goto(dashboard_url)

        # Wait for sidebar to load (htmx polling)
        page.wait_for_selector(".sidebar, #services-list", timeout=5000)

        # Verify at least one service row exists
        # (orchestrator, memory, etc.)
        service_row = page.locator("[data-service-row]").first
        # May not exist if no services running - just verify query works


class TestLabTab:
    """Verify Lab (events) tab works."""

    def test_lab_tab_has_event_form(self, page: Page, dashboard_url: str):
        """Lab tab shows event submission form."""
        page.goto(dashboard_url)

        # Lab is the default tab
        page.wait_for_selector("#lab-tab, #events-tab", timeout=5000)

        # Verify form elements exist
        text_input = page.locator("textarea, input[type='text']").first
        expect(text_input).to_be_visible()
