"""Integration tests for router registration order (Issue #173).

Tests verify that dashboard backend routes take precedence over fun_api routes
when both use the same /api prefix, preventing endpoint shadowing.
"""

import pytest
from fastapi import FastAPI, APIRouter
from fastapi.testclient import TestClient


class TestRouterRegistrationOrder:
    """Test that first-registered router takes precedence for overlapping routes."""

    def test_first_router_takes_precedence(self):
        """When two routers have overlapping paths, first registration wins."""
        app = FastAPI()

        # First router (should take precedence)
        router1 = APIRouter(prefix="/api")

        @router1.get("/test")
        def first_endpoint():
            return {"source": "router1"}

        # Second router (should be shadowed)
        router2 = APIRouter(prefix="/api")

        @router2.get("/test")
        def second_endpoint():
            return {"source": "router2"}

        # Register router1 first
        app.include_router(router1)
        app.include_router(router2)

        client = TestClient(app)
        response = client.get("/api/test")

        # First router should handle the request
        assert response.status_code == 200
        assert response.json()["source"] == "router1"

    def test_dashboard_batch_endpoint_accessible(self):
        """Dashboard backend router's batch endpoint should be accessible.

        This test verifies the fix for the router collision that made
        /api/events/batch unreachable when it was only in fun_api router.
        """
        # Import the actual dashboard app
        from backend.main import app

        client = TestClient(app)

        # Test that /api/events/batch exists and is reachable
        # Use a malformed request to test endpoint existence (not full functionality)
        response = client.post(
            "/api/events/batch",
            json={"invalid": "should return 400 for non-array body"},
        )

        # Should return 400 (validation error), not 404 (not found)
        # This confirms the endpoint is registered and reachable
        assert response.status_code == 400
        assert "error" in response.json()

    def test_batch_endpoint_returns_404_if_not_registered(self):
        """Endpoint returns 404 when not registered (baseline test)."""
        app = FastAPI()

        # Deliberately don't register any routers
        client = TestClient(app)

        response = client.post("/api/events/batch", json=[])

        # Should return 404 (not found)
        assert response.status_code == 404

    def test_second_router_unique_paths_still_accessible(self):
        """Second router's unique paths (not overlapping) should still work."""
        app = FastAPI()

        router1 = APIRouter(prefix="/api")

        @router1.get("/first-only")
        def first_only():
            return {"source": "router1"}

        router2 = APIRouter(prefix="/api")

        @router2.get("/second-only")
        def second_only():
            return {"source": "router2"}

        app.include_router(router1)
        app.include_router(router2)

        client = TestClient(app)

        # Both unique endpoints should work
        response1 = client.get("/api/first-only")
        assert response1.status_code == 200
        assert response1.json()["source"] == "router1"

        response2 = client.get("/api/second-only")
        assert response2.status_code == 200
        assert response2.json()["source"] == "router2"

    def test_different_prefixes_no_collision(self):
        """Routers with different prefixes don't collide."""
        app = FastAPI()

        router1 = APIRouter(prefix="/api")

        @router1.get("/test")
        def api_test():
            return {"prefix": "api"}

        router2 = APIRouter(prefix="/fun_api")

        @router2.get("/test")
        def fun_api_test():
            return {"prefix": "fun_api"}

        app.include_router(router1)
        app.include_router(router2)

        client = TestClient(app)

        # Both should work with different prefixes
        response1 = client.get("/api/test")
        assert response1.status_code == 200
        assert response1.json()["prefix"] == "api"

        response2 = client.get("/fun_api/test")
        assert response2.status_code == 200
        assert response2.json()["prefix"] == "fun_api"
