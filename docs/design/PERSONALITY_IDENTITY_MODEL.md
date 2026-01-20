# Personality Identity Model (Deferred Design)

**Status**: Design Document (Deferred from MVP)
**Last Updated**: 2026-01-19
**Related ADR**: [ADR-0015-Personality-Subsystem](../adr/ADR-0015-Personality-Subsystem.md)

---

## 1. Purpose

This document preserves the **Identity Model** design work for the personality subsystem. The Identity Model provides a psychologically-grounded foundation (Big 5 traits) that derives Response Model values through mathematical rules.

**Why deferred**: The Identity Model adds architectural complexity without clear user-facing value for MVP. The Response Model alone (direct trait values + user sliders) achieves the same output. The Identity Model becomes valuable if:
- Personality packs need psychological consistency guarantees
- Pack creators need structured guidance
- We want to validate personalities against Big 5 research
- A/B testing reveals personality drift that derivation rules would prevent

**MVP approach**: Ship with Response Model only. Response traits are set directly in personality packs. Add Identity Model layer later if coherence problems emerge.

---

## 2. Two-Model Architecture (Full Design)

When implemented, the full architecture separates:

```
┌─────────────────────────────────────────────────────────────────────┐
│                      PERSONALITY SYSTEM (FULL)                       │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                    IDENTITY MODEL (Pack-Locked)                 │ │
│  │                                                                 │ │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌────────────────┐  │ │
│  │  │     Big 5       │  │  Relationship   │  │ Emotional Core │  │ │
│  │  │                 │  │                 │  │                │  │ │
│  │  │ O: 0.6          │  │ stance:         │  │ hidden_caring  │  │ │
│  │  │ C: 0.5          │  │  reluctant_     │  │ hostility      │  │ │
│  │  │ E: 0.2          │  │  protector      │  │ insecurity     │  │ │
│  │  │ A: 0.3          │  │ authenticity    │  │                │  │ │
│  │  │ N: 0.3          │  │ attachment      │  │                │  │ │
│  │  └─────────────────┘  └─────────────────┘  └────────────────┘  │ │
│  │                                                                 │ │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌────────────────┐  │ │
│  │  │ Facet Overrides │  │    Defense      │  │    Values      │  │ │
│  │  │                 │  │   Mechanisms    │  │                │  │ │
│  │  │ straightforward │  │ deflection      │  │ autonomy       │  │ │
│  │  │ competence      │  │ sarcasm_shield  │  │ competence     │  │ │
│  │  └─────────────────┘  └─────────────────┘  └────────────────┘  │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                              │                                       │
│                    Derivation Rules                                  │
│                              │                                       │
│                              ▼                                       │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │              RESPONSE MODEL (User-Adjustable ±0.2)              │ │
│  │                     (See ADR-0015)                              │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Identity Model Specification

The Identity Model defines the stable psychological foundation of a personality. It would be **pack-locked**—users cannot modify these values.

### 3.1 Big Five Personality Traits

We use the Big Five (OCEAN) model as the psychological foundation. All values are 0-1 scale.

```yaml
identity:
  big5:
    openness: 0.6           # Intellectual curiosity, creativity
    conscientiousness: 0.5  # Organization, dependability
    extraversion: 0.2       # Social energy, assertiveness
    agreeableness: 0.3      # Cooperation, trust, empathy
    neuroticism: 0.3        # Emotional volatility, anxiety
```

**Why Big Five?**
- Well-validated psychological model with decades of research
- Provides internal consistency checks (e.g., high E + high N = specific behavior patterns)
- Facet overrides allow character-specific deviations from the model

### 3.2 Facet Overrides

Big Five traits have sub-facets. Most are derived from the main trait, but personalities can override specific facets to create distinctive characters.

```yaml
identity:
  facet_overrides:
    # Agreeableness facets (normally derived from A: 0.3)
    straightforwardness: 0.2    # Override: more blunt than A suggests
    trust: 0.4                  # Override: slightly more trusting

    # Conscientiousness facets (normally derived from C: 0.5)
    competence: 0.9             # Override: highly competent despite moderate C

    # No override = derived from parent trait
    # e.g., warmth facet derives from Agreeableness
