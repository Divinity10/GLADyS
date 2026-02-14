package com.gladys.sensor;

/**
 * Timeout configuration for gRPC calls to the orchestrator.
 * All timeout values are in milliseconds. A value of 0 or negative means no timeout.
 */
public class TimeoutConfig {

    /** Timeout for publishEvent RPC in milliseconds (default: 100ms) */
    public final long publishEventMs;

    /** Timeout for heartbeat RPC in milliseconds (default: 5000ms) */
    public final long heartbeatMs;

    /** Timeout for register RPC in milliseconds (default: 10000ms) */
    public final long registerMs;

    /**
     * Create a timeout configuration with specific values.
     *
     * @param publishEventMs Timeout for event publishing (milliseconds)
     * @param heartbeatMs Timeout for heartbeat (milliseconds)
     * @param registerMs Timeout for registration (milliseconds)
     */
    public TimeoutConfig(long publishEventMs, long heartbeatMs, long registerMs) {
        this.publishEventMs = publishEventMs;
        this.heartbeatMs = heartbeatMs;
        this.registerMs = registerMs;
    }

    /**
     * Create default timeout configuration.
     * - publishEvent: 100ms
     * - heartbeat: 5000ms
     * - register: 10000ms
     *
     * @return Default timeout configuration
     */
    public static TimeoutConfig defaults() {
        return new TimeoutConfig(100, 5000, 10000);
    }

    /**
     * Create a configuration with no timeouts (for testing).
     * All RPCs will wait indefinitely.
     *
     * @return No-timeout configuration
     */
    public static TimeoutConfig noTimeout() {
        return new TimeoutConfig(0, 0, 0);
    }

    /**
     * Create a builder for custom timeout configuration.
     *
     * @return Builder initialized with default values
     */
    public static Builder builder() {
        return new Builder();
    }

    public static class Builder {
        private long publishEventMs = 100;
        private long heartbeatMs = 5000;
        private long registerMs = 10000;

        /**
         * Set the timeout for event publishing.
         *
         * @param milliseconds Timeout in milliseconds (0 = no timeout)
         * @return This builder
         */
        public Builder publishEventMs(long milliseconds) {
            this.publishEventMs = milliseconds;
            return this;
        }

        /**
         * Set the timeout for heartbeat calls.
         *
         * @param milliseconds Timeout in milliseconds (0 = no timeout)
         * @return This builder
         */
        public Builder heartbeatMs(long milliseconds) {
            this.heartbeatMs = milliseconds;
            return this;
        }

        /**
         * Set the timeout for registration calls.
         *
         * @param milliseconds Timeout in milliseconds (0 = no timeout)
         * @return This builder
         */
        public Builder registerMs(long milliseconds) {
            this.registerMs = milliseconds;
            return this;
        }

        /**
         * Build the timeout configuration.
         *
         * @return Immutable TimeoutConfig instance
         */
        public TimeoutConfig build() {
            return new TimeoutConfig(publishEventMs, heartbeatMs, registerMs);
        }
    }
}
