package com.gladys.sensor;

import com.google.protobuf.Struct;

/**
 * Arguments for the HEALTH_CHECK command.
 */
public class HealthCheckArgs extends CommandArgs {

    public HealthCheckArgs(Struct raw) {
        super(raw);
    }

    /**
     * Create HealthCheckArgs from a protobuf Struct.
     *
     * @param struct Protobuf struct (may be null)
     * @return HealthCheckArgs instance
     */
    public static HealthCheckArgs fromStruct(Struct struct) {
        return new HealthCheckArgs(struct);
    }

    /**
     * Check if this is a deep health check (comprehensive validation).
     *
     * @return True if deep=true
     */
    public boolean isDeep() {
        return getBoolean("deep", false);
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
     * Create test args for HEALTH_CHECK command.
     *
     * @param deep Whether to perform deep check
     * @return Struct suitable for testing
     */
    public static Struct testArgs(boolean deep) {
        return CommandArgs.builder()
                .put("deep", deep)
                .build();
    }
}
