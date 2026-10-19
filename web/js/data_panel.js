/**
 * Data Explorer Panel
 * Manages list of 3D markers with search filtering, visibility toggles,
 * custom color pickers, and quick plot actions.
 */

export class DataExplorerPanel {
    constructor(containerElement, options = {}) {
        this.container = containerElement;
        this.trial = null;
        this.onMarkerVisibilityChanged = options.onMarkerVisibilityChanged || (() => {});
        this.onMarkerColorChanged = options.onMarkerColorChanged || (() => {});
        this.onMarkerSelected = options.onMarkerSelected || (() => {});
        this.onMarkerPlotRequested = options.onMarkerPlotRequested || (() => {});
        this.onAllVisibilityChanged = options.onAllVisibilityChanged || (() => {});

        this.markerColors = new Map();
        this.markerVisibility = new Map();
        this.selectedMarker = null;

        this._buildUI();
    }

    _buildUI() {
        this.container.innerHTML = `
            <div class="panel-header">
                <div class="panel-title-row">
                    <span class="panel-title">Data Explorer</span>
                    <span id="badge-marker-count" class="badge">0</span>
                </div>
                <div class="panel-search-bar">
                    <input type="text" id="input-marker-search" placeholder="Search markers..." class="search-input">
                </div>
                <div class="panel-batch-actions">
                    <button id="btn-show-all-markers" class="btn-xs">Show All</button>
                    <button id="btn-hide-all-markers" class="btn-xs">Hide All</button>
                </div>
            </div>
            <div id="marker-list-container" class="marker-list">
                <div class="empty-state">No markers loaded</div>
            </div>
        `;

        this.searchInput = this.container.querySelector('#input-marker-search');
        this.listContainer = this.container.querySelector('#marker-list-container');
        this.badgeCount = this.container.querySelector('#badge-marker-count');
        this.btnShowAll = this.container.querySelector('#btn-show-all-markers');
        this.btnHideAll = this.container.querySelector('#btn-hide-all-markers');

        this.searchInput.addEventListener('input', () => this._filterMarkers());
        this.btnShowAll.addEventListener('click', () => {
            this.markerVisibility.forEach((_, name) => this.markerVisibility.set(name, true));
            this._updateAllCheckboxes(true);
            this.onAllVisibilityChanged(true);
        });
        this.btnHideAll.addEventListener('click', () => {
            this.markerVisibility.forEach((_, name) => this.markerVisibility.set(name, false));
            this._updateAllCheckboxes(false);
            this.onAllVisibilityChanged(false);
        });
    }

    loadTrial(trial, initialColors = new Map()) {
        this.trial = trial;
        this.markerColors = new Map(initialColors);
        this.markerVisibility.clear();
        this.selectedMarker = null;
        this.searchInput.value = '';

        trial.markerNames.forEach(name => {
            this.markerVisibility.set(name, true);
        });

        this.badgeCount.textContent = trial.markerNames.length.toString();
        this._renderMarkerList();
    }

    _renderMarkerList() {
        if (!this.trial || this.trial.markerNames.length === 0) {
            this.listContainer.innerHTML = '<div class="empty-state">No markers loaded</div>';
            return;
        }

        const filter = this.searchInput.value.trim().toLowerCase();
        this.listContainer.innerHTML = '';

        this.trial.markerNames.forEach(name => {
            if (filter && !name.toLowerCase().includes(filter)) return;

            const isVisible = this.markerVisibility.get(name) !== false;
            const isSelected = this.selectedMarker === name;
            const colorObj = this.markerColors.get(name);
            const hexColor = colorObj ? '#' + colorObj.getHexString() : '#00d2ff';

            const itemEl = document.createElement('div');
            itemEl.className = `marker-item ${isSelected ? 'selected' : ''}`;
            itemEl.dataset.markerName = name;

            itemEl.innerHTML = `
                <input type="checkbox" class="marker-vis-check" ${isVisible ? 'checked' : ''} title="Toggle 3D Visibility">
                <div class="color-picker-wrapper" title="Click to change marker color">
                    <span class="color-swatch" style="background-color: ${hexColor}"></span>
                    <input type="color" class="marker-color-input" value="${hexColor}">
                </div>
                <span class="marker-name" title="${name}">${name}</span>
                <button class="btn-plot-marker" title="Plot X/Y/Z Curves">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M3.5 18.5l6-6 4 4L22 6.92 20.59 5.5l-7.09 7.08-4-4L2 16.08z"/></svg>
                </button>
            `;

            // Row click -> select marker
            itemEl.addEventListener('click', (e) => {
                if (e.target.closest('.marker-vis-check') || e.target.closest('.color-picker-wrapper') || e.target.closest('.btn-plot-marker')) {
                    return;
                }
                this.selectMarker(name);
                this.onMarkerSelected(name);
            });

            // Visibility toggle
            const checkEl = itemEl.querySelector('.marker-vis-check');
            checkEl.addEventListener('change', (e) => {
                const vis = e.target.checked;
                this.markerVisibility.set(name, vis);
                this.onMarkerVisibilityChanged(name, vis);
            });

            // Color change
            const colorInput = itemEl.querySelector('.marker-color-input');
            const swatchEl = itemEl.querySelector('.color-swatch');
            colorInput.addEventListener('input', (e) => {
                const newHex = e.target.value;
                swatchEl.style.backgroundColor = newHex;
                this.onMarkerColorChanged(name, newHex);
            });

            // Plot button
            const plotBtn = itemEl.querySelector('.btn-plot-marker');
            plotBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.selectMarker(name);
                this.onMarkerSelected(name);
                this.onMarkerPlotRequested(name);
            });

            this.listContainer.appendChild(itemEl);
        });
    }

    _filterMarkers() {
        this._renderMarkerList();
    }

    _updateAllCheckboxes(checked) {
        this.listContainer.querySelectorAll('.marker-vis-check').forEach(chk => {
            chk.checked = checked;
        });
    }

    selectMarker(name) {
        this.selectedMarker = name;
        this.listContainer.querySelectorAll('.marker-item').forEach(el => {
            const matches = el.dataset.markerName === name;
            el.classList.toggle('selected', matches);
            if (matches) {
                el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
            }
        });
    }
}
