# ADR-0006: Observability and Monitoring

| Field | Value |
|-------|-------|
| **Status** | Proposed |
| **Date** | 2025-01-27 |
| **Owner** | Mike Mulcahy (Divinity10) |
| **Contributors** | Scott |
| **Depends On** | ADR-0001, ADR-0004, ADR-0005 |

---

## 1. Context and Problem Statement

GLADyS consists of multiple components across different languages and processes. Without proper observability:
- Performance bottlenecks are invisible
- Debugging cross-component issues is difficult
- Optimization decisions lack data
- Users can't understand system behavior

This ADR defines the observability strategy including metrics, logging, tracing, alerting, and dashboards.

---

## 2. Decision Drivers

1. **Optimization:** Must identify bottlenecks to know when/where to add complexity (per ADR-0004)
2. **Debugging:** Must trace requests across component boundaries
3. **Reliability:** Must detect failures before users notice
4. **Simplicity:** Small team, can't maintain complex infrastructure
5. **Polyglot:** Must work across Rust, Python, and C#
6. **Local-first:** Must work without cloud services

---

## 3. Observability Pillars

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      OBSERVABILITY PILLARS                              │
│                                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │   METRICS   │  │   LOGGING   │  │   TRACING   │  │  ALERTING   │    │
│  │             │  │             │  │             │  │             │    │
│  │ Quantitative│  │ Event-based │  │ Request flow│  │ Automated   │    │
│  │ measurements│  │ records     │  │ across      │  │ notification│    │
│  │             │  │             │  │ components  │  │             │    │
│  │ "How much?" │  │ "What       │  │ "How did    │  │ "Something  │    │
│  │ "How fast?" │  │  happened?" │  │  this flow?"│  │  is wrong!" │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
│         │                │                │                │           │
│         └────────────────┴────────────────┴────────────────┘           │
│                                   │                                     │
│                                   ▼                                     │
│                          ┌─────────────┐                               │
│                          │ DASHBOARDS  │                               │
│                          │             │                               │
│                          │ Visual      │                               │
│                          │ monitoring  │                               │
│                          └─────────────┘                               │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Technology Stack

### 4.1 Selected Technologies

| Pillar | Technology | Rationale |
|--------|------------|-----------|
| **Metrics** | Prometheus | Industry standard, pull-based, local-friendly |
| **Logging** | Structured JSON → Loki | Queryable, integrates with Grafana |
| **Tracing** | OpenTelemetry → Jaeger | Vendor-neutral, polyglot support |
| **Alerting** | Prometheus Alertmanager | Integrates with Prometheus |
| **Dashboards** | Grafana | Unified view of metrics, logs, traces |

### 4.2 Deployment Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     LOCAL DEPLOYMENT                                     │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                     GLADyS COMPONENTS                       │  │
│  │                                                                   │  │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐             │  │
│  │  │Orchestr.│  │Salience │  │Executive│  │ Output  │             │  │
│  │  │  :9090  │  │  :9091  │  │  :9092  │  │  :9093  │             │  │
│  │  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘             │  │
│  │       │            │            │            │                   │  │
│  │       │ /metrics   │ /metrics   │ /metrics   │ /metrics         │  │
│  │       └────────────┴────────────┴────────────┘                   │  │
│  │                           │                                       │  │
│  └───────────────────────────┼───────────────────────────────────────┘  │
│                              │                                          │
│                              ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                    OBSERVABILITY STACK                             │ │
│  │                                                                    │ │
│  │  ┌────────────┐   ┌────────────┐   ┌────────────┐                │ │
│  │  │ Prometheus │   │    Loki    │   │   Jaeger   │                │ │
│  │  │   :9100    │   │   :3100    │   │   :16686   │                │ │
│  │  │            │   │            │   │            │                │ │
│  │  │  Metrics   │   │    Logs    │   │   Traces   │                │ │
│  │  └─────┬──────┘   └─────┬──────┘   └─────┬──────┘                │ │
│  │        │                │                │                        │ │
│  │        └────────────────┼────────────────┘                        │ │
│  │                         │                                         │ │
│  │                         ▼                                         │ │
│  │                  ┌────────────┐                                   │ │
│  │                  │  Grafana   │                                   │ │
│  │                  │   :3000    │                                   │ │
│  │                  └────────────┘                                   │ │
│  │                                                                    │ │
│  └───────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.3 Resource Requirements

