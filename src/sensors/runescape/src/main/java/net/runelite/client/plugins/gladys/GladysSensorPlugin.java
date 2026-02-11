package net.runelite.client.plugins.gladys;

import com.gladys.sensor.EventBuilder;
import com.gladys.sensor.GladysClient;
import com.gladys.sensor.HeartbeatManager;
import com.gladys.sensor.SensorRegistration;
import gladys.v1.Common;
import gladys.v1.Orchestrator.ComponentCapabilities;
import gladys.v1.Orchestrator.TransportMode;
import java.awt.image.BufferedImage;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import javax.inject.Inject;
import lombok.Getter;
import lombok.extern.slf4j.Slf4j;
import net.runelite.api.Actor;
import net.runelite.api.ChatMessageType;
import net.runelite.api.Client;
import net.runelite.api.GameState;
import net.runelite.api.HitsplatID;
import net.runelite.api.Item;
import net.runelite.api.ItemContainer;
import net.runelite.api.MenuAction;
import net.runelite.api.NPC;
import net.runelite.api.Player;
import net.runelite.api.Skill;
import net.runelite.api.SkullIcon;
import net.runelite.api.coords.WorldPoint;
import net.runelite.api.events.*;
import net.runelite.client.callback.ClientThread;
import net.runelite.client.config.ConfigManager;
import net.runelite.client.eventbus.Subscribe;
import net.runelite.client.plugins.Plugin;
import net.runelite.client.plugins.PluginDescriptor;
import net.runelite.client.ui.ClientToolbar;
import net.runelite.client.ui.NavigationButton;
import net.runelite.client.util.ImageUtil;
import net.runelite.client.util.Text;
import com.google.inject.Provides;

@PluginDescriptor(
	name = "GLADyS Sensor",
	description = "Sensor bridge between RuneLite and GLADyS",
	tags = {"gladys", "sensor", "external"}
)
@Slf4j
public class GladysSensorPlugin extends Plugin
{
	// SDK components
	private GladysClient gladysClient;
	private HeartbeatManager heartbeatManager;

	// Async event publishing — gRPC calls must not block RuneLite's client thread
	private ExecutorService eventExecutor;

	private static final String SENSOR_ID = "runescape";
	private static final int HEARTBEAT_INTERVAL_S = 30;

	@Inject
	private Client client;

	@Inject
	private ClientThread clientThread;

	@Inject
	private ClientToolbar clientToolbar;

	@Inject
	private GladysSensorConfig config;

	@Inject
	@Getter
	private ConfigManager configManager;

	private GladysSensorPanel panel;
	private NavigationButton navButton;

	@Provides
	GladysSensorConfig provideConfig(ConfigManager configManager)
	{
		return configManager.getConfig(GladysSensorConfig.class);
	}

	// State tracking for delta detection
	private final Map<Integer, WorldPoint> npcPositions = new HashMap<>();
	private final Map<String, WorldPoint> playerPositions = new HashMap<>();
	private final Map<Skill, Integer> previousLevels = new HashMap<>();
	private final Set<Actor> recentDeaths = new HashSet<>();

	// Animation/graphic dedup: track previous values per actor identity
	private final Map<Integer, Integer> npcAnimations = new HashMap<>();
	private final Map<String, Integer> playerAnimations = new HashMap<>();
	private final Map<Integer, Integer> npcGraphics = new HashMap<>();
	private final Map<String, Integer> playerGraphics = new HashMap<>();

	// Event counters for the panel
	@Getter
	private final Map<String, Integer> eventCounts = new LinkedHashMap<>();

	// Chat logging toggle (panel-controlled, not persisted)
	@Getter
	private boolean logToChat = false;

	public void setLogToChat(boolean value)
	{
		this.logToChat = value;
	}

