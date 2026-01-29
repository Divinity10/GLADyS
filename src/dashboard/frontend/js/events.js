// SSE event handling
document.body.addEventListener('htmx:sseMessage', function (e) {
    // This can be used for custom handling if needed
    // But htmx sse-swap handles most things
    console.log('SSE Message:', e.detail.data);
});

function eventTable() {
    return {
        events: [],
        filterSource: '',
        filterText: '',
        
        // This will be used if we want to manage the table with Alpine
        // instead of pure HTMX swaps for more complex client-side filtering
        addEvent(event) {
            this.events.unshift(event);
            if (this.events.length > 100) this.events.pop();
        }
    }
}
