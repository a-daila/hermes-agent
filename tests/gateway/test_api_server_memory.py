"""Tests for the curated-memory management endpoints on the API server.

Covers GET /api/memory and DELETE /api/memory:
- list both stores / single target
- target validation (rejects unknown values)
- delete single entry by old_text substring
- clear a single store
- clear both stores (default target=all)
- old_text + target=all is rejected
- 404 when old_text doesn't match any entry
- auth enforcement (401 with API_SERVER_KEY)
"""

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from gateway.config import PlatformConfig
from gateway.platforms.api_server import APIServerAdapter, cors_middleware


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_adapter(api_key: str = "") -> APIServerAdapter:
    extra = {}
    if api_key:
        extra["key"] = api_key
    return APIServerAdapter(PlatformConfig(enabled=True, extra=extra))


def _create_app(adapter: APIServerAdapter) -> web.Application:
    app = web.Application(middlewares=[cors_middleware])
    app["api_server_adapter"] = adapter
    app.router.add_get("/api/memory", adapter._handle_get_memory)
    app.router.add_delete("/api/memory", adapter._handle_delete_memory)
    return app


@pytest.fixture
def memory_home(tmp_path, monkeypatch):
    """Profile-scoped HERMES_HOME with seeded memory files."""
    hermes_home = tmp_path / ".hermes"
    memories = hermes_home / "memories"
    memories.mkdir(parents=True)

    # Use the canonical ENTRY_DELIMITER so MemoryStore parses the seed
    # files the same way it would in production.
    from tools.memory_tool import ENTRY_DELIMITER

    (memories / "MEMORY.md").write_text(
        ENTRY_DELIMITER.join([
            "Hermes repo lives at ~/.hermes/hermes-agent",
            "Project uses Python 3.11",
        ]),
        encoding="utf-8",
    )
    (memories / "USER.md").write_text(
        ENTRY_DELIMITER.join([
            "User goes by Teknium",
            "Timezone: US Pacific",
        ]),
        encoding="utf-8",
    )

    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    return hermes_home, memories


@pytest.fixture
def adapter():
    return _make_adapter()


@pytest.fixture
def auth_adapter():
    return _make_adapter(api_key="sk-secret")


# ---------------------------------------------------------------------------
# GET /api/memory
# ---------------------------------------------------------------------------


class TestGetMemory:
    @pytest.mark.asyncio
    async def test_list_all_default(self, adapter, memory_home):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.get("/api/memory")
            assert resp.status == 200
            data = await resp.json()
            assert set(data.keys()) == {"memory", "user"}
            assert data["memory"]["entry_count"] == 2
            assert "Hermes repo" in data["memory"]["entries"][0]
            assert data["user"]["entry_count"] == 2
            assert data["memory"]["char_limit"] > 0
            assert 0 <= data["memory"]["usage_percent"] <= 100

    @pytest.mark.asyncio
    async def test_list_memory_target_only(self, adapter, memory_home):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.get("/api/memory?target=memory")
            assert resp.status == 200
            data = await resp.json()
            assert set(data.keys()) == {"memory"}
            assert "user" not in data

    @pytest.mark.asyncio
    async def test_list_user_target_only(self, adapter, memory_home):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.get("/api/memory?target=user")
            assert resp.status == 200
            data = await resp.json()
            assert set(data.keys()) == {"user"}
            assert data["user"]["entry_count"] == 2

    @pytest.mark.asyncio
    async def test_invalid_target_rejected(self, adapter, memory_home):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.get("/api/memory?target=bogus")
            assert resp.status == 400
            data = await resp.json()
            assert "target" in data["error"]

    @pytest.mark.asyncio
    async def test_empty_when_no_files(self, adapter, tmp_path, monkeypatch):
        hermes_home = tmp_path / ".hermes"
        (hermes_home / "memories").mkdir(parents=True)
        monkeypatch.setenv("HERMES_HOME", str(hermes_home))

        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.get("/api/memory")
            assert resp.status == 200
            data = await resp.json()
            assert data["memory"]["entries"] == []
            assert data["memory"]["entry_count"] == 0
            assert data["user"]["entries"] == []


# ---------------------------------------------------------------------------
# DELETE /api/memory — single-entry removal
# ---------------------------------------------------------------------------


