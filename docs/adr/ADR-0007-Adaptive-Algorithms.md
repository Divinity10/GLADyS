# ADR-0007: Adaptive Algorithms

| Field | Value |
|-------|-------|
| **Status** | Proposed |
| **Date** | 2025-01-27 |
| **Owner** | Mike Mulcahy (Divinity10), Scott (scottcm) |
| **Contributors** | |
| **Module** | Intelligence |
| **Tags** | adaptation, ewma, feedback, personalization |
| **Depends On** | ADR-0001, ADR-0004, ADR-0006 |

---

## 1. Context and Problem Statement

GLADyS must adapt to individual users over time. Different users have different:
- Communication preferences (verbosity, formality, humor)
- Sarcasm and personality tolerance
- Skill levels in various domains
- Engagement patterns and proactivity preferences

Static configuration cannot serve all users well. The system needs principled algorithms for learning and adapting while maintaining stability and user control.

This ADR defines the adaptive algorithms, feedback mechanisms, safety bounds, and user controls.

---

## 2. Decision Drivers

1. **Personalization:** System should feel tailored to each user
2. **Stability:** Avoid oscillation or erratic behavior changes
3. **Transparency:** Users should understand what the system learned
4. **Control:** Users must be able to view, adjust, and reset learned parameters
5. **Safety:** Prevent runaway values or inappropriate adaptations
6. **Simplicity:** Algorithms should be understandable and debuggable

---

## 3. Algorithm Overview

### 3.1 Phase 1 Algorithms (Implement Now)

| Algorithm | Purpose | Implementation |
|-----------|---------|----------------|
| **EWMA** | User profile adaptation | Exponential weighted moving average |
| **Bayesian Update** | Confidence tracking | Beta distribution for binary outcomes |
| **Gradient Descent** | Threshold tuning | Online gradient descent with feedback |
| **Loss Function** | Performance measurement | Composite metric for optimization |

### 3.2 Phase 2 Algorithms (Later)

| Algorithm | Purpose | Implementation |
|-----------|---------|----------------|
| **Informed Search (A*)** | Memory retrieval optimization | Heuristic-guided memory search |
| **PID Control** | Proactivity regulation | Feedback loop for engagement |
| **Novelty/Entropy** | Habituation tuning | Information-theoretic surprise |

### 3.3 Phase 3 Algorithms (Future)

| Algorithm | Purpose | Implementation |
|-----------|---------|----------------|
| **Multi-armed Bandit** | A/B testing responses | Thompson sampling |
| **Policy Gradient** | Full response optimization | Reinforcement learning |

---

## 4. Feedback Collection

### 4.1 Feedback Types

| Type | Phase | Signal | Weight | Notes |
|------|-------|--------|--------|-------|
| **Explicit - Direct** | 1 | Thumbs up/down | 1.0 | Clear but sparse |
| **Explicit - Verbal** | 1 | "Too much sarcasm" | 1.0 | Natural language feedback |
| **Implicit - Engagement** | 2 | Response ignored/engaged | 0.7 | More data, needs interpretation |
| **Implicit - Correction** | 2 | User rephrased/repeated | 0.8 | Strong signal of failure |
| **Implicit - Interruption** | 2 | User interrupted speech | 0.6 | May indicate displeasure |

### 4.2 Weighting Strategy

Research in behavioral economics and industry practice (Netflix, Spotify, YouTube) shows implicit signals often predict user satisfaction better than explicit feedback due to social desirability bias and self-deception.

**Phase 1:** Explicit feedback only (clean signal while validating algorithms)

**Phase 2 Weighting:**

```python
def compute_effective_signal(explicit: Optional[float], implicit: float) -> float:
    """
    Combine explicit and implicit feedback.
    Implicit weighted higher due to revealed preference theory.
    """
    if explicit is None:
        return implicit
    
    # Strong explicit signals get more weight
    if abs(explicit - 0.5) > 0.4:  # Very positive or very negative
        return 0.5 * explicit + 0.5 * implicit
    
    # Normal weighting: implicit > explicit
    return 0.3 * explicit + 0.7 * implicit
```

### 4.3 Feedback Storage

```sql
-- Feedback events table
CREATE TABLE feedback_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    -- What triggered feedback
    event_id        UUID REFERENCES episodic_events(id),
    response_id     UUID,                   -- Response that received feedback
    
    -- Feedback details
    feedback_type   TEXT NOT NULL,          -- explicit_thumbs, explicit_verbal, implicit_engagement, etc.
    signal_value    FLOAT NOT NULL,         -- -1 to 1 (negative to positive)
    weight          FLOAT NOT NULL DEFAULT 1.0,
    
    -- Context
    active_personality  TEXT,
    active_traits       JSONB,
    
    -- What parameters this affects
    affected_params     TEXT[],             -- ['sarcasm_tolerance', 'verbosity_preference']
    
    -- Metadata
    processed           BOOLEAN DEFAULT false
);

CREATE INDEX idx_feedback_unprocessed ON feedback_events (timestamp) 
    WHERE processed = false;
```

---

## 5. EWMA Adaptation

