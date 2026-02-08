package com.gladys.sensor;

import gladys.v1.Orchestrator;

/**
 * One-shot registration helper for sensors.
 */
public final class SensorRegistration {

    private SensorRegistration() {
    }

    public static Orchestrator.RegisterResponse register(GladysClient client,
                                                          String sensorId, String sensorType,
                                                          Orchestrator.ComponentCapabilities capabilities) {
        return client.register(sensorId, sensorType, capabilities);
    }
}