	@Override
	protected void startUp() throws Exception
	{
		panel = injector.getInstance(GladysSensorPanel.class);
		panel.init(this);

		final BufferedImage icon = ImageUtil.loadImageResource(getClass(), "gladys_icon.png");

		navButton = NavigationButton.builder()
			.tooltip("GLADyS Sensor")
			.icon(icon)
			.priority(10)
			.panel(panel)
			.build();

		clientToolbar.addNavigation(navButton);

		// Connect to GLADyS orchestrator
		String host = config.orchestratorHost();
		int port = config.orchestratorPort();

		try
		{
			gladysClient = new GladysClient(host, port);

			// Register as a sensor
			ComponentCapabilities caps = ComponentCapabilities.newBuilder()
				.setTransportMode(TransportMode.TRANSPORT_MODE_EVENT)
				.build();
			SensorRegistration.register(gladysClient, SENSOR_ID, "sensor", caps);

			// Start heartbeat
			heartbeatManager = new HeartbeatManager(gladysClient, SENSOR_ID, HEARTBEAT_INTERVAL_S);
			heartbeatManager.start();

			// Background thread for async event publishing
			eventExecutor = Executors.newSingleThreadExecutor(r -> {
				Thread t = new Thread(r, "gladys-event-publisher");
				t.setDaemon(true);
				return t;
			});

			log.info("GLADyS Sensor connected to orchestrator at {}:{}", host, port);
		}
		catch (Exception e)
		{
			log.error("GLADyS Sensor failed to connect to orchestrator at {}:{}", host, port, e);
		}
	}

	@Override
	protected void shutDown() throws Exception
	{
		if (navButton != null)
		{
			clientToolbar.removeNavigation(navButton);
		}

		if (heartbeatManager != null)
		{
			heartbeatManager.stop();
		}

		if (eventExecutor != null)
		{
			eventExecutor.shutdown();
			try
			{
				if (!eventExecutor.awaitTermination(5, TimeUnit.SECONDS))
				{
					eventExecutor.shutdownNow();
				}
			}
			catch (InterruptedException e)
			{
				eventExecutor.shutdownNow();
			}
		}

		if (gladysClient != null)
		{
			gladysClient.close();
		}

		npcPositions.clear();
		playerPositions.clear();
		previousLevels.clear();
		recentDeaths.clear();
		npcAnimations.clear();
		playerAnimations.clear();
		npcGraphics.clear();
		playerGraphics.clear();
		eventCounts.clear();

		log.info("GLADyS Sensor stopped");
	}

	// ── Helpers ──────────────────────────────────────────────────

	private String actorKey(Actor actor)
	{
		if (actor instanceof NPC) return "npc:" + ((NPC) actor).getIndex();
		if (actor instanceof Player) return "p:" + ((Player) actor).getName();
		return "?";
	}

	private void emit(String eventType, Map<String, Object> payload, String chatSummary)
	{
		// Add game-specific context to structured data
		payload.put("event_type", eventType);
		payload.put("tick", client.getTickCount());

		// Classify intent
		String intent = classifyIntent(eventType, payload);

		// Build the event
		Common.Event event = new EventBuilder(SENSOR_ID)
			.text("RuneScape: " + (chatSummary != null ? chatSummary : eventType))
			.structured(payload)
			.intent(intent)
			.build();

		// Publish asynchronously — never block RuneLite's client thread
		if (gladysClient != null && eventExecutor != null && !eventExecutor.isShutdown())
		{
			eventExecutor.submit(() -> {
				try
				{
					gladysClient.publishEvent(event);
				}
				catch (Exception e)
				{
					log.warn("Failed to publish {} event: {}", eventType, e.getMessage());
				}
			});
		}

		// Update panel counts (keep existing behavior)
		eventCounts.merge(eventType, 1, Integer::sum);
		if (panel != null)
		{
			panel.updateCounts();
		}

		// Chat logging (keep existing behavior)
		if (logToChat && chatSummary != null && client.getGameState() == GameState.LOGGED_IN)
		{
			clientThread.invokeLater(() ->
				client.addChatMessage(ChatMessageType.GAMEMESSAGE, "",
					"[GLADyS:" + eventType + "] " + chatSummary, ""));
		}
	}

	private String classifyIntent(String eventType, Map<String, Object> payload)
	{
		switch (eventType)
		{
			case "menu_action":
				return "actionable";
			case "damage":
				Boolean isMine = (Boolean) payload.get("is_mine");
				return (isMine != null && isMine) ? "actionable" : "informational";
			case "stat_change":
				Boolean leveledUp = (Boolean) payload.get("leveled_up");
				return (leveledUp != null && leveledUp) ? "actionable" : "informational";
			case "chat":
				String channel = (String) payload.get("channel");
				return "private_chat".equals(channel) ? "actionable" : "informational";
			default:
				return "informational";
		}
	}