| Service | Memory | CPU | Storage | Notes |
|---------|--------|-----|---------|-------|
| Prometheus | 512MB-1GB | Low | 10GB | Depends on metric cardinality |
| Loki | 256MB-512MB | Low | 20GB | Log retention period |
| Jaeger | 256MB-512MB | Low | 5GB | Trace sampling reduces volume |
| Grafana | 256MB | Low | 1GB | Dashboards and queries |
| **Total** | ~1.5-2.5GB | Low | ~36GB | Acceptable overhead |

---

## 5. Metrics

### 5.1 Metric Types

| Type | Description | Example |
|------|-------------|---------|
| **Counter** | Monotonically increasing | `events_processed_total` |
| **Gauge** | Current value, can go up/down | `memory_cache_size` |
| **Histogram** | Distribution of values | `request_duration_seconds` |
| **Summary** | Pre-calculated percentiles | `response_size_bytes` |

### 5.2 Naming Convention

```
{namespace}_{component}_{metric}_{unit}

Examples:
gladys_orchestrator_events_routed_total
gladys_salience_evaluation_duration_seconds
gladys_memory_cache_hit_ratio
gladys_executive_tokens_used_total
```

### 5.3 Metrics by Component

#### 5.3.1 Orchestrator Metrics

```python
# Counters
gladys_orchestrator_events_routed_total{source, target}
gladys_orchestrator_commands_sent_total{command, target}
gladys_orchestrator_errors_total{type, component}

# Gauges
gladys_orchestrator_active_components
gladys_orchestrator_event_queue_depth
gladys_orchestrator_registered_sensors
gladys_orchestrator_registered_subscribers

# Histograms
gladys_orchestrator_routing_duration_seconds{target}
gladys_orchestrator_fanout_duration_seconds
```

#### 5.3.2 Sensor Metrics

```python
# Counters
gladys_sensor_events_emitted_total{sensor_id, event_type}
gladys_sensor_errors_total{sensor_id, error_type}
gladys_sensor_restarts_total{sensor_id}

# Gauges
gladys_sensor_state{sensor_id}  # 0=stopped, 1=starting, 2=active, etc.
gladys_sensor_buffer_size{sensor_id}

# Histograms
gladys_sensor_processing_duration_seconds{sensor_id}
gladys_sensor_event_size_bytes{sensor_id}
```

#### 5.3.3 Salience Gateway Metrics

```python
# Counters
gladys_salience_events_evaluated_total
gladys_salience_events_suppressed_total{reason}
gladys_salience_memory_queries_total{query_type}
gladys_salience_cache_hits_total{cache_type}
gladys_salience_cache_misses_total{cache_type}

# Gauges
gladys_salience_active_modulations
gladys_salience_habituation_rules

# Histograms
gladys_salience_evaluation_duration_seconds
gladys_salience_memory_query_duration_seconds{query_type}
gladys_salience_model_inference_duration_seconds

# Salience distribution (for tuning)
gladys_salience_score{dimension}  # Histogram of scores per dimension
```

#### 5.3.4 Memory Controller Metrics

```python
# Counters
gladys_memory_events_stored_total
gladys_memory_queries_total{type}  # semantic, structured, entity
gladys_memory_cache_evictions_total{level}

# Gauges
gladys_memory_l1_cache_size
gladys_memory_l2_buffer_size
gladys_memory_pending_persist_count
gladys_memory_db_connection_pool_used
gladys_memory_db_connection_pool_available

# Histograms
gladys_memory_query_duration_seconds{type, level}  # Which cache level served
gladys_memory_store_duration_seconds
gladys_memory_embedding_duration_seconds
```

#### 5.3.5 Executive Metrics

```python
# Counters
gladys_executive_decisions_total{action}  # speak, notify, log, none
gladys_executive_tokens_used_total{direction}  # input, output
gladys_executive_errors_total{type}

# Gauges
gladys_executive_context_window_utilization  # 0-1
gladys_executive_active_skills
gladys_executive_active_goals

# Histograms
gladys_executive_decision_duration_seconds
gladys_executive_response_length_tokens
gladys_executive_llm_inference_duration_seconds
```

#### 5.3.6 Output Metrics

```python
# Counters
gladys_output_utterances_total{voice}
gladys_output_interruptions_total
gladys_output_errors_total{type}

# Gauges
gladys_output_queue_depth
gladys_output_current_voice

# Histograms
gladys_output_tts_duration_seconds
gladys_output_audio_duration_seconds  # How long the speech was
gladys_output_time_to_first_audio_seconds
```

