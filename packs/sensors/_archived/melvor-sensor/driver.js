// ==UserScript==
// @name         GLADyS Melvor Driver
// @namespace    http://tampermonkey.net/
// @version      0.1
// @description  Extracts Melvor Idle state for GLADyS
// @author       Gemini
// @match        https://melvoridle.com/*
// @match        https://www.melvoridle.com/*
// @grant        GM_xmlhttpRequest
// ==/UserScript==

(function() {
    'use strict';

    const SENSOR_URL = 'http://localhost:8702/event';
    const POLL_INTERVAL = 1000;

    let lastEnemy = null;
    let lastPlayerHP = -1;
    let lastSkill = null;
    let lastXP = {}; // Map skillID -> xp

    // --- Communication ---

    function sendEvent(eventType, data) {
        const payload = {
            event_type: eventType,
            timestamp: new Date().toISOString(),
            data: data
        };

        // console.log(`[GLADyS] Sending ${eventType}`, payload);

        GM_xmlhttpRequest({
            method: "POST",
            url: SENSOR_URL,
            headers: { "Content-Type": "application/json" },
            data: JSON.stringify(payload),
            onerror: function(err) {
                console.error("GLADyS Sensor Error:", err);
            }
        });
    }

    // --- Hooks ---

    function hookCombat() {
        if (!window.game || !window.game.combat) return;

        // Hook onEnemyDeath
        // Note: Function names might vary by version. This is a best-guess based on API patterns.
        // We'll try to wrap the method if it exists.
        
        if (typeof window.game.combat.onEnemyDeath === 'function') {
            const originalDeath = window.game.combat.onEnemyDeath;
            window.game.combat.onEnemyDeath = function() {
                // Capture state before death logic clears it?
                const enemy = window.game.combat.enemy;
                const monsterName = enemy.monster ? enemy.monster.name : "Unknown";
                
                // Call original
                const res = originalDeath.apply(this, arguments);
                
                // Send event
                // Loot is hard to track synchronously here without parsing the drop table
                // We'll send what we know
                sendEvent("combat_killed", {
                    monster_name: monsterName,
                    loot: [], // Placeholder
                    xp_gained: 0 // Placeholder
                });
                return res;
            };
        }
        
        // Hook onPlayerDeath
        if (typeof window.game.combat.onPlayerDeath === 'function') {
            const originalPlayerDeath = window.game.combat.onPlayerDeath;
            window.game.combat.onPlayerDeath = function() {
                const enemy = window.game.combat.enemy;
                const monsterName = enemy.monster ? enemy.monster.name : "Unknown";
                
                sendEvent("combat_died", {
                    monster_name: monsterName,
                    player_hp: 0
                });
                
                return originalPlayerDeath.apply(this, arguments);
            }
        }
    }

    // --- Polling Fallback & State Tracking ---

    function pollState() {
        if (!window.game) return;

        // 1. Combat State
        if (window.game.combat && window.game.combat.isActive) {
            const enemy = window.game.combat.enemy;
            const player = window.game.combat.player;
            
            if (enemy && enemy.monster) {
                const monsterName = enemy.monster.name;
                
                // New fight?
                if (monsterName !== lastEnemy) {
                    lastEnemy = monsterName;
                    const area = window.game.combat.selectedArea ? window.game.combat.selectedArea.name : "Unknown Area";
                    
                    sendEvent("combat_started", {
                        monster_name: monsterName,
                        combat_area: area,
                        player_hp: player.hitpoints,
                        player_attack: player.stats.attack || 0,
                        player_defence: player.stats.defence || 0
                    });
                }
            } else {
                lastEnemy = null;
            }
        }

        // 2. Skill State (XP & Levels)
        // Iterate all skills
        if (window.game.skills) {
            // game.skills might be an array or object depending on version
            // Usually game.skills.forEach works if it's the manager, or game.mining etc.
            // Let's assume game.skills is iterable or we iterate known skills
            
            const skills = window.game.skills; 
            // If it's a Set or Map or Array
            // Let's try generic iteration over standard skill IDs if possible
            // Or use game.mining, game.woodcutting if they exist on game object
            
            // Simpler: Check active action
            const activeAction = window.game.activeAction;
            if (activeAction) {
                // Determine skill from action
                // This is complex. Let's just monitor XP of all skills.
            }
        }
    }

    function init() {
        console.log("[GLADyS] Melvor Driver Initializing...");
        
        // Wait for game load
        const checkGame = setInterval(() => {
            if (window.game && window.isLoaded) {
                clearInterval(checkGame);
                console.log("[GLADyS] Game loaded, hooking...");
                hookCombat();
                setInterval(pollState, POLL_INTERVAL);
            }
        }, 1000);
    }

    if (document.readyState === 'complete') {
        init();
    } else {
        window.addEventListener('load', init);
    }

})();
