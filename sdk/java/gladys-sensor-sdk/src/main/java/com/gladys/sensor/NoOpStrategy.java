package com.gladys.sensor;

import gladys.v1.Common;

/** Passthrough strategy that always allows publishing. */
public class NoOpStrategy implements FlowStrategy {
    @Override
    public boolean shouldPublish(Common.Event event) {
        return true;
    }
}