#### 5.3.7 Security Metrics (see ADR-0008)

```python
# Counters
gladys_security_permission_checks_total{permission, verdict}  # allow, deny, abort
gladys_security_aborts_total{plugin_id, reason}
gladys_security_consent_grants_total{plugin_id, permission}
gladys_security_consent_revokes_total{plugin_id, permission}

# Gauges
gladys_security_active_plugins{trust_level}  # first_party, signed, unsigned
gladys_security_user_age  # For age-gated permission enforcement

# Histograms
gladys_security_permission_check_duration_seconds{handler}
```

### 5.4 Critical Metrics for Optimization Decisions

These metrics drive the complexity addition framework (ADR-0004):

| Metric | Threshold | Action When Exceeded |
|--------|-----------|---------------------|
| `memory_query_duration_seconds` P95 | > 50ms | Add/tune L1 cache |
| `memory_cache_hit_ratio` | < 0.3 | Adjust cache size/eviction |
| `salience_evaluation_duration_seconds` P95 | > 150ms | Profile model, consider smaller |
| `executive_decision_duration_seconds` P95 | > 500ms | Reduce context, optimize prompts |
| `orchestrator_event_queue_depth` | > 100 | Increase processing capacity |
| `output_time_to_first_audio_seconds` P95 | > 200ms | Tune TTS, consider streaming |

### 5.5 Prometheus Configuration

```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'orchestrator'
    static_configs:
      - targets: ['localhost:9090']
    
  - job_name: 'salience'
    static_configs:
      - targets: ['localhost:9091']
    
  - job_name: 'executive'
    static_configs:
      - targets: ['localhost:9092']
    
  - job_name: 'output'
    static_configs:
      - targets: ['localhost:9093']
    
  - job_name: 'sensors'
    file_sd_configs:
      - files:
          - '/etc/prometheus/sensors/*.json'
        refresh_interval: 30s
```

---

## 6. Logging

### 6.1 Structured Log Format

All components emit JSON-structured logs:

```json
{
  "timestamp": "2025-01-27T14:30:00.123Z",
  "level": "INFO",
  "component": "salience-gateway",
  "message": "Event evaluated",
  "trace_id": "abc123def456",
  "span_id": "789xyz",
  "request_id": "req-001",
  "event_id": "evt-123",
  "source": "minecraft-sensor",
  "salience": {
    "threat": 0.8,
    "novelty": 0.6
  },
  "duration_ms": 45,
  "metadata": {
    "model": "phi-3-mini",
    "cache_hit": false
  }
}
```

### 6.2 Log Levels

| Level | Usage | Examples |
|-------|-------|----------|
| **ERROR** | Failures requiring attention | Component crash, DB connection lost |
| **WARN** | Degraded but functional | Retry succeeded, cache miss spike |
| **INFO** | Normal operations | Event processed, component started |
| **DEBUG** | Detailed debugging | Full event content, query plans |
| **TRACE** | Verbose tracing | Every function entry/exit |

**Production default:** INFO
**Debugging:** DEBUG or TRACE (per-component configurable)

### 6.3 Log Categories

```python
# Standard log fields
REQUIRED_FIELDS = [
    "timestamp",      # ISO 8601
    "level",          # ERROR, WARN, INFO, DEBUG, TRACE
    "component",      # Component ID
    "message",        # Human-readable message
]

TRACING_FIELDS = [
    "trace_id",       # OpenTelemetry trace ID
    "span_id",        # OpenTelemetry span ID
    "request_id",     # Application request ID
]

CONTEXT_FIELDS = [
    "event_id",       # If processing an event
    "entity_id",      # If related to an entity
    "sensor_id",      # If related to a sensor
    "user_action",    # If triggered by user
]
```

### 6.4 Key Log Events

| Component | Event | Level | When |
|-----------|-------|-------|------|
| Orchestrator | `component_registered` | INFO | New component joins |
| Orchestrator | `component_failed` | ERROR | Health check failed |
| Orchestrator | `event_routed` | DEBUG | Event delivered |
| Sensor | `sensor_activated` | INFO | Sensor started |
| Sensor | `event_emitted` | DEBUG | Event created |
| Salience | `event_evaluated` | DEBUG | Salience computed |
| Salience | `event_suppressed` | DEBUG | Below threshold |
| Memory | `cache_miss` | DEBUG | L1 miss, queried L3 |
| Memory | `query_slow` | WARN | Query exceeded budget |
| Executive | `decision_made` | INFO | Action decided |
| Executive | `response_generated` | DEBUG | Full response |
| Output | `speech_started` | DEBUG | TTS began |
| Output | `speech_interrupted` | INFO | User interrupted |

