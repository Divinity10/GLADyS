package com.gladys.sensor;

import com.google.protobuf.Struct;

/**
 * Arguments for the START command.
 */
public class StartArgs extends CommandArgs {

    public StartArgs(Struct raw) {
        super(raw);
    }

    /**
     * Create StartArgs from a protobuf Struct.
     *
     * @param struct Protobuf struct (may be null)
     * @return StartArgs instance
     */
    public static StartArgs fromStruct(Struct struct) {
        return new StartArgs(struct);
    }

    /**
     * Check if this is a dry-run start (validate only, don't actually start).
     *
     * @return True if dry_run=true
     */
    public boolean isDryRun() {
        return getBoolean("dry_run", false);
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
     * Create test args for START command.
     *
     * @param dryRun Whether this is a dry run
     * @return Struct suitable for testing
     */
    public static Struct testArgs(boolean dryRun) {
        return CommandArgs.builder()
                .put("dry_run", dryRun)
                .build();
    }
}
