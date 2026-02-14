package com.gladys.sensor;

import com.google.protobuf.Struct;
import gladys.v1.Common;
import gladys.v1.Orchestrator;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.*;

class CommandDispatcherTest {

    private AtomicBoolean errorHandlerCalled;

    @BeforeEach
    void setUp() {
        errorHandlerCalled = new AtomicBoolean(false);
    }

    @Test
    void testDispatchStartSetsActive() {
        CommandDispatcher dispatcher = CommandDispatcher.builder()
                .onStart(args -> null)
                .build();

        CommandDispatcher.DispatchResult result = dispatcher.dispatch(
                Orchestrator.Command.COMMAND_START, Struct.getDefaultInstance());

        assertFalse(result.hasError());
        assertEquals(Common.ComponentState.COMPONENT_STATE_ACTIVE, result.state);
        assertEquals(Common.ComponentState.COMPONENT_STATE_ACTIVE, dispatcher.getCurrentState());
    }

    @Test
    void testDispatchStopSetsStopped() {
        CommandDispatcher dispatcher = CommandDispatcher.builder()
                .onStop(args -> null)
                .build();

        CommandDispatcher.DispatchResult result = dispatcher.dispatch(
                Orchestrator.Command.COMMAND_STOP, Struct.getDefaultInstance());

        assertFalse(result.hasError());
        assertEquals(Common.ComponentState.COMPONENT_STATE_STOPPED, result.state);
        assertEquals(Common.ComponentState.COMPONENT_STATE_STOPPED, dispatcher.getCurrentState());
    }

    @Test
    void testDispatchPauseSetsPaused() {
        CommandDispatcher dispatcher = CommandDispatcher.builder()
                .onPause(() -> null)
                .build();

        CommandDispatcher.DispatchResult result = dispatcher.dispatch(
                Orchestrator.Command.COMMAND_PAUSE, Struct.getDefaultInstance());

        assertFalse(result.hasError());
        assertEquals(Common.ComponentState.COMPONENT_STATE_PAUSED, result.state);
        assertEquals(Common.ComponentState.COMPONENT_STATE_PAUSED, dispatcher.getCurrentState());
    }

    @Test
    void testDispatchResumeFromPausedSetsActive() {
        CommandDispatcher dispatcher = CommandDispatcher.builder()
                .onPause(() -> null)
                .onResume(() -> null)
                .build();

        // First pause
        dispatcher.dispatch(Orchestrator.Command.COMMAND_PAUSE, Struct.getDefaultInstance());
        assertEquals(Common.ComponentState.COMPONENT_STATE_PAUSED, dispatcher.getCurrentState());

        // Then resume
        CommandDispatcher.DispatchResult result = dispatcher.dispatch(
                Orchestrator.Command.COMMAND_RESUME, Struct.getDefaultInstance());

        assertFalse(result.hasError());
        assertEquals(Common.ComponentState.COMPONENT_STATE_ACTIVE, result.state);
        assertEquals(Common.ComponentState.COMPONENT_STATE_ACTIVE, dispatcher.getCurrentState());
    }

    @Test
    void testDispatchHealthCheckUnchanged() {
        CommandDispatcher dispatcher = CommandDispatcher.builder()
                .onStart(args -> null)
                .onHealthCheck(args -> null)
                .build();

        // Set state to ACTIVE first
        dispatcher.dispatch(Orchestrator.Command.COMMAND_START, Struct.getDefaultInstance());
        assertEquals(Common.ComponentState.COMPONENT_STATE_ACTIVE, dispatcher.getCurrentState());

        // Health check should not change state
        CommandDispatcher.DispatchResult result = dispatcher.dispatch(
                Orchestrator.Command.COMMAND_HEALTH_CHECK, Struct.getDefaultInstance());

        assertFalse(result.hasError());
        assertEquals(Common.ComponentState.COMPONENT_STATE_ACTIVE, result.state);
        assertEquals(Common.ComponentState.COMPONENT_STATE_ACTIVE, dispatcher.getCurrentState());
    }

