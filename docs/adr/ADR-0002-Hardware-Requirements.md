# ADR-0002: Hardware Requirements

| Field | Value |
|-------|-------|
| **Status** | Proposed |
| **Date** | 2025-01-27 |
| **Owner** | Mike Mulcahy (Divinity10), Scott (scottcm) |
| **Contributors** | |
| **Module** | Platform |
| **Tags** | hardware, gpu, performance |
| **Depends On** | ADR-0001 |

---

## 1. Context and Problem Statement

The GLADyS requires hardware capable of running multiple ML models concurrently with sub-second response latency. This ADR defines hardware requirements based on the architecture specified in ADR-0001.

Key constraints:
- Multiple models run simultaneously (sensors, salience, embeddings, executive, TTS)
- Target latency: ~1000ms end-to-end
- Local-first architecture (data stays on user's machine)
- Initial scope: single user, single machine
- Must support dynamic loading/unloading of sensors
- Hybrid cloud option available for development phase

---

## 2. Current Hardware Baseline

The team has existing hardware that informs upgrade decisions:

| Component | Current Spec | Assessment |
|-----------|--------------|------------|
| CPU | Intel i5 9600K (6C/6T, 3.7GHz) | Adequate for inference orchestration |
| RAM | 64 GB DDR4 | Good; enables CPU offloading |
| GPU | RTX 2070 8GB | **Limiting factor**; single small model only |
| PCIe | Second x16 slot available | Enables dual-GPU upgrade path |
| Software | OpenWebUI + Ollama, Gemma 3 4B | Working baseline |

### Current Hardware Limitations

| Configuration | Supported? | Notes |
|---------------|------------|-------|
| Single 7B Q4 model | ✓ | ~4-5GB, leaves some headroom |
| Gemma 3 4B + Whisper small | ✓ | ~3GB + 1GB |
| Two models concurrently | ✗ | Not enough VRAM |
| 13B+ models | ✗ | Requires offloading (slow) |
| Full concurrent architecture | ✗ | Needs 24GB+ VRAM |

---

## 3. Component Resource Requirements

### 3.1 GPU Memory (VRAM) by Component

| Component | Model Type | VRAM (FP16) | VRAM (Q4/Q8) | Notes |
|-----------|-----------|-------------|--------------|-------|
| Audio Sensor | Whisper small | 1 GB | - | Real-time streaming |
| Audio Sensor | Whisper medium | 2 GB | - | Better accuracy |
| Visual Sensor | YOLO v8 | 1-2 GB | - | Object detection |
| Visual Sensor | Gemma 3 4B | 8 GB | 3 GB | Multimodal, current setup |
| Visual Sensor | Florence-2 | 4-8 GB | - | More capable vision |
| Salience Evaluator | Phi-3 Mini (3.8B) | 8 GB | 2.5 GB | Fast, capable |
| Salience Evaluator | Qwen2 (3B) | 6 GB | 2.5 GB | Alternative |
| Embedding Model | all-MiniLM-L6-v2 | 0.5 GB | - | 384 dims, fast |
| Embedding Model | BGE-base | 1 GB | - | Better quality |
| Executive | Llama 3.1 (8B) | 16 GB | 5 GB | Good baseline |
| Executive | Qwen2.5 (14B) | 28 GB | 10 GB | Recommended local |
| Executive | Qwen2.5 (32B) | 64 GB | 20 GB | Excellent reasoning |
| Executive | Remote API | 0 GB | 0 GB | Offload to cloud |
| TTS | Piper | 0.5 GB | - | Fast, lightweight |
| TTS | Bark | 2-4 GB | - | More expressive |
| TTS | Coqui XTTS | 2-3 GB | - | Voice cloning |

### 3.2 Model Comparison

| Model | Params | VRAM (Q4) | Reasoning | Personality | Multimodal | Speed | Best For |
|-------|--------|-----------|-----------|-------------|------------|-------|----------|
| Gemma 3 4B | 4B | 3GB | ★★☆☆☆ | ★★☆☆☆ | ✓ | ★★★★★ | Vision, simple tasks |
| Phi-3 Mini | 3.8B | 2.5GB | ★★★☆☆ | ★★☆☆☆ | ✗ | ★★★★★ | Salience, classification |
| Llama 3.1 8B | 8B | 5GB | ★★★☆☆ | ★★★☆☆ | ✗ | ★★★★☆ | General, good balance |
| Qwen2.5 7B | 7B | 4.5GB | ★★★☆☆ | ★★★☆☆ | ✗ | ★★★★☆ | Instruction following |
| Mistral 7B | 7B | 4.5GB | ★★★☆☆ | ★★★☆☆ | ✗ | ★★★★☆ | General purpose |
| Qwen2.5 14B | 14B | 10GB | ★★★★☆ | ★★★★☆ | ✗ | ★★★☆☆ | Executive (recommended) |
| Llama 3.1 70B | 70B | 40GB | ★★★★★ | ★★★★★ | ✗ | ★★☆☆☆ | Best local quality |

### 3.3 Gemma 3 4B Assessment

Current setup uses Gemma 3 4B. Evaluation for AI roles:

| Role | Suitable? | Assessment |
|------|-----------|------------|
| Executive | ✗ | Personality and reasoning too limited |
| Salience evaluator | ✓ | Can classify/score events |
| Visual sensor | ✓ | Good fit—its multimodal strength |
| General assistant | Marginal | Not for nuanced friend |

**Recommendation:** Keep Gemma 3 4B for vision tasks. Use larger model for Executive.

### 3.4 Concurrent Usage Scenarios

**Scenario A: Minimal Local (Remote Executive)**
| Component | VRAM |
|-----------|------|
| Whisper small | 1 GB |
| Gemma 3 4B (Vision) | 3 GB |
| Phi-3 Mini (Salience) Q4 | 2.5 GB |
| Embedding | 0.5 GB |
| Piper TTS | 0.5 GB |
| **Total** | **7.5 GB** |

**Scenario B: Local Executive (8B model)**
| Component | VRAM |
|-----------|------|
| Whisper medium | 2 GB |
| Gemma 3 4B (Vision) | 3 GB |
| Phi-3 Mini (Salience) Q4 | 2.5 GB |
| Embedding | 1 GB |
| Llama 3.1 8B Q4 (Executive) | 5 GB |
| Piper TTS | 0.5 GB |
| **Total** | **14 GB** |

**Scenario C: Quality Local (14B Executive)**
| Component | VRAM |
|-----------|------|
| Whisper medium | 2 GB |
| Gemma 3 4B (Vision) | 3 GB |
| Phi-3 Mini (Salience) Q4 | 2.5 GB |
| Embedding | 1 GB |
| Qwen2.5 14B Q4 (Executive) | 10 GB |
| Coqui TTS | 2 GB |
| **Total** | **20.5 GB** |

**Scenario D: Maximum Quality (32B Executive)**
| Component | VRAM |
|-----------|------|
| Whisper medium | 2 GB |
| Gemma 3 4B (Vision) | 3 GB |
| Phi-3 Mini (Salience) Q4 | 2.5 GB |
| Embedding | 1 GB |
| Qwen2.5 32B Q4 (Executive) | 20 GB |
| Coqui TTS | 2 GB |
| **Total** | **30.5 GB** |

---

## 4. Cloud and Hybrid Options

### 4.1 Cloud API Services

| Provider | Service | Models Available | Pricing (per 1M tokens) |
|----------|---------|------------------|------------------------|
| OpenAI | API | GPT-4o, GPT-4-turbo | $2.50-10 input, $10-30 output |
| Anthropic | API | Claude 3.5 Sonnet, Opus | $3-15 input, $15-75 output |
| Google | Vertex AI | Gemini Pro, Ultra | $1.25-5 input, $5-15 output |
| Microsoft | Azure OpenAI | GPT-4o, GPT-4-turbo | Same as OpenAI |
| Mistral | API | Mistral Large, Medium | $2-8 input, $6-24 output |
| Groq | API | Llama, Mixtral | $0.05-0.27 (very fast inference) |
| Together.ai | API | Many open models | $0.20-2.00 |
| Fireworks.ai | API | Many open models | $0.20-1.00 |

### 4.2 GPU Rental (Self-Managed)

| Provider | GPU | $/hour | VRAM | Notes |
|----------|-----|--------|------|-------|
| RunPod | RTX 4090 | $0.44 | 24GB | Spot pricing |
| RunPod | A100 80GB | $1.99 | 80GB | On-demand |
| Lambda Labs | A100 40GB | $1.10 | 40GB | When available |
| Lambda Labs | H100 | $2.49 | 80GB | Premium |
| Vast.ai | RTX 4090 | $0.30-0.50 | 24GB | Marketplace, variable |
| Vast.ai | A100 | $1.00-1.50 | 40-80GB | Marketplace |
| AWS | p4d.24xlarge | $32.77 | 320GB | Enterprise (8x A100) |
| Azure | NC24ads A100 | $3.67 | 80GB | Enterprise |
| GCP | a2-highgpu-1g | $3.67 | 40GB | Enterprise |

### 4.3 Latency Comparison

| Deployment | Network RTT | Inference Time | Total Latency | Notes |
|------------|-------------|----------------|---------------|-------|
| Local (RTX 4090, 8B Q4) | 0 ms | 300-500 ms | 300-500 ms | Best case |
| Local (RTX 4090, 14B Q4) | 0 ms | 500-800 ms | 500-800 ms | Good |
| Cloud API (OpenAI/Claude) | 50-150 ms | 500-2000 ms | 600-2500 ms | Variable load |
| Cloud API (Groq) | 50-100 ms | 100-300 ms | 150-400 ms | Optimized inference |
| Cloud GPU (your model) | 50-100 ms | 300-800 ms | 400-900 ms | Depends on instance |

**Note:** Groq provides notably fast inference. Within 1000ms latency budget for most cases.

### 4.4 Cost Analysis

**Development Scenario:**
- 8 hours/day active use
- ~100 Executive calls/hour during active use
- ~500 tokens per call average
- 22 days/month
- **Monthly tokens: 8.8M**

| Option | Monthly Cost | Notes |
|--------|--------------|-------|
| OpenAI GPT-4o | $88-176 | $10-20 per 1M blended |
| Claude 3.5 Sonnet | $132 | $15 per 1M blended |
| Groq (Llama 70B) | $24 | $0.27 per 1M |
| Together.ai (Llama 70B) | $18 | $0.20 per 1M |
| Local (after hardware) | $30-50 | Electricity only |

**Production Scenario (heavier use):**
- 12 hours/day, 200 calls/hour, 30 days/month
- **Monthly tokens: 36M**

| Option | Monthly Cost |
|--------|--------------|
| OpenAI GPT-4o | $360-720 |
| Claude 3.5 Sonnet | $540 |
| Groq | $97 |
| Together.ai | $72 |
| Local | $50-80 (electricity) |

### 4.5 Microsoft for Startups (Founders Hub)

| Tier | Credits | Requirements |
|------|---------|--------------|
| Level 1 | $1,000 | Any startup, self-service |
| Level 2 | $5,000 | LLC or equivalent |
| Level 3 | $25,000 | VC-backed or accelerator |
| Level 4 | $150,000 | Series A+ or select accelerators |

**$5,000 Azure credits provide:**
- ~500M tokens GPT-4o mini (~5 years development)
- ~50M tokens GPT-4o (~6 months development)
- ~16M tokens GPT-4 Turbo

**Recommendation:** Apply for Level 2 ($5,000) to extend development runway.

### 4.6 Break-Even Analysis

| Hardware Cost | Monthly Cloud Cost | Break-Even |
|---------------|-------------------|------------|
| $850 (3090 upgrade) | $100/month | 8.5 months |
| $850 (3090 upgrade) | $500/month (heavy use) | 2 months |
| $1,900 (4090 new) | $100/month | 19 months |
| $1,900 (4090 new) | $500/month | 4 months |

---

## 5. GPU Options

### 5.1 Consumer GPUs

| GPU | VRAM | Price (USD) | Supports Scenario | Notes |
|-----|------|-------------|-------------------|-------|
| RTX 4070 | 12 GB | $550 | A only | Remote Executive required |
| RTX 4070 Ti Super | 16 GB | $800 | A, B (tight) | Limited headroom |
| RTX 4080 Super | 16 GB | $1,000 | A, B (tight) | Faster than 4070 Ti |
| RTX 4090 | 24 GB | $1,800-2,000 | A, B, C | Best consumer option |
| RTX 5090 | 32 GB | $2,000+ | A, B, C, D (tight) | When available |

### 5.2 Used GPUs (Recommended for Budget)

| GPU | VRAM | Used Price (USD) | Supports Scenario | Notes |
|-----|------|------------------|-------------------|-------|
| RTX 3080 12GB | 12 GB | $450-550 | A, B (tight) | Budget option |
| RTX 3090 | 24 GB | $700-900 | A, B, C | **Best value for upgrade** |
| RTX 3090 Ti | 24 GB | $800-1,000 | A, B, C | Slightly faster |

### 5.3 Professional GPUs

| GPU | VRAM | Price (USD) | Supports Scenario | Notes |
|-----|------|-------------|-------------------|-------|
| RTX A4000 | 16 GB | $1,000 (used) | A, B | Workstation card |
| RTX A5000 | 24 GB | $2,500 (used) | A, B, C | Better than 4090 for sustained |
| RTX A6000 | 48 GB | $4,000-5,000 (used) | All | Comfortable headroom |
| RTX 6000 Ada | 48 GB | $6,500+ | All | Current generation pro |

### 5.4 Datacenter GPUs (Used Market)

| GPU | VRAM | Price (USD) | Supports Scenario | Notes |
|-----|------|-------------|-------------------|-------|
| A100 40GB | 40 GB | $5,000-8,000 | All | Purpose-built for ML |
| A100 80GB | 80 GB | $10,000-15,000 | All + future | Maximum headroom |
| H100 | 80 GB | $25,000+ | Overkill | Training-focused |

### 5.5 Multi-GPU Considerations

**Critical:** VRAM does not pool across GPUs.

| Configuration | Usable VRAM per Model |
|---------------|----------------------|
| 1x RTX 2070 8GB | 8GB |
| 2x RTX 2070 8GB | Still 8GB per model |
| RTX 3090 + RTX 2070 | 24GB + 8GB (separate pools) |

**What dual-GPU enables:**
- Run different models on each GPU (sensors on one, executive on other)
- Does NOT enable running one large model across both (without complex tensor parallelism)

For the AI architecture, dual-GPU works well:
```
GPU 0 (Large): Executive + Salience + Embeddings + TTS
GPU 1 (Small): Sensors (Audio + Vision)
```

---

## 6. CPU Requirements

| Tier | CPU | Cores/Threads | Notes |
|------|-----|---------------|-------|
| Current | i5 9600K | 6C/6T | Adequate for inference |
| Minimum | Ryzen 7 7700 / i7-13700 | 8C/16T | Good headroom |
| Recommended | Ryzen 9 7900X / i7-14700K | 12-16C/24T | Comfortable |
| High-end | Ryzen 9 7950X / i9-14900K | 16-24C/32T | Future-proof |

**Assessment:** Current i5 9600K is adequate. GPU is the bottleneck, not CPU. Upgrade CPU only with full system rebuild.

---

## 7. System Memory (RAM)

| Tier | RAM | Notes |
|------|-----|-------|
| Current | 64 GB DDR4 | Good for all scenarios |
| Minimum | 32 GB | Tight; limits concurrent operations |
| Recommended | 64 GB | Comfortable for all scenarios |
| High-end | 128 GB | Allows RAM offloading for larger models |

**Assessment:** Current 64GB is sufficient. No upgrade needed.

---

## 8. Storage

| Use Case | Size | Speed | Notes |
|----------|------|-------|-------|
| OS + Applications | 100 GB | Fast | NVMe SSD |
| Models | 50-200 GB | Fast | Depends on model count |
| PostgreSQL + pgvector | 50-500 GB | Fast | Grows with memory retention |
| Backups | 500+ GB | Moderate | Can be HDD |

**Recommendation:** 2 TB NVMe primary, external/NAS for backups.

---

## 9. Power Supply

| Configuration | GPU TDP | System | PSU Needed |
|---------------|---------|--------|------------|
| RTX 2070 alone | 215W | 150W | 500-550W |
| RTX 2070 + RTX 3090 | 565W | 150W | **850W+ required** |
| RTX 4090 alone | 450W | 150W | 850-1000W |
| RTX 5090 alone | 575W | 150W | 1000-1200W |

**Note:** Dual-GPU setup (2070 + 3090) requires PSU upgrade to 850W minimum.

---

## 10. Recommended Configurations

### 10.1 Immediate: Hybrid Cloud (No Hardware Purchase)

Use current hardware with cloud Executive.

| Component | Deployment | Notes |
|-----------|------------|-------|
| Sensors | Local (RTX 2070) | Gemma 3 4B for vision |
| Salience | Local (RTX 2070) | Model swap with sensors |
| Memory/Embeddings | Local (CPU) | PostgreSQL + small embedding model |
| **Executive** | **Azure OpenAI / Groq** | Use MS credits or Groq for speed |
| TTS | Local | Piper (lightweight) |

**Cost:** $0-100/month (covered by MS credits initially)

**Limitations:** Model swapping (not concurrent), cloud latency, API dependency

### 10.2 Recommended Upgrade: Dual-GPU (RTX 3090 + RTX 2070)

Add RTX 3090 to existing system.

| Item | Spec | Price (USD) |
|------|------|-------------|
| GPU | RTX 3090 24GB (used) | $700-900 |
| PSU | 850W 80+ Gold | $100-130 |
| **Total** | | **$800-1,030** |

**Resulting Configuration:**
```
GPU 0: RTX 3090 24GB (Primary)
├── Executive (Qwen2.5 14B Q4)     ~10 GB
├── Salience (Phi-3 Mini Q4)        ~2.5 GB
├── Embeddings (BGE-base)           ~1 GB
├── TTS (Piper)                     ~0.5 GB
└── Headroom                        ~10 GB

GPU 1: RTX 2070 8GB (Secondary)
├── Audio Sensor (Whisper medium)   ~2 GB
├── Visual Sensor (Gemma 3 4B)      ~3 GB
└── Headroom                        ~3 GB
```

**Supports:** Full concurrent architecture, Scenarios A-C

**Ollama Multi-GPU:**
```bash
CUDA_VISIBLE_DEVICES=0 ollama run qwen2.5:14b
CUDA_VISIBLE_DEVICES=1 ollama run gemma3:4b
```

### 10.3 Alternative: Single GPU Upgrade (RTX 4090)

Replace RTX 2070 with RTX 4090.

| Item | Spec | Price (USD) |
|------|------|-------------|
| GPU | RTX 4090 24GB | $1,800-2,000 |
| PSU | 1000W 80+ Gold (if needed) | $150 |
| **Total** | | **$1,950-2,150** |

**Pros:** Cleaner setup, newer/efficient architecture, single GPU to manage

**Cons:** Higher cost, loses dual-GPU flexibility

### 10.4 Full System Build (If Starting Fresh)

| Component | Specification | Price (USD) |
|-----------|--------------|-------------|
| CPU | Ryzen 9 7900X | $400 |
| Motherboard | X670E ATX | $280 |
| RAM | 64 GB DDR5-5600 | $200 |
| GPU | RTX 4090 24GB | $1,900 |
| Storage | 2 TB NVMe | $150 |
| PSU | 1000W 80+ Gold | $150 |
| Case | Full tower, good airflow | $150 |
| Cooler | 360mm AIO | $150 |
| **Total** | | **~$3,400** |

### 10.5 High-End Build (Maximum Local Capability)

| Component | Specification | Price (USD) |
|-----------|--------------|-------------|
| CPU | Ryzen 9 7950X | $550 |
| Motherboard | X670E ATX | $300 |
| RAM | 128 GB DDR5-5600 | $400 |
| GPU | RTX A6000 48GB (used) | $4,500 |
| Storage | 2 TB NVMe + 2 TB SATA SSD | $250 |
| PSU | 1000W 80+ Platinum | $180 |
| Case | Full tower | $150 |
| Cooler | 360mm AIO | $150 |
| **Total** | | **~$6,500** |

---

## 11. Decision

### 11.1 Immediate (Phase 1)

1. **Apply for MS Founders Hub Level 2** ($5,000 Azure credits)
2. **Add Llama 3.1 8B Q4** to Ollama for text reasoning
3. **Keep Gemma 3 4B** for vision/multimodal
4. **Use Azure OpenAI or Groq** for Executive during development
5. Model swap on current RTX 2070 (not concurrent)

**Cost:** $0 hardware, API covered by credits

### 11.2 Short-Term (Phase 2)

**Purchase used RTX 3090 + PSU upgrade (~$850-1,000)**

This enables:
- Full concurrent architecture
- Local Executive (Qwen2.5 14B)
- No ongoing API costs
- Complete privacy

### 11.3 Upgrade Path

| Starting Point | Next Upgrade | Trigger |
|----------------|--------------|---------|
| 2070 + Cloud | Add RTX 3090 | Want full local |
| 2070 + 3090 | Replace both with 4090/5090 | Want simpler setup |
| 4090 (24GB) | A6000 (48GB) | Need 32B+ models |
| A6000 (48GB) | A100/H100 | Need 70B+ models |

---

## 12. Pre-Purchase Checklist (For RTX 3090)

Before purchasing:

1. **Check PSU wattage** — Label on power supply. Need 850W+ for dual GPU.
2. **Check PSU connectors** — Need two 8-pin PCIe cables for 3090.
3. **Measure case clearance** — RTX 3090 is 300-340mm long, 3 slots wide.
4. **Verify PCIe slot** — Confirmed x16 slot available.

**RTX 3090 Shopping Tips:**

| Brand/Model | Notes |
|-------------|-------|
| Founders Edition | Compact, good cooling, premium price |
| EVGA FTW3 | Excellent (no warranty—EVGA exited GPU market) |
| ASUS TUF | Reliable, good cooling |
| MSI Gaming X Trio | Large, runs cool |

**Where to buy:** eBay (check ratings), r/hardwareswap, local (test before buying)

**Fair price:** $700-900 depending on model/condition

---

## 13. Consequences

### 13.1 Positive

1. Clear upgrade path from current hardware
2. Dual-GPU option maximizes existing investment
3. Cloud hybrid extends runway with MS credits
4. Break-even favors local for sustained use

### 13.2 Negative

1. Dual-GPU adds complexity (device assignment, thermals)
2. Used GPU market has risks (mining wear, no warranty)
3. PSU upgrade required for dual-GPU

### 13.3 Risks

1. Model sizes increasing—24GB may become tight in 2-3 years
2. Used RTX 3090 availability varies
3. RTX 5090 release may shift value calculations

---

## 14. Related Decisions

- ADR-0001: GLADyS Architecture
- ADR-0003: Plugin Manifest Specification (pending)
- ADR-0004: Memory Schema Details (pending)

---

## 15. Notes

Prices as of January 2025. GPU market is volatile.

For used GPUs: verify cooling compatibility, check for mining wear, test before purchasing locally.

Groq provides fast inference at low cost—good option for development and latency-sensitive production use.

The dual-GPU path (RTX 3090 + existing RTX 2070) provides best value for enabling full local architecture given existing hardware.
