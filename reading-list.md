# GLADyS Design Reading List

Personal reading recommendations for improving GLADyS design understanding. Not committed to repo.

---

## Priority 1: Core Architecture Concepts

### Society of Mind - Marvin Minsky (1986)
**Why**: Foundation for modular cognitive architecture. Directly relevant to how GLADyS components (salience, executive, skills) interact.

### Sources of Power: How People Make Decisions - Gary Klein (1998)
**Why**: Recognition-Primed Decision (RPD) model. How experts make fast decisions without deliberation. Directly applicable to System 1 design and heuristic learning.

---

## Priority 2: Decision Theory

### Thinking, Fast and Slow - Daniel Kahneman (2011)
**Why**: If you haven't read it cover-to-cover, worth revisiting. System 1/2 framing, cognitive biases, how intuition fails and succeeds.

### Gut Feelings: The Intelligence of the Unconscious - Gerd Gigerenzer (2007)
**Why**: Counterpoint to Kahneman. Argues heuristics aren't just "biased System 1" but genuinely adaptive. Relevant to when GLADyS should trust fast heuristics vs escalate.

---

## Priority 3: Technical Foundations

### Reinforcement Learning: An Introduction - Sutton & Barto (2018, 2nd ed)
**Why**: Standard RL text. Relevant to reward signals, learning from feedback, exploration vs exploitation. Free PDF available.
- **Chapter 6**: Temporal Difference Learning - core concept for prediction error
- **Chapter 8**: Planning and Learning - experience replay fundamentals
- **Chapter 13**: Policy Gradient Methods - exploration vs exploitation
- Free PDF: http://incompleteideas.net/book/the-book.html

### Bayesian Data Analysis - Gelman et al. (2013, 3rd ed)
**Why**: Reference for conjugate priors, hierarchical models. More rigorous than coursework coverage. Consult specific chapters as needed rather than reading cover-to-cover.

---

## Priority 3.5: Learning Architecture (ADR-0010 Related) - NEW

These resources support the deferred validation and outcome-based learning design.

### Experience Replay

**Playing Atari with Deep Reinforcement Learning - Mnih et al. (2013)**
**Why**: Introduces experience replay in deep RL. GLADyS's deferred validation queue is essentially experience replay.
- https://arxiv.org/abs/1312.5602

**Prioritized Experience Replay - Schaul et al. (2015)**
**Why**: Replay surprising/important experiences more often. Post-MVP enhancement for GLADyS.
- https://arxiv.org/abs/1511.05952
- Key metric: TD-error magnitude determines priority

### Reward Shaping

**Reward Shaping in Reinforcement Learning - Ng, Harada, Russell (1999)**
**Why**: Formal treatment of how shaped rewards preserve optimal policy. Directly relevant to pack-provided OutcomeEvaluator design.
- "Policy invariance under reward transformations"
- ICML 1999

**Designing Reward Functions - OpenAI Blog**
**Why**: Practical examples of reward shaping pitfalls. Cautions about reward hacking.
- https://openai.com/research/faulty-reward-functions

### Prediction Error & Dopamine

**A Neural Substrate of Prediction and Reward - Schultz et al. (1997)**
**Why**: Seminal paper showing dopamine neurons encode prediction error, not reward itself. Biological basis for temporal difference learning.
- Science 275(5306):1593-9
- "Dopamine neurons report an error in the prediction of reward"

**Dopamine, uncertainty and TD learning - Niv (2009)**
**Why**: Connects TD learning to dopamine signaling. Good overview of computational neuroscience of reward.
- Behavioral and Brain Functions 5:6

### Exploration vs Exploitation

**Exploration exploitation in Go: UCT for Monte-Carlo Go**
**Why**: Upper Confidence Bounds for balancing exploration. Relevant to epsilon parameter design.

**Curiosity-driven Exploration by Self-Supervised Prediction - Pathak et al. (2017)**
**Why**: Intrinsic motivation via prediction error. Could inform novelty detection in GLADyS.
- https://arxiv.org/abs/1705.05363

### Hebbian Learning

**Organization of Behavior - Donald Hebb (1949)**
**Why**: Original source of "neurons that fire together, wire together". Historical reference.
- Classic, cited but rarely read in full

**Hebbian Learning and Spiking Neurons - Gerstner & Kistler (2002)**
**Why**: Modern treatment of Hebbian learning. Chapter 10 specifically.
- https://neuronaldynamics.epfl.ch/online/Ch10.html (free online)

### Sleep and Memory Consolidation

