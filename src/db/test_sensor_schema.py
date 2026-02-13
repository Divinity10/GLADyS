"""
Test suite for sensor dashboard database schema.

Verifies:
- Table creation (sensors, sensor_status, sensor_metrics)
- Foreign key constraints and CASCADE behavior
- Unique constraints
- CHECK constraints
- Indexes
- Table ownership
"""

import asyncio
import os
import uuid
from datetime import datetime

import asyncpg
import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def db_connection():
    """Create a test database connection."""
    # Use TEST_DB_URL environment variable or default
    db_url = os.getenv(
        "TEST_DB_URL",
        "postgresql://gladys:gladys@localhost:5432/gladys"
    )

    conn = await asyncpg.connect(db_url)
    try:
        yield conn
    finally:
        await conn.close()


@pytest_asyncio.fixture
async def clean_tables(db_connection):
    """Clean sensor tables before each test."""
    await db_connection.execute("DELETE FROM sensor_metrics")
    await db_connection.execute("DELETE FROM sensor_status")
    await db_connection.execute("DELETE FROM sensors")
    await db_connection.execute("DELETE FROM skills")
    yield
    # Cleanup after test
    await db_connection.execute("DELETE FROM sensor_metrics")
    await db_connection.execute("DELETE FROM sensor_status")
    await db_connection.execute("DELETE FROM sensors")
    await db_connection.execute("DELETE FROM skills")


@pytest.mark.asyncio
async def test_sensors_table_exists(db_connection):
    """Verify sensors table exists with all expected columns."""
    result = await db_connection.fetch("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'sensors'
        ORDER BY ordinal_position
    """)

    columns = {row['column_name']: row for row in result}

    # Verify all required columns exist
    assert 'id' in columns
    assert 'skill_id' in columns
    assert 'sensor_name' in columns
    assert 'sensor_type' in columns
    assert 'source_pattern' in columns
    assert 'heartbeat_interval_s' in columns
    assert 'adapter_language' in columns
    assert 'driver_count' in columns
    assert 'expected_consolidation_min' in columns
    assert 'expected_consolidation_max' in columns
    assert 'manifest' in columns
    assert 'config' in columns
    assert 'created_at' in columns
    assert 'updated_at' in columns

    # Verify data types
    assert 'uuid' in columns['id']['data_type']
    assert 'uuid' in columns['skill_id']['data_type']
    assert columns['sensor_name']['data_type'] == 'text'
    assert columns['sensor_type']['data_type'] == 'text'
    assert columns['manifest']['data_type'] == 'jsonb'


@pytest.mark.asyncio
async def test_sensor_status_table_exists(db_connection):
    """Verify sensor_status table exists with all expected columns."""
    result = await db_connection.fetch("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'sensor_status'
        ORDER BY ordinal_position
    """)

    columns = {row['column_name']: row for row in result}

    # Verify all required columns exist
    assert 'sensor_id' in columns
    assert 'status' in columns
    assert 'last_heartbeat' in columns
    assert 'last_error' in columns
    assert 'error_count' in columns
    assert 'active_sources' in columns
    assert 'events_received' in columns
    assert 'events_published' in columns
    assert 'updated_at' in columns

    # Verify data types
    assert 'uuid' in columns['sensor_id']['data_type']
    assert columns['status']['data_type'] == 'text'
    assert 'ARRAY' in columns['active_sources']['data_type']
    assert columns['events_received']['data_type'] == 'bigint'
    assert columns['events_published']['data_type'] == 'bigint'


