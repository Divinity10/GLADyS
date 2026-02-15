package com.gladys.sensor;

import java.util.Objects;

public final class EmitResult {
    private final int sent;
    private final int suppressed;

    public EmitResult(int sent, int suppressed) {
        this.sent = sent;
        this.suppressed = suppressed;
    }

    public int sent() {
        return sent;
    }

    public int suppressed() {
        return suppressed;
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        if (!(obj instanceof EmitResult)) {
            return false;
        }
        EmitResult other = (EmitResult) obj;
        return sent == other.sent && suppressed == other.suppressed;
    }

    @Override
    public int hashCode() {
        return Objects.hash(sent, suppressed);
    }
}
