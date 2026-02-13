# GLADyS Benchmarking Strategy

**Goal:** empirically validate the "Polyglot Architecture" (Python Orchestrator + Rust Memory Fast Path) against a pure Python baseline. We need to prove that the complexity cost of Rust is paid for by necessary performance gains in the critical path.

---

## 1. Critical Paths to Measure

We are comparing two implementations of the **Salience Gateway** (the "Amygdala"):

1. **Python Implementation** (`src/memory/python`): Easy to write, ecosystem rich, but GIL-bound.
2. **Rust Implementation** (`src/memory/rust`): High performance, type-safe, but higher complexity.

### The Test Loop

`Sensor (Mock)` -> `Orchestrator` -> `SalienceGateway (Target)` -> `Orchestrator`

We measure the **Round Trip Time (RTT)** seen by the Orchestrator. This includes gRPC serialization overhead, which is a real-world cost.

---

## 2. Benchmark Scenarios & Success Criteria

### Scenario A: The "Gamer" Load (Active Usage)

* **Conditions:** 100 events/second (e.g., rapid movement, combat logs, chat). 500 active heuristics.
* **Target Metric:** p99 Latency < 10ms.
* **Why:** To ensure the system feels "real-time" and doesn't lag the game.

### Scenario B: The "Mouse/Eye" Stress (High Frequency)

* **Conditions:** 1,000 events/second (e.g., raw cursor tracking, gaze data). 2,000 active heuristics.
* **Target Metric:** Throughput > 1,000 req/s without dropping events.
* **Why:** To determine if we can handle raw sensor streams or if pre-aggregation is required.

### Scenario C: The "Wisdom" Load (Memory Volume)

* **Conditions:** 10,000 loaded heuristics. Mixed traffic (10 events/sec).
* **Target Metric:** Memory footprint < 500MB. Lookup time < 5ms.
* **Why:** As GLADyS learns, she will accumulate thousands of micro-rules. Retrieval must remain O(1) or O(log n), not O(n).

---

## 3. Interpretation & Action Guide

Use this table to diagnose issues based on benchmark results.

| Metric | Condition | Diagnosis | Possible Solution / Action |
| :--- | :--- | :--- | :--- |
| **Python Throughput** | Caps at ~200-500 req/s | **GIL Contention.** The CPU is spending all its time locking/unlocking the Global Interpreter Lock while iterating heuristics. | **Action:** Confirm transition to Rust for this workload. Python cannot handle this density of CPU-bound checks without heavy multiprocessing (which adds IPC overhead). |
| **Rust Throughput** | Caps unexpectedly low | **Lock Contention.** Readers are fighting for the `RwLock<MemoryCache>`. | **Action:** Shard the cache (e.g., 4 shards based on Event ID hash) or switch to a lock-free read structure (e.g., `evmap`). |
| **Latency p99** | Spikes > 50ms (Periodic) | **Garbage Collection (GC).** Python is pausing to clean up thousands of temporary objects created during matching. | **Action (Python):** Reduce object creation (use `__slots__`, reuse buffers). <br>**Action (Rust):** Check for large allocations in the hot path. Pre-allocate vectors. |
| **Memory Usage** | Rust > Python | **Structure Bloat.** Rust structs might be storing redundant strings instead of references/interned strings. | **Action:** Use `Arc<str>` for shared strings (like heuristic names/sources) to deduplicate memory. |
| **Accuracy** | Rust != Python | **Logic Drift.** The matching algorithms (word overlap, fuzzy match) have diverged. | **Action:** Run `tests/test_proto_contract.py` or equivalent logic parity tests. Do not optimize speed until output is identical. |

---

## 4. Specific Code Optimizations

If benchmarks fail to meet targets, apply these specific patterns.

### Level 1: Algorithmic Fixes (Low Effort)

* **HashSet Pre-calculation (Rust):**
  * *Issue:* Creating `HashSet` from `condition_text` on every request is O(N) allocation.
  * *Fix:* Store the `HashSet<String>` or `BTreeSet` inside `CachedHeuristic` at load time. Request matching becomes pure set intersection (read-only).
* **Early Exit:**
  * *Issue:* Checking all 5,000 heuristics even after a perfect match found.
  * *Fix:* Sort heuristics by `confidence` descending. Return immediately on first match > 0.9 confidence.

### Level 2: Architectural Fixes (Medium Effort)

* **Batching:**
  * *Issue:* gRPC overhead per packet is high (~0.5ms).
  * *Fix:* Sensors send `BatchEvent` containing 10-50 updates. SalienceGateway processes matches in parallel loops.

### Level 3: "Nuclear" Options (High Effort)

* **SIMD Vectorization:**
  * *Use Case:* If we move to embedding-based matching in the fast path.
  * *Fix:* Use SIMD instructions (AVX2/NEON) to compute cosine similarity for 8 vectors at once.
* **Shared Memory (shm):**
  * *Use Case:* If gRPC local loopback is the bottleneck (>50% of time).
  * *Fix:* Use memory-mapped files or shared memory ring buffers for IPC between Orchestrator and Memory.

---

## 5. How to Run Benchmarks

1. **Ensure Environment Isolation:** Stop all other Docker containers.
2. **Run the Benchmark Script:**

    ```bash
    # Run baseline (Python)
    python src/integration/benchmark_salience.py --target python --rate 100 --duration 30

    # Run challenger (Rust)
    python src/integration/benchmark_salience.py --target rust --rate 100 --duration 30
    ```

3. **Analyze Report:** Look at the `p99` and `throughput` columns in the output JSON.
