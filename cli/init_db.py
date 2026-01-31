#!/usr/bin/env python3
"""Initialize the GLADyS PostgreSQL database for local development.

Creates the gladys user/database and runs all migrations.
Run via: make init-db  (or: python cli/init_db.py)

Prerequisites:
  - PostgreSQL running locally on port 5432
  - sudo/postgres superuser access (for CREATE USER / CREATE DATABASE)
  - pgvector extension installed (apt install postgresql-NN-pgvector)
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "src" / "db" / "migrations"

DB_NAME = os.environ.get("DB_NAME", "gladys")
DB_USER = os.environ.get("DB_USER", "gladys")
DB_PASS = os.environ.get("DB_PASS", "gladys")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_HOST = os.environ.get("DB_HOST", "localhost")


def _psql_cmd(dbname: str, as_postgres: bool) -> list[str]:
    """Build the psql command prefix for the given auth mode."""
    if as_postgres and sys.platform != "win32":
        # Peer auth via sudo — no host flag needed
        return ["sudo", "-u", "postgres", "psql", "-p", DB_PORT, "-d", dbname]
    # Password auth as gladys user
    return ["psql", "-h", DB_HOST, "-p", DB_PORT, "-U", DB_USER, "-d", dbname]


def _psql_env() -> dict[str, str]:
    """Environment with PGPASSWORD set for password auth."""
    env = os.environ.copy()
    env["PGPASSWORD"] = DB_PASS
    return env


def run_psql(sql: str, dbname: str = "postgres", as_postgres: bool = True) -> tuple[bool, str]:
    """Run a SQL statement via psql. Returns (success, output)."""
    cmd = _psql_cmd(dbname, as_postgres) + ["-c", sql]
    env = None if as_postgres else _psql_env()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=env)
    output = result.stdout.strip()
    if result.returncode != 0:
        return False, result.stderr.strip()
    return True, output


def run_psql_file(filepath: Path, dbname: str, as_postgres: bool = True) -> tuple[bool, str]:
    """Run a SQL file via psql. Returns (success, output)."""
    if as_postgres and sys.platform != "win32":
        # postgres user can't read files in /root etc, so pipe stdin instead
        cmd = _psql_cmd(dbname, as_postgres)
        with open(filepath) as f:
            sql = f.read()
        result = subprocess.run(cmd, input=sql, capture_output=True, text=True, timeout=60)
    else:
        cmd = _psql_cmd(dbname, as_postgres) + ["-f", str(filepath)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=_psql_env())
    output = result.stdout.strip()
    if result.returncode != 0:
        return False, result.stderr.strip()
    return True, output


def check_postgres_running() -> bool:
    """Check if PostgreSQL is accepting connections."""
    ok, _ = run_psql("SELECT 1;")
    return ok


def create_user() -> bool:
    """Create the gladys database user if it doesn't exist."""
    ok, output = run_psql(f"SELECT 1 FROM pg_roles WHERE rolname = '{DB_USER}';")
    if not ok:
        print(f"  FAIL  Cannot query pg_roles: {output}")
        return False
    if "1" in output:
        print(f"  OK    User '{DB_USER}' already exists")
        return True

    ok, output = run_psql(f"CREATE USER {DB_USER} WITH PASSWORD '{DB_PASS}';")
    if ok:
        print(f"  OK    Created user '{DB_USER}'")
    else:
        print(f"  FAIL  Could not create user: {output}")
    return ok


def create_database() -> bool:
    """Create the gladys database if it doesn't exist."""
    ok, output = run_psql(f"SELECT 1 FROM pg_database WHERE datname = '{DB_NAME}';")
    if not ok:
        print(f"  FAIL  Cannot query pg_database: {output}")
        return False
    if "1" in output:
        print(f"  OK    Database '{DB_NAME}' already exists")
        return True

    ok, output = run_psql(f"CREATE DATABASE {DB_NAME} OWNER {DB_USER};")
    if ok:
        print(f"  OK    Created database '{DB_NAME}'")
    else:
        print(f"  FAIL  Could not create database: {output}")
    return ok


def grant_permissions() -> bool:
    """Grant the gladys user permissions to create extensions."""
    ok, output = run_psql(f"GRANT ALL PRIVILEGES ON DATABASE {DB_NAME} TO {DB_USER};")
    if not ok:
        print(f"  WARN  Could not grant privileges: {output}")
    return True


def create_extensions() -> bool:
    """Create required extensions (needs superuser)."""
    for ext in ("uuid-ossp", "vector"):
        ok, output = run_psql(
            f'CREATE EXTENSION IF NOT EXISTS "{ext}";', dbname=DB_NAME, as_postgres=True
        )
        if ok:
            print(f"  OK    Extension {ext}")
        else:
            if "already exists" in output:
                print(f"  OK    Extension {ext} (already installed)")
            else:
                print(f"  FAIL  Extension {ext}: {output}")
                return False
    return True


def run_migrations() -> bool:
    """Run all migration files in order as the gladys user."""
    if not MIGRATIONS_DIR.exists():
        print(f"  FAIL  Migrations directory not found: {MIGRATIONS_DIR}")
        return False

    migrations = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migrations:
        print("  SKIP  No migration files found")
        return True

    all_ok = True
    for migration in migrations:
        # Run as gladys user (password auth) — avoids /root permission issues
        ok, output = run_psql_file(migration, DB_NAME, as_postgres=False)
        if ok:
            print(f"  OK    {migration.name}")
        else:
            if "already exists" in output or "NOTICE" in output:
                print(f"  OK    {migration.name} (already applied)")
            else:
                print(f"  FAIL  {migration.name}")
                for line in output.splitlines()[:5]:
                    print(f"        {line}")
                all_ok = False

    return all_ok


def main() -> int:
    print("GLADyS Database Setup")
    print("=" * 40)
    print(f"  Host: {DB_HOST}  Port: {DB_PORT}  DB: {DB_NAME}  User: {DB_USER}")
    print()

    print("Checking PostgreSQL:")
    if not check_postgres_running():
        print("  FAIL  PostgreSQL is not running or not accessible")
        print("        Start it with: sudo systemctl start postgresql")
        return 1
    print("  OK    PostgreSQL is running")

    print("\nCreating user and database:")
    if not create_user():
        return 1
    if not create_database():
        return 1
    grant_permissions()

    print("\nCreating extensions (requires superuser):")
    if not create_extensions():
        return 1

    print("\nRunning migrations:")
    if not run_migrations():
        print("\nMigrations had errors. Check output above.")
        return 1

    print("\n" + "=" * 40)
    print("Database ready.")
    print(f"  DSN: host={DB_HOST} port={DB_PORT} dbname={DB_NAME} user={DB_USER}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
