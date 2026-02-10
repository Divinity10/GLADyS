// --- Pending Event Tracking ---
// Events submitted but not yet responded to. Shown in queue panel.

const pendingEvents = new Map();  // event_id -> {source, text, submitted_at}
const PENDING_TIMEOUT_MS = 60000;  // 60s — fallback expiry if event never appears anywhere

function addPendingEvent(eventId, source, text) {
    pendingEvents.set(eventId, {source, text, submitted_at: Date.now()});
    updateQueuePanel();
}

function removePendingEvent(eventId) {
    pendingEvents.delete(eventId);
    updateQueuePanel();
}

// Listen for SSE messages — when a response row arrives, remove from pending
document.body.addEventListener('htmx:sseMessage', function (e) {
    // Parse the event_id from the delivered row HTML
    const match = e.detail.data && e.detail.data.match(/id="event-([^"]+)"/);
    if (match) {
        removePendingEvent(match[1]);
    }
});

// --- Queue Polling ---

let queuePollInterval = 2000;
let queuePollTimer = null;

function startQueuePolling() {
    pollQueue();
    queuePollTimer = setInterval(pollQueue, queuePollInterval);
}

function pollQueue() {
    const body = document.getElementById('queue-table-body');
    if (!body) return;

    const now = Date.now();
    const eventTable = document.getElementById('event-table-body');

    // Remove pending events that already appear in the main event table or have expired
    for (const [id, ev] of pendingEvents) {
        const inEventTable = eventTable && eventTable.querySelector('#event-' + id);
        const expired = now - ev.submitted_at > PENDING_TIMEOUT_MS;
        if (inEventTable || expired) {
            pendingEvents.delete(id);
        }
    }

    fetch('/api/queue/rows')
        .then(r => r.text())
        .then(serverHtml => {
            // Build pending rows only for events NOT already in server queue
            let pendingHtml = '';
            for (const [id, ev] of pendingEvents) {
                // Event appeared in server queue — it's been received, remove from pending
                if (serverHtml.includes(id.substring(0, 12))) {
                    pendingEvents.delete(id);
                    continue;
                }
                const age = Math.round((now - ev.submitted_at) / 1000);
                pendingHtml +=
                    '<tr class="border-b border-gray-800 text-[11px] bg-blue-900/20">' +
                    '<td class="font-mono truncate">' + id.substring(0, 12) + '&hellip;</td>' +
                    '<td><span class="px-1 bg-gray-700 rounded">' + ev.source + '</span></td>' +
                    '<td class="truncate max-w-xs">' + ev.text + '</td>' +
                    '<td class="text-blue-300">pending</td>' +
                    '<td class="text-secondary">' + age + 's</td>' +
                    '</tr>';
            }

            body.innerHTML = pendingHtml + serverHtml;
            updateQueuePanel();
        })
        .catch(() => {
            // On error, still show pending events
            const body = document.getElementById('queue-table-body');
            if (body && pendingEvents.size > 0) {
                let html = '';
                for (const [id, ev] of pendingEvents) {
                    const age = Math.round((Date.now() - ev.submitted_at) / 1000);
                    html +=
                        '<tr class="border-b border-gray-800 text-[11px] bg-blue-900/20">' +
                        '<td class="font-mono truncate">' + id.substring(0, 12) + '&hellip;</td>' +
                        '<td><span class="px-1 bg-gray-700 rounded">' + ev.source + '</span></td>' +
                        '<td class="truncate max-w-xs">' + ev.text + '</td>' +
                        '<td class="text-blue-300">pending</td>' +
                        '<td class="text-secondary">-</td>' +
                        '</tr>';
                }
                body.innerHTML = html;
                updateQueuePanel();
            } else {
                const panel = document.getElementById('queue-panel');
                if (panel) panel.style.display = 'none';
            }
        });
}

function updateQueuePanel() {
    const body = document.getElementById('queue-table-body');
    const panel = document.getElementById('queue-panel');
    const count = document.getElementById('queue-count');
    if (!body || !panel || !count) return;
    const rowCount = body.querySelectorAll('tr').length;
    count.textContent = rowCount;
    panel.style.display = rowCount > 0 ? '' : 'none';
}

function boostQueuePolling() {
    clearInterval(queuePollTimer);
    queuePollInterval = 500;
    queuePollTimer = setInterval(pollQueue, 500);
    pollQueue();
    setTimeout(() => {
        clearInterval(queuePollTimer);
        queuePollInterval = 2000;
        queuePollTimer = setInterval(pollQueue, 2000);
    }, 10000);
}

function toggleQueuePanel() {
    const body = document.getElementById('queue-body');
    const toggle = document.getElementById('queue-toggle');
    if (body.style.display === 'none') {
        body.style.display = '';
        toggle.innerHTML = '&#x25BC;';
    } else {
        body.style.display = 'none';
        toggle.innerHTML = '&#x25B6;';
    }
}

// --- Status Bar ---

function clearStatusAfterDelay(ms) {
    setTimeout(() => {
        const el = document.getElementById('submit-status');
        if (el) el.innerHTML = '';
    }, ms || 5000);
}

// --- Batch File Upload ---

function uploadBatchFile(input) {
    const file = input.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = function(e) {
        let events;
        try {
            events = JSON.parse(e.target.result);
        } catch {
            document.getElementById('submit-status').innerHTML =
                '<span class="text-red-400">Error: Invalid JSON file</span>';
            clearStatusAfterDelay(8000);
            return;
        }
        const payload = Array.isArray(events)
            ? events.map(ev => ({
                ...ev,
                intent: ev && ev.intent ? ev.intent : 'unknown'
            }))
            : events;
        fetch('/api/events/batch', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        })
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                document.getElementById('submit-status').innerHTML =
                    '<span class="text-red-400">Error: ' + data.error + '</span>';
                clearStatusAfterDelay(8000);
            } else {
                document.getElementById('submit-status').innerHTML =
                    '<span class="text-green-400">Batch: ' + data.accepted + ' events sent</span>';
                clearStatusAfterDelay();
                // Track all batch events as pending
                for (let i = 0; i < data.event_ids.length; i++) {
                    const src = events[i] && events[i].source || 'batch';
                    const txt = events[i] && events[i].text || '';
                    addPendingEvent(data.event_ids[i], src, txt.substring(0, 60));
                }
                boostQueuePolling();
            }
        });
    };
    reader.readAsText(file);
    input.value = '';
}

// --- Event Deletion ---

function deleteEvent(eventId) {
    fetch('/api/events/' + eventId, { method: 'DELETE' })
        .then(r => r.json())
        .then(data => {
            if (data.deleted) {
                var row = document.getElementById('event-' + eventId);
                var detail = document.getElementById('detail-' + eventId);
                if (row) row.remove();
                if (detail) detail.remove();
            }
        });
}

function clearAllEvents() {
    if (!confirm('Delete all events from the table? This archives them in the database.')) return;
    fetch('/api/events', { method: 'DELETE' })
        .then(r => r.json())
        .then(data => {
            var body = document.getElementById('event-table-body');
            if (body) body.innerHTML = '';
            var status = document.getElementById('submit-status');
            if (status) {
                status.innerHTML = '<span class="text-green-400">' + data.deleted + ' events cleared</span>';
                clearStatusAfterDelay();
            }
        });
}

// Start polling when script loads
startQueuePolling();
