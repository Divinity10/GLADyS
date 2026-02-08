package com.gladys.sensor;

import com.google.protobuf.ListValue;
import com.google.protobuf.Struct;
import com.google.protobuf.Timestamp;
import com.google.protobuf.Value;
import gladys.v1.Common;

import java.time.Instant;
import java.util.Map;
import java.util.UUID;

/**
 * Fluent builder for GLADyS Event protobuf messages.
 * Populates fields that sensors are responsible for (1-5, 11-12, 15).
 * Fields populated downstream (6-10) are not exposed.
 */
public class EventBuilder {

    private final String source;
    private String rawText;
    private Map<String, Object> structured;
    private String intent;
    private Map<String, Object> evaluationData;

    public EventBuilder(String source) {
        if (source == null || source.isEmpty()) {
            throw new IllegalArgumentException("source must not be null or empty");
        }
        this.source = source;
    }

    public EventBuilder text(String rawText) {
        this.rawText = rawText;
        return this;
    }

    public EventBuilder structured(Map<String, Object> structured) {
        this.structured = structured;
        return this;
    }

    public EventBuilder intent(String intent) {
        this.intent = intent;
        return this;
    }

    public EventBuilder evaluationData(Map<String, Object> evaluationData) {
        this.evaluationData = evaluationData;
        return this;
    }

    public Common.Event build() {
        Instant now = Instant.now();

        Common.Event.Builder builder = Common.Event.newBuilder()
                .setId(UUID.randomUUID().toString())
                .setTimestamp(Timestamp.newBuilder()
                        .setSeconds(now.getEpochSecond())
                        .setNanos(now.getNano())
                        .build())
                .setSource(source)
                .setMetadata(Common.RequestMetadata.newBuilder()
                        .setRequestId(UUID.randomUUID().toString())
                        .setTimestampMs(now.toEpochMilli())
                        .setSourceComponent(source)
                        .build());

        if (rawText != null) {
            builder.setRawText(rawText);
        }
        if (structured != null) {
            builder.setStructured(mapToStruct(structured));
        }
        if (intent != null) {
            builder.setIntent(intent);
        }
        if (evaluationData != null) {
            builder.setEvaluationData(mapToStruct(evaluationData));
        }

        return builder.build();
    }

    static Struct mapToStruct(Map<String, Object> map) {
        Struct.Builder structBuilder = Struct.newBuilder();
        for (Map.Entry<String, Object> entry : map.entrySet()) {
            structBuilder.putFields(entry.getKey(), objectToValue(entry.getValue()));
        }
        return structBuilder.build();
    }

    private static Value objectToValue(Object obj) {
        if (obj == null) {
            return Value.newBuilder().setNullValueValue(0).build();
        } else if (obj instanceof String) {
            return Value.newBuilder().setStringValue((String) obj).build();
        } else if (obj instanceof Number) {
            return Value.newBuilder().setNumberValue(((Number) obj).doubleValue()).build();
        } else if (obj instanceof Boolean) {
            return Value.newBuilder().setBoolValue((Boolean) obj).build();
        } else if (obj instanceof Map) {
            @SuppressWarnings("unchecked")
            Map<String, Object> mapObj = (Map<String, Object>) obj;
            return Value.newBuilder().setStructValue(mapToStruct(mapObj)).build();
        } else if (obj instanceof Iterable) {
            ListValue.Builder listBuilder = ListValue.newBuilder();
            for (Object item : (Iterable<?>) obj) {
                listBuilder.addValues(objectToValue(item));
            }
            return Value.newBuilder().setListValue(listBuilder.build()).build();
        } else {
            return Value.newBuilder().setStringValue(obj.toString()).build();
        }
    }
}
