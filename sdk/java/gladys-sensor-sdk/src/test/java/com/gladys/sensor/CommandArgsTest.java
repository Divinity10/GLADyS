package com.gladys.sensor;

import com.google.protobuf.Struct;
import com.google.protobuf.ListValue;
import com.google.protobuf.Value;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class CommandArgsTest {

    private static class TestableCommandArgs extends CommandArgs {
        TestableCommandArgs(Struct raw) {
            super(raw);
        }

        boolean readBoolean(String key, boolean defaultValue) {
            return getBoolean(key, defaultValue);
        }

        int readInt(String key, int defaultValue) {
            return getInt(key, defaultValue);
        }

        String readString(String key, String defaultValue) {
            return getString(key, defaultValue);
        }
    }

    @Test
    void testStartArgsDefaults() {
        StartArgs args = new StartArgs(null);
        assertFalse(args.isDryRun());
    }

    @Test
    void testStartArgsFromStruct() {
        Struct struct = CommandArgs.builder()
                .put("dry_run", true)
                .build();

        StartArgs args = new StartArgs(struct);
        assertTrue(args.isDryRun());
    }

    @Test
    void testStartArgsMissingFieldsGetDefaults() {
        // Struct with unrelated field
        Struct struct = CommandArgs.builder()
                .put("something_else", "value")
                .build();

        StartArgs args = new StartArgs(struct);
        assertFalse(args.isDryRun(), "Missing dry_run should default to false");
    }

    @Test
    void testStopArgsDefaults() {
        StopArgs args = new StopArgs(null);
        assertFalse(args.isForce());
        assertEquals(5000, args.getTimeoutMs());
    }

    @Test
    void testRecoverArgsDefaults() {
        RecoverArgs args = new RecoverArgs(null);
        assertEquals("default", args.getStrategy());
    }

    @Test
    void testHealthCheckArgsDefaults() {
        HealthCheckArgs args = new HealthCheckArgs(null);
        assertFalse(args.isDeep());
    }

    @Test
    void testRawEscapeHatch() {
        Struct struct = CommandArgs.builder()
                .put("custom_key", "custom_value")
                .put("dry_run", true)
                .build();

        StartArgs args = new StartArgs(struct);

        // raw() escape hatch returns the value
        assertEquals("custom_value", args.raw("custom_key", "fallback"));

        // raw() returns default for missing keys
        assertEquals("fallback", args.raw("nonexistent", "fallback"));

        // raw Struct is accessible
        assertNotNull(args.raw());
        assertTrue(args.raw().containsFields("custom_key"));
    }

    @Test
    void testStopArgsFromStruct() {
        Struct struct = StopArgs.testArgs(true, false);
        StopArgs args = new StopArgs(struct);
        assertTrue(args.isForce());
    }

    @Test
    void testRecoverArgsFromStruct() {
        Struct struct = RecoverArgs.testArgs("restart");
        RecoverArgs args = new RecoverArgs(struct);
        assertEquals("restart", args.getStrategy());
    }

    @Test
    void testHealthCheckArgsFromStruct() {
        Struct struct = HealthCheckArgs.testArgs(true);
        HealthCheckArgs args = new HealthCheckArgs(struct);
        assertTrue(args.isDeep());
    }

    @Test
    void testStructToMap() {
        Struct struct = CommandArgs.builder()
                .put("name", "test")
                .put("count", 42)
                .put("enabled", true)
                .build();

        var map = CommandArgs.structToMap(struct);
        assertEquals("test", map.get("name"));
        assertEquals(42.0, map.get("count"));
        assertEquals(true, map.get("enabled"));
    }

    @Test
    void testGetBooleanCoercesStringTrue() {
        Struct struct = CommandArgs.builder()
                .put("enabled", "true")
                .build();
        TestableCommandArgs args = new TestableCommandArgs(struct);
        assertTrue(args.readBoolean("enabled", false));
    }

    @Test
    void testGetBooleanCoercesStringYes() {
        Struct struct = CommandArgs.builder()
                .put("enabled", "yes")
                .build();
        TestableCommandArgs args = new TestableCommandArgs(struct);
        assertTrue(args.readBoolean("enabled", false));
    }

    @Test
    void testGetBooleanCoercesNumberOne() {
        Struct struct = Struct.newBuilder()
                .putFields("enabled", Value.newBuilder().setNumberValue(1.0).build())
                .build();
        TestableCommandArgs args = new TestableCommandArgs(struct);
        assertTrue(args.readBoolean("enabled", false));
    }

    @Test
    void testGetBooleanCoercesNumberZero() {
        Struct struct = Struct.newBuilder()
                .putFields("enabled", Value.newBuilder().setNumberValue(0.0).build())
                .build();
        TestableCommandArgs args = new TestableCommandArgs(struct);
        assertFalse(args.readBoolean("enabled", true));
    }

    @Test
    void testGetIntCoercesString() {
        Struct struct = CommandArgs.builder()
                .put("count", "42")
                .build();
        TestableCommandArgs args = new TestableCommandArgs(struct);
        assertEquals(42, args.readInt("count", 0));
    }

    @Test
    void testGetIntInvalidStringReturnsDefault() {
        Struct struct = CommandArgs.builder()
                .put("count", "abc")
                .build();
        TestableCommandArgs args = new TestableCommandArgs(struct);
        assertEquals(7, args.readInt("count", 7));
    }

    @Test
    void testGetStringCoercesBool() {
        Struct struct = CommandArgs.builder()
                .put("value", true)
                .build();
        TestableCommandArgs args = new TestableCommandArgs(struct);
        assertEquals("true", args.readString("value", "fallback"));
    }

    @Test
    void testGetStringCoercesNumber() {
        Struct struct = Struct.newBuilder()
                .putFields("value", Value.newBuilder().setNumberValue(3.14).build())
                .build();
        TestableCommandArgs args = new TestableCommandArgs(struct);
        assertEquals("3.14", args.readString("value", "fallback"));
    }

    @Test
    void testRawReturnsNestedStruct() {
        Struct nested = Struct.newBuilder()
                .putFields("name", Value.newBuilder().setStringValue("config").build())
                .putFields("enabled", Value.newBuilder().setBoolValue(true).build())
                .build();
        Struct root = Struct.newBuilder()
                .putFields("config", Value.newBuilder().setStructValue(nested).build())
                .build();
        StartArgs args = new StartArgs(root);

        Object value = args.raw("config", Map.of());
        assertInstanceOf(Map.class, value);

        @SuppressWarnings("unchecked")
        Map<String, Object> map = (Map<String, Object>) value;
        assertEquals("config", map.get("name"));
        assertEquals(true, map.get("enabled"));
    }

    @Test
    void testRawReturnsListValue() {
        Struct child = Struct.newBuilder()
                .putFields("item", Value.newBuilder().setStringValue("nested").build())
                .build();
        Value listValue = Value.newBuilder()
                .setListValue(ListValue.newBuilder()
                        .addValues(Value.newBuilder().setStringValue("first").build())
                        .addValues(Value.newBuilder().setNumberValue(2.0).build())
                        .addValues(Value.newBuilder().setStructValue(child).build())
                        .build())
                .build();
        Struct root = Struct.newBuilder()
                .putFields("items", listValue)
                .build();
        StartArgs args = new StartArgs(root);

        Object value = args.raw("items", List.of());
        assertInstanceOf(List.class, value);

        @SuppressWarnings("unchecked")
        List<Object> list = (List<Object>) value;
        assertEquals("first", list.get(0));
        assertEquals(2.0, list.get(1));
        assertInstanceOf(Map.class, list.get(2));

        @SuppressWarnings("unchecked")
        Map<String, Object> nested = (Map<String, Object>) list.get(2);
        assertEquals("nested", nested.get("item"));
    }
}