### 5.1 Core Algorithm

Exponential Weighted Moving Average with dual time scales (TCP/IP inspired, per ADR-0004):

```python
class EWMAAdapter:
    """
    Dual-timescale EWMA for user trait adaptation.
    
    Short-term: Responds quickly to recent observations
    Long-term: Updates only when short-term is stable
    """
    
    def __init__(
        self,
        initial_value: float = 0.5,
        alpha: float = 0.4,           # Short-term learning rate
        beta: float = 0.08,           # Long-term learning rate
        stability_threshold: float = 0.1,
        stability_window: int = 10
    ):
        self.short_term = initial_value
        self.long_term = initial_value
        self.alpha = alpha
        self.beta = beta
        self.stability_threshold = stability_threshold
        self.stability_window = stability_window
        self.recent_values: List[float] = []
    
    def observe(self, value: float, confidence_weight: float = 1.0) -> Tuple[float, float]:
        """
        Update based on new observation.
        
        Args:
            value: Observed signal (0-1)
            confidence_weight: How much to trust this observation (0-1)
        
        Returns:
            (short_term, long_term) updated values
        """
        # Adjust alpha by confidence weight
        effective_alpha = self.alpha * confidence_weight
        
        # Update short-term
        self.short_term = effective_alpha * value + (1 - effective_alpha) * self.short_term
        
        # Track for stability calculation
        self.recent_values.append(self.short_term)
        if len(self.recent_values) > self.stability_window:
            self.recent_values.pop(0)
        
        # Update long-term only if stable
        if self._is_stable():
            self.long_term = self.beta * self.short_term + (1 - self.beta) * self.long_term
        
        return self.short_term, self.long_term
    
    def _is_stable(self) -> bool:
        """Check if short-term has stabilized."""
        if len(self.recent_values) < self.stability_window:
            return False
        variance = statistics.variance(self.recent_values)
        return variance < self.stability_threshold
    
    def get_effective_value(self, stability_weight: float = None) -> float:
        """
        Get value to use for decisions.
        More stable = weight long-term more.
        """
        if stability_weight is None:
            stability_weight = self._compute_stability_weight()
        return stability_weight * self.long_term + (1 - stability_weight) * self.short_term
    
    def _compute_stability_weight(self) -> float:
        """Higher when short-term is stable."""
        if len(self.recent_values) < self.stability_window:
            return 0.3  # Default to short-term when insufficient data
        variance = statistics.variance(self.recent_values)
        # Map variance to weight: low variance → high weight on long-term
        return max(0.0, min(1.0, 1.0 - variance * 5))
```

### 5.2 Parameter-Specific Learning Rates

Different parameters adapt at different speeds based on their nature:

| Parameter Category | α (short-term) | β (long-term) | Rationale |
|-------------------|----------------|---------------|-----------|
| **Mood/State** | 0.5-0.6 | 0.10 | Changes quickly, track closely |
| **Communication Style** | 0.3-0.4 | 0.08 | Moderate stability |
| **Humor/Sarcasm** | 0.3-0.4 | 0.08 | Context-dependent |
| **Verbosity** | 0.3-0.4 | 0.08 | Moderate stability |
| **Domain Skill** | 0.15-0.25 | 0.05 | Slow to change, noisy signal |
| **Personality Compatibility** | 0.2-0.3 | 0.06 | Fairly stable |
| **Play Style** | 0.2-0.3 | 0.06 | Reasonably stable |
| **Factual Knowledge** | 0.1-0.2 | 0.03 | High confidence once learned |
| **Long-term Traits** | 0.05-0.1 | 0.02 | Very stable |

### 5.3 Configuration

```yaml
# config/adaptation_rates.yaml
parameters:
  # Mood and state (fast)
  current_mood:
    alpha: 0.55
    beta: 0.10
    category: mood
  
  # Communication preferences (moderate)
  sarcasm_tolerance:
    alpha: 0.35
    beta: 0.08
    category: communication
  
  verbosity_preference:
    alpha: 0.35
    beta: 0.08
    category: communication
  
  humor_appreciation:
    alpha: 0.35
    beta: 0.08
    category: communication
  
  formality_preference:
    alpha: 0.30
    beta: 0.08
    category: communication
  
  # Skill assessments (slow)
  skill_minecraft_combat:
    alpha: 0.20
    beta: 0.05
    category: skill
  
  skill_minecraft_building:
    alpha: 0.20
    beta: 0.05
    category: skill
  
  skill_minecraft_redstone:
    alpha: 0.20
    beta: 0.05
    category: skill
  
  # Behavioral patterns (slow)
  proactivity_tolerance:
    alpha: 0.25
    beta: 0.06
    category: behavior
  
  play_style_aggressive:
    alpha: 0.25
    beta: 0.06
    category: behavior

defaults:
  alpha: 0.30
  beta: 0.08
  stability_threshold: 0.1
  stability_window: 10
```

---

## 6. Bayesian Confidence Tracking

### 6.1 Purpose

