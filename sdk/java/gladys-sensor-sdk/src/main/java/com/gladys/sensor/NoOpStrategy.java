package com.gladys.sensor;

import gladys.v1.Common;

/** Passthrough strategy that always allows publishing. */
public class NoOpStrategy implements FlowStrategy {
    @Override
    public boolean shouldPublish(Common.Event event) {
        return true;
    }

    @Override
    public int availableTokens() {
        return Integer.MAX_VALUE;
    }

    @Override
    public void consume(int n) {
        // no-op
    }
}