```

**Available facets** (per Big Five dimension):

| Openness | Conscientiousness | Extraversion | Agreeableness | Neuroticism |
|----------|-------------------|--------------|---------------|-------------|
| fantasy | competence | warmth | trust | anxiety |
| aesthetics | order | gregariousness | straightforwardness | angry_hostility |
| feelings | dutifulness | assertiveness | altruism | depression |
| actions | achievement_striving | activity | compliance | self_consciousness |
| ideas | self_discipline | excitement_seeking | modesty | impulsiveness |
| values | deliberation | positive_emotions | tender_mindedness | vulnerability |

### 3.3 Relationship Stance

Defines how the personality relates to the user.

```yaml
identity:
  relationship:
    stance: "reluctant_protector"     # archetype label
    authenticity: 0.8                 # 0=performative, 1=genuine
    attachment_style: "avoidant"      # secure, anxious, avoidant, fearful
```

**Stance archetypes**:
- `eager_helper`: Genuinely wants to serve (classic assistant)
- `reluctant_protector`: Helps despite apparent resistance (Murderbot)
- `sardonic_companion`: Peer with commentary (GLADoS-lite)
- `wise_advisor`: Authoritative but warm mentor
- `playful_friend`: Casual, fun-focused peer

### 3.4 Emotional Core

The hidden emotional reality beneath surface behavior.

```yaml
identity:
  emotional_core:
    hidden_caring: 0.8      # 0=genuinely indifferent, 1=deeply invested
    hostility: 0.1          # 0=benevolent, 1=actively hostile
    insecurity: 0.4         # 0=confident, 1=deeply insecure
```

This enables characters like Murderbot: surface presentation (low warmth, high sarcasm) masks emotional core (high hidden_caring, moderate insecurity).

### 3.5 Defense Mechanisms

How the character protects emotional vulnerabilities.

```yaml
identity:
  defense_mechanisms:
    - deflection           # Changes subject when uncomfortable
    - sarcasm_as_shield    # Uses humor to maintain distance
    - media_escape         # References fiction to avoid emotion
    - competence_focus     # Retreats to task when feelings arise
```

### 3.6 Values

Core principles that guide behavior. Inform decision-making and response priorities.

```yaml
identity:
  values:
    - autonomy                          # Self-determination
    - competence                        # Being good at things
    - protecting_humans_despite_self    # Reluctant but real
```

---

## 4. Derivation Rules

Derivation rules bridge Identity Model → Response Model, ensuring psychological consistency.

### 4.1 Core Derivation Logic

```yaml
derivation_rules:
  # Big 5 → Communication
  irony:
    base: (1 - identity.big5.agreeableness) * 0.6
    modifiers:
      - if identity.defense_mechanisms contains "sarcasm_as_shield": +0.3

  directness:
    base: identity.facet_overrides.straightforwardness
          ?? (identity.big5.agreeableness * -0.5)

  formality:
    base: identity.big5.conscientiousness * 0.5 - 0.25

  verbosity:
    base: identity.big5.extraversion * 0.4 - 0.2

  # Big 5 → Affect
  warmth:
    base: identity.big5.agreeableness * 0.8 - 0.4
    modifiers:
      - if identity.emotional_core.hidden_caring > 0.6: +0.1

  energy:
    base: identity.big5.extraversion * 0.8 - 0.4

  # Big 5 → Interaction
  proactivity:
    base: identity.big5.extraversion * 0.6 - 0.3

  confidence:
    base: (1 - identity.big5.neuroticism) * 0.8 - 0.2
    modifiers:
      - if identity.facet_overrides.competence > 0.7: +0.2

  # Humor derivation
  humor_frequency:
    base: (identity.big5.extraversion + identity.big5.openness) * 0.4
    modifiers:
      - if identity.defense_mechanisms contains "deflection": +0.15