### 6.5 Loki Configuration

```yaml
# loki-config.yaml
auth_enabled: false

server:
  http_listen_port: 3100

ingester:
  lifecycler:
    ring:
      kvstore:
        store: inmemory
      replication_factor: 1
  chunk_idle_period: 5m
  chunk_retain_period: 30s

schema_config:
  configs:
    - from: 2025-01-01
      store: boltdb-shipper
      object_store: filesystem
      schema: v11
      index:
        prefix: index_
        period: 24h

storage_config:
  boltdb_shipper:
    active_index_directory: /loki/index
    cache_location: /loki/cache
    shared_store: filesystem
  filesystem:
    directory: /loki/chunks

limits_config:
  enforce_metric_name: false
  reject_old_samples: true
  reject_old_samples_max_age: 168h  # 7 days
```

### 6.6 Log Shipping

Each component ships logs via Promtail or directly to Loki:

```yaml
# promtail-config.yaml
server:
  http_listen_port: 9080

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://localhost:3100/loki/api/v1/push

scrape_configs:
  - job_name: gladys
    static_configs:
      - targets:
          - localhost
        labels:
          job: gladys
          __path__: /var/log/gladys/*.log
    pipeline_stages:
      - json:
          expressions:
            level: level
            component: component
            trace_id: trace_id
      - labels:
          level:
          component:
          trace_id:
```

---

## 7. Distributed Tracing

### 7.1 Trace Context Propagation

All inter-component calls propagate trace context via gRPC metadata:

```
traceparent: 00-{trace_id}-{span_id}-{flags}
tracestate: gladys=v1
```

### 7.2 Span Definitions

| Span Name | Component | Parent | Description |
|-----------|-----------|--------|-------------|
| `sensor.capture` | Sensor | None | Raw data capture |
| `sensor.process` | Sensor | capture | Processing raw data |
| `sensor.emit` | Sensor | process | Sending to orchestrator |
| `orchestrator.receive` | Orchestrator | emit | Receiving event |
| `orchestrator.fanout` | Orchestrator | receive | Distributing to subscribers |
| `salience.evaluate` | Salience | fanout | Computing salience |
| `salience.model_inference` | Salience | evaluate | LLM/model call |
| `salience.memory_query` | Salience | evaluate | Retrieving memories |
| `memory.query` | Memory | memory_query | Database query |
| `memory.cache_check` | Memory | query | Cache lookup |
| `executive.process` | Executive | fanout | Processing event |
| `executive.llm_inference` | Executive | process | Main LLM call |
| `executive.decide` | Executive | process | Making decision |
| `output.speak` | Output | decide | TTS generation |

### 7.3 Trace Visualization

```
sensor.capture (50ms)
└── sensor.process (30ms)
    └── sensor.emit (5ms)
        └── orchestrator.receive (2ms)
            └── orchestrator.fanout (3ms)
                ├── salience.evaluate (150ms)
                │   ├── salience.model_inference (80ms)
                │   └── salience.memory_query (50ms)
                │       └── memory.query (45ms)
                │           └── memory.cache_check (5ms) [MISS]
                │
                └── executive.process (400ms)
                    ├── executive.llm_inference (350ms)
                    └── executive.decide (30ms)
                        └── output.speak (80ms)
```

### 7.4 OpenTelemetry Configuration

#### Python Components

```python
# otel_config.py
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient, GrpcInstrumentorServer

def configure_tracing(service_name: str):
    # Set up tracer provider
    provider = TracerProvider()
    
    # Configure Jaeger exporter
    jaeger_exporter = JaegerExporter(
        agent_host_name="localhost",
        agent_port=6831,
    )
    
    provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))
    trace.set_tracer_provider(provider)
    
    # Instrument gRPC
    GrpcInstrumentorClient().instrument()
    GrpcInstrumentorServer().instrument()
    
    return trace.get_tracer(service_name)
```

#### Rust Orchestrator

```rust
// Using tracing + opentelemetry crates
use opentelemetry::global;
use opentelemetry_jaeger::new_agent_pipeline;
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::Registry;

fn init_tracing() -> Result<(), Box<dyn Error>> {
    let tracer = new_agent_pipeline()
        .with_service_name("orchestrator")
        .with_endpoint("localhost:6831")
        .install_batch(opentelemetry::runtime::Tokio)?;
    
    let telemetry = tracing_opentelemetry::layer().with_tracer(tracer);
    
    let subscriber = Registry::default()
        .with(telemetry)
        .with(tracing_subscriber::fmt::layer());
    
    tracing::subscriber::set_global_default(subscriber)?;
    Ok(())
}
```

