package net.runelite.client.plugins.gladys;

import net.runelite.client.config.Config;
import net.runelite.client.config.ConfigGroup;
import net.runelite.client.config.ConfigItem;
import net.runelite.client.config.ConfigSection;

@ConfigGroup("gladys")
public interface GladysSensorConfig extends Config
{
	@ConfigSection(
		name = "Connection",
		description = "GLADyS orchestrator connection settings",
		position = 0
	)
	String connectionSection = "connection";

	@ConfigItem(
		keyName = "orchestratorHost",
		name = "Orchestrator Host",
		description = "Hostname of the GLADyS orchestrator",
		section = connectionSection,
		position = 0
	)
	default String orchestratorHost()
	{
		return "localhost";
	}

	@ConfigItem(
		keyName = "orchestratorPort",
		name = "Orchestrator Port",
		description = "gRPC port of the GLADyS orchestrator",
		section = connectionSection,
		position = 1
	)
	default int orchestratorPort()
	{
		return 50051;
	}

	@ConfigSection(
		name = "Event Categories",
		description = "Toggle which event types the sensor emits",
		position = 1
	)
	String eventSection = "events";

	@ConfigItem(
		keyName = "spawnDespawn",
		name = "Spawn / Despawn",
		description = "Entity spawn and despawn events",
		section = eventSection,
		position = 0
	)
	default boolean spawnDespawn()
	{
		return true;
	}

	@ConfigItem(
		keyName = "movement",
		name = "Movement",
		description = "Entity position change events (delta-only)",
		section = eventSection,
		position = 1
	)
	default boolean movement()
	{
		return true;
	}

	@ConfigItem(
		keyName = "damage",
		name = "Damage",
		description = "Hitsplat events",
		section = eventSection,
		position = 2
	)
	default boolean damage()
	{
		return true;
	}

	@ConfigItem(
		keyName = "statChange",
		name = "Stat Change",
		description = "Skill XP, level, and boost changes",
		section = eventSection,
		position = 3
	)
	default boolean statChange()
	{
		return true;
	}

	@ConfigItem(
		keyName = "actionState",
		name = "Action State",
		description = "Animation and graphic/spotanim changes",
		section = eventSection,
		position = 4
	)
	default boolean actionState()
	{
		return true;
	}

	@ConfigItem(
		keyName = "menuAction",
		name = "Menu Action",
		description = "Player menu clicks (attack, use, pick-up, etc.)",
		section = eventSection,
		position = 5
	)
	default boolean menuAction()
	{
		return true;
	}

	@ConfigItem(
		keyName = "itemChange",
		name = "Item Change",
		description = "Inventory, equipment, and ground item changes",
		section = eventSection,
		position = 6
	)
	default boolean itemChange()
	{
		return true;
	}

	@ConfigItem(
		keyName = "chat",
		name = "Chat",
		description = "Chat messages, overhead text, social events",
		section = eventSection,
		position = 7
	)
	default boolean chat()
	{
		return true;
	}

	@ConfigItem(
		keyName = "sessionState",
		name = "Session State",
		description = "Login, logout, world hop, focus, GE events",
		section = eventSection,
		position = 8
	)
	default boolean sessionState()
	{
		return true;
	}

	@ConfigItem(
		keyName = "sound",
		name = "Sound",
		description = "Sound effect events (high volume in busy areas)",
		section = eventSection,
		position = 9
	)
	default boolean sound()
	{
		return false;
	}

	@ConfigItem(
		keyName = "misc",
		name = "Misc",
		description = "Experimental: objects, projectiles, varbits, interacting changes",
		section = eventSection,
		position = 10
	)
	default boolean misc()
	{
		return false;
	}
}