EWMA provides smoothed values but no measure of certainty. Bayesian tracking answers:
- "How confident am I about this preference?"
- "Should I still be exploring or have I converged?"
- "What should I tell the user about my certainty?"

### 6.2 Implementation

```python
class BayesianTracker:
    """
    Track confidence for a parameter using Beta distribution.
    
    Beta distribution is natural for modeling probability/rate parameters.
    Alpha = positive observations + prior
    Beta = negative observations + prior
    """
    
    def __init__(self, prior_alpha: float = 1.0, prior_beta: float = 1.0):
        """
        Initialize with prior beliefs.
        
        Args:
            prior_alpha: Prior positive evidence (default 1 = uniform prior)
            prior_beta: Prior negative evidence (default 1 = uniform prior)
        """
        self.alpha = prior_alpha
        self.beta = prior_beta
        self.observation_count = 0
    
    def update(self, observation: float, weight: float = 1.0):
        """
        Update beliefs based on observation.
        
        Args:
            observation: Value between 0 (negative) and 1 (positive)
            weight: How much to count this observation
        """
        # Treat observation as soft evidence
        self.alpha += observation * weight
        self.beta += (1 - observation) * weight
        self.observation_count += 1
    
    @property
    def mean(self) -> float:
        """Expected value (MAP estimate)."""
        return self.alpha / (self.alpha + self.beta)
    
    @property
    def variance(self) -> float:
        """Uncertainty in estimate."""
        total = self.alpha + self.beta
        return (self.alpha * self.beta) / (total ** 2 * (total + 1))
    
    @property
    def confidence(self) -> float:
        """
        Confidence level (0-1).
        Higher with more observations and lower variance.
        """
        # Based on total evidence
        total_evidence = self.alpha + self.beta - 2  # Subtract prior
        evidence_confidence = 1 - (1 / (1 + total_evidence * 0.1))
        
        # Penalize high variance
        max_variance = 0.25  # Variance of uniform distribution
        variance_confidence = 1 - (self.variance / max_variance)
        
        return evidence_confidence * variance_confidence
    
    def sample(self) -> float:
        """Sample from posterior for Thompson sampling."""
        return random.betavariate(self.alpha, self.beta)
    
    def credible_interval(self, level: float = 0.95) -> Tuple[float, float]:
        """Return credible interval for the parameter."""
        from scipy import stats
        dist = stats.beta(self.alpha, self.beta)
        lower = dist.ppf((1 - level) / 2)
        upper = dist.ppf(1 - (1 - level) / 2)
        return (lower, upper)
```

### 6.3 Integration with EWMA

```python
class AdaptiveParameter:
    """
    Full adaptive parameter with EWMA smoothing and Bayesian confidence.
    """
    
    def __init__(
        self,
        name: str,
        initial_value: float = 0.5,
        alpha: float = 0.3,
        beta: float = 0.08,
        prior_strength: float = 1.0
    ):
        self.name = name
        self.ewma = EWMAAdapter(initial_value, alpha, beta)
        self.bayesian = BayesianTracker(prior_strength, prior_strength)
        self.bounds = ParameterBounds.get(name)
    
    def observe(self, value: float, feedback_weight: float = 1.0):
        """Process new observation."""
        # Clamp to bounds
        value = max(self.bounds.min, min(self.bounds.max, value))
        
        # Confidence-weighted learning rate
        confidence_factor = 1.0 - (self.bayesian.confidence * 0.7)
        
        # Update EWMA
        self.ewma.observe(value, confidence_weight=confidence_factor * feedback_weight)
        
        # Update Bayesian
        self.bayesian.update(value, weight=feedback_weight)
    
    @property
    def value(self) -> float:
        """Current effective value."""
        return self.ewma.get_effective_value()
    
    @property
    def confidence(self) -> float:
        """Current confidence in value."""
        return self.bayesian.confidence
    
    @property
    def is_converged(self) -> bool:
        """Has parameter stabilized?"""
        return self.confidence > 0.7 and self.ewma._is_stable()
    
    def to_dict(self) -> dict:
        """Export state."""
        return {
            "name": self.name,
            "value": self.value,
            "short_term": self.ewma.short_term,
            "long_term": self.ewma.long_term,
            "confidence": self.confidence,
            "observation_count": self.bayesian.observation_count,
            "bayesian_alpha": self.bayesian.alpha,
            "bayesian_beta": self.bayesian.beta,
        }
```

---

## 7. Gradient Descent for Threshold Tuning

### 7.1 Purpose

Tune system thresholds (e.g., "when should I speak?") based on feedback.

### 7.2 Implementation