	private Map<String, Object> entityMap(Actor actor)
	{
		Map<String, Object> m = new LinkedHashMap<>();
		if (actor instanceof NPC)
		{
			NPC npc = (NPC) actor;
			m.put("entity_type", "npc");
			m.put("name", npc.getName());
			m.put("id", npc.getId());
			m.put("index", npc.getIndex());
			m.put("combat_level", npc.getCombatLevel());
		}
		else if (actor instanceof Player)
		{
			Player player = (Player) actor;
			boolean isLocal = player == client.getLocalPlayer();
			m.put("entity_type", isLocal ? "local_player" : "player");
			m.put("name", player.getName());
			m.put("combat_level", player.getCombatLevel());
			m.put("skull", skullName(player.getSkullIcon()));
			if (player.getOverheadIcon() != null)
			{
				m.put("overhead_prayer", player.getOverheadIcon().name().toLowerCase());
			}
			m.put("is_friend", player.isFriend());
			m.put("is_clan_member", player.isClanMember());
			m.put("team", player.getTeam());
		}

		if (actor.getWorldLocation() != null)
		{
			WorldPoint wp = actor.getWorldLocation();
			Map<String, Object> pos = new LinkedHashMap<>();
			pos.put("x", wp.getX());
			pos.put("y", wp.getY());
			pos.put("plane", wp.getPlane());
			m.put("position", pos);
		}

		return m;
	}

	private String entityName(Actor actor)
	{
		String name = actor.getName();
		if (name == null) return "?";
		if (actor instanceof NPC) return name + "(npc)";
		if (actor == client.getLocalPlayer()) return name + "(me)";
		return name;
	}

	private Map<String, Object> positionMap(WorldPoint wp)
	{
		Map<String, Object> m = new LinkedHashMap<>();
		m.put("x", wp.getX());
		m.put("y", wp.getY());
		m.put("plane", wp.getPlane());
		return m;
	}

	private String hitsplatTypeName(int type)
	{
		if (type == HitsplatID.DAMAGE_ME || type == HitsplatID.DAMAGE_OTHER
			|| type == HitsplatID.DAMAGE_MAX_ME) return "damage";
		if (type == HitsplatID.BLOCK_ME || type == HitsplatID.BLOCK_OTHER) return "block";
		if (type == HitsplatID.POISON) return "poison";
		if (type == HitsplatID.VENOM) return "venom";
		if (type == HitsplatID.DISEASE || type == HitsplatID.DISEASE_BLOCKED) return "disease";
		if (type == HitsplatID.HEAL) return "heal";
		if (type == HitsplatID.PRAYER_DRAIN) return "prayer_drain";
		if (type == HitsplatID.BLEED) return "bleed";
		if (type == HitsplatID.BURN) return "burn";
		if (type == HitsplatID.DOOM) return "doom";
		if (type == HitsplatID.CORRUPTION) return "corruption";
		if (type == HitsplatID.SANITY_DRAIN) return "sanity_drain";
		if (type == HitsplatID.SANITY_RESTORE) return "sanity_restore";
		return "unknown_" + type;
	}

	private String skullName(int skull)
	{
		if (skull == SkullIcon.NONE) return null;
		if (skull == SkullIcon.SKULL) return "skull";
		if (skull == SkullIcon.SKULL_FIGHT_PIT) return "skull_fight_pit";
		if (skull == SkullIcon.SKULL_HIGH_RISK) return "skull_high_risk";
		if (skull == SkullIcon.FORINTHRY_SURGE) return "forinthry_surge";
		if (skull >= SkullIcon.LOOT_KEYS_ONE && skull <= SkullIcon.LOOT_KEYS_FIVE)
			return "loot_keys_" + (skull - SkullIcon.LOOT_KEYS_ONE + 1);
		return "skull_" + skull;
	}

	private String iconToAccountType(String name)
	{
		if (name == null) return null;
		if (name.contains("<img=2>")) return "ironman";
		if (name.contains("<img=3>")) return "ultimate_ironman";
		if (name.contains("<img=10>")) return "hardcore_ironman";
		if (name.contains("<img=41>")) return "group_ironman";
		if (name.contains("<img=42>")) return "hardcore_group_ironman";
		if (name.contains("<img=43>")) return "unranked_group_ironman";
		return null;
	}

