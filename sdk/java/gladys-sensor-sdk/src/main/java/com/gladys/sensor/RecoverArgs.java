package com.gladys.sensor;

import com.google.protobuf.Struct;

/**
 * Arguments for the RECOVER command.
 */
public class RecoverArgs extends CommandArgs {

    public RecoverArgs(Struct raw) {
        super(raw);
    }

    /**
     * Create RecoverArgs from a protobuf Struct.
     *
     * @param struct Protobuf struct (may be null)
     * @return RecoverArgs instance
     */
    public static RecoverArgs fromStruct(Struct struct) {
        return new RecoverArgs(struct);
    }

    /**
     * Get the recovery strategy.
     *
     * @return Strategy name (e.g., "restart", "reset", "reconnect") or "default"
     */
    public String getStrategy() {
        return getString("strategy", "default");
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
     * Create test args for RECOVER command.
     *
     * @param strategy Recovery strategy name
     * @return Struct suitable for testing
     */
    public static Struct testArgs(String strategy) {
        return CommandArgs.builder()
                .put("strategy", strategy)
                .build();
    }
}