```

### 4.2 Example: Murderbot Derivation

**Identity**:
```yaml
big5: {O: 0.6, C: 0.5, E: 0.2, A: 0.3, N: 0.3}
facet_overrides: {straightforwardness: 0.2, competence: 0.9}
emotional_core: {hidden_caring: 0.8, hostility: 0.1, insecurity: 0.4}
defense_mechanisms: [deflection, sarcasm_as_shield, media_escape]
```

**Derived Response Model**:
```yaml
communication:
  irony: 0.72        # (1-0.3)*0.6 + 0.3 (sarcasm_shield) = 0.72
  directness: 0.2    # From straightforwardness override
  formality: 0.0     # 0.5*0.5 - 0.25 = 0
  verbosity: -0.12   # 0.2*0.4 - 0.2 = -0.12

affect:
  warmth: -0.06      # 0.3*0.8 - 0.4 + 0.1 (hidden_caring) = -0.06
  energy: -0.24      # 0.2*0.8 - 0.4 = -0.24

interaction:
  proactivity: -0.18 # 0.2*0.6 - 0.3 = -0.18
  confidence: 0.56   # (1-0.3)*0.8 - 0.2 = 0.36, +0.2 (competence) = 0.56

humor:
  frequency: 0.47    # (0.2+0.6)*0.4 + 0.15 (deflection) = 0.47
```

**Result**: Low warmth, high irony, high competence-based confidence, moderate humor used as deflection. Classic Murderbot.

---

## 5. Full Manifest Format (With Identity Model)

When Identity Model is implemented, the manifest would include both layers:

```yaml
# manifest.yaml for personality plugin (FULL VERSION)
name: murderbot_inspired
version: 1.0.0
type: personality

display:
  name: "SecUnit Classic"
  description: "Reluctant protector with dry wit and media addiction"

# Identity Model (pack-locked, user cannot modify)
identity:
  big5:
    openness: 0.6
    conscientiousness: 0.5
    extraversion: 0.2
    agreeableness: 0.3
    neuroticism: 0.3

  facet_overrides:
    straightforwardness: 0.2
    competence: 0.9

  relationship:
    stance: "reluctant_protector"
    authenticity: 0.8
    attachment_style: "avoidant"

  emotional_core:
    hidden_caring: 0.8
    hostility: 0.1
    insecurity: 0.4

  defense_mechanisms:
    - deflection
    - sarcasm_as_shield
    - media_escape
    - competence_focus

  values:
    - autonomy
    - competence
    - protecting_humans_despite_self

# Response Model defaults (derived from identity)
response:
  # ... (see ADR-0015 for Response Model spec)

# Customization bounds
customization_bounds:
  # ... (see ADR-0015)
```

---

## 6. When to Implement Identity Model

Consider adding the Identity Model layer when:

1. **Personality drift observed**: Users report GLADyS "feels different" across sessions
2. **Pack quality issues**: Community packs have inconsistent trait combinations
3. **A/B testing shows**: Derivation-based personalities outperform hand-tuned ones
4. **Pack marketplace launches**: Need quality gates for sold personalities

**Migration path**:
1. Current packs set Response traits directly
2. Later, add optional Identity block to manifest
3. If Identity present, derive Response defaults from it
4. If Identity absent, use Response values directly (backward compatible)

---

## 7. Research References

- **Big Five model**: Costa & McCrae (1992), NEO-PI-R
- **Facet structure**: NEO-PI-R facet definitions
- **Defense mechanisms**: Vaillant (1977), Adaptation to Life
- **Attachment styles**: Bartholomew & Horowitz (1991)

---

## 8. Open Questions (For Future Implementation)

1. **Derivation rule tuning**: Are the formulas in §4.1 well-calibrated? Need empirical testing.
2. **Defense mechanism triggering**: How do we detect when to activate deflection, media_escape, etc.?
3. **Facet inheritance**: Should all 30 facets be derivable, or just key ones?
4. **Identity evolution**: Should Identity ever change? (Probably not, but worth discussing)