	private String gameStateName(GameState state)
	{
		switch (state)
		{
			case LOGGED_IN: return "logged_in";
			case LOGIN_SCREEN: return "login_screen";
			case LOADING: return "loading";
			case CONNECTION_LOST: return "connection_lost";
			case HOPPING: return "hopping";
			default: return state.name().toLowerCase();
		}
	}

	// ── Spawn / Despawn ─────────────────────────────────────────

	@Subscribe
	public void onNpcSpawned(NpcSpawned event)
	{
		if (!config.spawnDespawn()) return;

		NPC npc = event.getNpc();
		Map<String, Object> payload = new LinkedHashMap<>();
		payload.put("action", "spawn");
		payload.put("entity", entityMap(npc));
		emit("spawn_despawn", payload, "spawn " + entityName(npc));
	}

	@Subscribe
	public void onNpcDespawned(NpcDespawned event)
	{
		if (!config.spawnDespawn()) return;

		NPC npc = event.getNpc();
		String reason = recentDeaths.contains(npc) ? "death" : "unknown";

		Map<String, Object> payload = new LinkedHashMap<>();
		payload.put("action", "despawn");
		payload.put("entity", entityMap(npc));
		payload.put("reason", reason);
		emit("spawn_despawn", payload, "despawn " + entityName(npc) + " (" + reason + ")");

		npcPositions.remove(npc.getIndex());
		npcAnimations.remove(npc.getIndex());
		npcGraphics.remove(npc.getIndex());
		recentDeaths.remove(npc);
	}

	@Subscribe
	public void onPlayerSpawned(PlayerSpawned event)
	{
		if (!config.spawnDespawn()) return;

		Player player = event.getPlayer();
		Map<String, Object> payload = new LinkedHashMap<>();
		payload.put("action", "spawn");
		payload.put("entity", entityMap(player));
		emit("spawn_despawn", payload, "spawn " + entityName(player));
	}

	@Subscribe
	public void onPlayerDespawned(PlayerDespawned event)
	{
		if (!config.spawnDespawn()) return;

		Player player = event.getPlayer();
		String reason = recentDeaths.contains(player) ? "death" : "unknown";

		Map<String, Object> payload = new LinkedHashMap<>();
		payload.put("action", "despawn");
		payload.put("entity", entityMap(player));
		payload.put("reason", reason);
		emit("spawn_despawn", payload, "despawn " + entityName(player) + " (" + reason + ")");

		if (player.getName() != null)
		{
			playerPositions.remove(player.getName());
			playerAnimations.remove(player.getName());
			playerGraphics.remove(player.getName());
		}
		recentDeaths.remove(player);
	}

	@Subscribe
	public void onActorDeath(ActorDeath event)
	{
		recentDeaths.add(event.getActor());
	}

	// ── Movement (delta-only, polled on GameTick) ───────────────

	@Subscribe
	public void onGameTick(GameTick event)
	{
		recentDeaths.clear();

		if (!config.movement()) return;

		// NPC movements
		for (NPC npc : client.getNpcs())
		{
			if (npc == null || npc.getName() == null) continue;

			WorldPoint current = npc.getWorldLocation();
			WorldPoint previous = npcPositions.get(npc.getIndex());

			if (previous != null && !current.equals(previous))
			{
				Map<String, Object> payload = new LinkedHashMap<>();
				payload.put("entity", entityMap(npc));
				payload.put("from", positionMap(previous));
				payload.put("to", positionMap(current));
				emit("movement", payload,
					entityName(npc) + " moved to " + current.getX() + "," + current.getY());
			}

			npcPositions.put(npc.getIndex(), current);
		}

		// Local player — use getLocalPlayer() as sole source of truth
		Player local = client.getLocalPlayer();
		if (local != null && local.getName() != null)
		{
			WorldPoint current = local.getWorldLocation();
			WorldPoint previous = playerPositions.get(local.getName());

			if (previous != null && !current.equals(previous))
			{
				Map<String, Object> payload = new LinkedHashMap<>();
				payload.put("entity", entityMap(local));
				payload.put("from", positionMap(previous));
				payload.put("to", positionMap(current));
				emit("movement", payload,
					entityName(local) + " moved to " + current.getX() + "," + current.getY());
			}

			playerPositions.put(local.getName(), current);
		}

		// Other players — skip local player by name to avoid dual-source position conflict
		// (reference equality fails: getPlayers() returns different object than getLocalPlayer())
		String localName = (local != null) ? local.getName() : null;
		for (Player player : client.getPlayers())
		{
			if (player == null || player.getName() == null) continue;
			if (player.getName().equals(localName)) continue;

			WorldPoint current = player.getWorldLocation();
			WorldPoint previous = playerPositions.get(player.getName());

			if (previous != null && !current.equals(previous))
			{
				Map<String, Object> payload = new LinkedHashMap<>();
				payload.put("entity", entityMap(player));
				payload.put("from", positionMap(previous));
				payload.put("to", positionMap(current));
				emit("movement", payload,
					entityName(player) + " moved to " + current.getX() + "," + current.getY());
			}

			playerPositions.put(player.getName(), current);
		}
	}

