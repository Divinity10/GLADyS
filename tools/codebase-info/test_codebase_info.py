"""Tests for codebase-info tool.

These tests run against actual source files in the repo,
validating that the parser extracts correct data.
"""

import pytest
from pathlib import Path

from codebase_info import (
    find_root,
    cmd_rpcs,
    cmd_ports,
    cmd_schema,
    cmd_tree,
    cmd_routers,
    _parse_proto_services,
    _parse_cli_ports,
    _parse_docker_compose_ports,
    _parse_create_tables,
    _parse_alter_add_columns,
)


@pytest.fixture
def root():
    return find_root()


# --- rpcs ---

class TestRpcs:
    def test_finds_all_services(self, root):
        output = cmd_rpcs(root)
        assert "MemoryStorage" in output
        assert "SalienceGateway" in output
        assert "OrchestratorService" in output
        assert "ExecutiveService" in output

    def test_finds_key_rpcs(self, root):
        output = cmd_rpcs(root)
        assert "StoreEvent" in output
        assert "EvaluateSalience" in output
        assert "PublishEvent" in output
        assert "ProcessEvent" in output

    def test_extracts_comments_as_purpose(self, root):
        output = cmd_rpcs(root)
        # StoreEvent has comment "Store a new episodic event"
        assert "Store a new episodic event" in output
        # ProcessEvent has a comment too
        assert "Process an event" in output

    def test_section_headers_excluded_from_purpose(self, root):
        output = cmd_rpcs(root)
        # Section dividers should not leak into purpose text
        # StoreEntity should NOT include "--- Semantic Memory ---"
        lines = output.split("\n")
        for line in lines:
            if "StoreEntity" in line:
                assert "---" not in line
                break

    def test_proto_parser_handles_nested_braces(self):
        """Service body with nested message braces shouldn't break parsing."""
        proto = '''
service TestService {
    // Do something
    rpc DoThing(Req) returns (Resp);
}

message Req {
    string id = 1;
}
'''
        results = _parse_proto_services(proto)
        assert len(results) == 1
        assert results[0][0] == "TestService"
        assert len(results[0][1]) == 1
        assert results[0][1][0][0] == "DoThing"
        assert results[0][1][0][1] == "Do something"


# --- ports ---

class TestPorts:
    def test_finds_all_services(self, root):
        output = cmd_ports(root)
        assert "orchestrator" in output
        assert "memory_python" in output
        assert "memory_rust" in output
        assert "executive" in output
        assert "db" in output
        assert "dashboard" in output

    def test_local_ports_correct(self, root):
        output = cmd_ports(root)
        assert "50050" in output  # orchestrator local
        assert "50051" in output  # memory_python local
        assert "50052" in output  # memory_rust local

    def test_docker_ports_correct(self, root):
        output = cmd_ports(root)
        assert "50060" in output  # orchestrator docker
        assert "50061" in output  # memory_python docker
        assert "5433" in output   # db docker

    def test_descriptions_present(self, root):
        output = cmd_ports(root)
        assert "Event routing" in output
        assert "PostgreSQL" in output

    def test_cli_parser(self, root):
        cli_path = root / "cli" / "_gladys.py"
        local, docker, desc = _parse_cli_ports(cli_path)
        assert local["orchestrator"] == "50050"
        assert docker["orchestrator"] == "50060"
        assert local["dashboard"] == "8502"

    def test_docker_compose_parser(self, root):
        docker_path = root / "docker" / "docker-compose.yml"
        ports = _parse_docker_compose_ports(docker_path)
        assert "postgres" in ports
        assert "5433:5432" in ports["postgres"]


# --- schema ---

class TestSchema:
    def test_finds_core_tables(self, root):
        output = cmd_schema(root)
        assert "episodic_events" in output
        assert "entities" in output
        assert "heuristics" in output
        assert "feedback_events" in output
        assert "user_profile" in output

    def test_finds_later_tables(self, root):
        output = cmd_schema(root)
        assert "heuristic_fires" in output
        assert "relationships" in output

    def test_includes_added_columns(self, root):
        output = cmd_schema(root)
        # predicted_success added in migration 005
        assert "predicted_success" in output
        # decision_path added in migration 012
        assert "decision_path" in output

    def test_create_table_parser(self):
        sql = """
CREATE TABLE IF NOT EXISTS test_table (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    value FLOAT
);
"""
        tables = {}
        comments = {}
        _parse_create_tables(sql, tables, comments)
        assert "test_table" in tables
        cols = {c[0] for c in tables["test_table"]}
        assert "id" in cols
        assert "name" in cols
        assert "value" in cols

    def test_alter_table_parser(self):
        sql = "ALTER TABLE test_table ADD COLUMN IF NOT EXISTS new_col TEXT;"
        tables = {"test_table": [("id", "UUID")]}
        _parse_alter_add_columns(sql, tables)
        cols = {c[0] for c in tables["test_table"]}
        assert "new_col" in cols

    def test_alter_no_duplicates(self):
        sql = "ALTER TABLE test_table ADD COLUMN IF NOT EXISTS id UUID;"
        tables = {"test_table": [("id", "UUID")]}
        _parse_alter_add_columns(sql, tables)
        assert len(tables["test_table"]) == 1


# --- tree ---

class TestTree:
    def test_includes_key_dirs(self, root):
        output = cmd_tree(root, max_depth=1)
        assert "src/" in output
        assert "proto/" in output
        assert "docs/" in output
        assert "tools/" in output

    def test_annotations_present(self, root):
        output = cmd_tree(root, max_depth=2)
        assert "CLI entry points" in output
        assert "Protocol Buffer definitions" in output

    def test_excludes_ignored(self, root):
        output = cmd_tree(root, max_depth=3)
        assert "__pycache__" not in output
        assert ".git/" not in output
        assert "node_modules" not in output

    def test_depth_limit(self, root):
        output_shallow = cmd_tree(root, max_depth=1)
        output_deep = cmd_tree(root, max_depth=3)
        assert len(output_deep) > len(output_shallow)


# --- routers ---

class TestRouters:
    def test_finds_dashboard_routers(self, root):
        output = cmd_routers(root)
        assert "Dashboard (HTML)" in output
        assert "events" in output
        assert "heuristics" in output

    def test_finds_fun_api_routers(self, root):
        output = cmd_routers(root)
        assert "Fun API (JSON)" in output
        assert "cache" in output
        assert "llm" in output

    def test_counts_endpoints(self, root):
        output = cmd_routers(root)
        assert "GET" in output
        assert "POST" in output