#### C# Executive

```csharp
// Using OpenTelemetry.NET
using OpenTelemetry;
using OpenTelemetry.Trace;

public static class Telemetry
{
    public static TracerProvider ConfigureTracing()
    {
        return Sdk.CreateTracerProviderBuilder()
            .SetResourceBuilder(ResourceBuilder.CreateDefault()
                .AddService("executive"))
            .AddSource("GLADyS.Executive")
            .AddGrpcClientInstrumentation()
            .AddJaegerExporter(o =>
            {
                o.AgentHost = "localhost";
                o.AgentPort = 6831;
            })
            .Build();
    }
}
```

### 7.5 Jaeger Configuration

```yaml
# jaeger-config.yaml (all-in-one for local dev)
collector:
  zipkin:
    host-port: :9411
  otlp:
    enabled: true

query:
  base-path: /jaeger

storage:
  type: badger
  badger:
    ephemeral: false
    directory-key: /badger/key
    directory-value: /badger/data
```

### 7.6 Sampling Strategy

For development: **100% sampling** (capture all traces)

For production (if needed):

```yaml
# Probabilistic sampling
sampling:
  type: probabilistic
  param: 0.1  # 10% of traces

# Rate limiting
sampling:
  type: ratelimiting
  param: 100  # 100 traces per second
```

---

## 8. Alerting

### 8.1 Alert Categories

| Category | Severity | Response Time | Examples |
|----------|----------|---------------|----------|
| **Critical** | P1 | Immediate | System down, data loss risk |
| **Warning** | P2 | Hours | Degraded performance, component unhealthy |
| **Info** | P3 | Days | Approaching limits, optimization opportunity |

### 8.2 Alert Rules

```yaml
# prometheus-alerts.yml
groups:
  - name: gladys_critical
    rules:
      - alert: ComponentDown
        expr: up{job=~"orchestrator|salience|executive|output"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Component {{ $labels.job }} is down"
          description: "{{ $labels.job }} has been unreachable for more than 1 minute"
      
      - alert: ExecutiveLatencyHigh
        expr: histogram_quantile(0.95, gladys_executive_decision_duration_seconds_bucket) > 0.8
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Executive decision latency exceeds budget"
          description: "P95 latency is {{ $value }}s, budget is 0.6s"
      
      - alert: MemoryDatabaseDown
        expr: gladys_memory_db_connection_pool_available == 0
        for: 30s
        labels:
          severity: critical
        annotations:
          summary: "Memory database connection pool exhausted"

  - name: gladys_warning
    rules:
      - alert: HighEventQueueDepth
        expr: gladys_orchestrator_event_queue_depth > 100
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Event queue depth is high"
          description: "Queue depth is {{ $value }}, processing may be falling behind"
      
      - alert: LowCacheHitRate
        expr: gladys_memory_cache_hit_ratio < 0.3
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "Memory cache hit rate is low"
          description: "Cache hit rate is {{ $value }}, consider tuning cache size"
      
      - alert: SensorRestarting
        expr: increase(gladys_sensor_restarts_total[10m]) > 3
        labels:
          severity: warning
        annotations:
          summary: "Sensor {{ $labels.sensor_id }} is restarting frequently"
      
      - alert: HighTokenUsage
        expr: rate(gladys_executive_tokens_used_total[1h]) > 10000
        labels:
          severity: warning
        annotations:
          summary: "High token usage rate"
          description: "Using {{ $value }} tokens/hour"

  - name: gladys_info
    rules:
      - alert: ApproachingContextLimit
        expr: gladys_executive_context_window_utilization > 0.85
        for: 10m
        labels:
          severity: info
        annotations:
          summary: "Context window utilization is high"
          description: "Utilization is {{ $value }}, consider memory summarization"
      
      - alert: SlowMemoryQueries
        expr: histogram_quantile(0.95, gladys_memory_query_duration_seconds_bucket) > 0.04
        for: 15m
        labels:
          severity: info
        annotations:
          summary: "Memory queries approaching budget"
          description: "P95 is {{ $value }}s, budget is 50ms. Consider adding cache."
```

### 8.3 Alertmanager Configuration

