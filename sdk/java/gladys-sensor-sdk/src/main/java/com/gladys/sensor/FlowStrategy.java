package com.gladys.sensor;

import gladys.v1.Common;

/** Strategy interface — called before every event publish. */
public interface FlowStrategy {
    boolean shouldPublish(Common.Event event);
    int availableTokens();
    void consume(int n);
}