```python
class ThresholdOptimizer:
    """
    Online gradient descent for threshold parameters.
    """
    
    def __init__(
        self,
        initial_threshold: float = 0.5,
        learning_rate: float = 0.01,
        min_threshold: float = 0.1,
        max_threshold: float = 0.9
    ):
        self.threshold = initial_threshold
        self.learning_rate = learning_rate
        self.min_threshold = min_threshold
        self.max_threshold = max_threshold
        self.update_count = 0
    
    def update(self, score: float, should_have_acted: bool, did_act: bool):
        """
        Update threshold based on outcome.
        
        Args:
            score: The salience score that was evaluated
            should_have_acted: True if action was appropriate (from feedback)
            did_act: True if system did act (score > threshold)
        """
        # Compute gradient
        if did_act and not should_have_acted:
            # False positive: acted when shouldn't have
            # Raise threshold (positive gradient)
            gradient = 1.0
        elif not did_act and should_have_acted:
            # False negative: didn't act when should have
            # Lower threshold (negative gradient)
            gradient = -1.0
        else:
            # Correct decision
            gradient = 0.0
        
        # Apply with decaying learning rate
        effective_lr = self.learning_rate / (1 + self.update_count * 0.01)
        self.threshold += effective_lr * gradient
        
        # Clamp to bounds
        self.threshold = max(self.min_threshold, min(self.max_threshold, self.threshold))
        self.update_count += 1
    
    def should_act(self, score: float) -> bool:
        """Decide if score exceeds threshold."""
        return score > self.threshold
```

### 7.3 Salience Threshold Tuning

```python
class SalienceThresholdTuner:
    """
    Tune salience thresholds per dimension.
    """
    
    def __init__(self):
        self.thresholds = {
            "threat": ThresholdOptimizer(0.6, learning_rate=0.02),  # Conservative for safety
            "opportunity": ThresholdOptimizer(0.5, learning_rate=0.01),
            "humor": ThresholdOptimizer(0.4, learning_rate=0.01),
            "goal_relevance": ThresholdOptimizer(0.5, learning_rate=0.01),
            "social": ThresholdOptimizer(0.4, learning_rate=0.01),
            "overall": ThresholdOptimizer(0.5, learning_rate=0.01),  # Combined threshold
        }
    
    def record_outcome(
        self,
        salience_scores: Dict[str, float],
        did_respond: bool,
        feedback: float  # -1 (bad) to 1 (good)
    ):
        """
        Record outcome and update thresholds.
        
        feedback > 0 and did_respond: Good decision to respond
        feedback > 0 and not did_respond: Missed opportunity (should have responded)
        feedback < 0 and did_respond: Shouldn't have responded
        feedback < 0 and not did_respond: Good decision to stay silent
        """
        should_have_responded = feedback > 0
        
        for dimension, score in salience_scores.items():
            if dimension in self.thresholds:
                self.thresholds[dimension].update(
                    score=score,
                    should_have_acted=should_have_responded,
                    did_act=did_respond
                )
```

---

## 8. Loss Function

### 8.1 Composite Loss

```python
def compute_interaction_loss(interaction: Interaction) -> float:
    """
    Compute total loss for an interaction.
    Lower is better. Used for optimization tracking.
    """
    
    # Timing loss: Did we respond at the right time?
    timing_loss = 0.0
    if interaction.responded and interaction.user_ignored:
        timing_loss = 1.0  # Spoke when shouldn't have
    elif not interaction.responded and interaction.user_wanted_response:
        timing_loss = 0.7  # Silent when shouldn't have been (less bad)
    
    # Relevance loss: Was response relevant?
    relevance_loss = 1.0 - interaction.relevance_score  # 0-1
    
    # Tone loss: Did tone match user preference?
    tone_loss = abs(interaction.response_tone - interaction.preferred_tone)
    
    # Verbosity loss: Was length appropriate?
    if interaction.preferred_length > 0:
        verbosity_loss = abs(
            interaction.response_length - interaction.preferred_length
        ) / interaction.preferred_length
        verbosity_loss = min(1.0, verbosity_loss)  # Cap at 1
    else:
        verbosity_loss = 0.0
    
    # Weighted combination
    total_loss = (
        0.35 * timing_loss +
        0.30 * relevance_loss +
        0.20 * tone_loss +
        0.15 * verbosity_loss
    )
    
    return total_loss


def compute_session_loss(interactions: List[Interaction]) -> float:
    """Aggregate loss over a session."""
    if not interactions:
        return 0.0
    
    losses = [compute_interaction_loss(i) for i in interactions]
    
    # Weight recent interactions more heavily
    weights = [1.0 + 0.1 * i for i in range(len(losses))]
    weighted_sum = sum(l * w for l, w in zip(losses, weights))
    
    return weighted_sum / sum(weights)
```

### 8.2 Loss Tracking

```python
# Metrics for observability (ADR-0006)
gladys_learning_interaction_loss{type}  # timing, relevance, tone, verbosity, total
gladys_learning_session_loss
gladys_learning_loss_trend  # Rolling average
```

---

## 9. Cold Start and Priors

### 9.1 Personality-Based Priors

When a user selects a personality, initialize parameters with matching priors:

```python
PERSONALITY_PRIORS = {
    "murderbot": {
        "sarcasm_tolerance": AdaptivePrior(value=0.8, confidence=0.3),
        "verbosity_preference": AdaptivePrior(value=0.3, confidence=0.3),
        "humor_appreciation": AdaptivePrior(value=0.7, confidence=0.3),
        "formality_preference": AdaptivePrior(value=0.3, confidence=0.2),
        "proactivity_tolerance": AdaptivePrior(value=0.3, confidence=0.3),
        "enthusiasm_tolerance": AdaptivePrior(value=0.2, confidence=0.3),
    },
    "helpful_assistant": {
        "sarcasm_tolerance": AdaptivePrior(value=0.4, confidence=0.3),
        "verbosity_preference": AdaptivePrior(value=0.5, confidence=0.2),
        "humor_appreciation": AdaptivePrior(value=0.5, confidence=0.2),
        "formality_preference": AdaptivePrior(value=0.6, confidence=0.2),
        "proactivity_tolerance": AdaptivePrior(value=0.7, confidence=0.3),
        "enthusiasm_tolerance": AdaptivePrior(value=0.7, confidence=0.3),
    },
    "neutral": {
        # All parameters start at 0.5 with low confidence
    }
}

@dataclass
class AdaptivePrior:
    value: float        # Starting value
    confidence: float   # Starting confidence (affects Bayesian alpha/beta)
```

### 9.2 Initialization

```python
class UserProfile:
    """User's adaptive parameters."""
    
    def __init__(self, personality_id: str = "neutral"):
        self.personality_id = personality_id
        self.parameters: Dict[str, AdaptiveParameter] = {}
        self._initialize_from_personality(personality_id)
    
    def _initialize_from_personality(self, personality_id: str):
        """Set priors based on selected personality."""
        priors = PERSONALITY_PRIORS.get(personality_id, PERSONALITY_PRIORS["neutral"])
        config = load_adaptation_config()
        
        for param_name, param_config in config["parameters"].items():
            prior = priors.get(param_name, AdaptivePrior(0.5, 0.1))
            
            # Convert confidence to Bayesian prior strength
            prior_strength = 1.0 + prior.confidence * 4  # 1-5 range
            
            self.parameters[param_name] = AdaptiveParameter(
                name=param_name,
                initial_value=prior.value,
                alpha=param_config["alpha"],
                beta=param_config["beta"],
                prior_strength=prior_strength
            )
```

---

## 10. Safety Bounds

### 10.1 Parameter Bounds

```python
@dataclass
class ParameterBound:
    min: float
    max: float
    warning_min: Optional[float] = None
    warning_max: Optional[float] = None
    description: str = ""

PARAMETER_BOUNDS = {
    # Communication style
    "sarcasm_tolerance": ParameterBound(
        min=0.0, max=0.95,
        warning_max=0.9,
        description="Maximum sarcasm level before it becomes grating"
    ),
    "verbosity_preference": ParameterBound(
        min=0.1, max=0.95,
        description="Always some response, never walls of text"
    ),
    "humor_appreciation": ParameterBound(
        min=0.0, max=0.9,
        description="Can be serious, but not 100% comedy"
    ),
    "formality_preference": ParameterBound(
        min=0.05, max=0.95,
        description="Full range is reasonable"
    ),
    
    # Behavior
    "proactivity_tolerance": ParameterBound(
        min=0.05, max=0.90,
        warning_min=0.1,
        warning_max=0.85,
        description="Never fully silent, never constantly talking"
    ),
    "helpfulness": ParameterBound(
        min=0.3, max=1.0,
        description="Core function, shouldn't go too low"
    ),
    "enthusiasm_tolerance": ParameterBound(
        min=0.05, max=0.95,
        description="Full range is reasonable"
    ),
    
    # System thresholds
    "salience_threshold_overall": ParameterBound(
        min=0.1, max=0.9,
        description="Never respond to everything, never ignore all"
    ),
    "response_delay_ms": ParameterBound(
        min=100, max=3000,
        description="Never instant (uncanny), never too slow"
    ),
}
```

### 10.2 Bounds Configuration

```yaml
# config/parameter_bounds.yaml
bounds:
  sarcasm_tolerance:
    min: 0.0
    max: 0.95
    warning_max: 0.9
  
  verbosity_preference:
    min: 0.1
    max: 0.95
  
  proactivity_tolerance:
    min: 0.05
    max: 0.90
    warning_min: 0.1
    warning_max: 0.85
  
  # ... etc

# User can override in user_bounds.yaml
user_overrides:
  sarcasm_tolerance:
    max: 1.0
    acknowledged_warning: true
```

### 10.3 Bounds Enforcement

```python
class BoundsEnforcer:
    """Enforce and warn about parameter bounds."""
    
    def __init__(self):
        self.bounds = self._load_bounds()
        self.user_overrides = self._load_user_overrides()
    
    def apply(self, param_name: str, value: float) -> Tuple[float, Optional[str]]:
        """
        Apply bounds to value.
        
        Returns:
            (clamped_value, warning_message or None)
        """
        bound = self._get_effective_bound(param_name)
        warning = None
        
        # Check warnings first
        if bound.warning_min and value < bound.warning_min:
            warning = f"{param_name} is very low ({value:.2f}). This may reduce functionality."
        elif bound.warning_max and value > bound.warning_max:
            warning = f"{param_name} is very high ({value:.2f}). This may affect experience quality."
        
        # Clamp to hard bounds
        clamped = max(bound.min, min(bound.max, value))
        
        return clamped, warning
    
    def _get_effective_bound(self, param_name: str) -> ParameterBound:
        """Get bound with user overrides applied."""
        base = self.bounds.get(param_name, ParameterBound(0.0, 1.0))
        override = self.user_overrides.get(param_name, {})
        
        return ParameterBound(
            min=override.get("min", base.min),
            max=override.get("max", base.max),
            warning_min=override.get("warning_min", base.warning_min),
            warning_max=override.get("warning_max", base.warning_max),
        )
```