class TestDeleteMemoryEntry:
    @pytest.mark.asyncio
    async def test_remove_by_old_text(self, adapter, memory_home):
        _, memories = memory_home
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.delete("/api/memory?target=memory&old_text=Python%203.11")
            assert resp.status == 200
            data = await resp.json()
            assert data["ok"] is True
            assert data["target"] == "memory"
            assert data["remaining"]["entry_count"] == 1

        # File on disk reflects the removal
        from tools.memory_tool import ENTRY_DELIMITER
        remaining = (memories / "MEMORY.md").read_text(encoding="utf-8")
        assert "Python 3.11" not in remaining
        assert "Hermes repo" in remaining
        assert ENTRY_DELIMITER not in remaining  # only one entry left

    @pytest.mark.asyncio
    async def test_remove_no_match_returns_404(self, adapter, memory_home):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.delete(
                "/api/memory?target=memory&old_text=this-string-does-not-exist"
            )
            assert resp.status == 404
            data = await resp.json()
            assert "No entry matched" in data["error"]

    @pytest.mark.asyncio
    async def test_old_text_with_target_all_rejected(self, adapter, memory_home):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.delete("/api/memory?target=all&old_text=anything")
            assert resp.status == 400
            data = await resp.json()
            assert "old_text" in data["error"]


# ---------------------------------------------------------------------------
# DELETE /api/memory — clear semantics
# ---------------------------------------------------------------------------


class TestClearMemory:
    @pytest.mark.asyncio
    async def test_clear_memory_target(self, adapter, memory_home):
        _, memories = memory_home
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.delete("/api/memory?target=memory")
            assert resp.status == 200
            data = await resp.json()
            assert data["ok"] is True
            assert data["cleared"]["memory"]["removed"] == 2
            assert data["cleared"]["memory"]["entry_count"] == 0
            assert "user" not in data["cleared"]

        assert (memories / "MEMORY.md").read_text(encoding="utf-8") == ""
        assert "Teknium" in (memories / "USER.md").read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_clear_user_target(self, adapter, memory_home):
        _, memories = memory_home
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.delete("/api/memory?target=user")
            assert resp.status == 200
            data = await resp.json()
            assert data["cleared"]["user"]["removed"] == 2

        assert "Teknium" not in (memories / "USER.md").read_text(encoding="utf-8")
        assert "Hermes repo" in (memories / "MEMORY.md").read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_clear_all_default(self, adapter, memory_home):
        _, memories = memory_home
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.delete("/api/memory")
            assert resp.status == 200
            data = await resp.json()
            assert data["target"] == "all"
            assert data["cleared"]["memory"]["removed"] == 2
            assert data["cleared"]["user"]["removed"] == 2

        assert (memories / "MEMORY.md").read_text(encoding="utf-8") == ""
        assert (memories / "USER.md").read_text(encoding="utf-8") == ""

    @pytest.mark.asyncio
    async def test_clear_when_already_empty(self, adapter, tmp_path, monkeypatch):
        hermes_home = tmp_path / ".hermes"
        (hermes_home / "memories").mkdir(parents=True)
        monkeypatch.setenv("HERMES_HOME", str(hermes_home))

        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.delete("/api/memory")
            assert resp.status == 200
            data = await resp.json()
            assert data["cleared"]["memory"]["removed"] == 0
            assert data["cleared"]["user"]["removed"] == 0


# ---------------------------------------------------------------------------
# Auth enforcement
# ---------------------------------------------------------------------------


class TestAuthRequired:
    @pytest.mark.asyncio
    async def test_get_requires_auth(self, auth_adapter, memory_home):
        app = _create_app(auth_adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.get("/api/memory")
            assert resp.status == 401

    @pytest.mark.asyncio
    async def test_delete_requires_auth(self, auth_adapter, memory_home):
        app = _create_app(auth_adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.delete("/api/memory")
            assert resp.status == 401

    @pytest.mark.asyncio
    async def test_get_with_valid_key(self, auth_adapter, memory_home):
        app = _create_app(auth_adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.get(
                "/api/memory",
                headers={"Authorization": "Bearer sk-secret"},
            )
            assert resp.status == 200

    @pytest.mark.asyncio
    async def test_delete_with_valid_key(self, auth_adapter, memory_home):
        _, memories = memory_home
        app = _create_app(auth_adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.delete(
                "/api/memory?target=memory",
                headers={"Authorization": "Bearer sk-secret"},
            )
            assert resp.status == 200

        assert (memories / "MEMORY.md").read_text(encoding="utf-8") == ""