	// ── Damage ──────────────────────────────────────────────────

	@Subscribe
	public void onHitsplatApplied(HitsplatApplied event)
	{
		if (!config.damage()) return;

		String typeName = hitsplatTypeName(event.getHitsplat().getHitsplatType());
		int amount = event.getHitsplat().getAmount();

		Map<String, Object> payload = new LinkedHashMap<>();
		payload.put("target", entityMap(event.getActor()));
		payload.put("amount", amount);
		payload.put("type", typeName);
		payload.put("is_mine", event.getHitsplat().isMine());
		emit("damage", payload,
			entityName(event.getActor()) + " hit " + amount + " (" + typeName + ")");
	}

	// ── Stat Change ─────────────────────────────────────────────

	@Subscribe
	public void onStatChanged(StatChanged event)
	{
		if (!config.statChange()) return;

		Skill skill = event.getSkill();
		int currentLevel = event.getLevel();
		Integer prevLevel = previousLevels.get(skill);
		boolean leveledUp = prevLevel != null && currentLevel > prevLevel;
		previousLevels.put(skill, currentLevel);

		Map<String, Object> payload = new LinkedHashMap<>();
		payload.put("skill", skill.getName());
		payload.put("xp", event.getXp());
		payload.put("level", currentLevel);
		payload.put("boosted_level", event.getBoostedLevel());
		payload.put("leveled_up", leveledUp);

		String summary = skill.getName() + " xp=" + event.getXp() + " lvl=" + currentLevel;
		if (leveledUp) summary += " LEVEL UP!";
		emit("stat_change", payload, summary);
	}

	// ── Action State (deduped) ──────────────────────────────────

	@Subscribe
	public void onAnimationChanged(AnimationChanged event)
	{
		if (!config.actionState()) return;

		Actor actor = event.getActor();
		int animId = actor.getAnimation();

		// Dedup: only emit if animation actually changed for this actor
		Integer prevAnim;
		if (actor instanceof NPC)
		{
			int idx = ((NPC) actor).getIndex();
			prevAnim = npcAnimations.put(idx, animId);
		}
		else if (actor instanceof Player)
		{
			String name = actor.getName();
			if (name == null) return;
			prevAnim = playerAnimations.put(name, animId);
		}
		else
		{
			return;
		}

		if (prevAnim != null && prevAnim == animId) return;

		Map<String, Object> payload = new LinkedHashMap<>();
		payload.put("entity", entityMap(actor));
		payload.put("change_type", "animation");
		payload.put("animation_id", animId);

		String desc = animId == -1 ? "idle" : String.valueOf(animId);
		emit("action_state", payload, entityName(actor) + " anim=" + desc);
	}

	@Subscribe
	public void onGraphicChanged(GraphicChanged event)
	{
		if (!config.actionState()) return;

		Actor actor = event.getActor();
		int gfxId = actor.getGraphic();

		// Dedup: only emit if graphic actually changed for this actor
		Integer prevGfx;
		if (actor instanceof NPC)
		{
			int idx = ((NPC) actor).getIndex();
			prevGfx = npcGraphics.put(idx, gfxId);
		}
		else if (actor instanceof Player)
		{
			String name = actor.getName();
			if (name == null) return;
			prevGfx = playerGraphics.put(name, gfxId);
		}
		else
		{
			return;
		}

		if (prevGfx != null && prevGfx == gfxId) return;

		Map<String, Object> payload = new LinkedHashMap<>();
		payload.put("entity", entityMap(actor));
		payload.put("change_type", "graphic");
		payload.put("graphic_id", gfxId);
		emit("action_state", payload, entityName(actor) + " gfx=" + gfxId);
	}