```yaml
# alertmanager.yml
global:
  resolve_timeout: 5m

route:
  receiver: 'default'
  group_by: ['alertname', 'severity']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  
  routes:
    - match:
        severity: critical
      receiver: 'critical'
      repeat_interval: 1h
    
    - match:
        severity: warning
      receiver: 'warning'
      repeat_interval: 4h

receivers:
  - name: 'default'
    # Local notification (desktop/log)
    webhook_configs:
      - url: 'http://localhost:9095/alert'
  
  - name: 'critical'
    webhook_configs:
      - url: 'http://localhost:9095/alert'
    # Future: add email, SMS, PagerDuty
  
  - name: 'warning'
    webhook_configs:
      - url: 'http://localhost:9095/alert'
```

### 8.4 Local Alert Notification

Simple Python service to display desktop notifications:

```python
# alert_notifier.py
from flask import Flask, request
import subprocess

app = Flask(__name__)

@app.route('/alert', methods=['POST'])
def handle_alert():
    data = request.json
    for alert in data.get('alerts', []):
        summary = alert['annotations'].get('summary', 'Alert')
        severity = alert['labels'].get('severity', 'info')
        
        # Desktop notification (Linux)
        subprocess.run([
            'notify-send',
            f'GLADyS [{severity.upper()}]',
            summary
        ])
        
        # Also log
        print(f"[{severity}] {summary}")
    
    return 'OK', 200

if __name__ == '__main__':
    app.run(port=9095)
```

---

## 9. Dashboards

### 9.1 Dashboard Organization

| Dashboard | Audience | Purpose |
|-----------|----------|---------|
| **System Overview** | All | High-level health at a glance |
| **Component Deep Dive** | Developers | Detailed metrics per component |
| **Performance Analysis** | Developers | Latency distributions, bottlenecks |
| **Memory System** | Developers | Cache performance, query patterns |
| **User Experience** | All | Response times, speech quality |

### 9.2 System Overview Dashboard

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      GLADyS - SYSTEM OVERVIEW                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  COMPONENT HEALTH                    EVENT THROUGHPUT                   │
│  ┌─────────────────────────┐        ┌─────────────────────────┐        │
│  │ Orchestrator    [GREEN] │        │  Events/min             │        │
│  │ Salience        [GREEN] │        │  ████████████ 450       │        │
│  │ Executive       [GREEN] │        │                         │        │
│  │ Output          [GREEN] │        │  Decisions/min          │        │
│  │ Minecraft Sens  [GREEN] │        │  ████████ 120           │        │
│  │ Audio Sensor    [YELLOW]│        └─────────────────────────┘        │
│  └─────────────────────────┘                                           │
│                                                                         │
│  END-TO-END LATENCY (P95)            RESOURCE USAGE                    │
│  ┌─────────────────────────┐        ┌─────────────────────────┐        │
│  │  Target: 1000ms         │        │  GPU Memory: 18/24 GB   │        │
│  │  Current: 847ms         │        │  ████████████████░░░░   │        │
│  │  ████████████████░░░░   │        │                         │        │
│  │                         │        │  System RAM: 32/64 GB   │        │
│  │  Breakdown:             │        │  ████████████░░░░░░░░   │        │
│  │  Sensor:     52ms       │        │                         │        │
│  │  Salience:  148ms       │        │  CPU: 35%               │        │
│  │  Executive: 512ms       │        │  ███████░░░░░░░░░░░░░   │        │
│  │  Output:     78ms       │        └─────────────────────────┘        │
│  └─────────────────────────┘                                           │
│                                                                         │
│  RECENT ALERTS                       ACTIVE SENSORS                     │
│  ┌─────────────────────────┐        ┌─────────────────────────┐        │
│  │ [WARN] Low cache hit    │        │ ● minecraft-sensor      │        │
│  │        rate (28%)       │        │ ● audio-sensor          │        │
│  │        14:25            │        │ ○ vscode-sensor         │        │
│  │                         │        │ ○ browser-sensor        │        │
│  │ [INFO] Context util     │        └─────────────────────────┘        │
│  │        high (87%)       │                                           │
│  │        14:20            │                                           │
│  └─────────────────────────┘                                           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 9.3 Key Grafana Panels

#### Latency Distribution

```
Panel: Histogram
Query: histogram_quantile(0.95, sum(rate(gladys_executive_decision_duration_seconds_bucket[5m])) by (le))
Title: Executive Decision Latency (P95)
Thresholds: 
  - 500ms: green
  - 600ms: yellow
  - 800ms: red
```