**Sleep-dependent memory consolidation - Stickgold (2005)**
**Why**: How sleep consolidates memories. Scientific basis for GLADyS "sleep mode" processing.
- Nature 437, 1272-1278

**Reactivation of hippocampal ensemble memories during sleep - Wilson & McNaughton (1994)**
**Why**: Hippocampal replay during sleep. Biological experience replay.
- Science 265(5172):676-9

---

## Priority 4: Attention and Salience

### Seeley et al. (2007) - "Dissociable Intrinsic Connectivity Networks for Salience Processing and Executive Control"
**Why**: Original salience network paper. Understanding what salience means neurologically helps design the GLADyS salience subsystem.

### Attention papers (survey)
- Corbetta & Shulman (2002) - "Control of goal-directed and stimulus-driven attention in the brain"
- Posner & Petersen (1990) - "The attention system of the human brain"

---

## Optional / Interest-Based

### The Predictive Mind - Jakob Hohwy (2013)
**Why**: Predictive processing framework. Brain as prediction machine. Could inform how GLADyS models expectations and detects novelty.

### Surfing Uncertainty - Andy Clark (2015)
**Why**: More accessible take on predictive processing. Same relevance as Hohwy.

### Superintelligence / Human Compatible - Bostrom / Russell
**Why**: AI safety perspectives. Not directly applicable to GLADyS architecture but relevant to long-term thinking about user trust and control.

---

## Papers to Find

These are specific to gaps identified in GLADyS design:

1. **Salience computation algorithms** - How to quantify "what's important" from sensor streams
2. **Attention budgeting** - Computational models of limited attention allocation
3. **Online Bayesian learning** - Practical implementations of conjugate prior updates
4. **Context-aware learning** - How to partition beliefs by context without overfitting

---

## Priority 5: Memory Architecture (ADR-0004 Related)

### Complementary Learning Systems in Brains and Machines - Kumaran, Hassabis, McClelland (2016)
**Why**: Directly relevant to episodic/semantic split. Explains why fast and slow learning require separate systems.
- TICS Paper: https://www.cell.com/trends/cognitive-sciences/fulltext/S1364-6613(16)30043-2

### Why We Sleep - Matthew Walker (2017)
**Why**: Chapters on memory consolidation. Scientific basis for "sleep mode" batch processing.
- Popular science, accessible

### pgvector Documentation + Benchmarks
**Why**: HNSW vs IVFFlat tradeoffs. Practical tuning for vector indices.
- https://github.com/pgvector/pgvector

---

## Priority 6: Vector Search Deep Dive

### Billion-scale similarity search with GPUs - Facebook Research
**Why**: FAISS paper, explains IVF and PQ compression. Relevant for scaling episodic memory.
- https://arxiv.org/abs/1702.08734

### HNSW Original Paper - Malkov & Yashunin
**Why**: The algorithm pgvector uses. Understanding helps tune `m` and `ef_construction` parameters.
- "Efficient and robust approximate nearest neighbor search using Hierarchical Navigable Small World graphs"
- https://arxiv.org/abs/1603.09320

---

## Priority 7: Schema Evolution

### Evolutionary Database Design - Fowler & Sadalage
**Why**: Patterns for schema migration. Relevant for embedding dimension changes, adding Bayesian columns.
- https://martinfowler.com/articles/evodb.html

---

## Priority 8: Episodic Memory Theory

### Memory: A Self-Referential Account - Tulving
**Why**: Original episodic/semantic distinction. Deep theoretical foundation.
- Academic, dense - use as reference

### Making Working Memory Work - Baddeley
**Why**: Working memory model. Relevant to L0/L1 cache design.
- Classic cognitive psychology

---

## Papers to Find

These are specific to gaps identified in GLADyS design:

1. **Salience computation algorithms** - How to quantify "what's important" from sensor streams
2. **Attention budgeting** - Computational models of limited attention allocation
3. **Online Bayesian learning** - Practical implementations of conjugate prior updates
4. **Context-aware learning** - How to partition beliefs by context without overfitting
5. **LSM tree compaction strategies** - RocksDB/LevelDB papers for memory tiering inspiration
6. **Hippocampal indexing theory** - How hippocampus indexes neocortical memories

---

## Notes

- Start with Klein and revisit Kahneman - most directly applicable to current design gaps
- Gigerenzer provides useful pushback on over-deliberation
- Sutton & Barto for RL grounding when designing feedback loops
- Papers are reference material, not cover-to-cover reads
- **For memory design**: CLS paper is the must-read; Walker for sleep mode rationale
- **For vector search**: pgvector docs first, then FAISS paper if scaling becomes an issue
