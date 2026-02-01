function appState() {
    return {
        activeTab: localStorage.getItem('activeTab') || 'lab',
        environment: localStorage.getItem('environment') || 'local',
        selectedService: 'all',
        serviceActionPending: false,
        serviceAction: '',
        serviceStatusMsg: '',
        warmingOllama: false,

        init() {
            this.$watch('activeTab', (val) => {
                localStorage.setItem('activeTab', val);
                // Trigger data refresh when switching tabs
                this.$nextTick(() => {
                    if (val === 'lab') {
                        // Re-fetch event rows for the Lab tab
                        const tbody = document.getElementById('event-table-body');
                        if (tbody) {
                            fetch('/api/events/rows?limit=25&offset=0')
                                .then(r => r.text())
                                .then(html => { tbody.innerHTML = html; });
                        }
                    } else if (val === 'knowledge') {
                        // Dispatch event for Alpine.js knowledge component
                        window.dispatchEvent(new CustomEvent('refresh-knowledge'));
                    } else {
                        // For HTMX tabs (learning, llm, logs, settings), re-trigger load
                        const tabDiv = document.querySelector(`[x-show="activeTab === '${val}'"]`);
                        if (tabDiv) htmx.trigger(tabDiv, 'load');
                    }
                });
            });
            this.$watch('environment', (val) => {
                localStorage.setItem('environment', val);
                this.switchEnvironment(val);
            });
        },

        selectService(name) {
            this.selectedService = name;
        },

        async switchEnvironment(env) {
            console.log(`Switching environment to ${env}`);
            try {
                await fetch('/api/config/environment', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ mode: env })
                });
                // Trigger a refresh of health and metrics
                htmx.trigger('#sidebar', 'load');
                htmx.trigger('#metrics-strip', 'load');
            } catch (err) {
                console.error('Failed to switch environment:', err);
            }
        },

        async _doServiceAction(action) {
            const name = this.selectedService;
            const label = name === 'all' ? 'all services' : name;
            this.serviceActionPending = true;
            this.serviceAction = action;
            this.serviceStatusMsg = action === 'start' ? `Starting ${label}...`
                : action === 'stop' ? `Stopping ${label}...`
                : `Restarting ${label}...`;

            // Fire the action (don't await — it blocks until service is up/down)
            const actionPromise = fetch(`/api/services/${name}/${action}`, { method: 'POST' })
                .then(r => r.json())
                .catch(err => ({ success: false, output: String(err) }));

            // Poll health every 2s so user sees intermediate states
            const pollInterval = setInterval(() => {
                htmx.trigger('#sidebar', 'load');
            }, 2000);

            // Wait for the action to actually finish
            const data = await actionPromise;

            // Stop polling, do one final refresh
            clearInterval(pollInterval);
            htmx.trigger('#sidebar', 'load');
            await new Promise(r => setTimeout(r, 500));

            if (!data.success) {
                this.serviceStatusMsg = `${action} failed: ${data.output || 'unknown error'}`;
                setTimeout(() => { this.serviceStatusMsg = ''; }, 8000);
            } else {
                this.serviceStatusMsg = '';
            }
            this.serviceActionPending = false;
            this.serviceAction = '';
        },

        async startService() {
            await this._doServiceAction('start');
        },

        async stopService() {
            const name = this.selectedService;
            if (!confirm(`Are you sure you want to stop ${name === 'all' ? 'ALL services' : name}?`)) return;
            await this._doServiceAction('stop');
        },

        async restartService() {
            const name = this.selectedService;
            if (name === 'all' && !confirm('Are you sure you want to restart ALL services?')) return;
            await this._doServiceAction('restart');
        },

        async warmOllama() {
            this.warmingOllama = true;
            try {
                await fetch('/api/llm/warm', { method: 'POST' });
            } catch (err) {
                console.error('Failed to warm Ollama:', err);
            } finally {
                this.warmingOllama = false;
            }
        },

        // Column Resizing
        resizeColumn(e) {
            const th = e.target.closest('th');
            const startX = e.clientX;
            const startWidth = th.offsetWidth;
            
            e.target.classList.add('resizing');
            
            const moveHandler = (e) => {
                const diff = e.clientX - startX;
                th.style.width = `${Math.max(50, startWidth + diff)}px`;
            };
            
            const upHandler = () => {
                e.target.classList.remove('resizing');
                window.removeEventListener('mousemove', moveHandler);
                window.removeEventListener('mouseup', upHandler);
            };
            
            window.addEventListener('mousemove', moveHandler);
            window.addEventListener('mouseup', upHandler);
        }
    }
}
