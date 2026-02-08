// ==UserScript==
// @name         GLADyS Sudoku Driver
// @namespace    http://tampermonkey.net/
// @version      0.1
// @description  Extracts Websudoku state for GLADyS
// @author       Gemini
// @match        https://*.websudoku.com/*
// @grant        GM_xmlhttpRequest
// ==/UserScript==

(function() {
    'use strict';

    const SENSOR_URL = 'http://localhost:8701/event';
    const POLL_INTERVAL = 2000; // Backup polling

    let lastBoardState = "";
    let solution = "";
    let puzzleId = "";
    let difficulty = 0;

    // --- State Extraction ---

    function getBoardString() {
        let board = "";
        // Websudoku uses inputs with IDs like 'f00', 'f01' ... 'f88' where x is col, y is row?
        // Or generic iteration. The grid is 9x9.
        // Let's assume standard reading order: Row 0 (Col 0-8), Row 1...
        
        for (let row = 0; row < 9; row++) {
            for (let col = 0; col < 9; col++) {
                // IDs are typically f{col}{row} on websudoku.com? 
                // Let's try to find input by generic selector if ID varies
                // Actually, standard iteration is safest if we can find the table
                // But let's look for the input IDs 'f00' -> 'f88' (col, row)
                // Note: Websudoku actually uses `id="f{col}{row}"` (x, y)
                
                const id = `f${col}${row}`; 
                const input = document.getElementById(id);
                if (input) {
                    const val = input.value;
                    if (val && /^[1-9]$/.test(val)) {
                        board += val;
                    } else {
                        board += "0";
                    }
                } else {
                    board += "0";
                }
            }
        }
        return board;
    }

    function getSolutionString() {
        const cheatInput = document.getElementsByName("cheat")[0];
        return cheatInput ? cheatInput.value : "".padEnd(81, '0');
    }

    function getMeta() {
        // Extract ID and Difficulty from text like "Puzzle 1,234,567 - Easy"
        // Usually in an element, maybe generic text search
        const bodyText = document.body.innerText;
        
        // Find ID
        const idMatch = bodyText.match(/Puzzle (\d+(?:,\d+)*)/);
        const pId = idMatch ? idMatch[1].replace(/,/g, '') : "unknown";

        // Find Difficulty
        let diff = 1;
        if (bodyText.includes("Easy")) diff = 1;
        else if (bodyText.includes("Medium")) diff = 2;
        else if (bodyText.includes("Hard")) diff = 3;
        else if (bodyText.includes("Evil")) diff = 4;
        
        return { pId, diff };
    }

    // --- Communication ---

    function sendEvent(eventType, data) {
        const payload = {
            event_type: eventType,
            timestamp: new Date().toISOString(),
            data: data
        };

        console.log(`[GLADyS] Sending ${eventType}`, payload);

        GM_xmlhttpRequest({
            method: "POST",
            url: SENSOR_URL,
            headers: { "Content-Type": "application/json" },
            data: JSON.stringify(payload),
            onload: function(response) {
                // console.log("Response:", response.responseText);
            },
            onerror: function(err) {
                console.error("GLADyS Sensor Error:", err);
            }
        });
    }

    // --- Logic ---

    function init() {
        console.log("[GLADyS] Driver initializing...");

        // 1. Get Static Data
        solution = getSolutionString();
        const meta = getMeta();
        puzzleId = meta.pId;
        difficulty = meta.diff;
        
        // 2. Initial State
        const currentBoard = getBoardString();
        lastBoardState = currentBoard;

        sendEvent("puzzle_start", {
            board: currentBoard,
            solution: solution,
            difficulty: difficulty,
            puzzle_id: puzzleId
        });

        // 3. Attach Listeners
        for (let row = 0; row < 9; row++) {
            for (let col = 0; col < 9; col++) {
                const id = `f${col}${row}`;
                const input = document.getElementById(id);
                if (input && !input.readOnly) {
                    input.addEventListener('change', (e) => onCellChange(row, col, e.target.value));
                    // Also listen for 'input' for real-time, but 'change' is safer for "committed" answers
                    // Spec says "detect when user enters a number". 'input' fires immediately.
                    input.addEventListener('input', (e) => {
                        // Optional: Debounce if needed, but 'change' covers the commit
                    });
                }
            }
        }
        
        // 4. Hook "How am I doing?" or completion if possible
        // For now, check completion on every move
    }

    function onCellChange(row, col, value) {
        if (!value || !/^[1-9]$/.test(value)) return; // Ignore clear or invalid

        const currentBoard = getBoardString();
        lastBoardState = currentBoard;
        
        // Check correctness locally against cheat string
        // solution string is 81 chars, index = row * 9 + col
        const idx = row * 9 + col;
        const correctChar = solution[idx];
        const isCorrect = (value === correctChar);

        sendEvent("cell_filled", {
            board: currentBoard,
            row: row,
            col: col,
            value: parseInt(value),
            is_correct: isCorrect
        });

        checkCompletion(currentBoard);
    }

    function checkCompletion(board) {
        if (!board.includes("0")) {
             if (board === solution) {
                 // Success!
                 // In a real scenario, we might want to scrape the time from the page's timer
                 // But for now, we'll let the sensor timestamp handle the "when"
                 // and maybe scrape the timer text if we can find it.
                 // Websudoku timer is often in element with ID 'timer'?
                 
                 let seconds = 0;
                 const timerEl = document.getElementById("timer");
                 if (timerEl) {
                     // specific parsing if needed, but let's just send the event
                 }

                 sendEvent("puzzle_complete", {
                     board: board,
                     solution: solution,
                     time_seconds: 0, // Placeholder, difficult to scrape accurately without specific selector
                     error_count: 0 // Placeholder
                 });
             }
        }
    }

    // Wait for load
    window.addEventListener('load', () => {
        // Websudoku frames... sometimes the puzzle is in a frame?
        // The URL pattern matches *.websudoku.com/* so we should run on the main page or frame
        // Check if we have the board
        if (document.getElementById("f00")) {
            init();
        }
    });

})();
