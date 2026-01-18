# ADR-0005: gRPC Service Contracts

| Field | Value |
|-------|-------|
| **Status** | Proposed |
| **Date** | 2025-01-27 |
| **Owner** | Mike Mulcahy (Divinity10), Scott (scottcm) |
| **Contributors** | |
| **Module** | Contracts |
| **Tags** | grpc, api, transport, timeouts |
| **Depends On** | ADR-0001, ADR-0003, ADR-0004 |

---

## 1. Context and Problem Statement

GLADyS consists of multiple components written in different languages (Rust orchestrator, Python sensors/salience/memory, C# executive). These components must communicate reliably with low latency.

This ADR defines the gRPC service contracts, message formats, communication patterns, and supporting infrastructure (auth, tracing, error handling).

---

## 2. Decision Drivers

1. **Latency:** Total budget ~1000ms; inter-component communication must be fast
2. **Polyglot:** Must work across Rust, Python, and C#
3. **Type safety:** Contracts should catch errors at compile time where possible
4. **Extensibility:** New sensors and skills without contract changes
5. **Observability:** Tracing and logging built-in from day one
6. **Future-proofing:** Prepare for distributed deployment without major refactoring

---

## 3. Communication Topology

### 3.1 Component Relationships

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         ORCHESTRATOR (Rust)                              │
│                                                                          │
│   • Message broker (pub/sub fan-out)                                     │
│   • Lifecycle management                                                 │
│   • Health monitoring                                                    │
│   • Service registry                                                     │
└──────────────────────────────────────────────────────────────────────────┘
       │              │                │                │
       │ gRPC         │ gRPC           │ gRPC           │ gRPC
       │ bidir        │                │                │
       ▼              ▼                ▼                ▼
┌────────────┐  ┌───────────────┐  ┌────────────┐  ┌────────────┐
│  SENSORS   │  │   SALIENCE    │  │ EXECUTIVE  │  │  OUTPUTS   │
│  (Python)  │  │   GATEWAY     │  │   (C#)     │  │  (Python)  │
│            │  │   (Python)    │  │            │  │            │
│ Audio      │  │               │  │            │  │ TTS        │
│ Visual     │  │ ┌───────────┐ │  │            │  │            │
│ Minecraft  │  │ │  MEMORY   │ │  │            │  │            │
│            │  │ │CONTROLLER │ │  │            │  │            │
│            │  │ └───────────┘ │  │            │  │            │
└────────────┘  └───────────────┘  └────────────┘  └────────────┘
                       │                  │
                       │◄─────────────────┘
                       │ Direct query (Memory Controller)
```

### 3.2 Message Flow Patterns

| Flow | Pattern | Routing |
|------|---------|---------|
| Sensor → Salience | Pub/Sub via Orchestrator | Parallel fan-out |
| Sensor → Orchestrator (logging) | Pub/Sub | Same event, parallel subscriber |
| Salience → Executive | Unary | Direct routing via Orchestrator |
| Executive → Memory | Unary | Direct to Memory Controller |
| Executive → Output | Unary + Status Stream | Direct + async notify to Orchestrator |
| Orchestrator → Any | Unary | Lifecycle commands |

### 3.3 Pub/Sub Fan-Out

When a sensor emits an event, Orchestrator delivers to all subscribers in parallel:

```
Sensor emits event
        │
        ▼
   Orchestrator
        │
        ├──► Salience Gateway (processes event)
        │         │
        │         └──► Executive (if salient)
        │
        └──► Orchestrator log (records event)
```

Salience Gateway does not wait for Orchestrator logging. Both receive simultaneously.

---

## 4. Service Definitions

### 4.1 Package Structure

```
gladys/
├── v1/
│   ├── common.proto           # Shared messages
│   ├── orchestrator.proto     # Orchestrator service
│   ├── sensor.proto           # Sensor service
│   ├── salience.proto         # Salience Gateway service
│   ├── memory.proto           # Memory Controller service
│   ├── executive.proto        # Executive service
│   └── output.proto           # Output service
```

### 4.2 Common Messages

```protobuf
syntax = "proto3";
package gladys.v1;

import "google/protobuf/struct.proto";
import "google/protobuf/timestamp.proto";

// ============================================================================
// REQUEST METADATA (included in all RPCs)
// ============================================================================

message RequestMetadata {
    string request_id = 1;          // UUID, generated at origin
    string trace_id = 2;            // OpenTelemetry trace ID
    string span_id = 3;             // OpenTelemetry span ID
    int64 timestamp_ms = 4;         // Request creation time (Unix ms)
    string source_component = 5;    // Originating component ID
}

// ============================================================================
// EVENTS
// ============================================================================

message Event {
    string id = 1;                              // UUID
    google.protobuf.Timestamp timestamp = 2;
    string source = 3;                          // Sensor ID
    
    // Content
    string raw_text = 4;                        // Natural language description
    google.protobuf.Struct structured = 5;     // Domain-specific fields
    
    // Salience (populated by Salience Gateway)
    SalienceVector salience = 6;
    
    // Entity references (populated by Entity Extractor)
    repeated string entity_ids = 7;
    
    // Optional pre-tokenized payload (for LLM injection)
    repeated int32 tokens = 8;
    string tokenizer_id = 9;
    
    // Metadata
    RequestMetadata metadata = 15;
}

message SalienceVector {
    float threat = 1;               // 0-1
    float opportunity = 2;          // 0-1
    float humor = 3;                // 0-1
    float novelty = 4;              // 0-1
    float goal_relevance = 5;       // 0-1
    float social = 6;               // 0-1
    float emotional = 7;            // -1 to 1
    float actionability = 8;        // 0-1
    float habituation = 9;          // 0-1
}

// ============================================================================
// ENTITIES
// ============================================================================

message Entity {
    string id = 1;                  // UUID
    string canonical_name = 2;
    repeated string aliases = 3;
    string entity_type = 4;         // person, place, item, concept
    google.protobuf.Struct attributes = 5;
    google.protobuf.Timestamp first_seen = 6;
    google.protobuf.Timestamp last_seen = 7;
}

// ============================================================================
// USER PROFILE
// ============================================================================

message UserTrait {
    string category = 1;            // personality, preference, behavior, context
    string name = 2;
    float value = 3;
    float confidence = 4;
    float short_term = 5;           // EWMA short-term value
    float long_term = 6;            // EWMA long-term value
}

message UserProfile {
    repeated UserTrait traits = 1;
}

// ============================================================================
// COMPONENT STATUS
// ============================================================================

enum ComponentState {
    COMPONENT_STATE_UNKNOWN = 0;
    COMPONENT_STATE_STARTING = 1;
    COMPONENT_STATE_ACTIVE = 2;
    COMPONENT_STATE_PAUSED = 3;
    COMPONENT_STATE_STOPPING = 4;
    COMPONENT_STATE_STOPPED = 5;
    COMPONENT_STATE_ERROR = 6;
    COMPONENT_STATE_DEAD = 7;
}

message ComponentStatus {
    string component_id = 1;
    ComponentState state = 2;
    string message = 3;             // Human-readable status
    google.protobuf.Timestamp last_heartbeat = 4;
    map<string, string> metrics = 5;  // Key-value metrics
}

// ============================================================================
// ERRORS
// ============================================================================

message ErrorDetail {
    string code = 1;                // Machine-readable error code
    string message = 2;             // Human-readable message
    map<string, string> metadata = 3;
}
```

### 4.3 Orchestrator Service

```protobuf
syntax = "proto3";
package gladys.v1;

import "gladys/v1/common.proto";

// ============================================================================
// ORCHESTRATOR SERVICE
// ============================================================================

service OrchestratorService {
    // --------------------------------------------------------------------
    // Event Routing
    // --------------------------------------------------------------------
    
    // Sensors publish events through this streaming RPC
    // Orchestrator fans out to subscribers
    rpc PublishEvents(stream Event) returns (stream EventAck);
    
    // Components subscribe to receive events
    rpc SubscribeEvents(SubscribeRequest) returns (stream Event);
    
    // --------------------------------------------------------------------
    // Component Lifecycle
    // --------------------------------------------------------------------
    
    // Register a component with the orchestrator
    rpc RegisterComponent(RegisterRequest) returns (RegisterResponse);
    
    // Unregister (graceful shutdown)
    rpc UnregisterComponent(UnregisterRequest) returns (UnregisterResponse);
    
    // Send lifecycle command to a component
    rpc SendCommand(CommandRequest) returns (CommandResponse);
    
    // --------------------------------------------------------------------
    // Health & Status
    // --------------------------------------------------------------------
    
    // Components send periodic heartbeats
    rpc Heartbeat(HeartbeatRequest) returns (HeartbeatResponse);
    
    // Get status of all components
    rpc GetSystemStatus(SystemStatusRequest) returns (SystemStatusResponse);
    
    // --------------------------------------------------------------------
    // Service Discovery
    // --------------------------------------------------------------------
    
    // Resolve component address by ID
    rpc ResolveComponent(ResolveRequest) returns (ResolveResponse);
}

// ----------------------------------------------------------------------------
// Event Routing Messages
// ----------------------------------------------------------------------------

message EventAck {
    string event_id = 1;
    bool accepted = 2;
    string error_message = 3;       // If not accepted
}

message SubscribeRequest {
    string subscriber_id = 1;
    repeated string source_filters = 2;   // Empty = all sources
    repeated string event_types = 3;      // Empty = all types
}

// ----------------------------------------------------------------------------
// Registration Messages
// ----------------------------------------------------------------------------

message RegisterRequest {
    string component_id = 1;
    string component_type = 2;      // sensor, salience, executive, output, memory
    string address = 3;             // host:port
    ComponentCapabilities capabilities = 4;
    RequestMetadata metadata = 15;
}

message ComponentCapabilities {
    // Transport mode (for sensors)
    TransportMode transport_mode = 1;
    int32 batch_size = 2;
    int32 batch_interval_ms = 3;
    
    // Supported instructions (for configurable sensors)
    bool configurable = 4;
    repeated string supported_instructions = 5;
    
    // Instance policy
    InstancePolicy instance_policy = 6;
}

enum TransportMode {
    TRANSPORT_MODE_UNSPECIFIED = 0;
    TRANSPORT_MODE_STREAMING = 1;
    TRANSPORT_MODE_BATCHED = 2;
    TRANSPORT_MODE_EVENT = 3;
}

enum InstancePolicy {
    INSTANCE_POLICY_SINGLE = 0;     // Default: only one instance allowed
    INSTANCE_POLICY_MULTIPLE = 1;   // Multiple instances allowed
}

message RegisterResponse {
    bool success = 1;
    string error_message = 2;
    string assigned_id = 3;         // May differ from requested if conflict
}

message UnregisterRequest {
    string component_id = 1;
    RequestMetadata metadata = 15;
}

message UnregisterResponse {
    bool success = 1;
}

// ----------------------------------------------------------------------------
// Command Messages
// ----------------------------------------------------------------------------

message CommandRequest {
    string target_component_id = 1;
    Command command = 2;
    RequestMetadata metadata = 15;
}

enum Command {
    COMMAND_UNSPECIFIED = 0;
    COMMAND_START = 1;
    COMMAND_STOP = 2;
    COMMAND_PAUSE = 3;
    COMMAND_RESUME = 4;
    COMMAND_RELOAD = 5;
    COMMAND_HEALTH_CHECK = 6;
}

message CommandResponse {
    bool success = 1;
    string error_message = 2;
    ComponentStatus status = 3;
}

// ----------------------------------------------------------------------------
// Health Messages
// ----------------------------------------------------------------------------

message HeartbeatRequest {
    string component_id = 1;
    ComponentState state = 2;
    map<string, string> metrics = 3;
    RequestMetadata metadata = 15;
}

message HeartbeatResponse {
    bool acknowledged = 1;
    repeated PendingCommand pending_commands = 2;  // Commands queued for this component
}

message PendingCommand {
    string command_id = 1;
    Command command = 2;
}

message SystemStatusRequest {
    RequestMetadata metadata = 15;
}

message SystemStatusResponse {
    repeated ComponentStatus components = 1;
    google.protobuf.Timestamp timestamp = 2;
}

// ----------------------------------------------------------------------------
// Service Discovery Messages
// ----------------------------------------------------------------------------

message ResolveRequest {
    string component_id = 1;
    string component_type = 2;      // Alternative: resolve by type
    RequestMetadata metadata = 15;
}

message ResolveResponse {
    bool found = 1;
    string address = 2;
    ComponentCapabilities capabilities = 3;
}
```

### 4.4 Sensor Service

```protobuf
syntax = "proto3";
package gladys.v1;

import "gladys/v1/common.proto";

// ============================================================================
// SENSOR SERVICE (implemented by each sensor)
// ============================================================================

service SensorService {
    // --------------------------------------------------------------------
    // Lifecycle
    // --------------------------------------------------------------------
    
    // Initialize sensor (called after process start)
    rpc Initialize(InitializeRequest) returns (InitializeResponse);
    
    // Start processing (begin emitting events)
    rpc Start(StartRequest) returns (StartResponse);
    
    // Stop processing (stop emitting events, prepare for shutdown)
    rpc Stop(StopRequest) returns (StopResponse);
    
    // Pause (temporarily stop, keep state)
    rpc Pause(PauseRequest) returns (PauseResponse);
    
    // Resume from pause
    rpc Resume(ResumeRequest) returns (ResumeResponse);
    
    // Health check
    rpc HealthCheck(HealthCheckRequest) returns (HealthCheckResponse);
    
    // Get current status
    rpc GetStatus(GetStatusRequest) returns (GetStatusResponse);
    
    // --------------------------------------------------------------------
    // Configuration (optional - for configurable sensors)
    // --------------------------------------------------------------------
    
    // Executive can send attention/configuration hints
    // Sensors may ignore or partially implement
    rpc Configure(ConfigureRequest) returns (ConfigureResponse);
}

// ----------------------------------------------------------------------------
// Lifecycle Messages
// ----------------------------------------------------------------------------

message InitializeRequest {
    string sensor_id = 1;
    google.protobuf.Struct config = 2;  // Sensor-specific configuration
    RequestMetadata metadata = 15;
}

message InitializeResponse {
    bool success = 1;
    string error_message = 2;
    ComponentCapabilities capabilities = 3;
}

message StartRequest {
    RequestMetadata metadata = 15;
}

message StartResponse {
    bool success = 1;
    string error_message = 2;
}

message StopRequest {
    bool save_state = 1;            // Persist state for later resume
    RequestMetadata metadata = 15;
}

message StopResponse {
    bool success = 1;
    string state_file = 2;          // Path to saved state, if any
}

message PauseRequest {
    RequestMetadata metadata = 15;
}

message PauseResponse {
    bool success = 1;
}

message ResumeRequest {
    RequestMetadata metadata = 15;
}

message ResumeResponse {
    bool success = 1;
}

message HealthCheckRequest {
    RequestMetadata metadata = 15;
}

message HealthCheckResponse {
    bool healthy = 1;
    ComponentState state = 2;
    string message = 3;
    map<string, string> diagnostics = 4;
}

message GetStatusRequest {
    RequestMetadata metadata = 15;
}

message GetStatusResponse {
    ComponentStatus status = 1;
}

// ----------------------------------------------------------------------------
// Configuration Messages (Executive → Sensor instructions)
// ----------------------------------------------------------------------------

message ConfigureRequest {
    oneof instruction {
        AttentionFocus focus = 1;
        SensitivityAdjustment sensitivity = 2;
        EntityWatch watch_entity = 3;
        FilterRule filter = 4;
    }
    RequestMetadata metadata = 15;
}

message AttentionFocus {
    string region = 1;              // Sensor-specific region identifier
    float priority_boost = 2;       // How much to boost salience (0-1)
    int32 duration_seconds = 3;     // How long to maintain focus (0 = indefinite)
}

message SensitivityAdjustment {
    string parameter = 1;           // Which sensitivity to adjust
    float value = 2;                // New value
}

message EntityWatch {
    string entity_id = 1;
    string entity_name = 2;
    float priority_boost = 3;
}

message FilterRule {
    string filter_type = 1;         // include, exclude
    string pattern = 2;             // What to filter
}

message ConfigureResponse {
    bool accepted = 1;
    bool fully_implemented = 2;     // false if partially supported
    string message = 3;
}
```

### 4.5 Salience Gateway Service

```protobuf
syntax = "proto3";
package gladys.v1;

import "gladys/v1/common.proto";

// ============================================================================
// SALIENCE GATEWAY SERVICE
// ============================================================================

service SalienceGatewayService {
    // Evaluate salience of an event
    // Returns enriched event with salience scores and relevant memories
    rpc EvaluateEvent(EvaluateEventRequest) returns (EvaluateEventResponse);
    
    // Batch evaluation (for high-throughput scenarios)
    rpc EvaluateEventBatch(EvaluateEventBatchRequest) returns (EvaluateEventBatchResponse);
    
    // Update salience thresholds (from Executive modulation)
    rpc ModulateSalience(ModulateSalienceRequest) returns (ModulateSalienceResponse);
    
    // Lifecycle
    rpc HealthCheck(HealthCheckRequest) returns (HealthCheckResponse);
    rpc GetStatus(GetStatusRequest) returns (GetStatusResponse);
}

// ----------------------------------------------------------------------------
// Evaluation Messages
// ----------------------------------------------------------------------------

message EvaluateEventRequest {
    Event event = 1;
    EvaluationContext context = 2;
    RequestMetadata metadata = 15;
}

message EvaluationContext {
    repeated string active_goals = 1;
    repeated string focus_entities = 2;     // Entities to prioritize
    string active_sensor = 3;               // Currently focused sensor
    SalienceModulation modulation = 4;      // Active modulation from Executive
}

message EvaluateEventResponse {
    Event enriched_event = 1;               // Event with salience populated
    repeated RetrievedMemory relevant_memories = 2;
    UserProfile user_profile_snapshot = 3;   // Current user traits
    bool should_process = 4;                 // false if below threshold / habituated
    string skip_reason = 5;                  // Why should_process is false
}

message RetrievedMemory {
    string id = 1;
    string type = 2;                        // episodic, semantic_fact, entity
    string content = 3;                     // Formatted for LLM injection
    float relevance_score = 4;
}

message EvaluateEventBatchRequest {
    repeated Event events = 1;
    EvaluationContext context = 2;
    RequestMetadata metadata = 15;
}

message EvaluateEventBatchResponse {
    repeated EvaluateEventResponse results = 1;
}

// ----------------------------------------------------------------------------
// Modulation Messages
// ----------------------------------------------------------------------------

message ModulateSalienceRequest {
    SalienceModulation modulation = 1;
    RequestMetadata metadata = 15;
}

message SalienceModulation {
    // Threshold adjustments
    map<string, float> threshold_adjustments = 1;  // dimension → adjustment
    
    // Suppression rules
    repeated SuppressionRule suppressions = 2;
    
    // Heightening rules
    repeated HeighteningRule heightenings = 3;
    
    // Duration
    int32 duration_seconds = 4;             // 0 = until changed
}

message SuppressionRule {
    string source = 1;                      // Sensor ID to suppress
    string dimension = 2;                   // Salience dimension
    float factor = 3;                       // Multiply score by this (< 1)
}

message HeighteningRule {
    string source = 1;
    string dimension = 2;
    float factor = 3;                       // Multiply score by this (> 1)
}

message ModulateSalienceResponse {
    bool applied = 1;
    string message = 2;
}
```

### 4.6 Memory Controller Service

```protobuf
syntax = "proto3";
package gladys.v1;

import "gladys/v1/common.proto";
import "google/protobuf/timestamp.proto";

// ============================================================================
// MEMORY CONTROLLER SERVICE
// ============================================================================

service MemoryControllerService {
    // --------------------------------------------------------------------
    // Event Storage
    // --------------------------------------------------------------------
    
    // Store an event (after salience evaluation)
    rpc StoreEvent(StoreEventRequest) returns (StoreEventResponse);
    
    // Batch store
    rpc StoreEventBatch(StoreEventBatchRequest) returns (StoreEventBatchResponse);
    
    // --------------------------------------------------------------------
    // Queries
    // --------------------------------------------------------------------
    
    // Semantic similarity search
    rpc SemanticSearch(SemanticSearchRequest) returns (SemanticSearchResponse);
    
    // Structured query (time, source, salience filters)
    rpc QueryEvents(QueryEventsRequest) returns (QueryEventsResponse);
    
    // Get events for an entity
    rpc GetEntityEvents(GetEntityEventsRequest) returns (GetEntityEventsResponse);
    
    // Composite relevance query (combines semantic + structured)
    rpc GetRelevantMemories(GetRelevantMemoriesRequest) returns (GetRelevantMemoriesResponse);
    
    // --------------------------------------------------------------------
    // Entities
    // --------------------------------------------------------------------
    
    rpc GetEntity(GetEntityRequest) returns (GetEntityResponse);
    rpc UpsertEntity(UpsertEntityRequest) returns (UpsertEntityResponse);
    rpc SearchEntities(SearchEntitiesRequest) returns (SearchEntitiesResponse);
    
    // --------------------------------------------------------------------
    // Semantic Facts
    // --------------------------------------------------------------------
    
    rpc GetFacts(GetFactsRequest) returns (GetFactsResponse);
    rpc UpsertFact(UpsertFactRequest) returns (UpsertFactResponse);
    
    // --------------------------------------------------------------------
    // User Profile
    // --------------------------------------------------------------------
    
    rpc GetUserProfile(GetUserProfileRequest) returns (GetUserProfileResponse);
    rpc UpdateUserTrait(UpdateUserTraitRequest) returns (UpdateUserTraitResponse);
    
    // --------------------------------------------------------------------
    // Lifecycle
    // --------------------------------------------------------------------
    
    rpc HealthCheck(HealthCheckRequest) returns (HealthCheckResponse);
    rpc GetStatus(GetStatusRequest) returns (GetStatusResponse);
}

// ----------------------------------------------------------------------------
// Event Storage Messages
// ----------------------------------------------------------------------------

message StoreEventRequest {
    Event event = 1;
    RequestMetadata metadata = 15;
}

message StoreEventResponse {
    bool success = 1;
    string stored_id = 2;
}

message StoreEventBatchRequest {
    repeated Event events = 1;
    RequestMetadata metadata = 15;
}

message StoreEventBatchResponse {
    int32 stored_count = 1;
    repeated string failed_ids = 2;
}

// ----------------------------------------------------------------------------
// Query Messages
// ----------------------------------------------------------------------------

message SemanticSearchRequest {
    string query_text = 1;
    repeated float query_embedding = 2;     // Pre-computed (optional)
    
    // Filters
    string source_filter = 3;
    int32 time_filter_hours = 4;
    map<string, float> salience_filters = 5;  // dimension → min value
    
    int32 limit = 10;
    RequestMetadata metadata = 15;
}

message SemanticSearchResponse {
    repeated ScoredEvent results = 1;
}

message ScoredEvent {
    Event event = 1;
    float score = 2;
}

message QueryEventsRequest {
    // Time range
    google.protobuf.Timestamp start_time = 1;
    google.protobuf.Timestamp end_time = 2;
    
    // Filters
    repeated string sources = 3;
    map<string, float> min_salience = 4;
    bool include_archived = 5;
    
    // Pagination
    int32 limit = 6;
    int32 offset = 7;
    
    RequestMetadata metadata = 15;
}

message QueryEventsResponse {
    repeated Event events = 1;
    int32 total_count = 2;
}

message GetEntityEventsRequest {
    string entity_id = 1;
    int32 limit = 2;
    RequestMetadata metadata = 15;
}

message GetEntityEventsResponse {
    repeated Event events = 1;
}

message GetRelevantMemoriesRequest {
    // Current context for relevance scoring
    string context_summary = 1;
    repeated string entity_ids = 2;
    map<string, float> salience_weights = 3;  // dimension → weight
    
    int32 limit = 4;
    RequestMetadata metadata = 15;
}

message GetRelevantMemoriesResponse {
    repeated RetrievedMemory memories = 1;
}

// ----------------------------------------------------------------------------
// Entity Messages
// ----------------------------------------------------------------------------

message GetEntityRequest {
    string entity_id = 1;
    RequestMetadata metadata = 15;
}

message GetEntityResponse {
    Entity entity = 1;
    bool found = 2;
}

message UpsertEntityRequest {
    Entity entity = 1;
    RequestMetadata metadata = 15;
}

message UpsertEntityResponse {
    string entity_id = 1;
    bool created = 2;               // true if new, false if updated
}

message SearchEntitiesRequest {
    string query = 1;               // Name or alias search
    string entity_type = 2;
    int32 limit = 3;
    RequestMetadata metadata = 15;
}

message SearchEntitiesResponse {
    repeated Entity entities = 1;
}

// ----------------------------------------------------------------------------
// Semantic Facts Messages
// ----------------------------------------------------------------------------

message SemanticFact {
    string id = 1;
    string subject_text = 2;
    string subject_entity_id = 3;
    string predicate = 4;
    string object_text = 5;
    string object_entity_id = 6;
    float confidence = 7;
}

message GetFactsRequest {
    string subject_entity_id = 1;
    string predicate = 2;
    float min_confidence = 3;
    int32 limit = 4;
    RequestMetadata metadata = 15;
}

message GetFactsResponse {
    repeated SemanticFact facts = 1;
}

message UpsertFactRequest {
    SemanticFact fact = 1;
    repeated string source_event_ids = 2;
    RequestMetadata metadata = 15;
}

message UpsertFactResponse {
    string fact_id = 1;
    bool created = 2;
}

// ----------------------------------------------------------------------------
// User Profile Messages
// ----------------------------------------------------------------------------

message GetUserProfileRequest {
    repeated string categories = 1;     // Empty = all
    RequestMetadata metadata = 15;
}

message GetUserProfileResponse {
    UserProfile profile = 1;
}

message UpdateUserTraitRequest {
    string category = 1;
    string name = 2;
    float observed_value = 3;
    RequestMetadata metadata = 15;
}

message UpdateUserTraitResponse {
    UserTrait updated_trait = 1;
}
```

### 4.7 Executive Service

```protobuf
syntax = "proto3";
package gladys.v1;

import "gladys/v1/common.proto";

// ============================================================================
// EXECUTIVE SERVICE
// ============================================================================

service ExecutiveService {
    // Process an enriched event and generate response
    rpc ProcessEvent(ProcessEventRequest) returns (ProcessEventResponse);
    
    // Direct query (user asked something)
    rpc HandleQuery(HandleQueryRequest) returns (HandleQueryResponse);
    
    // Update personality configuration
    rpc UpdatePersonality(UpdatePersonalityRequest) returns (UpdatePersonalityResponse);
    
    // Get current goals/focus
    rpc GetFocus(GetFocusRequest) returns (GetFocusResponse);
    
    // Set goals/focus
    rpc SetFocus(SetFocusRequest) returns (SetFocusResponse);
    
    // Lifecycle
    rpc HealthCheck(HealthCheckRequest) returns (HealthCheckResponse);
    rpc GetStatus(GetStatusRequest) returns (GetStatusResponse);
}

// ----------------------------------------------------------------------------
// Event Processing Messages
// ----------------------------------------------------------------------------

message ProcessEventRequest {
    Event enriched_event = 1;
    repeated RetrievedMemory relevant_memories = 2;
    UserProfile user_profile = 3;
    ExecutiveContext context = 4;
    RequestMetadata metadata = 15;
}

message ExecutiveContext {
    string active_personality_id = 1;
    PersonalityTraits current_traits = 2;
    repeated string active_goals = 3;
    repeated string active_skill_ids = 4;
}

message PersonalityTraits {
    float humor = 1;
    float sarcasm = 2;
    float formality = 3;
    float proactive = 4;
    float enthusiasm = 5;
    float helpfulness = 6;
    float verbosity = 7;
}

message ProcessEventResponse {
    ExecutiveDecision decision = 1;
}

message ExecutiveDecision {
    ActionType action = 1;
    string response_text = 2;           // What to say (if speaking)
    OutputTarget output_target = 3;     // Where to send response
    
    // Modulation signals for Salience Gateway
    SalienceModulation salience_modulation = 4;
    
    // Instructions for sensors (optional)
    repeated SensorInstruction sensor_instructions = 5;
    
    // Memory operations
    repeated MemoryOperation memory_operations = 6;
}

enum ActionType {
    ACTION_NONE = 0;                    // Do nothing
    ACTION_SPEAK = 1;                   // Say something
    ACTION_NOTIFY = 2;                  // Non-verbal notification
    ACTION_LOG = 3;                     // Just log, no output
}

enum OutputTarget {
    OUTPUT_TTS = 0;                     // Text-to-speech
    OUTPUT_TEXT = 1;                    // Text display
    OUTPUT_BOTH = 2;                    // Both TTS and text
}

message SensorInstruction {
    string sensor_id = 1;
    ConfigureRequest configuration = 2;
}

message MemoryOperation {
    MemoryOpType op_type = 1;
    string entity_id = 2;
    google.protobuf.Struct data = 3;
}

enum MemoryOpType {
    MEMORY_OP_UPDATE_ENTITY = 0;
    MEMORY_OP_CREATE_FACT = 1;
    MEMORY_OP_UPDATE_USER_TRAIT = 2;
}

// ----------------------------------------------------------------------------
// Query Handling Messages
// ----------------------------------------------------------------------------

message HandleQueryRequest {
    string query_text = 1;
    repeated RetrievedMemory context_memories = 2;
    UserProfile user_profile = 3;
    ExecutiveContext context = 4;
    RequestMetadata metadata = 15;
}

message HandleQueryResponse {
    string response_text = 1;
    OutputTarget output_target = 2;
}

// ----------------------------------------------------------------------------
// Personality Messages
// ----------------------------------------------------------------------------

message UpdatePersonalityRequest {
    string personality_id = 1;          // Switch to this personality
    PersonalityTraits trait_overrides = 2;  // Or just override traits
    RequestMetadata metadata = 15;
}

message UpdatePersonalityResponse {
    bool success = 1;
    string active_personality_id = 2;
    PersonalityTraits effective_traits = 3;
}

// ----------------------------------------------------------------------------
// Focus Messages
// ----------------------------------------------------------------------------

message GetFocusRequest {
    RequestMetadata metadata = 15;
}

message GetFocusResponse {
    repeated string active_goals = 1;
    repeated string focus_entities = 2;
    string focus_sensor = 3;
}

message SetFocusRequest {
    repeated string goals = 1;
    repeated string focus_entities = 2;
    string focus_sensor = 3;
    RequestMetadata metadata = 15;
}

message SetFocusResponse {
    bool success = 1;
}
```

### 4.8 Output Service

```protobuf
syntax = "proto3";
package gladys.v1;

import "gladys/v1/common.proto";

// ============================================================================
// OUTPUT SERVICE
// ============================================================================

service OutputService {
    // Text-to-speech
    rpc Speak(SpeakRequest) returns (stream SpeakStatus);
    
    // Interrupt current speech
    rpc Interrupt(InterruptRequest) returns (InterruptResponse);
    
    // Display text (non-TTS)
    rpc DisplayText(DisplayTextRequest) returns (DisplayTextResponse);
    
    // Get available voices
    rpc GetVoices(GetVoicesRequest) returns (GetVoicesResponse);
    
    // Set voice
    rpc SetVoice(SetVoiceRequest) returns (SetVoiceResponse);
    
    // Lifecycle
    rpc HealthCheck(HealthCheckRequest) returns (HealthCheckResponse);
    rpc GetStatus(GetStatusRequest) returns (GetStatusResponse);
}

// ----------------------------------------------------------------------------
// TTS Messages
// ----------------------------------------------------------------------------

message SpeakRequest {
    string text = 1;
    string voice_id = 2;                // Optional: override default
    SpeakOptions options = 3;
    RequestMetadata metadata = 15;
}

message SpeakOptions {
    float speed = 1;                    // 0.5 to 2.0, default 1.0
    float pitch = 2;                    // 0.5 to 2.0, default 1.0
    string emotion = 3;                 // For expressive TTS models
    bool interruptible = 4;             // Can be interrupted
}

message SpeakStatus {
    SpeakState state = 1;
    float progress = 2;                 // 0-1
    string message = 3;
}

enum SpeakState {
    SPEAK_STATE_QUEUED = 0;
    SPEAK_STATE_STARTED = 1;
    SPEAK_STATE_SPEAKING = 2;
    SPEAK_STATE_COMPLETED = 3;
    SPEAK_STATE_INTERRUPTED = 4;
    SPEAK_STATE_ERROR = 5;
}

message InterruptRequest {
    RequestMetadata metadata = 15;
}

message InterruptResponse {
    bool interrupted = 1;
    string state = 2;                   // What was interrupted
}

// ----------------------------------------------------------------------------
// Text Display Messages
// ----------------------------------------------------------------------------

message DisplayTextRequest {
    string text = 1;
    DisplayStyle style = 2;
    RequestMetadata metadata = 15;
}

message DisplayStyle {
    string color = 1;
    int32 duration_ms = 2;              // How long to display
    string position = 3;                // Screen position hint
}

message DisplayTextResponse {
    bool displayed = 1;
}

// ----------------------------------------------------------------------------
// Voice Management Messages
// ----------------------------------------------------------------------------

message Voice {
    string id = 1;
    string name = 2;
    string language = 3;
    string gender = 4;
    bool supports_emotion = 5;
}

message GetVoicesRequest {
    RequestMetadata metadata = 15;
}

message GetVoicesResponse {
    repeated Voice voices = 1;
    string current_voice_id = 2;
}

message SetVoiceRequest {
    string voice_id = 1;
    RequestMetadata metadata = 15;
}

message SetVoiceResponse {
    bool success = 1;
    string active_voice_id = 2;
}
```

---

## 5. Transport Strategy

### 5.1 Sensor Transport Modes

Sensors advertise their preferred transport mode in their manifest and during registration. Orchestrator uses the appropriate strategy.

```
┌─────────────────────────────────────────────────────────────┐
│                 TRANSPORT STRATEGY                          │
│                                                             │
│  ISensorTransport (interface)                               │
│      │                                                      │
│      ├── StreamingTransport                                 │
│      │       • Opens bidirectional stream                   │
│      │       • Sensor pushes events continuously            │
│      │       • Lowest latency                               │
│      │       • Use for: audio, visual, real-time            │
│      │                                                      │
│      ├── BatchedTransport                                   │
│      │       • Sensor buffers events locally                │
│      │       • Flushes on size or time threshold            │
│      │       • Efficient for high-frequency                 │
│      │       • Use for: system monitor, log watchers        │
│      │                                                      │
│      └── EventTransport                                     │
│              • Unary RPC per event                          │
│              • Simplest implementation                      │
│              • Higher overhead                              │
│              • Use for: low-frequency, sporadic events      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 Manifest Declaration

```yaml
# In sensor manifest (ADR-0003)
sensor:
  transport:
    mode: streaming          # streaming | batched | event
    batch_size: 10           # For batched mode
    batch_interval_ms: 100   # For batched mode
```

---

## 6. TTS Model Options

The Output service supports swappable TTS engines via Strategy pattern.

### 6.1 Model Comparison

| Model | Expressiveness | Latency | VRAM | Quality | Best For |
|-------|----------------|---------|------|---------|----------|
| **Piper** | Low (neutral) | ~50ms | ~0.5GB | Good | Fast responses, simple |
| **Coqui XTTS** | Medium | ~200ms | ~2.5GB | Very good | Voice cloning |
| **Bark** | High (emotion) | ~500ms | ~4GB | Excellent | Expressive, sarcasm |
| **StyleTTS 2** | High (style) | ~200ms | ~2GB | Excellent | Controllable style |
| **VALL-E X** | Very high | ~300ms | ~4GB | Excellent | Natural emotion |

### 6.2 Recommendation

**Phase 1:** Start with **Piper** (fast, simple, low resource)

**Phase 2:** Add **Bark** or **StyleTTS 2** when personality expression matters

### 6.3 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    TTS ARCHITECTURE                          │
│                                                             │
│  ITTSEngine (Strategy interface)                            │
│      │                                                      │
│      ├── PiperEngine : ITTSEngine                           │
│      ├── BarkEngine : ITTSEngine                            │
│      ├── CoquiEngine : ITTSEngine                           │
│      └── StyleTTSEngine : ITTSEngine                        │
│                                                             │
│  TTSOutput                                                  │
│      │                                                      │
│      └── Uses ITTSEngine (injected)                         │
│              │                                              │
│              └── AudioDecorator (normalization, effects)    │
│                      │                                      │
│                      └── StreamingAdapter (chunked output)  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

Configured via manifest (ADR-0003) and runtime settings.

---

## 7. Timeout Budget

### 7.1 Per-RPC Timeouts

| RPC | Timeout | Notes |
|-----|---------|-------|
| `PublishEvents` (stream) | N/A | Streaming, no per-call timeout |
| `EvaluateEvent` | 200ms | Salience model + memory lookup |
| `SemanticSearch` | 100ms | Vector search |
| `QueryEvents` | 100ms | Structured query |
| `GetRelevantMemories` | 100ms | Composite query |
| `ProcessEvent` | 600ms | Main LLM inference |
| `Speak` (initiation) | 100ms | Time to start speaking |
| `HealthCheck` | 500ms | Allow slow components |
| `Initialize` | 10000ms | Model loading |
| `Start/Stop` | 5000ms | State transitions |
| `Configure` | 1000ms | May involve model adjustment |

### 7.2 End-to-End Budget

```
Event flow timeline:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
0ms        100ms      300ms      400ms      1000ms
│           │          │          │           │
│ Sensor    │ Salience │ Memory   │ Executive │ Output
│ capture   │ eval     │ retrieve │ decide    │ start
│ 50ms      │ 150ms    │ 75ms     │ 500ms     │ 50ms
│           │          │          │           │
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Subtotal: ~825ms
Buffer: ~175ms
Total: ~1000ms
```

---

## 8. Error Handling

### 8.1 gRPC Retry Policy

```yaml
# Applied at gRPC channel level
retry_policy:
  max_attempts: 3
  initial_backoff: 10ms
  max_backoff: 100ms
  backoff_multiplier: 2.0
  retryable_status_codes:
    - UNAVAILABLE
    - RESOURCE_EXHAUSTED
    - ABORTED
```

### 8.2 Application-Level Circuit Breaker

```
┌─────────────────────────────────────────────────────────────┐
│                  CIRCUIT BREAKER STATES                      │
│                                                             │
│         ┌──────────────────────────────────────┐            │
│         │                                      │            │
│         ▼                                      │            │
│    ┌─────────┐   failures > 3     ┌───────────┴──┐         │
│    │ CLOSED  │──────────────────►│    OPEN      │         │
│    │(healthy)│                    │(not routing) │         │
│    └─────────┘                    └──────┬───────┘         │
│         ▲                                │                  │
│         │                                │ 30s timeout      │
│         │    success                     ▼                  │
│         │                         ┌─────────────┐          │
│         └─────────────────────────│ HALF-OPEN   │          │
│                                   │(test request)│          │
│                                   └─────────────┘          │
│                                          │                  │
│                                          │ failure          │
│                                          ▼                  │
│                                   Back to OPEN              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 8.3 Failure Recovery Sequence

```
Component failure detected
        │
        ▼
1. Stop routing new requests
        │
        ▼
2. Health check (500ms timeout)
        │
        ├── Success → Resume routing
        │
        └── Failure
                │
                ▼
        3. Attempt restart (up to 3 times)
                │
                ├── Success → Resume routing
                │
                └── Failure (3x)
                        │
                        ▼
                4. Mark DEAD, notify user
```

---

## 9. Security

### 9.1 Auth Strategy Pattern

```
┌─────────────────────────────────────────────────────────────┐
│                    AUTH ARCHITECTURE                         │
│                                                             │
│  IAuthProvider (Strategy interface)                         │
│      │                                                      │
│      ├── NoAuthProvider : IAuthProvider                     │
│      │       Phase 1: local only                            │
│      │                                                      │
│      ├── ApiKeyProvider : IAuthProvider                     │
│      │       Simple shared secret                           │
│      │                                                      │
│      ├── MtlsProvider : IAuthProvider                       │
│      │       Certificate-based                              │
│      │                                                      │
│      └── JwtProvider : IAuthProvider                        │
│              Token-based                                    │
│                                                             │
│  gRPC Interceptor                                           │
│      • Server: validates incoming credentials               │
│      • Client: attaches credentials to outgoing             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 9.2 Phase 1 Implementation

```python
# NoAuthProvider - just passes through
class NoAuthProvider(IAuthProvider):
    def validate(self, context) -> bool:
        return True
    
    def attach_credentials(self, metadata) -> dict:
        return metadata
```

### 9.3 Future Distributed Deployment

Config-driven channel selection:

```yaml
# Phase 1: Local
components:
  audio-sensor:
    type: local_grpc
    address: localhost:50051
    auth: none

# Phase 2: Distributed
components:
  audio-sensor:
    type: remote_grpc
    address: 192.168.1.100:50051
    auth: mtls
    cert_path: /certs/audio-sensor.pem
```

Orchestrator reads config, creates appropriate channel + auth provider.

### 9.4 Permission Enforcement Interceptors

Beyond authentication, gRPC interceptors enforce the permission model (see [ADR-0008](ADR-0008-Security-and-Privacy.md)):

```
┌─────────────────────────────────────────────────────────────────────────┐
│                  SECURITY INTERCEPTOR CHAIN                             │
│                                                                         │
│  Incoming gRPC Request                                                  │
│         │                                                               │
│         ▼                                                               │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 1. AUTHENTICATION INTERCEPTOR                                   │   │
│  │    • Extract plugin_id from metadata                            │   │
│  │    • Validate auth credentials (Phase 2+)                       │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│         │                                                               │
│         ▼                                                               │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 2. AUTHORIZATION INTERCEPTOR                                    │   │
│  │    • Map RPC method to required permission                      │   │
│  │    • Call Security Module permission chain                      │   │
│  │    • Check: age, trust, consent, scope, rate, constraints       │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│         │                                                               │
│         ▼                                                               │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 3. AUDIT INTERCEPTOR                                            │   │
│  │    • Log request (plugin, method, timestamp)                    │   │
│  │    • Log decision (allow/deny, reason)                          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│         │                                                               │
│         ▼                                                               │
│  Service Handler (if authorized)                                        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**RPC to Permission Mapping:**

| RPC Method | Required Permission |
|------------|---------------------|
| `ScreenCaptureService.Capture` | `screen.full`, `screen.window`, `screen.game`, or `screen.region` |
| `AudioCaptureService.Capture` | `audio.push_to_talk`, `audio.voice_activation`, or `audio.always_on` |
| `FileAccessService.Read` | `file.read.game`, `file.read.scoped`, or `file.read.any` |
| `GameModService.Query` | `game.mod.read` |
| `GameModService.Execute` | `game.mod.write` |
| `IoTGatewayService.ReadSensor` | `iot.sensor` |
| `IoTGatewayService.Control` | `iot.control` |
| `MemoryService.Query` | `memory.read` |
| `MemoryService.Store` | `memory.write` |

### 9.5 Shared Memory for High-Bandwidth Data

For image data, gRPC serialization overhead is prohibitive. Instead, the orchestrator uses shared memory:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                  SHARED MEMORY + gRPC HYBRID                            │
│                                                                         │
│  ORCHESTRATOR                                                           │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │                                                                   │ │
│  │  ┌─────────────────────────────────────────────────────────────┐ │ │
│  │  │ SHARED MEMORY REGION                                        │ │ │
│  │  │                                                             │ │ │
│  │  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐       │ │ │
│  │  │  │ Frame 0 │  │ Frame 1 │  │ Frame 2 │  │ Frame 3 │       │ │ │
│  │  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘       │ │ │
│  │  │                                                             │ │ │
│  │  │  Written by: Orchestrator (WRITE)                          │ │ │
│  │  │  Read by: Sensors (READ-ONLY, OS-enforced)                 │ │ │
│  │  └─────────────────────────────────────────────────────────────┘ │ │
│  │                                                                   │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│         │ gRPC: "Frame 2 ready"          ▲ Shared mem: read frame 2    │
│         ▼                                │                              │
│  ┌───────────────────────────────────────┴───────────────────────────┐ │
│  │ SENSOR PROCESS                                                    │ │
│  │                                                                   │ │
│  │  1. Receive gRPC notification (frame index, timestamp)           │ │
│  │  2. Read frame directly from shared memory (zero-copy)           │ │
│  │  3. Process frame with vision model                              │ │
│  │  4. Send structured event back via gRPC                          │ │
│  │                                                                   │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│  Performance comparison:                                                │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  gRPC only:     5-10ms per 1080p frame (serialize + deserialize) │  │
│  │  Shared memory: 0.01-0.1ms per frame (pointer read)              │  │
│  │  Improvement:   50-100x faster                                   │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Notification Message:**

```protobuf
// In orchestrator.proto
message FrameNotification {
  uint32 frame_index = 1;           // Index in shared memory ring buffer
  google.protobuf.Timestamp timestamp = 2;
  uint32 width = 3;
  uint32 height = 4;
  string format = 5;                // "RGBA", "RGB", etc.
  string source = 6;                // "full_screen", "window:Minecraft", etc.
}

service ScreenService {
  // Notification that a new frame is available in shared memory
  rpc StreamFrames(FrameStreamRequest) returns (stream FrameNotification);
}
```

See [ADR-0008](ADR-0008-Security-and-Privacy.md) Section 11 for shared memory implementation details.

---

## 10. Observability

### 10.1 Tracing (OpenTelemetry)

All RPCs include trace context via gRPC metadata:

```
traceparent: 00-{trace_id}-{span_id}-{flags}
```

Spans created:

| Span Name | Component | Description |
|-----------|-----------|-------------|
| `sensor.emit_event` | Sensor | Event creation to send |
| `orchestrator.route` | Orchestrator | Event receive to fan-out complete |
| `salience.evaluate` | Salience | Evaluation start to finish |
| `memory.query` | Memory | Query start to results |
| `executive.process` | Executive | Event receive to decision |
| `output.speak` | Output | Text receive to audio start |

### 10.2 Metrics

Each component exposes Prometheus metrics:

```
# Latency histograms
rpc_duration_seconds{method="EvaluateEvent", status="OK"}
rpc_duration_seconds{method="ProcessEvent", status="OK"}

# Counters
events_processed_total{source="minecraft-sensor"}
decisions_made_total{action="speak"}

# Gauges
active_connections{component="orchestrator"}
memory_cache_size{level="L1"}
```

### 10.3 Standard Metadata

All RPCs include `RequestMetadata`:

```protobuf
message RequestMetadata {
    string request_id = 1;          // UUID
    string trace_id = 2;            // OpenTelemetry
    string span_id = 3;             // OpenTelemetry
    int64 timestamp_ms = 4;         // Creation time
    string source_component = 5;    // Origin
}
```

---

## 11. Versioning

### 11.1 Package Versioning

```protobuf
package gladys.v1;  // Current version

// Future breaking changes:
package gladys.v2;
```

### 11.2 Field Deprecation

```protobuf
message Event {
    string id = 1;
    
    // Deprecated: use raw_text
    string text = 2 [deprecated = true];
    
    string raw_text = 3;
    
    // Reserved for removed fields
    reserved 4, 5;
    reserved "old_field";
}
```

### 11.3 Policy

| Version | Policy |
|---------|--------|
| 0.x | Breaking changes allowed with changelog |
| 0.9+ | Feature freeze, stabilization |
| 1.0+ | Semantic versioning, breaking = v2 package |

---

## 12. Future: Hot-Reload (Deferred)

Hot-reload of plugins without system restart is planned for a future release.

### 12.1 Open Questions

- State migration between versions
- Handling in-flight requests during reload
- Rollback strategy if new version fails
- Version compatibility validation

### 12.2 Placeholder Commands

Reserved for future implementation:

```protobuf
// In OrchestratorService (future)
rpc HotReload(HotReloadRequest) returns (HotReloadResponse);
rpc ValidateVersion(ValidateVersionRequest) returns (ValidateVersionResponse);
```

Contract details will be defined in a future ADR.

---

## 13. Consequences

### 13.1 Positive

1. Clear contracts between all components
2. Language-agnostic (Rust, Python, C# all supported)
3. Built-in observability (tracing, metrics)
4. Flexible transport strategies for different sensor types
5. Auth abstraction allows security evolution
6. Prepared for distributed deployment

### 13.2 Negative

1. Proto file maintenance overhead
2. gRPC adds complexity vs. simple HTTP
3. Streaming connections require connection management

### 13.3 Risks

1. Proto versioning mistakes could cause incompatibilities
2. Timeout tuning may need adjustment based on real usage
3. Circuit breaker thresholds need calibration

---

## 14. Related Decisions

- ADR-0001: GLADyS Architecture
- ADR-0003: Plugin Manifest Specification
- ADR-0004: Memory Schema Details
- ADR-0006: Observability & Monitoring
- ADR-0007: Adaptive Algorithms
- ADR-0008: Security and Privacy (permission enforcement, shared memory)

---

## 15. Appendix: Proto File Organization

```
protos/
├── gladys/
│   └── v1/
│       ├── common.proto
│       ├── orchestrator.proto
│       ├── sensor.proto
│       ├── salience.proto
│       ├── memory.proto
│       ├── executive.proto
│       └── output.proto
├── buf.yaml                    # Buf build config
└── buf.gen.yaml               # Code generation config
```

Build commands:

```bash
# Generate Python
buf generate --template buf.gen.python.yaml

# Generate C#
buf generate --template buf.gen.csharp.yaml

# Generate Rust
buf generate --template buf.gen.rust.yaml
```