---

## 11. User Controls

### 11.1 Available Controls

| Control | Command | Phase |
|---------|---------|-------|
| **View Summary** | "What have you learned about me?" | 1 |
| **View Full** | `gladys profile view` | 1 |
| **Reset All** | "Forget everything you've learned" / `gladys profile reset` | 1 |
| **Reset Category** | `gladys profile reset --category communication` | 1 |
| **Reset Parameter** | `gladys profile reset --param sarcasm_tolerance` | 1 |
| **Freeze** | "Stop learning" / `gladys profile freeze` | 1 |
| **Unfreeze** | "Resume learning" / `gladys profile unfreeze` | 1 |
| **Export** | `gladys profile export > profile.json` | 2 |
| **Import** | `gladys profile import profile.json` | 2 |
| **Edit** | `gladys profile set sarcasm_tolerance 0.8` | 2 |

### 11.2 Voice/Text Commands

```python
PROFILE_COMMANDS = {
    # View
    r"what (have you|did you) learn(ed)? about me": "view_summary",
    r"what do you (know|think) about me": "view_summary",
    r"show (me )?my profile": "view_summary",
    
    # Reset
    r"forget (everything|all) (you('ve)? )?learn(ed)?": "reset_all",
    r"reset (your )?learning": "reset_all",
    r"start (fresh|over)": "reset_all",
    
    # Freeze
    r"stop learning( about me)?": "freeze",
    r"don't learn (anything )?more": "freeze",
    r"freeze (your )?learning": "freeze",
    
    # Unfreeze
    r"(start|resume|continue) learning": "unfreeze",
    r"unfreeze": "unfreeze",
    
    # Transparency
    r"why did you (say|do|respond) (that|like that)": "explain_last",
    r"why (didn't|did not) you": "explain_last",
}
```

### 11.3 View Summary Response

```python
def generate_profile_summary(profile: UserProfile) -> str:
    """Generate natural language summary of learned profile."""
    
    high_confidence = []
    medium_confidence = []
    low_confidence = []
    
    for name, param in profile.parameters.items():
        readable_name = PARAM_DISPLAY_NAMES.get(name, name)
        
        if param.confidence > 0.7:
            high_confidence.append((readable_name, param.value, param.confidence))
        elif param.confidence > 0.4:
            medium_confidence.append((readable_name, param.value, param.confidence))
        else:
            low_confidence.append((readable_name, param.value, param.confidence))
    
    parts = []
    
    if high_confidence:
        parts.append("I'm quite confident that:")
        for name, value, conf in high_confidence[:3]:
            parts.append(f"  • {describe_preference(name, value)}")
    
    if medium_confidence:
        parts.append("\nI think:")
        for name, value, conf in medium_confidence[:3]:
            parts.append(f"  • {describe_preference(name, value)}")
    
    if low_confidence:
        parts.append(f"\nI'm still learning about: {', '.join(n for n,_,_ in low_confidence[:3])}")
    
    return "\n".join(parts)


def describe_preference(name: str, value: float) -> str:
    """Convert parameter to natural language."""
    DESCRIPTIONS = {
        "sarcasm_tolerance": {
            "high": "You appreciate a good dose of sarcasm",
            "medium": "You enjoy occasional sarcasm",
            "low": "You prefer things straight, minimal sarcasm"
        },
        "verbosity_preference": {
            "high": "You like detailed explanations",
            "medium": "You prefer balanced responses",
            "low": "You like things brief and to the point"
        },
        # ... etc
    }
    
    level = "high" if value > 0.65 else "low" if value < 0.35 else "medium"
    return DESCRIPTIONS.get(name, {}).get(level, f"{name}: {value:.0%}")
```

### 11.4 Transparency Responses

```python
def explain_decision(decision: Decision, profile: UserProfile) -> str:
    """Explain why a decision was made (on-demand)."""
    
    factors = []
    
    # Timing explanation
    if decision.salience_score:
        factors.append(f"The event had {decision.salience_score:.0%} salience")
        threshold = profile.get_threshold("overall")
        factors.append(f"Your response threshold is {threshold:.0%}")
    
    # Tone explanation
    if decision.response_tone:
        sarcasm = profile.get("sarcasm_tolerance")
        factors.append(
            f"I used {'more' if decision.response_tone > 0.5 else 'less'} sarcasm "
            f"because you seem to {'enjoy' if sarcasm.value > 0.5 else 'prefer less of'} it"
        )
    
    # Length explanation
    if decision.response_length:
        verbosity = profile.get("verbosity_preference")
        factors.append(
            f"I kept it {'detailed' if verbosity.value > 0.5 else 'brief'} "
            f"based on your usual preference"
        )
    
    return " ".join(factors) + "."
```