@pytest.mark.asyncio
async def test_sensor_metrics_table_exists(db_connection):
    """Verify sensor_metrics table exists with all expected columns."""
    result = await db_connection.fetch("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'sensor_metrics'
        ORDER BY ordinal_position
    """)

    columns = {row['column_name']: row for row in result}

    # Verify all required columns exist
    assert 'id' in columns
    assert 'sensor_id' in columns
    assert 'timestamp' in columns
    assert 'events_received' in columns
    assert 'events_published' in columns
    assert 'events_filtered' in columns
    assert 'events_errored' in columns
    assert 'avg_latency_ms' in columns
    assert 'consolidation_ratio' in columns
    assert 'inbound_queue_depth' in columns
    assert 'outbound_queue_depth' in columns
    assert 'driver_metrics' in columns
    assert 'created_at' in columns

    # Verify data types
    assert 'uuid' in columns['id']['data_type']
    assert 'uuid' in columns['sensor_id']['data_type']
    assert columns['events_received']['data_type'] == 'bigint'
    assert columns['events_published']['data_type'] == 'bigint'
    assert columns['driver_metrics']['data_type'] == 'jsonb'


@pytest.mark.asyncio
async def test_sensor_skill_fk_cascade(db_connection, clean_tables):
    """Verify sensors.skill_id foreign key with CASCADE delete."""
    # Create a skill pack
    skill_id = await db_connection.fetchval("""
        INSERT INTO skills (plugin_id, name, version, category, manifest)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
    """, 'melvor-pack', 'Melvor Pack', '1.0.0', 'game', '{}')

    # Create a sensor
    sensor_id = await db_connection.fetchval("""
        INSERT INTO sensors (skill_id, sensor_name, sensor_type, source_pattern, manifest)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
    """, skill_id, 'melvor-sensor', 'push', 'melvor', '{}')

    # Verify sensor was created
    count = await db_connection.fetchval(
        "SELECT COUNT(*) FROM sensors WHERE id = $1",
        sensor_id
    )
    assert count == 1

    # Delete the skill pack
    await db_connection.execute("DELETE FROM skills WHERE id = $1", skill_id)

    # Verify sensor was CASCADE deleted
    count = await db_connection.fetchval(
        "SELECT COUNT(*) FROM sensors WHERE id = $1",
        sensor_id
    )
    assert count == 0


@pytest.mark.asyncio
async def test_sensor_status_fk_cascade(db_connection, clean_tables):
    """Verify sensor_status.sensor_id foreign key with CASCADE delete."""
    # Create skill pack and sensor
    skill_id = await db_connection.fetchval("""
        INSERT INTO skills (plugin_id, name, version, category, manifest)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
    """, 'melvor-pack', 'Melvor Pack', '1.0.0', 'game', '{}')

    sensor_id = await db_connection.fetchval("""
        INSERT INTO sensors (skill_id, sensor_name, sensor_type, source_pattern, manifest)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
    """, skill_id, 'melvor-sensor', 'push', 'melvor', '{}')

    # Create sensor status
    await db_connection.execute("""
        INSERT INTO sensor_status (sensor_id, status)
        VALUES ($1, $2)
    """, sensor_id, 'active')

    # Verify status was created
    count = await db_connection.fetchval(
        "SELECT COUNT(*) FROM sensor_status WHERE sensor_id = $1",
        sensor_id
    )
    assert count == 1

    # Delete the sensor
    await db_connection.execute("DELETE FROM sensors WHERE id = $1", sensor_id)

    # Verify sensor_status was CASCADE deleted
    count = await db_connection.fetchval(
        "SELECT COUNT(*) FROM sensor_status WHERE sensor_id = $1",
        sensor_id
    )
    assert count == 0


@pytest.mark.asyncio
async def test_sensor_metrics_fk_cascade(db_connection, clean_tables):
    """Verify sensor_metrics.sensor_id foreign key with CASCADE delete."""
    # Create skill pack and sensor
    skill_id = await db_connection.fetchval("""
        INSERT INTO skills (plugin_id, name, version, category, manifest)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
    """, 'melvor-pack', 'Melvor Pack', '1.0.0', 'game', '{}')

    sensor_id = await db_connection.fetchval("""
        INSERT INTO sensors (skill_id, sensor_name, sensor_type, source_pattern, manifest)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
    """, skill_id, 'melvor-sensor', 'push', 'melvor', '{}')

    # Create multiple sensor metrics
    await db_connection.execute("""
        INSERT INTO sensor_metrics (sensor_id, events_received, events_published)
        VALUES ($1, $2, $3)
    """, sensor_id, 100, 5)

    await db_connection.execute("""
        INSERT INTO sensor_metrics (sensor_id, events_received, events_published)
        VALUES ($1, $2, $3)
    """, sensor_id, 200, 10)

    # Verify metrics were created
    count = await db_connection.fetchval(
        "SELECT COUNT(*) FROM sensor_metrics WHERE sensor_id = $1",
        sensor_id
    )
    assert count == 2

    # Delete the sensor
    await db_connection.execute("DELETE FROM sensors WHERE id = $1", sensor_id)

    # Verify sensor_metrics were CASCADE deleted
    count = await db_connection.fetchval(
        "SELECT COUNT(*) FROM sensor_metrics WHERE sensor_id = $1",
        sensor_id
    )
    assert count == 0


@pytest.mark.asyncio
async def test_sensors_unique_constraint(db_connection, clean_tables):
    """Verify unique constraint on (skill_id, sensor_name)."""
    # Create a skill pack
    skill_id = await db_connection.fetchval("""
        INSERT INTO skills (plugin_id, name, version, category, manifest)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
    """, 'melvor-pack', 'Melvor Pack', '1.0.0', 'game', '{}')

    # Create first sensor
    await db_connection.execute("""
        INSERT INTO sensors (skill_id, sensor_name, sensor_type, source_pattern, manifest)
        VALUES ($1, $2, $3, $4, $5)
    """, skill_id, 'melvor-sensor', 'push', 'melvor', '{}')

    # Attempt to create duplicate sensor with same skill_id and sensor_name
    with pytest.raises(asyncpg.UniqueViolationError):
        await db_connection.execute("""
            INSERT INTO sensors (skill_id, sensor_name, sensor_type, source_pattern, manifest)
            VALUES ($1, $2, $3, $4, $5)
        """, skill_id, 'melvor-sensor', 'push', 'melvor', '{}')


@pytest.mark.asyncio
async def test_check_constraints(db_connection, clean_tables):
    """Verify CHECK constraints on sensor_type and status fields."""
    # Create a skill pack
    skill_id = await db_connection.fetchval("""
        INSERT INTO skills (plugin_id, name, version, category, manifest)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
    """, 'melvor-pack', 'Melvor Pack', '1.0.0', 'game', '{}')

    # Test invalid sensor_type (should fail)
    with pytest.raises(asyncpg.CheckViolationError):
        await db_connection.execute("""
            INSERT INTO sensors (skill_id, sensor_name, sensor_type, source_pattern, manifest)
            VALUES ($1, $2, $3, $4, $5)
        """, skill_id, 'invalid-sensor', 'invalid_type', 'test', '{}')

    # Test valid sensor_type 'push'
    sensor_id = await db_connection.fetchval("""
        INSERT INTO sensors (skill_id, sensor_name, sensor_type, source_pattern, manifest)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
    """, skill_id, 'push-sensor', 'push', 'test', '{}')
    assert sensor_id is not None

    # Test valid sensor_type 'poll'
    sensor_id2 = await db_connection.fetchval("""
        INSERT INTO sensors (skill_id, sensor_name, sensor_type, source_pattern, manifest)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
    """, skill_id, 'poll-sensor', 'poll', 'test', '{}')
    assert sensor_id2 is not None

    # Create sensor_status with valid status
    await db_connection.execute("""
        INSERT INTO sensor_status (sensor_id, status)
        VALUES ($1, $2)
    """, sensor_id, 'active')

    # Test invalid status (should fail)
    with pytest.raises(asyncpg.CheckViolationError):
        await db_connection.execute("""
            INSERT INTO sensor_status (sensor_id, status)
            VALUES ($1, $2)
        """, sensor_id2, 'invalid_status')

    # Test all valid status values
    valid_statuses = ['inactive', 'active', 'disconnected', 'error', 'recovering']
    for i, status in enumerate(valid_statuses):
        # Create a new sensor for each status test
        sid = await db_connection.fetchval("""
            INSERT INTO sensors (skill_id, sensor_name, sensor_type, source_pattern, manifest)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
        """, skill_id, f'status-test-{i}', 'push', 'test', '{}')

        await db_connection.execute("""
            INSERT INTO sensor_status (sensor_id, status)
            VALUES ($1, $2)
        """, sid, status)


@pytest.mark.asyncio
async def test_indexes_exist(db_connection):
    """Verify all required indexes are created."""
    result = await db_connection.fetch("""
        SELECT indexname
        FROM pg_indexes
        WHERE tablename IN ('sensors', 'sensor_status', 'sensor_metrics')
    """)

    index_names = {row['indexname'] for row in result}

    # Sensors indexes
    assert 'idx_sensors_skill' in index_names
    assert 'idx_sensors_source_pattern' in index_names
    assert 'idx_sensors_type' in index_names

    # Sensor_status indexes
    assert 'idx_sensor_status_status' in index_names
    assert 'idx_sensor_status_heartbeat' in index_names

    # Sensor_metrics indexes
    assert 'idx_sensor_metrics_sensor_time' in index_names
    assert 'idx_sensor_metrics_timestamp' in index_names


@pytest.mark.asyncio
async def test_table_ownership(db_connection):
    """Verify table ownership is set to gladys user."""
    result = await db_connection.fetch("""
        SELECT tablename, tableowner
        FROM pg_tables
        WHERE tablename IN ('sensors', 'sensor_status', 'sensor_metrics')
    """)

    for row in result:
        assert row['tableowner'] == 'gladys', \
            f"Table {row['tablename']} owned by {row['tableowner']}, expected 'gladys'"


@pytest.mark.asyncio
async def test_full_sensor_registration_flow(db_connection, clean_tables):
    """Integration test: full sensor registration flow with all tables."""
    # Step 1: Create skill pack
    skill_id = await db_connection.fetchval("""
        INSERT INTO skills (plugin_id, name, version, category, manifest)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
    """, 'melvor-pack', 'Melvor Idle Pack', '1.0.0', 'game', '{"description": "Melvor Idle sensor pack"}')

    # Step 2: Create sensor
    sensor_id = await db_connection.fetchval("""
        INSERT INTO sensors (
            skill_id, sensor_name, sensor_type, source_pattern,
            heartbeat_interval_s, driver_count,
            expected_consolidation_min, expected_consolidation_max,
            manifest, config
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        RETURNING id
    """, skill_id, 'melvor-sensor', 'push', 'melvor',
        30, 1, 10.0, 40.0,
        '{"version": "1.0.0", "event_types": []}',
        '{"enabled": true}')

    # Step 3: Create initial sensor status
    await db_connection.execute("""
        INSERT INTO sensor_status (
            sensor_id, status, last_heartbeat,
            events_received, events_published
        )
        VALUES ($1, $2, $3, $4, $5)
    """, sensor_id, 'active', datetime.utcnow(), 0, 0)

    # Step 4: Create heartbeat metrics
    await db_connection.execute("""
        INSERT INTO sensor_metrics (
            sensor_id, events_received, events_published,
            events_filtered, events_errored,
            avg_latency_ms, consolidation_ratio,
            inbound_queue_depth, outbound_queue_depth,
            driver_metrics
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
    """, sensor_id, 1247, 52, 0, 0,
        15.3, 24.0, 0, 0,
        '{}')

    # Step 5: Query sensor with joins (verify all data accessible)
    result = await db_connection.fetchrow("""
        SELECT
            s.sensor_name,
            s.sensor_type,
            s.source_pattern,
            ss.status,
            ss.events_received as lifetime_received,
            ss.events_published as lifetime_published,
            sm.events_received as metric_received,
            sm.events_published as metric_published,
            sm.consolidation_ratio
        FROM sensors s
        JOIN sensor_status ss ON s.id = ss.sensor_id
        JOIN sensor_metrics sm ON s.id = sm.sensor_id
        WHERE s.id = $1
        ORDER BY sm.timestamp DESC
        LIMIT 1
    """, sensor_id)

    assert result['sensor_name'] == 'melvor-sensor'
    assert result['sensor_type'] == 'push'
    assert result['source_pattern'] == 'melvor'
    assert result['status'] == 'active'
    assert result['metric_received'] == 1247
    assert result['metric_published'] == 52
    assert result['consolidation_ratio'] == 24.0