    @Test
    void testDispatchRecoverSetsActive() {
        CommandDispatcher dispatcher = CommandDispatcher.builder()
                .onRecover(args -> null)
                .build();

        // Set state to ERROR first
        dispatcher.setCurrentState(Common.ComponentState.COMPONENT_STATE_ERROR);

        CommandDispatcher.DispatchResult result = dispatcher.dispatch(
                Orchestrator.Command.COMMAND_RECOVER, Struct.getDefaultInstance());

        assertFalse(result.hasError());
        assertEquals(Common.ComponentState.COMPONENT_STATE_ACTIVE, result.state);
        assertEquals(Common.ComponentState.COMPONENT_STATE_ACTIVE, dispatcher.getCurrentState());
    }

    @Test
    void testHandlerOverrideState() {
        CommandDispatcher dispatcher = CommandDispatcher.builder()
                .onStart(args -> Common.ComponentState.COMPONENT_STATE_STOPPED)
                .build();

        CommandDispatcher.DispatchResult result = dispatcher.dispatch(
                Orchestrator.Command.COMMAND_START, Struct.getDefaultInstance());

        assertFalse(result.hasError());
        assertEquals(Common.ComponentState.COMPONENT_STATE_STOPPED, result.state);
        assertEquals(Common.ComponentState.COMPONENT_STATE_STOPPED, dispatcher.getCurrentState());
    }

    @Test
    void testHandlerExceptionSetsError() {
        CommandDispatcher dispatcher = CommandDispatcher.builder()
                .onStart(args -> { throw new RuntimeException("startup failed"); })
                .build();

        CommandDispatcher.DispatchResult result = dispatcher.dispatch(
                Orchestrator.Command.COMMAND_START, Struct.getDefaultInstance());

        assertTrue(result.hasError());
        assertEquals("startup failed", result.errorMessage);
        assertEquals(Common.ComponentState.COMPONENT_STATE_ERROR, result.state);
        assertEquals(Common.ComponentState.COMPONENT_STATE_ERROR, dispatcher.getCurrentState());
    }

    @Test
    void testHealthCheckExceptionKeepsState() {
        CommandDispatcher dispatcher = CommandDispatcher.builder()
                .onStart(args -> null)
                .onHealthCheck(args -> { throw new RuntimeException("check failed"); })
                .build();

        // Start first to set ACTIVE state
        dispatcher.dispatch(Orchestrator.Command.COMMAND_START, Struct.getDefaultInstance());
        assertEquals(Common.ComponentState.COMPONENT_STATE_ACTIVE, dispatcher.getCurrentState());

        // Health check failure should preserve ACTIVE state
        CommandDispatcher.DispatchResult result = dispatcher.dispatch(
                Orchestrator.Command.COMMAND_HEALTH_CHECK, Struct.getDefaultInstance());

        assertTrue(result.hasError());
        assertEquals("check failed", result.errorMessage);
        assertEquals(Common.ComponentState.COMPONENT_STATE_ACTIVE, result.state);
        assertEquals(Common.ComponentState.COMPONENT_STATE_ACTIVE, dispatcher.getCurrentState());
    }

    @Test
    void testNoHandlerKeepsStateAndReturnsError() {
        CommandDispatcher dispatcher = CommandDispatcher.builder().build();

        dispatcher.setCurrentState(Common.ComponentState.COMPONENT_STATE_ACTIVE);

        CommandDispatcher.DispatchResult result = dispatcher.dispatch(
                Orchestrator.Command.COMMAND_START, Struct.getDefaultInstance());

        assertTrue(result.hasError());
        assertEquals("No handler registered for COMMAND_START", result.errorMessage);
        assertEquals(Common.ComponentState.COMPONENT_STATE_ACTIVE, result.state);
        assertEquals("No handler registered for COMMAND_START", dispatcher.getLastErrorMessage());
    }

    @Test
    void testErrorHandlerCalled() {
        CommandDispatcher dispatcher = CommandDispatcher.builder()
                .onStart(args -> { throw new RuntimeException("boom"); })
                .onCommandError((cmd, ex, state) -> {
                    errorHandlerCalled.set(true);
                    assertEquals(Orchestrator.Command.COMMAND_START, cmd);
                    assertEquals("boom", ex.getMessage());
                    // Return STOPPED instead of default ERROR
                    return Common.ComponentState.COMPONENT_STATE_STOPPED;
                })
                .build();

        CommandDispatcher.DispatchResult result = dispatcher.dispatch(
                Orchestrator.Command.COMMAND_START, Struct.getDefaultInstance());

        assertTrue(errorHandlerCalled.get());
        assertTrue(result.hasError());
        assertEquals("boom", result.errorMessage);
        assertEquals(Common.ComponentState.COMPONENT_STATE_STOPPED, result.state);
        assertEquals(Common.ComponentState.COMPONENT_STATE_STOPPED, dispatcher.getCurrentState());
    }