	// ── Menu Action ─────────────────────────────────────────────

	@Subscribe
	public void onMenuOptionClicked(MenuOptionClicked event)
	{
		if (!config.menuAction()) return;

		String target = Text.removeTags(event.getMenuTarget());
		Map<String, Object> payload = new LinkedHashMap<>();
		payload.put("option", event.getMenuOption());
		payload.put("target", target);
		payload.put("action_type", event.getMenuAction().name());
		payload.put("id", event.getId());
		payload.put("is_item_op", event.isItemOp());
		if (event.isItemOp())
		{
			payload.put("item_id", event.getItemId());
		}
		emit("menu_action", payload, event.getMenuOption() + " -> " + target);
	}

	// ── Item Change ─────────────────────────────────────────────

	@Subscribe
	public void onItemContainerChanged(ItemContainerChanged event)
	{
		if (!config.itemChange()) return;

		Map<String, Object> payload = new LinkedHashMap<>();
		payload.put("change_type", "container");
		payload.put("container_id", event.getContainerId());

		List<Map<String, Object>> items = new ArrayList<>();
		ItemContainer container = event.getItemContainer();
		int count = 0;
		if (container != null)
		{
			for (Item item : container.getItems())
			{
				if (item.getId() == -1) continue;
				Map<String, Object> itemMap = new LinkedHashMap<>();
				itemMap.put("item_id", item.getId());
				itemMap.put("quantity", item.getQuantity());
				items.add(itemMap);
				count++;
			}
		}
		payload.put("items", items);
		emit("item_change", payload, "container " + event.getContainerId() + " (" + count + " items)");
	}

	@Subscribe
	public void onItemSpawned(ItemSpawned event)
	{
		if (!config.itemChange()) return;

		Map<String, Object> payload = new LinkedHashMap<>();
		payload.put("change_type", "ground_spawn");
		payload.put("position", positionMap(event.getTile().getWorldLocation()));
		payload.put("item_id", event.getItem().getId());
		payload.put("quantity", event.getItem().getQuantity());
		emit("item_change", payload, "ground spawn item=" + event.getItem().getId());
	}

	@Subscribe
	public void onItemDespawned(ItemDespawned event)
	{
		if (!config.itemChange()) return;

		Map<String, Object> payload = new LinkedHashMap<>();
		payload.put("change_type", "ground_despawn");
		payload.put("position", positionMap(event.getTile().getWorldLocation()));
		payload.put("item_id", event.getItem().getId());
		payload.put("quantity", event.getItem().getQuantity());
		emit("item_change", payload, "ground despawn item=" + event.getItem().getId());
	}

	// ── Chat ────────────────────────────────────────────────────

	@Subscribe
	public void onChatMessage(ChatMessage event)
	{
		if (!config.chat()) return;
		// Don't re-emit our own chat messages
		if (event.getMessage().startsWith("[GLADyS:")) return;

		String rawName = event.getName();
		String accountType = iconToAccountType(rawName);
		String cleanName = Text.removeTags(rawName);

		Map<String, Object> payload = new LinkedHashMap<>();
		payload.put("change_type", "message");
		payload.put("channel", event.getType().name().toLowerCase());
		payload.put("sender", cleanName);
		payload.put("message", event.getMessage());
		if (accountType != null)
		{
			payload.put("account_type", accountType);
		}

		String summary = event.getType().name().toLowerCase() + ": " + cleanName;
		if (accountType != null) summary += " [" + accountType + "]";
		summary += ": " + event.getMessage();
		emit("chat", payload, summary);
	}

	@Subscribe
	public void onOverheadTextChanged(OverheadTextChanged event)
	{
		if (!config.chat()) return;

		Map<String, Object> payload = new LinkedHashMap<>();
		payload.put("change_type", "overhead");
		payload.put("entity", entityMap(event.getActor()));
		payload.put("text", event.getOverheadText());
		emit("chat", payload, entityName(event.getActor()) + " says: " + event.getOverheadText());
	}

