package com.gladys.sensor;

import java.util.Map;
import java.util.logging.Logger;

/** Factory for creating flow control strategies from config. */
public final class FlowStrategyFactory {
    private static final Logger logger = Logger.getLogger(FlowStrategyFactory.class.getName());

    private FlowStrategyFactory() {
    }

    public static FlowStrategy create(Map<String, Object> config) {
        if (config == null) {
            return new NoOpStrategy();
        }

        Object rawName = config.get("strategy");
        String strategyName = rawName instanceof String
                ? ((String) rawName).toLowerCase()
                : "none";

        if ("none".equals(strategyName)) {
            return new NoOpStrategy();
        }

        if ("rate_limit".equals(strategyName)) {
            int maxEvents = parsePositiveInt(config.get("max_events"), "max_events");
            int windowSeconds = parsePositiveInt(config.get("window_seconds"), "window_seconds");
            return new RateLimitStrategy(maxEvents, windowSeconds);
        }

        logger.warning("Unknown flow control strategy '" + strategyName + "', falling back to NoOpStrategy");
        return new NoOpStrategy();
    }

    private static int parsePositiveInt(Object value, String field) {
        if (value instanceof Number) {
            double numeric = ((Number) value).doubleValue();
            if (numeric > 0 && numeric == Math.rint(numeric) && numeric <= Integer.MAX_VALUE) {
                return (int) numeric;
            }
            throw new IllegalArgumentException(field + " must be a positive integer");
        }

        if (value instanceof String) {
            try {
                int parsed = Integer.parseInt(((String) value).trim());
                if (parsed > 0) {
                    return parsed;
                }
            } catch (NumberFormatException ignored) {
                // handled below
            }
            throw new IllegalArgumentException(field + " must be a positive integer");
        }

        throw new IllegalArgumentException(field + " must be a positive integer");
    }
}