---

## 12. Learning Health Metrics

Integration with observability (ADR-0006):

```python
# Prometheus metrics for learning system

# Parameter tracking
gladys_learning_parameter_value{parameter, category}
gladys_learning_parameter_confidence{parameter, category}
gladys_learning_parameter_short_term{parameter}
gladys_learning_parameter_long_term{parameter}

# Update tracking
gladys_learning_updates_total{parameter, direction}  # up, down, none
gladys_learning_update_magnitude{parameter}  # Histogram

# Feedback tracking
gladys_learning_feedback_total{type, sentiment}  # explicit/implicit, positive/negative
gladys_learning_feedback_weight{type}

# Convergence tracking
gladys_learning_parameters_converged_total  # Count with confidence > 0.7
gladys_learning_parameters_stable_total     # Count with low recent variance

# Loss tracking
gladys_learning_interaction_loss{type}  # timing, relevance, tone, verbosity
gladys_learning_session_loss
gladys_learning_loss_7day_avg

# Health indicators
gladys_learning_frozen  # 0 or 1
gladys_learning_observation_count_total
```

---

## 13. Automated Tests

### 13.1 Test Categories

| Test Type | Purpose |
|-----------|---------|
| **Convergence** | Parameters converge with consistent feedback |
| **Stability** | Random noise doesn't cause oscillation |
| **Bounds** | Parameters stay within limits |
| **Reset** | Reset clears values correctly |
| **Cold Start** | Persona priors applied correctly |
| **Confidence** | Confidence increases with observations |
| **Threshold** | Thresholds tune correctly from feedback |

### 13.2 Example Tests

```python
import pytest
from gladys.learning import AdaptiveParameter, UserProfile, ThresholdOptimizer

class TestConvergence:
    """Test that parameters converge with consistent feedback."""
    
    def test_positive_feedback_increases_value(self):
        param = AdaptiveParameter("test_param", initial_value=0.5)
        initial = param.value
        
        # Apply 20 positive observations
        for _ in range(20):
            param.observe(0.9)
        
        assert param.value > initial
        assert param.value > 0.7
    
    def test_negative_feedback_decreases_value(self):
        param = AdaptiveParameter("test_param", initial_value=0.5)
        initial = param.value
        
        # Apply 20 negative observations
        for _ in range(20):
            param.observe(0.1)
        
        assert param.value < initial
        assert param.value < 0.3
    
    def test_confidence_increases_with_observations(self):
        param = AdaptiveParameter("test_param", initial_value=0.5)
        initial_confidence = param.confidence
        
        # Apply consistent observations
        for _ in range(30):
            param.observe(0.7)
        
        assert param.confidence > initial_confidence
        assert param.confidence > 0.5


class TestStability:
    """Test that noise doesn't cause oscillation."""
    
    def test_random_noise_no_oscillation(self):
        param = AdaptiveParameter("test_param", initial_value=0.5)
        
        # Apply random noise around 0.5
        import random
        values = []
        for _ in range(100):
            param.observe(0.5 + random.uniform(-0.2, 0.2))
            values.append(param.value)
        
        # Should stay near 0.5, not oscillate wildly
        assert all(0.3 < v < 0.7 for v in values)
        
        # Variance of output should be less than variance of input
        input_variance = 0.04  # Expected variance of uniform(-0.2, 0.2)
        output_variance = sum((v - 0.5)**2 for v in values) / len(values)
        assert output_variance < input_variance


class TestBounds:
    """Test parameter bounds enforcement."""
    
    def test_value_clamped_to_max(self):
        param = AdaptiveParameter("sarcasm_tolerance", initial_value=0.9)
        
        # Try to push above max
        for _ in range(50):
            param.observe(1.0)
        
        # Should not exceed bound (0.95)
        assert param.value <= 0.95
    
    def test_value_clamped_to_min(self):
        param = AdaptiveParameter("proactivity_tolerance", initial_value=0.1)
        
        # Try to push below min
        for _ in range(50):
            param.observe(0.0)
        
        # Should not go below bound (0.05)
        assert param.value >= 0.05


class TestReset:
    """Test reset functionality."""
    
    def test_full_reset(self):
        profile = UserProfile("murderbot")
        
        # Apply some learning
        profile.parameters["sarcasm_tolerance"].observe(0.5)
        profile.parameters["sarcasm_tolerance"].observe(0.5)
        
        # Reset
        profile.reset()
        
        # Should be back to persona priors
        sarcasm = profile.parameters["sarcasm_tolerance"]
        assert abs(sarcasm.value - 0.8) < 0.1  # Murderbot prior
        assert sarcasm.confidence < 0.4
    
    def test_category_reset(self):
        profile = UserProfile("neutral")
        
        # Learn some things
        profile.parameters["sarcasm_tolerance"].observe(0.9)
        profile.parameters["skill_minecraft_combat"].observe(0.9)
        
        # Reset only communication category
        profile.reset(category="communication")
        
        # Communication should reset
        assert profile.parameters["sarcasm_tolerance"].value == 0.5
        
        # Skill should be unchanged
        assert profile.parameters["skill_minecraft_combat"].value > 0.6


class TestColdStart:
    """Test persona-based cold start."""
    
    def test_murderbot_priors(self):
        profile = UserProfile("murderbot")
        
        # Should have high sarcasm tolerance
        assert profile.parameters["sarcasm_tolerance"].value > 0.7
        
        # Should have low proactivity tolerance
        assert profile.parameters["proactivity_tolerance"].value < 0.4
    
    def test_helpful_assistant_priors(self):
        profile = UserProfile("helpful_assistant")
        
        # Should have lower sarcasm tolerance
        assert profile.parameters["sarcasm_tolerance"].value < 0.5
        
        # Should have higher proactivity tolerance
        assert profile.parameters["proactivity_tolerance"].value > 0.6
    
    def test_neutral_priors(self):
        profile = UserProfile("neutral")
        
        # All should be near 0.5
        for param in profile.parameters.values():
            assert 0.4 < param.value < 0.6


class TestThresholdTuning:
    """Test threshold optimization."""
    
    def test_false_positives_raise_threshold(self):
        optimizer = ThresholdOptimizer(initial_threshold=0.5)
        initial = optimizer.threshold
        
        # Record false positives (acted when shouldn't have)
        for _ in range(10):
            optimizer.update(score=0.6, should_have_acted=False, did_act=True)
        
        # Threshold should increase
        assert optimizer.threshold > initial
    
    def test_false_negatives_lower_threshold(self):
        optimizer = ThresholdOptimizer(initial_threshold=0.5)
        initial = optimizer.threshold
        
        # Record false negatives (didn't act when should have)
        for _ in range(10):
            optimizer.update(score=0.4, should_have_acted=True, did_act=False)
        
        # Threshold should decrease
        assert optimizer.threshold < initial
```