    @Test
    void testHealthCheckExceptionCallsErrorHandler() {
        CommandDispatcher dispatcher = CommandDispatcher.builder()
                .onStart(args -> null)
                .onHealthCheck(args -> { throw new RuntimeException("health boom"); })
                .onCommandError((cmd, ex, state) -> {
                    errorHandlerCalled.set(true);
                    assertEquals(Orchestrator.Command.COMMAND_HEALTH_CHECK, cmd);
                    assertEquals("health boom", ex.getMessage());
                    return Common.ComponentState.COMPONENT_STATE_STOPPED;
                })
                .build();

        dispatcher.dispatch(Orchestrator.Command.COMMAND_START, Struct.getDefaultInstance());

        CommandDispatcher.DispatchResult result = dispatcher.dispatch(
                Orchestrator.Command.COMMAND_HEALTH_CHECK, Struct.getDefaultInstance());

        assertTrue(errorHandlerCalled.get());
        assertTrue(result.hasError());
        assertEquals(Common.ComponentState.COMPONENT_STATE_ACTIVE, result.state);
        assertEquals(Common.ComponentState.COMPONENT_STATE_ACTIVE, dispatcher.getCurrentState());
    }

    @Test
    void testErrorHandlerThrowingDoesNotEscapeDispatch() {
        CommandDispatcher dispatcher = CommandDispatcher.builder()
                .onStart(args -> { throw new RuntimeException("handler failed"); })
                .onCommandError((cmd, ex, state) -> {
                    throw new RuntimeException("error handler failed");
                })
                .build();

        CommandDispatcher.DispatchResult result = assertDoesNotThrow(() ->
                dispatcher.dispatch(Orchestrator.Command.COMMAND_START, Struct.getDefaultInstance()));

        assertTrue(result.hasError());
        assertEquals("handler failed", result.errorMessage);
        assertEquals(Common.ComponentState.COMPONENT_STATE_ERROR, result.state);
        assertEquals(Common.ComponentState.COMPONENT_STATE_ERROR, dispatcher.getCurrentState());
    }

    @Test
    void testDispatchIsSynchronized() throws Exception {
        Method dispatchMethod = CommandDispatcher.class.getDeclaredMethod(
                "dispatch", Orchestrator.Command.class, Struct.class);
        assertTrue(Modifier.isSynchronized(dispatchMethod.getModifiers()));

        CommandDispatcher dispatcher = CommandDispatcher.builder()
                .onStart(args -> null)
                .onStop(args -> null)
                .build();

        int threads = 8;
        int iterationsPerThread = 200;
        ExecutorService executor = Executors.newFixedThreadPool(threads);
        CountDownLatch ready = new CountDownLatch(threads);
        CountDownLatch start = new CountDownLatch(1);
        AtomicReference<Throwable> firstFailure = new AtomicReference<>();
        AtomicInteger failureCount = new AtomicInteger();

        try {
            for (int i = 0; i < threads; i++) {
                final boolean useStart = i % 2 == 0;
                executor.submit(() -> {
                    ready.countDown();
                    try {
                        start.await();
                        for (int j = 0; j < iterationsPerThread; j++) {
                            dispatcher.dispatch(
                                    useStart ? Orchestrator.Command.COMMAND_START : Orchestrator.Command.COMMAND_STOP,
                                    Struct.getDefaultInstance());
                        }
                    } catch (Throwable t) {
                        failureCount.incrementAndGet();
                        firstFailure.compareAndSet(null, t);
                    }
                });
            }

            assertTrue(ready.await(5, TimeUnit.SECONDS));
            start.countDown();
        } finally {
            executor.shutdown();
            assertTrue(executor.awaitTermination(10, TimeUnit.SECONDS));
        }

        if (firstFailure.get() != null) {
            fail("dispatch() failed during concurrent calls: " + firstFailure.get().getClass().getSimpleName());
        }
        assertEquals(0, failureCount.get(), "Expected no exceptions during concurrent dispatch calls");
    }
}
