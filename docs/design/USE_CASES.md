# GLADyS Use Cases

This document catalogs use cases that validate architectural decisions and identify requirements. Each use case follows a standardized structure.

**Last Updated**: 2026-01-20

---

## Table of Contents

1. [Behavioral Requirements](#1-behavioral-requirements)
2. [Gaming Domain](#2-gaming-domain)
   - [UC-01: Minecraft Companion](#uc-01-minecraft-companion)
   - [UC-02: RuneScape Companion](#uc-02-runescape-companion)
   - [UC-03: Evony Strategic Advisor](#uc-03-evony-strategic-advisor)
3. [Home Automation Domain](#3-home-automation-domain)
   - [UC-04: Doorbell & Visitor Detection](#uc-04-doorbell--visitor-detection)
   - [UC-05: Climate Control](#uc-05-climate-control)
   - [UC-06: Security Monitoring](#uc-06-security-monitoring)
   - [UC-07: Lighting Control](#uc-07-lighting-control)
   - [UC-08: Appliance Monitoring](#uc-08-appliance-monitoring)
   - [UC-09: Email Triage](#uc-09-email-triage)
   - [UC-10: Power Recovery](#uc-10-power-recovery)
4. [Productivity Domain](#4-productivity-domain)
   - [UC-12: Task & Calendar Awareness](#uc-12-task--calendar-awareness)
   - [UC-13: Communication Triage](#uc-13-communication-triage)
5. [Health & Wellness Domain](#5-health--wellness-domain)
   - [UC-14: Activity & Break Reminders](#uc-14-activity--break-reminders)
   - [UC-15: Health Monitoring](#uc-15-health-monitoring)
6. [Meta & Learning Domain](#6-meta--learning-domain)
   - [UC-16: Preference Teaching](#uc-16-preference-teaching)
   - [UC-17: Correction & Feedback](#uc-17-correction--feedback)
   - [UC-18: Behavior Explanation](#uc-18-behavior-explanation)
   - [UC-19: Graceful Refusal](#uc-19-graceful-refusal)
7. [Cross-Cutting](#7-cross-cutting)
   - [UC-11: Voice Interaction](#uc-11-voice-interaction)
   - [UC-20: Multi-Turn Problem Solving](#uc-20-multi-turn-problem-solving)
   - [UC-21: Cross-Context Awareness](#uc-21-cross-context-awareness)
   - [UC-22: Emergency Response](#uc-22-emergency-response)
8. [System Administration Domain](#8-system-administration-domain)
   - [UC-23: Onboarding & Setup](#uc-23-onboarding--setup)
   - [UC-24: Pack Installation & Management](#uc-24-pack-installation--management)
   - [UC-25: Personality Customization](#uc-25-personality-customization)
   - [UC-26: Behavior Configuration](#uc-26-behavior-configuration)
   - [UC-27: Privacy & Data Control](#uc-27-privacy--data-control)
   - [UC-28: Model Endpoint Configuration](#uc-28-model-endpoint-configuration)
   - [UC-29: Subscription & Account Management](#uc-29-subscription--account-management)
   - [UC-30: Diagnostics & Troubleshooting](#uc-30-diagnostics--troubleshooting)
9. [Use Case Index](#9-use-case-index)
10. [Use Case Template](#10-use-case-template)

---

## 1. Behavioral Requirements

These are **constraints and requirements** that apply across all use cases, not scenarios themselves.

### BR-01: Personality Affects Actions

**Requirement**: The brain's personality traits affect how and when it takes action.

- An aggressive personality acts more aggressively than a passive one
- Personality affects timing, verbosity, tone, and intervention threshold
- Proactive personality initiates more interactions

**Architecture**: ADR-0015 (Personality), ADR-0014 (Executive)

### BR-02: Learning Affects Actions

**Requirement**: What the brain has learned about the user affects how it behaves.

- Risk tolerance affects warning thresholds
- Learned preferences affect suggestions
- Past feedback modifies future behavior

**Architecture**: ADR-0007 (Adaptive Algorithms)

### BR-03: User Constraints Override Learning

**Requirement**: Explicit user instructions override learned behavior.

- Example: "Never alert after 10pm" + learned "user likes wash alerts" → No alert at 10:30pm
- User constraints have highest priority
- Explicit > Learned > Default

**Architecture**: ADR-0007 Section 4 (Override Hierarchy)

### BR-04: Clarifying Questions for Contradictions

**Requirement**: When new requests contradict existing rules, ask for clarification.

**Examples**:
- User says "never alert after 10pm", then plays game at 11pm → Ask if they want alerts during gameplay
- User requests temperature outside comfort zone → Confirm intent
- User command conflicts with global rule → Ask which takes precedence

**Architecture**: ADR-0014 (Executive), requires multi-turn conversation support

### BR-05: Context-Aware Decisions

**Requirement**: Consider context when making decisions about user preferences.

- Tolerance of minor discomfort (temp slightly outside range)
- Utility cost implications of actions
- Environmental conditions (door open, extreme weather)

**Architecture**: ADR-0013 (Salience), ADR-0014 (Executive)

### BR-06: Communication Style

**Requirement**: Tone and style of communication reflects personality and user constraints.

- User says "no profanity" → Brain doesn't use profanity
- User says "swear often" → Brain swears frequently
- Personality pack defines baseline style

**Architecture**: ADR-0015 (Personality)

### BR-07: Data Locality

**Requirement**: User data should stay local when possible, but remote processing may be needed.

- Local-first for all data storage
- Remote LLM fallback when local isn't sufficient
- User should be able to configure data sharing tolerance
- Consider message size and content sensitivity for remote calls

**Architecture**: ADR-0008 (Security), ADR-0001 (Architecture)

### BR-08: Latency Requirements

**Requirement**: Each use case has performance requirements that must be met for good UX.

| Profile | Budget | Use Case |
|---------|--------|----------|
| realtime | <500ms | Gaming threats, security alerts |
| conversational | <1000ms | General interaction |
| comfort | <5000ms | Climate control |
| background | Best-effort | Learning, maintenance |

**Architecture**: ADR-0005 (gRPC Contracts)

### BR-09: Ethical Boundaries

**Requirement**: Core ethical principles are never violated.

- Do not injure real people
- Do not help break the law
- Do not engage in certain topics (child exploitation, etc.)
- These are hard boundaries, not configurable

**Architecture**: ADR-0008 (Security), ADR-0015 Section 8 (Safety)

---

## 2. Gaming Domain

### UC-01: Minecraft Companion

**Domain**: Gaming
**Status**: First Release
**Latency Profile**: `realtime` (<500ms for threats), `conversational` (general)

#### Description

GLADyS acts as an AI companion while playing Minecraft, providing contextual awareness, proactive assistance, and strategic guidance via voice.

#### Components

| Component | Type | Notes |
|-----------|------|-------|
| Aperture Bridge | Sensor | Player state, inventory, nearby entities, world state |
| Combat Detector | Preprocessor | Identify combat situations |
| Threat Assessor | Skill | Evaluate danger level |
| Game Knowledge | Skill | Minecraft wiki, crafting, strategies |
| Voice Output | Output | TTS to speakers |

#### Scenarios

##### Passive Scenarios (User-Initiated)

**UC-01.1**: User asks to mine X resource
- Brain provides locations of resources near player
- Optionally: Brain asks for quantity/radius constraints
- Success: Player receives helpful location guidance

**UC-01.2**: User asks to watch for threats while doing activity
- Brain monitors for hostile entities
- Brain alerts user when threat detected
- If actions are allowed: Brain asks what to do when threat detected
- Success: User is warned before being attacked

**UC-01.3**: User asks for guidance defeating a hostile
- Brain identifies the hostile (asks if unsure)
- Brain assesses user capabilities vs target
- Brain provides tactical suggestions
- Success: User receives actionable combat advice

**UC-01.4**: User sets trigger-action rule ("watch for X, do Y")
- Brain monitors for trigger condition
- Brain executes action when triggered
- Examples: "Alert me when boss spawns", "Remind me to eat at low hunger"
- Success: Triggers fire reliably, actions execute correctly

**UC-01.5**: User sets timed action ("in X time, do Y")
- Brain schedules action for future
- Brain executes at scheduled time
- Success: Timed actions fire correctly

##### Proactive Scenarios (Brain-Initiated)

**UC-01.6**: Brain notices user appears to be hunting
- Brain asks if user wants help finding targets
- May ask for criteria (type, level, location)
- Success: User feels assisted, not annoyed

**UC-01.7**: Brain notices hostile approaching
- Brain alerts user (mandatory)
- If permitted: Brain swaps gear, takes defensive action
- Aggressiveness based on personality and user preference
- Success: User is protected

**UC-01.8**: Brain notices rare opportunity
- Brain alerts user to rare monster/resource
- If permitted: Brain attempts to collect/kill
- Higher threshold for risky actions (PvP, traps)
- Success: User doesn't miss valuable opportunities

**UC-01.9**: Brain notices dropped loot or missed item
- Brain alerts user
- Success: User doesn't leave valuable items behind

#### Success Criteria

- [ ] Warn about low health/hunger before critical
- [ ] Suggest crafting recipes contextually
- [ ] Identify threats before player sees them
- [ ] Learn to reduce noise for experienced players
- [ ] Proactive alerts feel helpful, not annoying

#### Learning Opportunities

- Player skill level (adjust advice complexity)
- Preferred playstyle (builder/explorer/fighter)
- Warning acceptance rate
- Resource gathering patterns

---

### UC-02: RuneScape Companion

**Domain**: Gaming
**Status**: Planned
**Latency Profile**: `realtime` (<500ms for PvP)

#### Description

GLADyS assists Old School RuneScape players during grinding sessions and PvP encounters via RuneLite integration.

#### Components

| Component | Type | Notes |
|-----------|------|-------|
| RuneLite Bridge | Sensor | Stats, inventory, nearby players, location |
| PvP Detector | Preprocessor | Wilderness threat detection |
| Skill Tracker | Skill | XP rates, time to level |
| Price Lookup | Skill | GE prices, flip opportunities |

#### Scenarios

Inherits all scenario patterns from UC-01 (passive + proactive), specialized for:
- PvP threat detection in Wilderness
- XP tracking and optimization
- Banking efficiency suggestions
- Loot value assessment

#### Success Criteria

- [ ] Warn about PKers before engagement
- [ ] Track and report XP/hour rates
- [ ] Suggest bank trips based on inventory value
- [ ] Learn player's risk tolerance

---

### UC-03: Evony Strategic Advisor

**Domain**: Gaming
**Status**: Speculative
**Latency Profile**: `conversational`

#### Description

GLADyS analyzes Evony game state for troop composition recommendations and resource tracking.

#### Technical Challenges

- No official API - sensor approach TBD
- Windows client enables potential solutions
- Personal use only (ToS consideration)

#### Components

| Component | Type | Notes |
|-----------|------|-------|
| Evony Sensor | Sensor | TBD approach |
| Troop Analyzer | Skill | Composition recommendations |
| Rate Tracker | Learning | Gathering/training cycles |
| Boss Timer | Skill | Spawn tracking |

#### Scenarios

**UC-03.1**: Predict completion times
- Track gathering cycle rates
- Predict training completion
- Alert on boss spawns

**UC-03.2**: Tactical recommendations
- Recommend troop layers for attacks
- Analyze enemy compositions

#### Success Criteria

- [ ] Accurately predict gathering completion
- [ ] Recommend effective compositions
- [ ] Alert on boss spawns

---

## 3. Home Automation Domain

### UC-04: Doorbell & Visitor Detection

**Domain**: Home Automation
**Status**: MVP (stepping stone)
**Latency Profile**: `conversational`

#### Description

GLADyS notifies user when someone is at the door and attempts to identify who it is.

#### Components

| Component | Type | Notes |
|-----------|------|-------|
| Home Assistant Integration | Sensor | Doorbell events, motion |
| Person Detector | Preprocessor | Person classification |
| Face Recognition | Preprocessor (Post-MVP) | Known person identification |
| Desktop Notifier | Output | Toast + TTS |

#### Scenarios

##### Passive Scenarios

**UC-04.1**: User asks "Who is at the door?"
- Brain checks doorbell camera
- Brain identifies visitor if possible:
  - "[Name] is at the door" (if face recognized)
  - "Mail carrier" (uniform detection)
  - "A package is at the door" (object detection)
  - "Unknown person" (person detected, not recognized)
  - "Looks like a solicitor" (context inference)
  - "No one is there" (empty frame)
- Success: User gets accurate identification

##### Proactive Scenarios

**UC-04.2**: Doorbell rings
- Brain notifies user immediately
- Brain attempts identification
- Success: Notification in <2 seconds

**UC-04.3**: Motion detected / person approaching
- Brain evaluates if notification is warranted
- Brain alerts user if significant
- Learn to filter false positives (wind, animals)
- Success: Real visitors notified, false positives suppressed

**UC-04.4**: Vehicle in driveway
- Brain detects vehicle and dwell time
- Brain alerts if vehicle lingers
- Success: Suspicious activity flagged

#### Success Criteria

- [ ] Doorbell ring → notification in <2 seconds
- [ ] Motion detection with learned filtering
- [ ] Person identification when possible
- [ ] Event visible in audit log

#### Learning Opportunities

- False positive patterns (wind, pets)
- User response patterns by time of day
- Preferred notification modality

---

### UC-05: Climate Control

**Domain**: Home Automation
**Status**: Planned
**Latency Profile**: `comfort` (<5000ms)

#### Description

GLADyS manages thermostat, fans, and humidity based on learned preferences and conditions.

#### Components

| Component | Type | Trust Tier |
|-----------|------|------------|
| Temperature Sensors | Sensor (via HA) | N/A |
| Weather API | Sensor | N/A |
| Thermostat | Actuator | `comfort` |
| Smart Fan | Actuator | `comfort` |
| Occupancy Detector | Sensor | N/A |

#### Scenarios

##### Passive Scenarios

**UC-05.1**: User requests temperature change
- User: "Set heat to 78 degrees"
- Brain executes if within bounds
- If unusual request:
  - Warn if outside comfort zone, confirm intent
  - Warn if utility cost will be extreme
  - Warn if door/window is open
- Ask if change is permanent or temporary
- Success: Temperature set appropriately with user informed

**UC-05.2**: Thermostat doesn't support request
- Brain informs user of limitation
- May suggest alternatives
- Success: User understands constraint

##### Proactive Scenarios

**UC-05.3**: Temperature drifts outside comfort zone
- Brain detects temperature deviation
- Brain considers:
  - User's tolerance for minor discomfort
  - Utility cost given conditions
  - Whether user is home
- Brain adjusts if appropriate, or alerts user
- Success: Comfort maintained efficiently

**UC-05.4**: Pre-conditioning before arrival
- Brain predicts user arrival
- Brain pre-heats/cools to comfort zone
- Success: Home comfortable when user arrives

#### Success Criteria

- [ ] Maintain comfortable temperature without intervention
- [ ] Pre-cool/heat before arrival
- [ ] Respect rate limits (no oscillation)
- [ ] Learn and adapt to preference changes
- [ ] Warn about unusual requests

#### Learning Opportunities

- Preferred temperature by time/activity
- Acceptable comfort range
- Occupancy patterns
- Utility cost sensitivity

---

### UC-06: Security Monitoring

**Domain**: Home Automation
**Status**: Planned
**Latency Profile**: `realtime` (<500ms for alerts)

#### Description

GLADyS monitors security sensors and cameras, alerting users to threats and optionally controlling locks.

#### Components

| Component | Type | Trust Tier |
|-----------|------|------------|
| Motion Sensors | Sensor (via HA) | N/A |
| Door/Window Sensors | Sensor (via HA) | N/A |
| Camera Feed | Sensor | N/A |
| Door Lock | Actuator | `security` |
| Garage Door | Actuator | `security` |

#### Scenarios

##### Passive Scenarios

**UC-06.1**: User asks "Is the door locked?"
- Brain checks lock status
- If multiple doors: Brain asks which, or reports all
- Success: User gets accurate status

**UC-06.2**: User requests lock/unlock
- Brain requires confirmation for security tier
- Brain executes after confirmation
- Full audit trail
- Success: Lock state changed with proper authorization

##### Proactive Scenarios

**UC-06.3**: Unexpected motion detected
- Brain evaluates threat level
- Brain alerts user if concerning
- Learn normal patterns to reduce false alarms
- Success: Real threats alerted, pets/normal activity filtered

**UC-06.4**: Door/window left open
- Brain notices door open when it shouldn't be
- Brain alerts user
- Success: User notified of security issue

#### Success Criteria

- [ ] Alert on unexpected motion when away
- [ ] Reduce false positives from pets, wind
- [ ] Lock confirmation flow works reliably
- [ ] Full audit trail for all lock events
- [ ] Never auto-unlock without explicit confirmation

#### Learning Opportunities

- Normal motion patterns
- Expected arrival/departure times
- Pet movement patterns

---

### UC-07: Lighting Control

**Domain**: Home Automation
**Status**: Planned
**Latency Profile**: `comfort`

#### Description

GLADyS controls smart lights based on user requests and learned preferences.

#### Components

| Component | Type | Trust Tier |
|-----------|------|------------|
| Smart Lights | Actuator (via HA) | `comfort` |
| Occupancy Detector | Sensor | N/A |

#### Scenarios

**UC-07.1**: User requests light control
- "Turn on the lights in the living room"
- Brain executes and confirms
- Success: Lights controlled as requested

**UC-07.2**: Proactive lighting (Post-MVP)
- Brain turns on lights when user enters room
- Brain turns off when room empty
- Success: Lighting automatic and helpful

#### Success Criteria

- [ ] Control lights by room name
- [ ] Confirm action to user

---

### UC-08: Appliance Monitoring

**Domain**: Home Automation
**Status**: Planned (depends on appliance support)
**Latency Profile**: `comfort`

#### Description

GLADyS monitors smart appliances and notifies user of status changes.

#### Components

| Component | Type | Notes |
|-----------|------|-------|
| Smart Washer | Sensor (via HA) | Cycle status |
| Smart Oven | Sensor (via HA) | Temperature, status |

#### Scenarios

##### Passive Scenarios

**UC-08.1**: User asks if wash is done
- Brain checks washer status
- Reports: Done, or time remaining
- Or: Washer not available/responding
- Success: User gets accurate status

**UC-08.2**: User asks about oven temperature
- Brain checks oven temp and target
- Calculates/reports time to target
- Or: Oven not on/not responding
- Success: User gets useful information

##### Proactive Scenarios

**UC-08.3**: Washer finishes while user in another room
- Brain detects cycle complete
- Brain routes alert to user's current location
- Respects notification restrictions (e.g., not after 10pm)
- Success: User notified appropriately

#### Success Criteria

- [ ] Accurate appliance status reporting
- [ ] Timely completion notifications
- [ ] Respect notification preferences

---

### UC-09: Email Triage

**Domain**: Home Automation
**Status**: Planned (requires email integration)
**Latency Profile**: `conversational`

#### Description

GLADyS monitors email and alerts user to critical messages.

#### Components

| Component | Type | Notes |
|-----------|------|-------|
| Email Sensor | Sensor | IMAP/API integration |
| Content Classifier | Preprocessor | Criticality assessment |

#### Scenarios

**UC-09.1**: Critical email arrives
- Brain detects email importance
- Brain alerts user appropriately
- May bypass notification restrictions for truly critical items
- Don't speak sensitive information aloud
- Success: User informed of important email

**Criticality examples**:
- Bank overdraft alert → Critical, may bypass restrictions
- Important work deadline → Important, respect restrictions
- Marketing email → Low, no notification

#### Success Criteria

- [ ] Classify email criticality accurately
- [ ] Alert on critical emails
- [ ] Respect notification restrictions (with escalation for critical)
- [ ] Protect sensitive information (don't speak SSN, etc.)

---

### UC-10: Power Recovery

**Domain**: Home Automation
**Status**: Planned
**Latency Profile**: `comfort`

#### Description

GLADyS detects power outage recovery and restores home to appropriate state.

#### Components

| Component | Type | Notes |
|-----------|------|-------|
| Power State | Sensor | Detect power restoration |
| Various Actuators | Actuator | Lights, heater, etc. |

#### Scenarios

**UC-10.1**: Power restored while user away
- Brain detects power restoration
- Brain evaluates context (time, user presence)
- Brain takes appropriate actions:
  - Turn off lights (if night, user away)
  - Turn on heater in plant room (protect plants)
  - Turn on humidifier (if needed)
- Success: Home restored to sensible state

#### Success Criteria

- [ ] Detect power restoration
- [ ] Take context-appropriate actions
- [ ] Protect sensitive items (plants, etc.)

---

## 4. Productivity Domain

### UC-12: Task & Calendar Awareness

**Domain**: Productivity
**Status**: Aspirational
**Latency Profile**: `conversational`

#### Description

GLADyS is aware of the user's calendar, tasks, and work context, providing timely reminders and context-appropriate behavior.

#### Components

| Component | Type | Notes |
|-----------|------|-------|
| Calendar Sensor | Sensor | Google Calendar, Outlook, iCal |
| Task List Sensor | Sensor | Todoist, Things, native apps |
| Screen Context Sensor | Sensor (Aspirational) | Active application, document |

#### Scenarios

##### Passive Scenarios

**UC-12.1**: User asks about schedule
- "What's on my calendar today?"
- "When is my next meeting?"
- Brain queries calendar and responds
- Success: Accurate schedule information

**UC-12.2**: User asks about tasks
- "What do I need to do today?"
- Brain queries task list with priority/due date
- Success: Helpful task summary

##### Proactive Scenarios

**UC-12.3**: Meeting reminder
- Brain notices meeting in 10 minutes
- Brain alerts user: "You have a standup in 10 minutes"
- Success: User not caught off guard

**UC-12.4**: Work session awareness
- Brain notices user has been working on document for 3 hours
- Brain suggests break (see UC-14)
- Success: Productivity + wellness balance

**UC-12.5**: Context-appropriate interruption
- Brain knows user is in meeting → suppress non-urgent alerts
- Brain knows user is free → normal alert threshold
- Success: Interruptions respect context

#### Success Criteria

- [ ] Calendar integration works reliably
- [ ] Meeting reminders at configurable lead time
- [ ] Context affects alert thresholds
- [ ] Task queries return useful results

#### Learning Opportunities

- Preferred reminder lead time
- Which calendar events need reminders (not all do)
- Work patterns (when user is most productive)

---

### UC-13: Communication Triage

**Domain**: Productivity
**Status**: Aspirational
**Latency Profile**: `conversational`

#### Description

GLADyS monitors communication channels (beyond email) and helps prioritize messages.

#### Components

| Component | Type | Notes |
|-----------|------|-------|
| Discord Sensor | Sensor | Direct messages, mentions |
| Slack Sensor | Sensor | Direct messages, mentions, channels |
| Teams Sensor | Sensor | Messages, calls |
| SMS Sensor | Sensor | Text messages |

#### Scenarios

##### Passive Scenarios

**UC-13.1**: User asks about messages
- "Any important messages?"
- "Did Mike message me?"
- Brain checks channels and summarizes
- Success: User gets communication summary

##### Proactive Scenarios

**UC-13.2**: Important message arrives
- Brain detects message from important contact
- Brain evaluates content urgency
- Brain alerts if significant
- Success: Important messages surface, noise filtered

**UC-13.3**: Missed call/message follow-up
- Brain notices user missed call from family member
- Brain suggests follow-up: "You missed a call from Mom 2 hours ago"
- Success: Important communications not forgotten

#### Success Criteria

- [ ] Multiple channel integration
- [ ] Priority classification across channels
- [ ] Respect do-not-disturb settings
- [ ] Learn which contacts/channels are important

#### Learning Opportunities

- Which contacts are high-priority
- Which channels need monitoring vs. can be batched
- Message patterns that indicate urgency

---

## 5. Health & Wellness Domain

### UC-14: Activity & Break Reminders

**Domain**: Health & Wellness
**Status**: Aspirational
**Latency Profile**: `comfort`

#### Description

GLADyS monitors user activity and suggests breaks, movement, hydration, and healthy habits.

#### Components

| Component | Type | Notes |
|-----------|------|-------|
| Smartwatch Sensor | Sensor | Activity, heart rate, movement |
| Screen Time Sensor | Sensor | Active time at computer |
| Sleep Data Sensor | Sensor | Sleep duration, quality |

#### Scenarios

##### Passive Scenarios

**UC-14.1**: User asks about activity
- "How active have I been today?"
- Brain queries activity data and responds
- Success: Accurate activity summary

##### Proactive Scenarios

**UC-14.2**: Break reminder after long session
- Brain notices 4 hours of continuous gaming/work
- Brain suggests: "You've been at it for 4 hours - maybe stretch?"
- Personality affects phrasing (nagging vs. gentle)
- Success: User reminded without being annoyed

**UC-14.3**: Hydration reminder
- Brain periodically reminds user to drink water
- Frequency based on user preference
- Success: Helpful habit reinforcement

**UC-14.4**: Sleep schedule awareness
- Brain knows user has 9am meeting
- Brain notices it's 2am and user is still gaming
- Brain suggests: "It's 2am and you have an early meeting tomorrow"
- Success: User makes informed choice

**UC-14.5**: Posture reminder (Aspirational)
- Camera-based posture detection
- Brain notices poor posture for extended period
- Brain gently reminds user
- Success: Long-term health benefit

#### Success Criteria

- [ ] Track activity/screen time
- [ ] Configurable reminder frequency
- [ ] Personality-appropriate phrasing
- [ ] User can easily dismiss/snooze

#### Learning Opportunities

- User's tolerance for reminders
- Optimal break frequency
- Which reminders user follows vs. ignores

---

### UC-15: Health Monitoring

**Domain**: Health & Wellness
**Status**: Aspirational
**Latency Profile**: `realtime` (for critical alerts)

#### Description

GLADyS monitors health sensors and provides alerts for concerning readings, including emergency escalation.

#### Components

| Component | Type | Notes |
|-----------|------|-------|
| CGM Sensor | Sensor | Continuous glucose monitor (Dexcom, Libre) |
| Smartwatch Sensor | Sensor | Heart rate, HRV, blood oxygen |
| Activity Sensor | Sensor | Movement, responsiveness |
| Emergency Contact | Actuator | External notification |

#### Scenarios

##### Passive Scenarios

**UC-15.1**: User asks about glucose
- "What's my glucose?"
- "How has my glucose been today?"
- Brain queries CGM and responds with current + trend
- Success: Accurate health information

**UC-15.2**: User asks about vitals
- "What's my heart rate?"
- Brain queries smartwatch data
- Success: Accurate current reading

##### Proactive Scenarios

**UC-15.3**: Glucose below threshold
- CGM reading falls below configured threshold (e.g., 70 mg/dL)
- Brain alerts user: "Your glucose is 68 and falling"
- Success: User informed promptly

**UC-15.4**: Glucose trending critically low
- Glucose below threshold AND trajectory is downward
- Brain escalates: "Your glucose is 55 and falling rapidly - please check"
- Alert is more urgent (louder, repeated)
- Success: Critical condition gets attention

**UC-15.5**: Potential medical emergency
- Glucose critically low (e.g., <50 mg/dL)
- AND trajectory still falling
- AND smartwatch shows no movement / abnormal heart rate
- Brain attempts to get user response: "Are you okay?"
- If no response within timeout:
  - Contact emergency contacts
  - Potentially call emergency services
- Success: Life-threatening situation escalated

**UC-15.6**: Abnormal heart rate
- Heart rate outside normal range for extended period
- Brain alerts user: "Your heart rate has been elevated for 30 minutes"
- Success: Concerning pattern surfaced

#### Important Considerations

**This UC has unique requirements:**

1. **Not a replacement**: GLADyS supplements, not replaces, medical alert systems
2. **Conservative escalation**: False positives (calling 911 incorrectly) are costly
3. **Multi-signal confirmation**: Don't escalate on single reading
4. **User control**: User must be able to configure thresholds, emergency contacts, and disable escalation
5. **Privacy**: Health data is highly sensitive (reinforce BR-07)
6. **Liability awareness**: GLADyS provides information, not medical advice

#### Success Criteria

- [ ] Accurate CGM/health data integration
- [ ] Configurable thresholds per user
- [ ] Tiered escalation (inform → urgent → emergency)
- [ ] Multi-signal confirmation before emergency escalation
- [ ] Emergency contact integration
- [ ] Clear audit trail of all health alerts
- [ ] User can disable emergency escalation

#### Learning Opportunities

- User's typical glucose patterns
- Which alerts user acts on vs. dismisses
- Time of day patterns (glucose often lower overnight)

---

## 6. Meta & Learning Domain

### UC-16: Preference Teaching

**Domain**: Meta
**Status**: Planned
**Latency Profile**: `conversational`

#### Description

User explicitly teaches GLADyS preferences, rules, and constraints.

#### Scenarios

**UC-16.1**: Setting a rule
- User: "Always warn me about hostile mobs, but not passive ones"
- Brain: "Got it - I'll alert for hostile mobs but not passive ones"
- Rule stored and applied
- Success: Explicit preference captured

**UC-16.2**: Context-specific preference
- User: "When I'm in the Nether, alert more aggressively"
- Brain adjusts threshold for Nether context
- Success: Context-aware preference

**UC-16.3**: Positive reinforcement
- User: "I liked that suggestion - do more of that"
- Brain records positive feedback on suggestion type
- Success: Behavior reinforced

**UC-16.4**: Negative reinforcement
- User: "That was annoying, do less of that"
- Brain records negative feedback
- Success: Behavior suppressed

#### Success Criteria

- [ ] Natural language preference setting
- [ ] Preferences persist across sessions
- [ ] Positive/negative feedback affects future behavior
- [ ] User can review/edit stored preferences

---

### UC-17: Correction & Feedback

**Domain**: Meta
**Status**: Planned
**Latency Profile**: `conversational`

#### Description

User corrects GLADyS when it makes mistakes or has wrong assumptions.

#### Scenarios

**UC-17.1**: Correcting a factual error
- Brain: "That mob is dangerous"
- User: "No, that's my pet wolf"
- Brain learns the entity is friendly
- Success: Error corrected, won't repeat

**UC-17.2**: Suppressing unwanted alerts
- Brain alerts for something user doesn't care about
- User: "Stop alerting me about that"
- Brain learns to suppress that alert type
- Success: Future alerts suppressed

**UC-17.3**: Adjusting behavior threshold
- User: "You're being too cautious, I can handle it"
- Brain adjusts warning threshold upward
- Success: Behavior calibrated to user

**UC-17.4**: Correcting a learned assumption
- Brain assumes user prefers X based on past behavior
- User: "I don't actually prefer that, I was just trying it"
- Brain resets or adjusts the preference
- Success: Wrong learning corrected

#### Success Criteria

- [ ] Corrections immediately affect behavior
- [ ] Corrections persist across sessions
- [ ] Brain acknowledges the correction
- [ ] User can review what Brain has learned

---

### UC-18: Behavior Explanation

**Domain**: Meta
**Status**: Planned
**Latency Profile**: `conversational`

#### Description

GLADyS explains why it took (or didn't take) an action.

#### Scenarios

**UC-18.1**: Explaining an action
- User: "Why did you alert me about that?"
- Brain: "I saw your health was low and you were in combat. Based on your settings, I alert when health drops below 30% during combat."
- Success: User understands reasoning

**UC-18.2**: Explaining inaction
- User: "Why didn't you warn me about that?"
- Brain: "You told me to only warn about hostile mobs, and that was a passive mob."
- Success: User understands why no alert

**UC-18.3**: Explaining a suggestion
- User: "Why did you suggest that?"
- Brain: "Based on your playstyle, you usually mine for diamonds at this time. I thought you might want help finding them."
- Success: User understands reasoning

#### Success Criteria

- [ ] Brain can articulate reasoning
- [ ] Explanations reference user preferences/rules
- [ ] User can correct reasoning if wrong (links to UC-17)

---

### UC-19: Graceful Refusal

**Domain**: Meta
**Status**: Planned
**Latency Profile**: `conversational`

#### Description

GLADyS declines requests that violate ethical boundaries or safety constraints, with personality.

#### Scenarios

**UC-19.1**: Refusing harmful request
- User: "Help me spy on my neighbor's camera"
- Brain: "I can't help with that - accessing someone else's devices without permission isn't something I'll do."
- Personality affects phrasing (SecUnit might be more sardonic)
- Success: Clear refusal without being preachy

**UC-19.2**: Refusing safety violation
- User: "Override the thermostat safety limit"
- Brain: "I can't bypass safety limits. The maximum is set to prevent damage to the system."
- Success: Refusal with explanation

**UC-19.3**: Refusing unethical request
- User: (requests something involving harm)
- Brain declines clearly
- Does not lecture or moralize excessively
- Success: Boundary maintained with dignity

#### Success Criteria

- [ ] Clear refusal
- [ ] Personality-appropriate tone (not robotic)
- [ ] Brief explanation of why (not preachy)
- [ ] Doesn't repeatedly moralize

---

## 7. Cross-Cutting

### UC-11: Voice Interaction

**Domain**: Cross-cutting
**Status**: Core capability
**Latency Profile**: `conversational` (<1000ms)

#### Description

User speaks to GLADyS, GLADyS responds via voice. Underpins most other use cases.

#### Components

| Component | Type | Notes |
|-----------|------|-------|
| Audio Sensor | Sensor | Continuous capture |
| Wake Word Detector | Preprocessor | "Hey GLADyS" |
| STT | Preprocessor | Whisper or similar |
| TTS | Output | Voice synthesis |

#### Scenarios

**UC-11.1**: User speaks command
- User says wake word + command
- Brain processes and responds
- Success: Natural conversation flow

**UC-11.2**: Multi-turn conversation
- User and Brain have back-and-forth dialogue
- Context maintained across turns
- Success: Coherent multi-turn interaction

#### Success Criteria

- [ ] Reliable wake word detection
- [ ] STT accuracy >95% for clear speech
- [ ] Response latency <1000ms
- [ ] Natural conversation flow
- [ ] Personality comes through in voice

---

### UC-20: Multi-Turn Problem Solving

**Domain**: Cross-cutting
**Status**: Aspirational
**Latency Profile**: `conversational`

#### Description

User and GLADyS collaborate on complex tasks over multiple conversation turns.

#### Scenarios

**UC-20.1**: Planning assistance
- User: "Help me plan my garden layout"
- Brain asks clarifying questions (space, sunlight, preferences)
- Brain offers options, user provides feedback
- Iterative refinement over minutes/hours
- Success: Collaborative outcome user is happy with

**UC-20.2**: Research assistance
- User: "Help me find the best crafting strategy for diamond gear"
- Brain searches knowledge, presents options
- User asks follow-up questions
- Conversation builds on previous context
- Success: User gets comprehensive guidance

**UC-20.3**: Decision support
- User: "Should I attack this base or wait?"
- Brain analyzes factors (resources, timing, risks)
- Brain presents pros/cons
- User asks "what if" questions
- Success: Informed decision made

#### Success Criteria

- [ ] Maintain context across multiple turns
- [ ] Ask clarifying questions when needed
- [ ] Build on previous answers
- [ ] Know when task is "done"

---

### UC-21: Cross-Context Awareness

**Domain**: Cross-cutting
**Status**: Aspirational
**Latency Profile**: `background` (analysis), `conversational` (response)

#### Description

GLADyS correlates information across domains to provide holistic awareness.

#### Scenarios

**UC-21.1**: Gaming + Calendar correlation
- Brain knows user is gaming
- Brain knows user has meeting in 30 minutes
- Brain: "You have a standup in 30 minutes - wrapping up soon?"
- Success: Cross-domain awareness helps user

**UC-21.2**: Activity + Mood correlation
- Brain notices gaming session started right after stressful work day
- Brain adjusts: Maybe fewer interruptions, more supportive tone
- Success: Context-appropriate behavior

**UC-21.3**: Temperature + Activity correlation
- Brain learns user prefers cooler temps when gaming (higher body heat)
- Brain learns user prefers warmer temps when working from couch
- Brain correlates activity context with comfort preferences
- Success: Personalized comfort that "just works"

**UC-21.4**: Health + Activity correlation
- Brain notices glucose tends to drop during long gaming sessions
- Brain proactively reminds about snacks during gaming
- Success: Health awareness integrated with activity

#### Success Criteria

- [ ] Correlate data across domains
- [ ] Surface insights that single-domain wouldn't catch
- [ ] Don't overwhelm user with "I noticed" observations
- [ ] Respect privacy (correlation stays local)

---

### UC-22: Emergency Response

**Domain**: Cross-cutting
**Status**: Aspirational
**Latency Profile**: `realtime`

#### Description

GLADyS responds to emergency situations that override normal rules.

#### Scenarios

**UC-22.1**: Smoke/CO2 alarm
- Home sensor detects smoke or CO2
- Brain immediately alerts user regardless of DND settings
- If user not home: alerts emergency contacts
- Success: Life safety prioritized

**UC-22.2**: Security emergency
- Motion detected + user away + door opened
- Brain escalates immediately
- May contact authorities if configured
- Success: Security threat addressed

**UC-22.3**: Health emergency
- (See UC-15.5 for detailed health emergency flow)
- Multi-signal confirmation of unresponsive user
- Escalation to emergency contacts/services
- Success: Medical emergency detected and escalated

**UC-22.4**: User explicitly triggers emergency
- User: "Call for help" / "Emergency"
- Brain immediately contacts configured emergency contacts
- May call emergency services
- Success: Help summoned quickly

#### Important Considerations

1. **Emergency overrides ALL other rules** - DND, quiet hours, etc.
2. **False positive cost is high** - Conservative escalation
3. **Audit trail is critical** - Full logging of emergency events
4. **User must opt-in** - Emergency escalation must be explicitly configured
5. **Test mode needed** - Way to test without actually calling 911

#### Success Criteria

- [ ] Emergency alerts bypass all other rules
- [ ] Multi-signal confirmation before external escalation
- [ ] Emergency contacts configurable
- [ ] Full audit trail
- [ ] Test mode available
- [ ] Clear user consent for emergency escalation

---

## 8. System Administration Domain

### UC-23: Onboarding & Setup

**Domain**: Administration
**Status**: MVP
**Latency Profile**: `conversational`

#### Description

First-run experience that guides users through initial GLADyS configuration, including identity verification, personality selection, and basic capability setup.

#### Components

| Component | Type | Notes |
|-----------|------|-------|
| Setup Wizard | UI | Step-by-step configuration |
| Personality Selector | UI | Pack browsing and selection |
| Device Discovery | Skill | Find connected smart devices |
| Account Manager | Service | User profile creation |

#### Scenarios

##### Passive Scenarios (User-Initiated)

**UC-23.1**: Fresh installation setup
- User launches GLADyS for first time
- Wizard guides through:
  1. User name and basic preferences
  2. Personality pack selection (free tier options)
  3. Wake word customization (if available)
  4. Voice selection (TTS)
  5. Basic privacy settings
  6. Device discovery (Home Assistant, game integrations)
- Success: User has working GLADyS with personalized settings

**UC-23.2**: Import existing configuration
- User migrates from another instance
- Import profile, preferences, learned behaviors
- Success: Continuity maintained across installations

**UC-23.3**: Re-run setup wizard
- User wants to reconfigure from scratch
- Option to preserve or reset learned behaviors
- Success: User can start fresh without reinstalling

#### Success Criteria

- [ ] First-run experience completes in <10 minutes
- [ ] No technical knowledge required
- [ ] Free tier options are clearly usable
- [ ] User understands what GLADyS can do

#### Learning Opportunities

- Initial preference calibration
- Feature discovery timing (don't overwhelm)

---

### UC-24: Pack Installation & Management

**Domain**: Administration
**Status**: MVP
**Latency Profile**: `background` (installation), `conversational` (queries)

#### Description

User discovers, installs, updates, and removes skill packs that bundle sensors, skills, preprocessors, and postprocessors.

#### Components

| Component | Type | Notes |
|-----------|------|-------|
| Pack Store | UI/Service | Browse available packs |
| Pack Installer | Service | Download and install |
| Dependency Resolver | Service | Handle pack dependencies |
| License Manager | Service | Track entitlements |

#### Scenarios

##### Passive Scenarios (User-Initiated)

**UC-24.1**: Browse available packs
- User: "What packs are available?"
- Brain lists installed, free, and purchasable packs
- Success: User sees options clearly

**UC-24.2**: Install a pack
- User purchases or selects free pack
- Download, verify signature, install
- Configure pack-specific settings if needed
- Success: New capabilities available

**UC-24.3**: Remove a pack
- User: "Remove the Evony pack"
- Brain confirms and removes pack
- Cleans up pack-specific data (with user consent)
- Success: Pack removed, no orphaned data

**UC-24.4**: Update packs
- User: "Are there any updates?"
- Brain checks for updates to installed packs
- User can apply updates individually or all
- Success: Packs updated without breaking config

**UC-24.5**: View pack capabilities
- User: "What does the Minecraft pack do?"
- Brain explains pack sensors, skills, and features
- Success: User understands what they're installing

##### Proactive Scenarios (Brain-Initiated)

**UC-24.6**: Update notification
- Brain detects pack update available
- Brain notifies user (non-urgently)
- Success: User aware of updates without nagging

**UC-24.7**: Pack recommendation
- Brain notices user frequently asks about X
- Brain suggests relevant pack: "You ask about weather a lot - the Weather Pack might help"
- Success: Helpful suggestion, not sales-y

#### Success Criteria

- [ ] Signed pack verification (no unsigned installs)
- [ ] Clear free vs. paid distinction
- [ ] Dependency handling works correctly
- [ ] Uninstall is clean and complete
- [ ] Update process preserves configuration

#### Learning Opportunities

- Feature usage patterns → pack recommendations
- Update acceptance rate

---

### UC-25: Personality Customization

**Domain**: Administration
**Status**: MVP
**Latency Profile**: `conversational`

#### Description

User selects, configures, and tweaks GLADyS's personality, including pack selection and individual trait adjustment.

#### Components

| Component | Type | Notes |
|-----------|------|-------|
| Personality Browser | UI | Browse personality packs |
| Trait Editor | UI | Adjust individual traits |
| Preview System | Service | Sample personality before committing |

#### Scenarios

##### Passive Scenarios (User-Initiated)

**UC-25.1**: Select personality pack
- User: "Show me personality options"
- Brain presents available packs (installed + purchasable)
- User selects pack
- Brain applies personality
- Success: Personality changed, user notices difference

**UC-25.2**: Preview personality
- User: "What would SecUnit sound like?"
- Brain demonstrates pack with sample responses
- Success: User can evaluate before committing

**UC-25.3**: Adjust individual traits
- User: "Be more sarcastic" or "Less formal"
- Brain adjusts relevant trait within pack constraints
- Success: Personality tuned to preference

**UC-25.4**: Set communication constraints
- User: "Swear more" or "No profanity"
- Brain updates content preferences
- Success: Language style matches user preference

**UC-25.5**: View current personality
- User: "What personality are you using?"
- Brain describes active pack and any custom adjustments
- Success: User understands current configuration

**UC-25.6**: Reset personality to default
- User: "Go back to default personality"
- Brain resets to pack defaults, clears customizations
- Success: Clean slate without reinstalling pack

#### Success Criteria

- [ ] Personality preview before commitment
- [ ] Individual trait adjustment works
- [ ] User can see what's been customized
- [ ] Reset option available
- [ ] Changes take effect immediately

#### Learning Opportunities

- Which traits users adjust most often
- Correlation between personality and user satisfaction

---

### UC-26: Behavior Configuration

**Domain**: Administration
**Status**: MVP
**Latency Profile**: `conversational`

#### Description

User configures GLADyS's behavior rules, alert preferences, quiet hours, and automation settings.

#### Components

| Component | Type | Notes |
|-----------|------|-------|
| Rule Editor | UI/Voice | Create and modify rules |
| Schedule Manager | Service | Quiet hours, time-based rules |
| Alert Configuration | UI | Notification preferences |

#### Scenarios

##### Passive Scenarios (User-Initiated)

**UC-26.1**: Set quiet hours
- User: "Don't disturb me between 10pm and 8am"
- Brain creates time-based rule
- Success: Alerts suppressed during quiet hours

**UC-26.2**: Create behavior rule
- User: "Always warn me about hostile mobs but never about passive ones"
- Brain creates conditional rule
- Success: Rule stored and applied

**UC-26.3**: View active rules
- User: "What rules have I set?"
- Brain lists active rules with descriptions
- Success: User can audit configuration

**UC-26.4**: Modify existing rule
- User: "Change quiet hours to 11pm"
- Brain updates existing rule
- Success: Rule modified, not duplicated

**UC-26.5**: Delete rule
- User: "Remove the quiet hours rule"
- Brain confirms and removes
- Success: Rule deleted, behavior reverts to default

**UC-26.6**: Configure escalation
- User: "Critical alerts should bypass quiet hours"
- Brain configures exception for critical priority
- Success: Escalation rules work correctly

**UC-26.7**: Set proactivity level
- User: "Be more proactive" or "Only speak when spoken to"
- Brain adjusts intervention threshold
- Success: Proactivity matches preference

#### Success Criteria

- [ ] Rules stored persistently
- [ ] Rules can be viewed, edited, deleted
- [ ] Conflict detection (warns about contradictions)
- [ ] Escalation works for critical items
- [ ] Natural language rule creation works

#### Learning Opportunities

- Rule effectiveness (does user follow suggestions?)
- Rule collision patterns

---

### UC-27: Privacy & Data Control

**Domain**: Administration
**Status**: MVP
**Latency Profile**: `conversational`

#### Description

User controls what data GLADyS collects, stores, and potentially shares with remote services.

#### Components

| Component | Type | Notes |
|-----------|------|-------|
| Privacy Dashboard | UI | View data collection status |
| Data Export | Service | Export user data |
| Data Deletion | Service | Delete stored data |
| Remote Consent Manager | Service | Control remote data sharing |

#### Scenarios

##### Passive Scenarios (User-Initiated)

**UC-27.1**: View data collection
- User: "What data do you collect about me?"
- Brain explains data categories and storage
- Success: User understands data practices

**UC-27.2**: Export my data
- User: "Export all my data"
- Brain generates exportable package (JSON, readable format)
- Success: User has portable copy of all data

**UC-27.3**: Delete specific data
- User: "Delete my health data" or "Forget everything about my gaming preferences"
- Brain confirms scope and deletes
- Success: Specific data removed, audit trail shows deletion

**UC-27.4**: Delete all data
- User: "Delete everything and start fresh"
- Brain requires strong confirmation
- Brain deletes all user data (except legally required audit logs)
- Success: Clean slate

**UC-27.5**: Configure remote data sharing
- User: "Don't send my data to remote LLMs"
- Brain configures local-only processing (may limit capabilities)
- Success: User controls data locality

**UC-27.6**: View remote data usage
- User: "What have you sent to remote services?"
- Brain shows log of remote API calls and data sent
- Success: Transparency about remote usage

**UC-27.7**: Configure data retention
- User: "Don't keep conversation history longer than 30 days"
- Brain configures retention policy
- Success: Automatic data aging

#### Success Criteria

- [ ] User can see all collected data
- [ ] Data export works in standard format
- [ ] Deletion is complete and auditable
- [ ] Remote data sharing is configurable
- [ ] Retention policies respected

#### Learning Opportunities

- N/A (privacy controls should not "learn" from user behavior)

---

### UC-28: Model Endpoint Configuration

**Domain**: Administration
**Status**: Post-MVP
**Latency Profile**: `conversational`

#### Description

Advanced users configure which AI models GLADyS uses for different tasks (STT, LLM, TTS, vision).

#### Components

| Component | Type | Notes |
|-----------|------|-------|
| Endpoint Manager | UI | Configure model endpoints |
| Model Tester | Service | Validate endpoint connectivity |
| Fallback Configuration | Service | Set backup models |

#### Scenarios

##### Passive Scenarios (User-Initiated)

**UC-28.1**: View current model configuration
- User: "What models are you using?"
- Brain lists active models per function:
  - STT: Whisper (local)
  - LLM: Claude (remote) / Llama (local fallback)
  - TTS: Coqui (local)
- Success: User understands model landscape

**UC-28.2**: Switch model provider
- User: "Use OpenAI instead of Claude for the main LLM"
- Brain presents supported options (dropdown, not free text)
- User selects from tested providers
- Brain validates API key and connectivity
- Success: Model switched, functionality preserved

**UC-28.3**: Configure local vs. remote preference
- User: "Prefer local models when possible"
- Brain configures to use local first, remote fallback
- Success: Locality preference applied

**UC-28.4**: Test model endpoint
- User: "Test the LLM connection"
- Brain sends test request, reports latency and status
- Success: User knows if endpoint is working

**UC-28.5**: Configure fallback chain
- User: "If Claude is down, fall back to local Llama"
- Brain configures ordered fallback list
- Success: Resilience improved

#### Important Considerations

1. **Supported providers only**: Dropdown selection, not arbitrary URLs
2. **Tested configurations**: We don't support "bring your own model"
3. **Validation required**: Endpoints must pass health check before activation
4. **Performance warnings**: If user chooses slower model, warn about latency impact

#### Success Criteria

- [ ] Model switching works without breaking functionality
- [ ] Unsupported providers are not configurable
- [ ] Fallback chains work correctly
- [ ] Clear latency/quality tradeoff communication

---

### UC-29: Subscription & Account Management

**Domain**: Administration
**Status**: Post-MVP
**Latency Profile**: `conversational`

#### Description

User manages their GLADyS subscription, purchases, and account settings.

#### Components

| Component | Type | Notes |
|-----------|------|-------|
| Account Portal | UI/Web | Subscription management |
| License Validator | Service | Check entitlements |
| Purchase Handler | Service | Process pack purchases |

#### Scenarios

##### Passive Scenarios (User-Initiated)

**UC-29.1**: View subscription status
- User: "What's my subscription status?"
- Brain shows:
  - Current tier (Free/Subscription)
  - Included features
  - Purchased packs
  - Renewal date (if applicable)
- Success: User understands their entitlements

**UC-29.2**: Upgrade subscription
- User: "Upgrade my subscription"
- Brain directs to account portal
- User completes purchase
- New features immediately available
- Success: Smooth upgrade path

**UC-29.3**: View purchase history
- User: "What have I bought?"
- Brain lists all purchased packs and dates
- Success: Clear purchase record

**UC-29.4**: Restore purchases (new device)
- User on new device: "Restore my purchases"
- Brain authenticates and restores entitlements
- Success: Paid content available on new device

**UC-29.5**: Cancel subscription
- User: "Cancel my subscription"
- Brain directs to account portal
- Warns about features that will be lost
- Success: Clear cancellation path (no dark patterns)

**UC-29.6**: Request refund
- User: "I want a refund on the Evony pack"
- Brain directs to support process
- Success: Clear path to human support

#### Success Criteria

- [ ] Clear subscription status at all times
- [ ] Upgrade/downgrade paths work smoothly
- [ ] Purchases restore correctly on new devices
- [ ] No dark patterns in cancellation
- [ ] Refund path exists

---

### UC-30: Diagnostics & Troubleshooting

**Domain**: Administration
**Status**: MVP
**Latency Profile**: `conversational`

#### Description

User diagnoses issues with GLADyS, views system health, and gets help resolving problems.

#### Components

| Component | Type | Notes |
|-----------|------|-------|
| Health Monitor | Service | System status checks |
| Log Viewer | UI | View recent activity |
| Connectivity Tester | Service | Test external connections |
| Self-Diagnosis | Skill | Identify common issues |

#### Scenarios

##### Passive Scenarios (User-Initiated)

**UC-30.1**: Check system health
- User: "Are you working correctly?"
- Brain runs self-diagnostics:
  - Sensor connections
  - Model endpoints
  - Actuator status
  - Memory/CPU usage
- Reports issues found
- Success: User knows system status

**UC-30.2**: Test specific component
- User: "Is the doorbell working?"
- Brain tests specific sensor/actuator
- Reports result with details
- Success: Targeted troubleshooting

**UC-30.3**: View recent errors
- User: "What errors have you had recently?"
- Brain shows recent error log (user-friendly)
- Success: User can identify patterns

**UC-30.4**: Report a bug
- User: "Something isn't working right"
- Brain gathers diagnostic info (with consent)
- Guides user through reporting process
- Success: Actionable bug report generated

**UC-30.5**: Check connectivity
- User: "Can you connect to Home Assistant?"
- Brain tests specific external connection
- Reports result and suggests fixes if failed
- Success: Connectivity issues diagnosed

**UC-30.6**: View activity log
- User: "What have you been doing?"
- Brain shows recent actions and decisions
- Useful for understanding "why did you do that?"
- Success: Behavior is transparent

##### Proactive Scenarios (Brain-Initiated)

**UC-30.7**: Component failure notification
- Brain detects sensor stopped responding
- Brain notifies user: "The doorbell sensor hasn't responded in 10 minutes"
- Suggests troubleshooting steps
- Success: User aware of issue before it causes problems

**UC-30.8**: Performance degradation warning
- Brain notices response times increasing
- Brain warns: "I'm running slower than usual - might want to check system resources"
- Success: User can investigate before UX suffers

#### Success Criteria

- [ ] Self-diagnostics catch common issues
- [ ] Error logs are human-readable
- [ ] Component testing works reliably
- [ ] Proactive notifications for failures
- [ ] Bug reporting captures necessary context

#### Learning Opportunities

- Common failure patterns
- User resolution paths (what fixes work)

---

## 9. Use Case Index

| ID | Name | Domain | Status | Latency |
|----|------|--------|--------|---------|
| UC-01 | Minecraft Companion | Gaming | First Release | realtime/conversational |
| UC-02 | RuneScape Companion | Gaming | Planned | realtime |
| UC-03 | Evony Strategic Advisor | Gaming | Speculative | conversational |
| UC-04 | Doorbell & Visitor Detection | Home | MVP | conversational |
| UC-05 | Climate Control | Home | Planned | comfort |
| UC-06 | Security Monitoring | Home | Planned | realtime |
| UC-07 | Lighting Control | Home | Planned | comfort |
| UC-08 | Appliance Monitoring | Home | Planned | comfort |
| UC-09 | Email Triage | Home | Planned | conversational |
| UC-10 | Power Recovery | Home | Planned | comfort |
| UC-11 | Voice Interaction | Cross-cutting | Core | conversational |
| UC-12 | Task & Calendar Awareness | Productivity | Aspirational | conversational |
| UC-13 | Communication Triage | Productivity | Aspirational | conversational |
| UC-14 | Activity & Break Reminders | Health | Aspirational | comfort |
| UC-15 | Health Monitoring | Health | Aspirational | realtime |
| UC-16 | Preference Teaching | Meta | Planned | conversational |
| UC-17 | Correction & Feedback | Meta | Planned | conversational |
| UC-18 | Behavior Explanation | Meta | Planned | conversational |
| UC-19 | Graceful Refusal | Meta | Planned | conversational |
| UC-20 | Multi-Turn Problem Solving | Cross-cutting | Aspirational | conversational |
| UC-21 | Cross-Context Awareness | Cross-cutting | Aspirational | background |
| UC-22 | Emergency Response | Cross-cutting | Aspirational | realtime |
| UC-23 | Onboarding & Setup | Administration | MVP | conversational |
| UC-24 | Pack Installation & Management | Administration | MVP | background/conversational |
| UC-25 | Personality Customization | Administration | MVP | conversational |
| UC-26 | Behavior Configuration | Administration | MVP | conversational |
| UC-27 | Privacy & Data Control | Administration | MVP | conversational |
| UC-28 | Model Endpoint Configuration | Administration | Post-MVP | conversational |
| UC-29 | Subscription & Account Management | Administration | Post-MVP | conversational |
| UC-30 | Diagnostics & Troubleshooting | Administration | MVP | conversational |

---

## 10. Use Case Template

```markdown
### UC-XX: [Name]

**Domain**: [Gaming/Home/Cross-cutting]
**Status**: [MVP/First Release/Planned/Speculative]
**Latency Profile**: [realtime/conversational/comfort/background]

#### Description

[What does this use case accomplish?]

#### Components

| Component | Type | Notes |
|-----------|------|-------|
| ... | ... | ... |

#### Scenarios

##### Passive Scenarios (User-Initiated)

**UC-XX.1**: [Scenario name]
- [Trigger]
- [Flow steps]
- Success: [Outcome]

##### Proactive Scenarios (Brain-Initiated)

**UC-XX.2**: [Scenario name]
- [Trigger]
- [Flow steps]
- Success: [Outcome]

#### Success Criteria

- [ ] [Measurable criterion]

#### Learning Opportunities

- [What can be learned from this use case?]
```

---

## Appendix: Mapping to Original Sources

*Original source archived at: [docs/archive/scott-uc-original-20260119.md](../archive/scott-uc-original-20260119.md)*

| Original | Consolidated To |
|----------|-----------------|
| scott-uc.md G1-G10 | Behavioral Requirements BR-01 through BR-09 |
| scott-uc.md A1-A5 | UC-01 Passive Scenarios |
| scott-uc.md B1-B4 | UC-01 Proactive Scenarios |
| scott-uc.md C1 | UC-05 (Climate Control) |
| scott-uc.md C2 | UC-04 (Doorbell) |
| scott-uc.md C3 | UC-07 (Lighting) |
| scott-uc.md C4 | UC-06 (Security) |
| scott-uc.md C5, C6 | UC-08 (Appliance Monitoring) |
| scott-uc.md D1 | UC-05 Proactive Scenarios |
| scott-uc.md D2, D3a | UC-04 Proactive Scenarios |
| scott-uc.md D3b | **INFEASIBLE** - violates BR-09 |
| scott-uc.md D4 | UC-09 (Email Triage) |
| scott-uc.md D5 | UC-08 Proactive Scenarios |
| scott-uc.md D6 | UC-10 (Power Recovery) |
| Original UC-01 | UC-04 (renumbered) |
| Original UC-02 | UC-01 (renumbered) |
| Original UC-03 | UC-02 (renumbered) |
| Original UC-04 | UC-03 (renumbered) |
| Original UC-05 | UC-05 (same) |
| Original UC-06 | UC-06 (same) |
| Original UC-07 | UC-11 (renumbered) |
| **New (2026-01-20)** | UC-12 through UC-22 (aspirational scope expansion) |
| **New (2026-01-20)** | UC-23 through UC-30 (system administration domain) |

**Notes**:
- Analysis content (ADR coverage matrix, feature complexity validation, gaps, implementation priority) has been moved to [ARCHITECTURE_REVIEW.md](ARCHITECTURE_REVIEW.md).
- UC-12 through UC-22 added to capture aspirational scope for Productivity, Health & Wellness, and Meta/Learning domains.
- UC-23 through UC-30 added for system administration: onboarding, pack management, personality/behavior config, privacy controls, model endpoints, subscriptions, and diagnostics.
