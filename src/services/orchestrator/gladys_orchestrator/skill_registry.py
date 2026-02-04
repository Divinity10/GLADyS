"""Skill Registry for GLADyS.

Loads skill manifests from plugins directory and indexes capabilities for discovery.
Used by Executive to find skills that can perform specific actions.

This is distinct from registry.py which handles runtime component registration.
SkillRegistry handles static skill manifest loading and capability indexing.

Skills are:
1. Loaded from YAML manifest files on disk
2. Indexed in-memory for fast capability queries
3. Synced to PostgreSQL for persistence and cross-component access
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from gladys_common import get_logger

logger = get_logger(__name__)


@dataclass
class MethodInfo:
    """Information about a skill method."""

    name: str
    description: str
    capabilities: list[str]  # Which high-level capabilities this method provides
    parameters: list[dict[str, Any]]
    returns: dict[str, Any]


@dataclass
class SkillInfo:
    """Information about a loaded skill."""

    plugin_id: str
    name: str
    version: str
    description: str
    category: str  # style_modifier, domain_expertise, capability, etc.
    capabilities: list[str]  # High-level capabilities (for discovery)
    methods: list[MethodInfo]  # Callable methods (for capability skills)
    activation: dict[str, Any]  # When this skill activates
    manifest_path: Path
    raw_manifest: dict[str, Any]


@dataclass
class CapabilityMatch:
    """Result of a capability query."""

    skill_id: str
    skill_name: str
    method_name: str
    method_description: str
    capability: str
    parameters: list[dict[str, Any]]
    returns: dict[str, Any]


class SkillRegistry:
    """
    Registry for skill manifests.

    Loads skill manifests from disk and indexes capabilities for discovery.

    Usage:
        registry = SkillRegistry()
        registry.load_from_directory(Path("packs/skills"))

        # Find skills that can check player status
        matches = registry.query_capability("check_player_status")
        # Returns: [CapabilityMatch(skill_id="minecraft-skill", method_name="check_player", ...)]
    """

    def __init__(self):
        self._skills: dict[str, SkillInfo] = {}  # plugin_id -> SkillInfo
        self._capability_index: dict[str, list[tuple[str, str]]] = {}  # capability -> [(skill_id, method_name)]

    def load_from_directory(self, skills_dir: Path) -> int:
        """
        Load all skill manifests from a directory.

        Args:
            skills_dir: Path to skills directory (e.g., packs/skills)

        Returns:
            Number of skills loaded
        """
        if not skills_dir.exists():
            logger.warning("Skills directory does not exist", path=str(skills_dir))
            return 0

        loaded = 0
        for manifest_path in skills_dir.glob("*/manifest.yaml"):
            try:
                self.load_manifest(manifest_path)
                loaded += 1
            except Exception as e:
                logger.error("Failed to load manifest", path=str(manifest_path), error=str(e))

        logger.info("Loaded skills from directory", count=loaded, path=str(skills_dir))
        return loaded

    def load_manifest(self, manifest_path: Path) -> SkillInfo:
        """
        Load a single skill manifest.

        Args:
            manifest_path: Path to manifest.yaml file

        Returns:
            SkillInfo object

        Raises:
            ValueError: If manifest is invalid
            FileNotFoundError: If manifest doesn't exist
        """
        with open(manifest_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        # Validate required fields
        if "plugin" not in raw:
            raise ValueError(f"Missing 'plugin' section in {manifest_path}")

        plugin = raw["plugin"]
        required_fields = ["id", "name", "version", "type"]
        for field_name in required_fields:
            if field_name not in plugin:
                raise ValueError(f"Missing required field 'plugin.{field_name}' in {manifest_path}")

        if plugin["type"] != "skill":
            raise ValueError(f"Expected type 'skill', got '{plugin['type']}' in {manifest_path}")

        skill_section = raw.get("skill", {})

        # Parse methods (for capability skills)
        methods: list[MethodInfo] = []
        for method_raw in skill_section.get("methods", []):
            method = MethodInfo(
                name=method_raw.get("name", ""),
                description=method_raw.get("description", ""),
                capabilities=method_raw.get("capabilities", []),
                parameters=method_raw.get("parameters", []),
                returns=method_raw.get("returns", {}),
            )
            methods.append(method)

        # Create SkillInfo
        skill = SkillInfo(
            plugin_id=plugin["id"],
            name=plugin["name"],
            version=plugin["version"],
            description=plugin.get("description", ""),
            category=skill_section.get("category", ""),
            capabilities=skill_section.get("capabilities", []),
            methods=methods,
            activation=skill_section.get("activation", {}),
            manifest_path=manifest_path,
            raw_manifest=raw,
        )

        # Register skill
        self._skills[skill.plugin_id] = skill

        # Index capabilities
        for cap in skill.capabilities:
            if cap not in self._capability_index:
                self._capability_index[cap] = []
            # Find methods that provide this capability
            for method in methods:
                if cap in method.capabilities:
                    self._capability_index[cap].append((skill.plugin_id, method.name))
            # If no method explicitly provides this capability, index skill without method
            if not any(cap in m.capabilities for m in methods):
                self._capability_index[cap].append((skill.plugin_id, ""))

        logger.debug("Loaded skill", plugin_id=skill.plugin_id, category=skill.category, method_count=len(methods))
        return skill

    def query_capability(self, capability: str) -> list[CapabilityMatch]:
        """
        Find skills that provide a specific capability.

        Args:
            capability: The capability to search for (e.g., "check_player_status")

        Returns:
            List of CapabilityMatch objects describing skills/methods that can provide it
        """
        matches: list[CapabilityMatch] = []

        if capability not in self._capability_index:
            return matches

        for skill_id, method_name in self._capability_index[capability]:
            skill = self._skills.get(skill_id)
            if not skill:
                continue

            # Find the method (if any)
            method = next((m for m in skill.methods if m.name == method_name), None)

            match = CapabilityMatch(
                skill_id=skill_id,
                skill_name=skill.name,
                method_name=method_name,
                method_description=method.description if method else skill.description,
                capability=capability,
                parameters=method.parameters if method else [],
                returns=method.returns if method else {},
            )
            matches.append(match)

        return matches

    def query_capabilities_fuzzy(self, query: str) -> list[CapabilityMatch]:
        """
        Find skills using fuzzy text matching on capabilities.

        Useful for natural language queries like "what can check if a player is online?"

        Args:
            query: Natural language query

        Returns:
            List of CapabilityMatch objects
        """
        query_lower = query.lower()
        query_words = set(query_lower.split())

        matches: list[CapabilityMatch] = []
        seen: set[tuple[str, str]] = set()

        # Score each capability by word overlap
        scored: list[tuple[int, str]] = []
        for cap in self._capability_index:
            cap_words = set(cap.lower().replace("_", " ").split())
            overlap = len(query_words & cap_words)
            if overlap > 0:
                scored.append((overlap, cap))

        # Sort by score (descending)
        scored.sort(reverse=True)

        # Return matches for top capabilities
        for _, cap in scored:
            for match in self.query_capability(cap):
                key = (match.skill_id, match.method_name)
                if key not in seen:
                    seen.add(key)
                    matches.append(match)

        return matches

    def get_skill(self, skill_id: str) -> SkillInfo | None:
        """Get skill info by ID."""
        return self._skills.get(skill_id)

    def get_all_skills(self) -> list[SkillInfo]:
        """Get all loaded skills."""
        return list(self._skills.values())

    def get_all_capabilities(self) -> list[str]:
        """Get all indexed capabilities."""
        return list(self._capability_index.keys())

    @property
    def skill_count(self) -> int:
        """Number of loaded skills."""
        return len(self._skills)

    @property
    def capability_count(self) -> int:
        """Number of indexed capabilities."""
        return len(self._capability_index)

    def sync_to_db(self, conn) -> int:
        """
        Sync loaded skills to PostgreSQL database.

        Args:
            conn: psycopg2 connection object

        Returns:
            Number of skills synced
        """
        if not self._skills:
            return 0

        synced = 0
        with conn.cursor() as cur:
            for skill in self._skills.values():
                # Convert methods to JSON-serializable format
                methods_json = [
                    {
                        "name": m.name,
                        "description": m.description,
                        "capabilities": m.capabilities,
                        "parameters": m.parameters,
                        "returns": m.returns,
                    }
                    for m in skill.methods
                ]

                # Upsert skill
                cur.execute(
                    """
                    INSERT INTO skills (
                        plugin_id, name, version, description, category,
                        capabilities, activation, methods, manifest, manifest_path
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (plugin_id) DO UPDATE SET
                        name = EXCLUDED.name,
                        version = EXCLUDED.version,
                        description = EXCLUDED.description,
                        category = EXCLUDED.category,
                        capabilities = EXCLUDED.capabilities,
                        activation = EXCLUDED.activation,
                        methods = EXCLUDED.methods,
                        manifest = EXCLUDED.manifest,
                        manifest_path = EXCLUDED.manifest_path,
                        updated_at = NOW()
                    """,
                    (
                        skill.plugin_id,
                        skill.name,
                        skill.version,
                        skill.description,
                        skill.category,
                        skill.capabilities,
                        json.dumps(skill.activation),
                        json.dumps(methods_json),
                        json.dumps(skill.raw_manifest),
                        str(skill.manifest_path),
                    ),
                )
                synced += 1

            conn.commit()

        logger.info("Synced skills to database", count=synced)
        return synced

    @classmethod
    def load_from_db(cls, conn) -> "SkillRegistry":
        """
        Load skills from database instead of files.

        Args:
            conn: psycopg2 connection object

        Returns:
            SkillRegistry populated from database
        """
        registry = cls()

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT plugin_id, name, version, description, category,
                       capabilities, activation, methods, manifest, manifest_path
                FROM skills
                """
            )

            for row in cur.fetchall():
                (
                    plugin_id,
                    name,
                    version,
                    description,
                    category,
                    capabilities,
                    activation,
                    methods_json,
                    manifest,
                    manifest_path,
                ) = row

                # Parse methods
                methods = [
                    MethodInfo(
                        name=m["name"],
                        description=m["description"],
                        capabilities=m["capabilities"],
                        parameters=m["parameters"],
                        returns=m["returns"],
                    )
                    for m in (methods_json or [])
                ]

                skill = SkillInfo(
                    plugin_id=plugin_id,
                    name=name,
                    version=version,
                    description=description or "",
                    category=category,
                    capabilities=capabilities or [],
                    methods=methods,
                    activation=activation or {},
                    manifest_path=Path(manifest_path) if manifest_path else Path(),
                    raw_manifest=manifest or {},
                )

                # Register in memory
                registry._skills[plugin_id] = skill

                # Index capabilities
                for cap in skill.capabilities:
                    if cap not in registry._capability_index:
                        registry._capability_index[cap] = []
                    for method in methods:
                        if cap in method.capabilities:
                            registry._capability_index[cap].append((plugin_id, method.name))
                    if not any(cap in m.capabilities for m in methods):
                        registry._capability_index[cap].append((plugin_id, ""))

        logger.info("Loaded skills from database", count=registry.skill_count)
        return registry
