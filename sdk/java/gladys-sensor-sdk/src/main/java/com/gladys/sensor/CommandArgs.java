package com.gladys.sensor;

import com.google.protobuf.Struct;
import com.google.protobuf.Value;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Base class for command arguments with lenient parsing.
 * Provides raw access to protobuf Struct and type-safe getters with defaults.
 */
public class CommandArgs {

    private final Struct raw;

    protected CommandArgs(Struct raw) {
        this.raw = raw != null ? raw : Struct.getDefaultInstance();
    }

    /**
     * Get the raw protobuf Struct (escape hatch for advanced usage).
     *
     * @return Raw command arguments as protobuf Struct
     */
    public Struct raw() {
        return raw;
    }

    /**
     * Get a raw value by key with a default.
     *
     * @param key Argument name
     * @param defaultValue Value to return if key is missing
     * @return The value or default
     */
    public Object raw(String key, Object defaultValue) {
        if (!raw.containsFields(key)) {
            return defaultValue;
        }
        Value value = raw.getFieldsOrDefault(key, Value.getDefaultInstance());
        Object converted = protobufValueToJava(value);
        return converted != null ? converted : defaultValue;
    }

    /**
     * Get a string argument with default value.
     *
     * @param key Argument name
     * @param defaultValue Value to return if key is missing or wrong type
     * @return String value or default
     */
    protected String getString(String key, String defaultValue) {
        if (!raw.containsFields(key)) {
            return defaultValue;
        }
        Value value = raw.getFieldsOrDefault(key, Value.getDefaultInstance());
        if (value.hasStringValue()) {
            return value.getStringValue();
        }
        if (value.hasBoolValue()) {
            return String.valueOf(value.getBoolValue());
        }
        if (value.hasNumberValue()) {
            return String.valueOf(value.getNumberValue());
        }
        return defaultValue;
    }

    /**
     * Get a boolean argument with default value.
     *
     * @param key Argument name
     * @param defaultValue Value to return if key is missing or wrong type
     * @return Boolean value or default
     */
    protected boolean getBoolean(String key, boolean defaultValue) {
        if (!raw.containsFields(key)) {
            return defaultValue;
        }
        Value value = raw.getFieldsOrDefault(key, Value.getDefaultInstance());
        if (value.hasBoolValue()) {
            return value.getBoolValue();
        }
        if (value.hasStringValue()) {
            String normalized = value.getStringValue().trim().toLowerCase(Locale.ROOT);
            if (normalized.equals("true") || normalized.equals("1") || normalized.equals("yes")) {
                return true;
            }
            if (normalized.equals("false") || normalized.equals("0") || normalized.equals("no")) {
                return false;
            }
        }
        if (value.hasNumberValue()) {
            return value.getNumberValue() != 0.0;
        }
        return defaultValue;
    }

    /**
     * Get an integer argument with default value.
     *
     * @param key Argument name
     * @param defaultValue Value to return if key is missing or wrong type
     * @return Integer value or default
     */
    protected int getInt(String key, int defaultValue) {
        if (!raw.containsFields(key)) {
            return defaultValue;
        }
        Value value = raw.getFieldsOrDefault(key, Value.getDefaultInstance());
        if (value.hasNumberValue()) {
            return (int) value.getNumberValue();
        }
        if (value.hasStringValue()) {
            try {
                return Integer.parseInt(value.getStringValue());
            } catch (NumberFormatException ignored) {
                return defaultValue;
            }
        }
        return defaultValue;
    }

    /**
     * Get a long argument with default value.
     *
     * @param key Argument name
     * @param defaultValue Value to return if key is missing or wrong type
     * @return Long value or default
     */
    protected long getLong(String key, long defaultValue) {
        if (!raw.containsFields(key)) {
            return defaultValue;
        }
        Value value = raw.getFieldsOrDefault(key, Value.getDefaultInstance());
        if (value.hasNumberValue()) {
            return (long) value.getNumberValue();
        }
        if (value.hasStringValue()) {
            try {
                return Long.parseLong(value.getStringValue());
            } catch (NumberFormatException ignored) {
                return defaultValue;
            }
        }
        return defaultValue;
    }

    /**
     * Get a double argument with default value.
     *
     * @param key Argument name
     * @param defaultValue Value to return if key is missing or wrong type
     * @return Double value or default
     */
    protected double getDouble(String key, double defaultValue) {
        if (!raw.containsFields(key)) {
            return defaultValue;
        }
        Value value = raw.getFieldsOrDefault(key, Value.getDefaultInstance());
        if (value.hasNumberValue()) {
            return value.getNumberValue();
        }
        return defaultValue;
    }

    /**
     * Check if an argument exists.
     *
     * @param key Argument name
     * @return True if argument is present
     */
    protected boolean has(String key) {
        return raw.containsFields(key);
    }

    /**
     * Convert a protobuf Struct to a plain Map.
     *
     * @param struct Protobuf struct
     * @return Map representation
     */
    public static Map<String, Object> structToMap(Struct struct) {
        Map<String, Object> map = new HashMap<>();
        for (Map.Entry<String, Value> entry : struct.getFieldsMap().entrySet()) {
            map.put(entry.getKey(), protobufValueToJava(entry.getValue()));
        }
        return map;
    }

    private static Object protobufValueToJava(Value value) {
        if (value.hasBoolValue()) {
            return value.getBoolValue();
        }
        if (value.hasNumberValue()) {
            return value.getNumberValue();
        }
        if (value.hasStringValue()) {
            return value.getStringValue();
        }
        if (value.hasStructValue()) {
            return structToMap(value.getStructValue());
        }
        if (value.hasListValue()) {
            List<Object> list = new ArrayList<>();
            for (Value item : value.getListValue().getValuesList()) {
                list.add(protobufValueToJava(item));
            }
            return list;
        }
        return null;
    }

    /**
     * Create a builder for test argument construction.
     *
     * @return New builder instance
     */
    public static Builder builder() {
        return new Builder();
    }

    /**
     * Builder for constructing CommandArgs in tests.
     */
    public static class Builder {
        private final Map<String, Value> fields = new HashMap<>();

        public Builder put(String key, String value) {
            fields.put(key, Value.newBuilder().setStringValue(value).build());
            return this;
        }

        public Builder put(String key, boolean value) {
            fields.put(key, Value.newBuilder().setBoolValue(value).build());
            return this;
        }

        public Builder put(String key, int value) {
            fields.put(key, Value.newBuilder().setNumberValue(value).build());
            return this;
        }

        public Builder put(String key, long value) {
            fields.put(key, Value.newBuilder().setNumberValue(value).build());
            return this;
        }

        public Builder put(String key, double value) {
            fields.put(key, Value.newBuilder().setNumberValue(value).build());
            return this;
        }

        public Struct build() {
            return Struct.newBuilder().putAllFields(fields).build();
        }
    }
}
