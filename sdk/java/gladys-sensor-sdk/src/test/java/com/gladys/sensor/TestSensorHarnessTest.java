package com.gladys.sensor;

import com.gladys.sensor.testing.TestSensorHarness;
import gladys.v1.Common;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class TestSensorHarnessTest {

    private TestSensorHarness harness;

    @BeforeEach
    void setUp() {
        CommandDispatcher dispatcher = CommandDispatcher.builder()
                .onStart(args -> null)
                .onStop(args -> null)
                .onPause(() -> null)
                .onResume(() -> null)
                .onReload(() -> null)
                .onHealthCheck(args -> null)
                .onRecover(args -> null)
                .build();

        harness = new TestSensorHarness(dispatcher);
    }

    @Test
    void testDispatchAllSevenCommands() {
        // START -> ACTIVE
        CommandDispatcher.DispatchResult result = harness.dispatchStart(StartArgs.testArgs(false));
        assertFalse(result.hasError());
        assertEquals(Common.ComponentState.COMPONENT_STATE_ACTIVE, harness.getState());

        // PAUSE -> PAUSED
        result = harness.dispatchPause();
        assertFalse(result.hasError());
        assertEquals(Common.ComponentState.COMPONENT_STATE_PAUSED, harness.getState());

        // RESUME -> ACTIVE
        result = harness.dispatchResume();
        assertFalse(result.hasError());
        assertEquals(Common.ComponentState.COMPONENT_STATE_ACTIVE, harness.getState());

        // RELOAD -> ACTIVE
        result = harness.dispatchReload();
        assertFalse(result.hasError());
        assertEquals(Common.ComponentState.COMPONENT_STATE_ACTIVE, harness.getState());

        // HEALTH_CHECK -> unchanged (ACTIVE)
        result = harness.dispatchHealthCheck(HealthCheckArgs.testArgs(false));
        assertFalse(result.hasError());
        assertEquals(Common.ComponentState.COMPONENT_STATE_ACTIVE, harness.getState());

        // RECOVER -> ACTIVE
        result = harness.dispatchRecover(RecoverArgs.testArgs("default"));
        assertFalse(result.hasError());
        assertEquals(Common.ComponentState.COMPONENT_STATE_ACTIVE, harness.getState());

        // STOP -> STOPPED
        result = harness.dispatchStop(StopArgs.testArgs(false, false));
        assertFalse(result.hasError());
        assertEquals(Common.ComponentState.COMPONENT_STATE_STOPPED, harness.getState());
    }

    @Test
    void testGetSetState() {
        // Initial state is UNKNOWN
        assertEquals(Common.ComponentState.COMPONENT_STATE_UNKNOWN, harness.getState());

        // Set state directly
        harness.setState(Common.ComponentState.COMPONENT_STATE_ACTIVE);
        assertEquals(Common.ComponentState.COMPONENT_STATE_ACTIVE, harness.getState());

        // Set to ERROR
        harness.setState(Common.ComponentState.COMPONENT_STATE_ERROR);
        assertEquals(Common.ComponentState.COMPONENT_STATE_ERROR, harness.getState());
    }
}