#### Cache Performance

```
Panel: Gauge
Query: sum(gladys_memory_cache_hits_total) / (sum(gladys_memory_cache_hits_total) + sum(gladys_memory_cache_misses_total))
Title: Memory Cache Hit Rate
Thresholds:
  - 0.3: red
  - 0.5: yellow
  - 0.7: green
```

#### Event Flow

```
Panel: Graph
Queries:
  - rate(gladys_sensor_events_emitted_total[1m]) as "Events Emitted"
  - rate(gladys_salience_events_evaluated_total[1m]) as "Events Evaluated"
  - rate(gladys_salience_events_suppressed_total[1m]) as "Events Suppressed"
  - rate(gladys_executive_decisions_total[1m]) as "Decisions Made"
Title: Event Flow Pipeline
```

### 9.4 Grafana Provisioning

```yaml
# grafana/provisioning/datasources/datasources.yml
apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9100
    isDefault: true
  
  - name: Loki
    type: loki
    access: proxy
    url: http://loki:3100
  
  - name: Jaeger
    type: jaeger
    access: proxy
    url: http://jaeger:16686
```

---

## 10. Health Checks

### 10.1 Health Check Endpoints

Each component exposes a health endpoint:

| Component | Endpoint | Port |
|-----------|----------|------|
| Orchestrator | `/health` | 9090 |
| Salience | `/health` | 9091 |
| Executive | `/health` | 9092 |
| Output | `/health` | 9093 |
| Memory | `/health` | 9094 |

### 10.2 Health Check Response

```json
{
  "status": "healthy",           // healthy, degraded, unhealthy
  "component": "salience-gateway",
  "version": "0.1.0",
  "uptime_seconds": 3600,
  "checks": {
    "model_loaded": true,
    "memory_connection": true,
    "gpu_available": true
  },
  "metrics": {
    "events_processed": 12500,
    "avg_latency_ms": 145,
    "error_rate": 0.001
  }
}
```

### 10.3 Health Status Logic

```python
def compute_health_status(checks: dict, metrics: dict) -> str:
    """
    Determine overall health status.
    """
    # Any critical check failed = unhealthy
    critical_checks = ['model_loaded', 'memory_connection']
    for check in critical_checks:
        if not checks.get(check, False):
            return "unhealthy"
    
    # Performance degraded = degraded
    if metrics.get('error_rate', 0) > 0.05:  # >5% errors
        return "degraded"
    
    if metrics.get('avg_latency_ms', 0) > 300:  # Slow
        return "degraded"
    
    return "healthy"
```

---

## 11. Correlation IDs

### 11.1 ID Types

| ID | Scope | Generated By | Purpose |
|----|-------|--------------|---------|
| `trace_id` | Full request journey | First component (sensor) | OpenTelemetry tracing |
| `span_id` | Single operation | Each component | OpenTelemetry tracing |
| `request_id` | Application request | Orchestrator | Application-level correlation |
| `event_id` | Single event | Sensor | Event identity |
| `session_id` | User session | Executive | Group related interactions |

### 11.2 Propagation

```
Sensor creates event:
  event_id: evt-001
  trace_id: abc123
  span_id: span-001

Orchestrator receives:
  trace_id: abc123 (propagated)
  span_id: span-002 (new)
  request_id: req-001 (generated)
  parent_span_id: span-001

Salience receives:
  trace_id: abc123 (propagated)
  span_id: span-003 (new)
  request_id: req-001 (propagated)
  event_id: evt-001 (propagated)
```

### 11.3 Querying by Correlation ID

**Find all logs for a trace:**
```
{trace_id="abc123"}
```

**Find all logs for an event:**
```
{event_id="evt-001"}
```

**Find slow traces:**
```
{component="executive"} |= "decision_made" | json | duration_ms > 500
```

---

## 12. Implementation Phases

### 12.1 Phase 1: Foundation (Implement Now)

| Item | Priority | Effort |
|------|----------|--------|
| Structured JSON logging | High | Low |
| Prometheus metrics endpoints | High | Medium |
| Basic health check endpoints | High | Low |
| Request ID propagation | High | Low |
| Console dashboard (text-based) | Medium | Low |

### 12.2 Phase 2: Visibility (Week 2-3)