---

## 14. Implementation Phases

### 14.1 Phase 1 (Implement Now)

| Component | Priority | Effort |
|-----------|----------|--------|
| EWMA core algorithm | High | Low |
| Bayesian confidence tracking | High | Low |
| Parameter bounds | High | Low |
| Cold start priors | High | Low |
| Explicit feedback collection | High | Medium |
| Gradient descent for thresholds | Medium | Low |
| Loss function tracking | Medium | Low |
| View/Reset controls | High | Medium |
| Freeze/Unfreeze | Medium | Low |
| Basic automated tests | High | Medium |
| Learning health metrics | Medium | Low |

### 14.2 Phase 2 (Later)

| Component | Priority | Effort |
|-----------|----------|--------|
| Implicit feedback (engagement) | High | Medium |
| Implicit feedback (corrections) | Medium | Medium |
| Informed search (A*) for memory | Medium | Medium |
| PID control for proactivity | Medium | Medium |
| Novelty/entropy for habituation | Medium | Medium |
| Export/Import | Low | Low |
| Edit controls | Low | Medium |
| Advanced transparency | Low | Medium |

### 14.3 Phase 3 (Future)

| Component | Priority | Effort |
|-----------|----------|--------|
| Multi-armed bandit | Medium | High |
| Policy gradient (RL) | Low | High |
| Transfer learning | Low | High |
| A/B testing framework | Low | High |

---

## 15. Consequences

### 15.1 Positive

1. System personalizes to each user over time
2. Clear mathematical foundation for adaptation
3. User maintains control and transparency
4. Safety bounds prevent extreme behavior
5. Metrics enable monitoring and debugging
6. Automated tests catch regressions

### 15.2 Negative

1. Added complexity in reasoning about behavior
2. More parameters to tune and maintain
3. Cold start still provides suboptimal initial experience
4. Users may not understand why system behaves as it does

### 15.3 Risks

1. Learning could converge to wrong values from biased feedback
2. Users may game the system (unlikely but possible)
3. Implicit feedback interpretation may be wrong

---

## 16. Related Decisions

- ADR-0001: GLADyS Architecture
- ADR-0004: Memory Schema Details (user_profile table)
- ADR-0005: gRPC Service Contracts (feedback signals)
- ADR-0006: Observability & Monitoring (learning metrics)

---

## 17. Appendix: Algorithm Reference

### EWMA Update

```
short_term(t) = α × observation + (1 - α) × short_term(t-1)

If stable:
  long_term(t) = β × short_term + (1 - β) × long_term(t-1)
```

### Bayesian Beta Update

```
posterior_α = prior_α + positive_observations
posterior_β = prior_β + negative_observations

mean = α / (α + β)
variance = αβ / ((α + β)² × (α + β + 1))
```

### Gradient Descent

```
threshold(t+1) = threshold(t) - learning_rate × gradient

gradient = +1 if false positive (raise threshold)
gradient = -1 if false negative (lower threshold)
gradient =  0 if correct
```

### Composite Loss

```
loss = 0.35 × timing_loss
     + 0.30 × relevance_loss
     + 0.20 × tone_loss
     + 0.15 × verbosity_loss
```