	// ── Session State ───────────────────────────────────────────

	@Subscribe
	public void onGameStateChanged(GameStateChanged event)
	{
		if (!config.sessionState()) return;

		String stateName = gameStateName(event.getGameState());
		Map<String, Object> payload = new LinkedHashMap<>();
		payload.put("change_type", "game_state");
		payload.put("state", stateName);

		// Include account info on login
		if (event.getGameState() == GameState.LOGGED_IN)
		{
			payload.put("account_type", client.getAccountType().name().toLowerCase());
			Player local = client.getLocalPlayer();
			if (local != null)
			{
				payload.put("player_name", local.getName());
				payload.put("combat_level", local.getCombatLevel());
			}
		}

		emit("session_state", payload, "state=" + stateName);
	}

	@Subscribe
	public void onFocusChanged(FocusChanged event)
	{
		if (!config.sessionState()) return;

		Map<String, Object> payload = new LinkedHashMap<>();
		payload.put("change_type", "focus");
		payload.put("focused", event.isFocused());
		emit("session_state", payload, "focus=" + event.isFocused());
	}

	@Subscribe
	public void onWorldChanged(WorldChanged event)
	{
		if (!config.sessionState()) return;

		Map<String, Object> payload = new LinkedHashMap<>();
		payload.put("change_type", "world_change");
		emit("session_state", payload, "world changed");
	}

	@Subscribe
	public void onGrandExchangeOfferChanged(GrandExchangeOfferChanged event)
	{
		if (!config.sessionState()) return;

		Map<String, Object> payload = new LinkedHashMap<>();
		payload.put("change_type", "ge_offer");
		payload.put("slot", event.getSlot());
		if (event.getOffer() != null)
		{
			Map<String, Object> offer = new LinkedHashMap<>();
			offer.put("state", event.getOffer().getState().name());
			offer.put("item_id", event.getOffer().getItemId());
			offer.put("quantity_sold", event.getOffer().getQuantitySold());
			offer.put("total_quantity", event.getOffer().getTotalQuantity());
			offer.put("price", event.getOffer().getPrice());
			offer.put("spent", event.getOffer().getSpent());
			payload.put("offer", offer);
		}
		emit("session_state", payload, "GE slot " + event.getSlot());
	}

	// ── Sound (disabled by default) ─────────────────────────────

	@Subscribe
	public void onSoundEffectPlayed(SoundEffectPlayed event)
	{
		if (!config.sound()) return;

		Map<String, Object> payload = new LinkedHashMap<>();
		payload.put("change_type", "sound");
		payload.put("sound_id", event.getSoundId());
		payload.put("delay", event.getDelay());
		if (event.getSource() != null)
		{
			payload.put("source", entityMap(event.getSource()));
		}
		emit("sound", payload, "sfx=" + event.getSoundId());
	}

	@Subscribe
	public void onAreaSoundEffectPlayed(AreaSoundEffectPlayed event)
	{
		if (!config.sound()) return;

		Map<String, Object> payload = new LinkedHashMap<>();
		payload.put("change_type", "area_sound");
		payload.put("sound_id", event.getSoundId());
		payload.put("range", event.getRange());
		payload.put("delay", event.getDelay());
		Map<String, Object> pos = new LinkedHashMap<>();
		pos.put("x", event.getSceneX());
		pos.put("y", event.getSceneY());
		payload.put("position", pos);
		if (event.getSource() != null)
		{
			payload.put("source", entityMap(event.getSource()));
		}
		emit("sound", payload, "area_sfx=" + event.getSoundId());
	}

	// ── Misc (disabled by default) ──────────────────────────────

	@Subscribe
	public void onInteractingChanged(InteractingChanged event)
	{
		if (!config.misc()) return;

		Map<String, Object> payload = new LinkedHashMap<>();
		payload.put("change_type", "interacting_changed");
		payload.put("source", entityMap(event.getSource()));
		if (event.getTarget() != null)
		{
			payload.put("target", entityMap(event.getTarget()));
		}
		else
		{
			payload.put("target", null);
		}
		String targetName = event.getTarget() != null ? entityName(event.getTarget()) : "nothing";
		emit("misc", payload, entityName(event.getSource()) + " -> " + targetName);
	}
}
