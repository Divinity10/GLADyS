package com.gladys.sensor;

import gladys.v1.Common;

import java.util.function.LongSupplier;

/** Token bucket rate limiter for event publishing. */
public class RateLimitStrategy implements FlowStrategy {
    private static final double NANOS_PER_SECOND = 1_000_000_000.0;

    private final double maxEvents;
    private final double refillRatePerNano;
    private final LongSupplier nanoTimeSupplier;
    private double tokens;
    private long lastRefillNanos;

    public RateLimitStrategy(int maxEvents, int windowSeconds) {
        this(maxEvents, windowSeconds, System::nanoTime);
    }

    RateLimitStrategy(int maxEvents, int windowSeconds, LongSupplier nanoTimeSupplier) {
        if (maxEvents <= 0) {
            throw new IllegalArgumentException("maxEvents must be positive");
        }
        if (windowSeconds <= 0) {
            throw new IllegalArgumentException("windowSeconds must be positive");
        }
        this.maxEvents = maxEvents;
        this.refillRatePerNano = maxEvents / (windowSeconds * NANOS_PER_SECOND);
        this.nanoTimeSupplier = nanoTimeSupplier;
        this.tokens = maxEvents;
        this.lastRefillNanos = nanoTimeSupplier.getAsLong();
    }

    private synchronized void refill() {
        long now = nanoTimeSupplier.getAsLong();
        long elapsedNanos = Math.max(0L, now - lastRefillNanos);
        lastRefillNanos = now;
        tokens = Math.min(maxEvents, tokens + (elapsedNanos * refillRatePerNano));
    }

    @Override
    public synchronized boolean shouldPublish(Common.Event event) {
        refill();
        if (tokens >= 1.0) {
            tokens -= 1.0;
            return true;
        }
        return false;
    }

    @Override
    public synchronized int availableTokens() {
        refill();
        return (int) tokens;
    }

    @Override
    public synchronized void consume(int n) {
        tokens -= n;
    }
}
