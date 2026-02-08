package com.gladys.sensor;

import com.google.protobuf.Struct;
import gladys.v1.Common;
import org.junit.jupiter.api.Test;

import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class EventBuilderTest {

    @Test
    void testBuilderSetsRequiredFields() {
        Common.Event event = new EventBuilder("runescape")
                .text("Player received 50 damage")
                .build();

        // id is a UUID
        assertNotNull(event.getId());
        assertFalse(event.getId().isEmpty());
        assertEquals(36, event.getId().length()); // UUID format: 8-4-4-4-12

        // timestamp is set
        assertTrue(event.getTimestamp().getSeconds() > 0);

        // source matches constructor arg
        assertEquals("runescape", event.getSource());

        // raw_text matches
        assertEquals("Player received 50 damage", event.getRawText());

        // metadata is auto-populated
        assertNotNull(event.getMetadata());
        assertFalse(event.getMetadata().getRequestId().isEmpty());
        assertTrue(event.getMetadata().getTimestampMs() > 0);
        assertEquals("runescape", event.getMetadata().getSourceComponent());
    }

    @Test
    void testStructuredDataConversion() {
        Map<String, Object> data = new HashMap<>();
        data.put("event_type", "damage");
        data.put("amount", 50);
        data.put("critical", true);

        Common.Event event = new EventBuilder("runescape")
                .structured(data)
                .build();

        Struct s = event.getStructured();
        assertEquals("damage", s.getFieldsOrThrow("event_type").getStringValue());
        assertEquals(50.0, s.getFieldsOrThrow("amount").getNumberValue());
        assertTrue(s.getFieldsOrThrow("critical").getBoolValue());
    }

    @Test
    void testIntentAndEvaluationData() {
        Map<String, Object> evalData = new HashMap<>();
        evalData.put("answer", "42");
        evalData.put("confidence", 0.95);

        Common.Event event = new EventBuilder("sudoku")
                .intent("actionable")
                .evaluationData(evalData)
                .build();

        assertEquals("actionable", event.getIntent());

        Struct eval = event.getEvaluationData();
        assertEquals("42", eval.getFieldsOrThrow("answer").getStringValue());
        assertEquals(0.95, eval.getFieldsOrThrow("confidence").getNumberValue(), 0.001);
    }
}
