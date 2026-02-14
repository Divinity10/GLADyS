package com.gladys.sensor;

import com.google.protobuf.Struct;

/**
 * Arguments for the STOP command.
 */
public class StopArgs extends CommandArgs {

    public StopArgs(Struct raw) {
        super(raw);
    }

    /**
     * Create StopArgs from a protobuf Struct.
     *
     * @param struct Protobuf struct (may be null)
     * @return StopArgs instance
     */
    public static StopArgs fromStruct(Struct struct) {
        return new StopArgs(struct);
    }

    /**
     * Check if this is a forced stop (skip graceful shutdown).
     *
     * @return True if force=true
     */
    public boolean isForce() {
        return getBoolean("force", false);
    }

    /**
     * Get shutdown timeout in milliseconds.
     *
     * @return Timeout value or 5000 if not specified
     */
    public long getTimeoutMs() {
        return getLong("timeout_ms", 5000);
    }

    /**
     * Create test args with defaults.
     *
     * @return Struct with default values
     */
    public static Struct testArgs() {
        return Struct.getDefaultInstance();
    }

    /**
     * Create test args for STOP command.
     *
     * @param force Whether to force stop
     * @param flush Whether to flush pending events
     * @return Struct suitable for testing
     */
    public static Struct testArgs(boolean force, boolean flush) {
        return CommandArgs.builder()
                .put("force", force)
                .put("flush", flush)
                .build();
    }
}