| Item | Priority | Effort |
|------|----------|--------|
| OpenTelemetry tracing | High | Medium |
| Prometheus + Grafana setup | High | Medium |
| System overview dashboard | High | Medium |
| Loki log aggregation | Medium | Medium |
| Basic alert rules | Medium | Low |

### 12.3 Phase 3: Maturity (Month 2+)

| Item | Priority | Effort |
|------|----------|--------|
| Jaeger trace visualization | Medium | Low |
| Deep-dive dashboards | Medium | Medium |
| Advanced alert rules | Medium | Medium |
| Alertmanager notifications | Low | Low |
| Performance analysis dashboards | Low | Medium |

---

## 13. Docker Compose for Observability Stack

```yaml
# docker-compose.observability.yml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus
    ports:
      - "9100:9090"
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
      - ./prometheus/alerts:/etc/prometheus/alerts
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=15d'

  loki:
    image: grafana/loki:latest
    container_name: loki
    ports:
      - "3100:3100"
    volumes:
      - ./loki/loki-config.yml:/etc/loki/local-config.yaml
      - loki_data:/loki
    command: -config.file=/etc/loki/local-config.yaml

  promtail:
    image: grafana/promtail:latest
    container_name: promtail
    volumes:
      - ./promtail/promtail-config.yml:/etc/promtail/config.yml
      - /var/log/gladys:/var/log/gladys:ro
    command: -config.file=/etc/promtail/config.yml

  jaeger:
    image: jaegertracing/all-in-one:latest
    container_name: jaeger
    ports:
      - "6831:6831/udp"   # Agent
      - "16686:16686"     # UI
      - "14268:14268"     # Collector HTTP
    environment:
      - COLLECTOR_ZIPKIN_HOST_PORT=:9411

  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    ports:
      - "3000:3000"
    volumes:
      - ./grafana/provisioning:/etc/grafana/provisioning
      - ./grafana/dashboards:/var/lib/grafana/dashboards
      - grafana_data:/var/lib/grafana
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_USERS_ALLOW_SIGN_UP=false

  alertmanager:
    image: prom/alertmanager:latest
    container_name: alertmanager
    ports:
      - "9093:9093"
    volumes:
      - ./alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml

volumes:
  prometheus_data:
  loki_data:
  grafana_data:
```

---

## 14. Consequences

### 14.1 Positive

1. Full visibility into system behavior
2. Data-driven optimization decisions
3. Faster debugging with correlated logs/traces
4. Proactive alerting before user impact
5. Standard tools with strong community support

### 14.2 Negative

1. Additional infrastructure to maintain
2. Storage requirements for metrics/logs/traces
3. Learning curve for Grafana/PromQL
4. Slight performance overhead from instrumentation

### 14.3 Risks

1. Alert fatigue if thresholds not tuned
2. Storage growth if retention not managed
3. Trace sampling may miss important requests

---

## 15. Related Decisions

- ADR-0001: GLADyS Architecture
- ADR-0004: Memory Schema Details (complexity triggers)
- ADR-0005: gRPC Service Contracts (tracing integration)
- ADR-0007: Adaptive Algorithms (metrics for learning)
- ADR-0008: Security and Privacy (security audit log, metrics)

---

## 16. Appendix: Quick Reference

### Start Observability Stack

```bash
docker-compose -f docker-compose.observability.yml up -d
```

### Access Points

| Service | URL |
|---------|-----|
| Grafana | http://localhost:3000 (admin/admin) |
| Prometheus | http://localhost:9100 |
| Jaeger | http://localhost:16686 |
| Loki | http://localhost:3100 |
| Alertmanager | http://localhost:9093 |

### Useful PromQL Queries

```promql
# End-to-end P95 latency
histogram_quantile(0.95, sum(rate(gladys_executive_decision_duration_seconds_bucket[5m])) by (le))

# Events per minute by source
sum(rate(gladys_sensor_events_emitted_total[1m])) by (sensor_id) * 60

# Cache hit rate
sum(gladys_memory_cache_hits_total) / (sum(gladys_memory_cache_hits_total) + sum(gladys_memory_cache_misses_total))

# Error rate
sum(rate(gladys_orchestrator_errors_total[5m])) / sum(rate(gladys_orchestrator_events_routed_total[5m]))
```

### Useful LogQL Queries

```logql
# All errors
{component=~".+"} |= "ERROR"

# Slow executive decisions
{component="executive"} | json | duration_ms > 500

# Events for specific trace
{trace_id="abc123"}

# Suppressed events with reason
{component="salience"} |= "event_suppressed" | json | reason != ""
```
