package com.gladys.sensor;

/**
 * Standard intent values for GLADyS events.
 * Intent indicates whether an event requires a response or is purely informational.
 */
public final class Intent {

    /**
     * Event requires a response/action from the system.
     * Example: User asks a question, game state requires decision.
     */
    public static final String ACTIONABLE = "actionable";

    /**
     * Event is purely informational, no response needed.
     * Example: Telemetry, status updates, logging.
     */
    public static final String INFORMATIONAL = "informational";

    /**
     * Intent classification is uncertain.
     * System will use default heuristics to determine routing.
     */
    public static final String UNKNOWN = "unknown";

    private Intent() {
        // Prevent instantiation
    }
}
