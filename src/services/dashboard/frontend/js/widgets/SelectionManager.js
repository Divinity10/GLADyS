/**
 * SelectionManager - Manages table row selection state.
 *
 * Usage:
 *   const selection = new SelectionManager('heuristics-list', 'bulk-action-bar', 'selected-count');
 *   window.heuristicsSelection = selection; // For backward compatibility
 */
export class SelectionManager {
    /**
     * @param {string} listContainerId - DOM id of the rows container
     * @param {string} bulkBarId - DOM id of the bulk action bar
     * @param {string} countId - DOM id of the selected count span
     */
    constructor(listContainerId, bulkBarId, countId) {
        this.listContainerId = listContainerId;
        this.bulkBarId = bulkBarId;
        this.countId = countId;
        this.selected = new Set();
    }

    toggle(id) {
        if (this.selected.has(id)) {
            this.selected.delete(id);
        } else {
            this.selected.add(id);
        }
        this.updateUI();
    }

    isSelected(id) {
        return this.selected.has(id);
    }

    clear() {
        this.selected.clear();
        this.updateUI();
    }

    getSelected() {
        return [...this.selected];
    }

    updateUI() {
        const bar = document.getElementById(this.bulkBarId);
        const count = document.getElementById(this.countId);
        if (this.selected.size > 0) {
            if (bar) bar.style.display = '';
            if (count) count.textContent = this.selected.size;
        } else {
            if (bar) bar.style.display = 'none';
        }
    }

    /**
     * Toggle all checkboxes in the list container.
     * Call this from the header checkbox onclick.
     */
    toggleAll() {
        const container = document.getElementById(this.listContainerId);
        if (!container) return;

        const checkboxes = container.querySelectorAll('input[type="checkbox"]');
        const allSelected = checkboxes.length > 0 && [...checkboxes].every(cb => cb.checked);

        checkboxes.forEach(cb => {
            cb.checked = !allSelected;
            const id = cb.value;
            if (!allSelected) {
                this.selected.add(id);
            } else {
                this.selected.delete(id);
            }
        });
        this.updateUI();
    }
}
