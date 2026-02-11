# RuneScape Sensor Event Specification

Event schema for the RuneScape sensor. Defines what data the sensor produces, organized by category and subtype.

## Common Event Envelope

Every event emitted by the sensor shares this structure:

| Field | Type | Description |
|-------|------|-------------|
| `event_type` | string | Category. One of the subtypes below. |
| `tick` | int | Server game tick when the event occurred. |
| `timestamp` | ISO 8601 string | Wall-clock time. For cross-system correlation. |
| `payload` | object | Subtype-specific data. |

## Entity Identification

Entities (players, NPCs) are referenced consistently across events:

| Field | Type | Description |
|-------|------|-------------|
| `entity_type` | string | `local_player`, `player`, `npc` |
| `name` | string | Display name. |
| `id` | int | NPC ID (from NpcID) or player ID. |
| `index` | int | NPC index in client cache (NPCs only). |
| `combat_level` | int | Combat level. |
| `position` | object | `{ "x": int, "y": int, "plane": int }` — world coordinates. |

NPCs are uniquely identified by `index` (their position in the client's NPC array). Players are identified by `name`.

---

## Event Subtypes

### Spawn / Despawn

Fired when an entity enters or leaves the visible game world.

**Default: enabled**

#### RuneLite Sources
- `NpcSpawned`, `NpcDespawned`
- `PlayerSpawned`, `PlayerDespawned`
- `ActorDeath`

#### Payload

| Field | Type | Description |
|-------|------|-------------|
| `action` | string | `spawn` or `despawn` |
| `entity` | Entity object | The entity that spawned or despawned. |
| `reason` | string | Despawn only. `death`, `out_of_range`, or `unknown`. Inferred from whether `ActorDeath` fired before the despawn event. |

#### Notes
- `PlayerDespawned` does not fire for the local player.
- `ActorDeath` fires before the corresponding despawn event, so the plugin can track recent deaths to populate `reason`.
- `NpcChanged` (composition change) is not a spawn/despawn but may be relevant for NPCs that transform (e.g., Verzik phases). Captured as a spawn of the new form if the ID changes.

---

### Movement

Fired when an entity's world position changes (delta-only).

**Default: enabled**

#### RuneLite Sources
- Polled via `GameTick`. Compare `Actor.getWorldLocation()` against tracked previous position.

#### Payload

| Field | Type | Description |
|-------|------|-------------|
| `entity` | Entity object | The entity that moved. |
| `from` | object | `{ "x": int, "y": int, "plane": int }` — previous position. |
| `to` | object | `{ "x": int, "y": int, "plane": int }` — new position. |

#### Notes
- Only fires when position actually changes. Idle entities produce no movement events.
- Uses server-side position (`getWorldLocation()`), which is ahead of the rendered client position.
- Plane changes (stairs, ladders) are movement events.

---

### Damage

Fired when a hitsplat is applied to any actor.

**Default: enabled**

#### RuneLite Sources
- `HitsplatApplied`

#### Payload

| Field | Type | Description |
|-------|------|-------------|
| `target` | Entity object | The entity that took damage. |
| `amount` | int | Damage value displayed. |
| `type` | string | Hitsplat type. One of: `damage`, `block`, `poison`, `venom`, `disease`, `heal`, `prayer_drain`, `bleed`, `burn`, `doom`, `corruption`, `sanity_drain`, `sanity_restore`. |
| `is_mine` | boolean | `true` if the local player dealt or received this hit (BLOCK_ME/DAMAGE_ME variants). |

#### Notes
- No source actor is available from RuneLite's API. Damage attribution must be inferred downstream by correlating with `InteractingChanged` data and tick timing.
- `isMine()` distinguishes hits involving the local player from hits between other entities.
- Max hits (DAMAGE_MAX_ME variants) are reported as `damage` type with the amount; they are not distinguished from normal hits.

---

### StatChange

Fired when a skill's XP, level, or boosted level changes.

**Default: enabled**

#### RuneLite Sources
- `StatChanged`

#### Payload

| Field | Type | Description |
|-------|------|-------------|
| `skill` | string | Skill name (e.g., `Mining`, `Attack`, `Hitpoints`). |
| `xp` | int | Total XP in the skill. |
| `level` | int | Real (unboosted) level. |
| `boosted_level` | int | Current effective level (includes boosts/drains). |
| `leveled_up` | boolean | `true` if `level` increased since last known value. |

#### Notes
- To detect level ups, the plugin tracks previous level per skill and compares on each `StatChanged` event.
- Boost decay (e.g., super combat potion wearing off) fires as a `StatChange` with decreasing `boosted_level`.
- Drinking a potion fires as a `StatChange` with increasing `boosted_level`.
- If multiple levels are gained at once (e.g., quest reward), RuneLite may fire one event per level or one event with the final level. The `leveled_up` flag will be `true` regardless.

---

### ActionState

Fired when an entity's animation or graphic/spotanim changes.

**Default: enabled**

#### RuneLite Sources
- `AnimationChanged`
- `GraphicChanged`

#### Payload

| Field | Type | Description |
|-------|------|-------------|
| `entity` | Entity object | The entity whose action state changed. |
| `change_type` | string | `animation` or `graphic`. |
| `animation_id` | int | Current animation ID (`-1` if idle). Animation change only. |
| `graphic_id` | int | Current graphic/spotanim ID. Graphic change only. |

#### Notes
- Animation IDs are raw integers. A mapping to human-readable names (e.g., 624 = mining) is a downstream concern, not a sensor concern.
- `animation_id: -1` means the entity returned to idle.
- Some skilling animations have brief gap frames between cycles. The AI may see rapid animation → idle → animation sequences during normal activity.

---

### MenuAction

Fired when the local player clicks a menu option (any action in the game).

**Default: enabled**

#### RuneLite Sources
- `MenuOptionClicked`

#### Payload

| Field | Type | Description |
|-------|------|-------------|
| `option` | string | The action text (e.g., `Attack`, `Use`, `Pick-up`, `Walk here`). |
| `target` | string | The target of the action (e.g., `Goblin (level-2)`, `Oak tree`). Includes color tags from RuneLite; strip before sending. |
| `action_type` | string | The `MenuAction` enum value (e.g., `NPC_SECOND_OPTION`, `ITEM_USE_ON_NPC`). |
| `id` | int | Identifier of the targeted object/actor/item. |
| `is_item_op` | boolean | `true` if this is an item operation. |
| `item_id` | int | Item ID, if `is_item_op` is `true`. |

#### Notes
- This is the richest event for understanding player intent. Every deliberate action goes through the menu system.
- `target` contains RuneLite color formatting tags (e.g., `<col=ffff00>`). These should be stripped to plain text before emission.
- `action_type` provides the mechanical type of action which disambiguates cases where `option` text is the same (e.g., multiple "Use" options).

---

### ItemChange

Fired when inventory, equipment, or ground items change.

**Default: enabled**

#### RuneLite Sources
- `ItemContainerChanged` (inventory, equipment, bank)
- `ItemSpawned`, `ItemDespawned` (ground items)
- `ItemQuantityChanged` (ground item stack changes)

#### Payload — Container Change

| Field | Type | Description |
|-------|------|-------------|
| `change_type` | string | `container` |
| `container_id` | int | Identifies which container (inventory, equipment, bank, etc.). |
| `items` | array | Full list of `{ "item_id": int, "quantity": int }` in the container. |

#### Payload — Ground Item

| Field | Type | Description |
|-------|------|-------------|
| `change_type` | string | `ground_spawn`, `ground_despawn`, or `ground_quantity` |
| `position` | object | `{ "x": int, "y": int, "plane": int }` — tile location. |
| `item_id` | int | Item ID. |
| `quantity` | int | Current quantity. |
| `old_quantity` | int | Previous quantity (`ground_quantity` only). |

#### Notes
- `ItemContainerChanged` fires with the full container contents, not a diff. The plugin could diff against previous state to emit only changes, or ship the full snapshot and let GLADyS handle it. For Phase, full snapshot is simpler.
- Container IDs: 93 = inventory, 94 = equipment, 95 = bank. Others exist for various interfaces.
- Ground item events fire during scene load for items already on the ground.

---

### Chat

Fired on chat messages, overhead text, and social events.

**Default: enabled**

#### RuneLite Sources
- `ChatMessage`
- `OverheadTextChanged`
- `ClanMemberJoined`, `ClanMemberLeft`
- `FriendsChatChanged`

#### Payload — Chat Message

| Field | Type | Description |
|-------|------|-------------|
| `change_type` | string | `message` |
| `channel` | string | Chat type: `game`, `public`, `private`, `clan`, `friends_chat`, `trade`, `broadcast`, `engine`, etc. Derived from `ChatMessageType`. |
| `sender` | string | Player name who sent the message. Empty for game messages. |
| `message` | string | Message contents. |

#### Payload — Overhead Text

| Field | Type | Description |
|-------|------|-------------|
| `change_type` | string | `overhead` |
| `entity` | Entity object | The actor speaking. |
| `text` | string | The overhead text. |

#### Payload — Social

| Field | Type | Description |
|-------|------|-------------|
| `change_type` | string | `clan_join`, `clan_leave`, or `friends_chat_change` |
| `member_name` | string | Name of the member (clan join/leave). |
| `joined` | boolean | `true` if joined, `false` if left (friends chat). |

#### Notes
- `ChatMessage` does not fire for NPC dialogue (that's widget-based).
- Game messages include things like "You can't reach that", "You need a Mining level of 60", quest completion text, etc.
- `OverheadTextChanged` captures NPC shouts (boss mechanics) and player overhead text.

---

### SessionState

Fired on client state changes: login, logout, loading, focus, world hops, and GE activity.

**Default: enabled**

#### RuneLite Sources
- `GameStateChanged`
- `FocusChanged`
- `WorldChanged`
- `GrandExchangeOfferChanged`

#### Payload — Game State

| Field | Type | Description |
|-------|------|-------------|
| `change_type` | string | `game_state` |
| `state` | string | `logged_in`, `login_screen`, `loading`, `connection_lost`, `hopping`. Derived from `GameState` enum. |

#### Payload — Focus

| Field | Type | Description |
|-------|------|-------------|
| `change_type` | string | `focus` |
| `focused` | boolean | `true` if client has focus, `false` if tabbed away. |

#### Payload — World Change

| Field | Type | Description |
|-------|------|-------------|
| `change_type` | string | `world_change` |

#### Payload — Grand Exchange

| Field | Type | Description |
|-------|------|-------------|
| `change_type` | string | `ge_offer` |
| `slot` | int | GE slot index (0-7). |
| `offer` | object | Offer details from `GrandExchangeOffer`. |

#### Notes
- `GameStateChanged` fires frequently during normal play (loading zones, hopping).
- `GrandExchangeOfferChanged` fires on login for all slots (with EMPTY state), then updates as the server provides data. Downstream should ignore initial login spam.
- `WorldChanged` fires before the connection is established to the new world.

---

### Sound (disabled by default)

Fired when sound effects play.

**Default: disabled**

#### RuneLite Sources
- `SoundEffectPlayed`
- `AreaSoundEffectPlayed`
- `AmbientSoundEffectCreated`

#### Payload — Sound Effect

| Field | Type | Description |
|-------|------|-------------|
| `change_type` | string | `sound`, `area_sound`, or `ambient` |
| `sound_id` | int | Sound effect ID. |
| `source` | Entity object or null | Source actor, if any. |
| `position` | object or null | `{ "x": int, "y": int }` — scene coordinates (area sound only). |
| `range` | int | Audio range (area sound only). |
| `delay` | int | Delay before playing. |

#### Notes
- Potentially useful as a leading indicator when visual data hasn't loaded (e.g., PvP veng scenarios where a player attacks from outside render distance but sounds play).
- Ambient sounds created during map load do not trigger events.
- High volume in busy areas. Disabled by default for this reason.

---

### Misc (disabled by default)

Catch-all for events that may have experimental or niche value.

**Default: disabled**

#### RuneLite Sources
- `GameObjectSpawned`, `GameObjectDespawned`
- `WallObjectSpawned`, `WallObjectDespawned`
- `DecorativeObjectSpawned`, `DecorativeObjectDespawned`
- `GroundObjectSpawned`, `GroundObjectDespawned`
- `WidgetLoaded`, `WidgetClosed`
- `ProjectileMoved`
- `VarbitChanged`
- `ScriptPreFired`, `ScriptPostFired`
- `InteractingChanged`

#### Notes
- These events are available for experimentation — testing how the AI responds to data we don't think it needs.
- `InteractingChanged` is in Misc because its primary value (damage attribution) is an inference concern, not a sensor concern. It can be promoted if downstream processing benefits from having it enabled.
- `VarbitChanged` exposes low-level game variables (run energy, special attack, quest state, spellbook, etc.) but requires mapping varbit IDs to meaningful names.
- World object events (GameObjects, WallObjects, etc.) are high volume during scene loads and of limited value unless tracking specific interactable objects (e.g., tree respawns).
- `ProjectileMoved` is redundant with damage/action events for most combat scenarios.

---

## Implementation Notes

### State Tracking (Plugin-Side)

The plugin must maintain minimal state to produce delta events:

- **Previous positions**: per-entity `WorldPoint` for movement delta detection.
- **Previous levels**: per-skill `int` for `leveled_up` flag on `StatChange`.
- **Recent deaths**: short-lived set of actors from `ActorDeath` to populate `reason` on despawn events.

All other data is read directly from RuneLite event objects and the `Client` API at event time.

### What the Sensor Does NOT Do

- No filtering or prioritization — that's the salience layer.
- No damage attribution — downstream correlates hitsplats with interaction data.
- No animation ID-to-name mapping — downstream or skill packs handle this.
- No deduplication of skilling animation cycles — the AI handles repetition.
- No spatial filtering (e.g., ignoring distant entities) — salience decides what matters.

