/**
 * Main Application Orchestrator for C3D Explorer Web
 */

import { C3DParser } from './c3d_parser.js';
import { Viewer3D } from './viewer_3d.js';
import { TimelineController } from './timeline.js';
import { CanvasPlotter } from './plotter.js';
import { DataExplorerPanel } from './data_panel.js';
import { EventManager } from './event_manager.js';

class C3DApp {
    constructor() {
        this.trial = null;
        this._initDOM();
        this._initComponents();
        this._attachEvents();
    }

    _initDOM() {
        // App header elements
        this.btnOpenFile = document.getElementById('btn-open-file');
        this.fileInput = document.getElementById('file-input');
        this.btnLoadSample = document.getElementById('btn-load-sample');
        this.dropZone = document.getElementById('drop-zone');
        this.loadingOverlay = document.getElementById('loading-overlay');
        this.loadingText = document.getElementById('loading-text');

        // Trial info badges
        this.lblTrialName = document.getElementById('trial-name');
        this.lblTrialFrames = document.getElementById('trial-frames');
        this.lblTrialRate = document.getElementById('trial-rate');
        this.lblTrialMarkers = document.getElementById('trial-markers');
        this.lblTrialAnalogs = document.getElementById('trial-analogs');

        // Viewport toolbar buttons
        this.btnResetCam = document.getElementById('btn-reset-cam');
        this.btnToggleGrid = document.getElementById('btn-toggle-grid');
        this.btnToggleAxes = document.getElementById('btn-toggle-axes');
        this.btnToggleTraj = document.getElementById('btn-toggle-traj');
        this.selectCamPreset = document.getElementById('select-cam-preset');

        // Drawers & Modals
        this.btnTogglePlotter = document.getElementById('btn-toggle-plotter');
        this.btnOpenEvents = document.getElementById('btn-open-events');
        this.plotDrawer = document.getElementById('plot-drawer');
        this.btnClosePlotter = document.getElementById('btn-close-plotter');
        this.btnFitROI = document.getElementById('btn-fit-roi');
        this.btnAutoRange = document.getElementById('btn-auto-range');
        this.eventModalEl = document.getElementById('event-modal');

        // Tooltip element for 3D marker hover
        this.marker3dTooltip = document.getElementById('marker-3d-tooltip');
        this.plotTooltip = document.getElementById('plot-tooltip');
    }

    _initComponents() {
        // 1. 3D Viewport
        const viewerContainer = document.getElementById('viewport-3d-container');
        this.viewer = new Viewer3D(viewerContainer, {
            onMarkerSelected: (name) => {
                this.dataPanel.selectMarker(name);
                if (name) {
                    this.plotter.plotMarker(name);
                }
            },
            onMarkerHovered: (name, screenX, screenY, pos3d) => {
                if (name && this.marker3dTooltip) {
                    this.marker3dTooltip.textContent = `${name} [${pos3d.x.toFixed(1)}, ${pos3d.y.toFixed(1)}, ${pos3d.z.toFixed(1)}]`;
                    this.marker3dTooltip.style.display = 'block';
                    this.marker3dTooltip.style.left = `${screenX + 12}px`;
                    this.marker3dTooltip.style.top = `${screenY - 12}px`;
                } else if (this.marker3dTooltip) {
                    this.marker3dTooltip.style.display = 'none';
                }
            }
        });

        // 2. Timeline
        const timelineContainer = document.getElementById('timeline-bar-container');
        this.timeline = new TimelineController(timelineContainer, {
            onFrameChanged: (frameIdx) => {
                this.viewer.setFrame(frameIdx);
                this.plotter.setFrame(frameIdx);
            },
            onTrimChanged: (start, end) => {
                this.plotter.setTrimBounds(start, end);
            }
        });

        // 3. Canvas Plotter
        const canvasEl = document.getElementById('plot-canvas');
        this.plotter = new CanvasPlotter(canvasEl, this.plotTooltip);

        // 4. Data Explorer Panel
        const sidePanelContainer = document.getElementById('data-explorer-container');
        this.dataPanel = new DataExplorerPanel(sidePanelContainer, {
            onMarkerVisibilityChanged: (name, visible) => {
                this.viewer.setMarkerVisibility(name, visible);
            },
            onMarkerColorChanged: (name, hex) => {
                this.viewer.setMarkerColor(name, hex);
            },
            onMarkerSelected: (name) => {
                this.viewer.selectMarker(name);
                if (name) {
                    this.plotter.plotMarker(name);
                }
            },
            onMarkerPlotRequested: (name) => {
                this._openPlotDrawer();
                this.plotter.plotMarker(name);
            },
            onAllVisibilityChanged: (visible) => {
                this.viewer.setAllMarkersVisibility(visible);
            }
        });

        // 5. Event Manager
        this.eventManager = new EventManager(this.eventModalEl, {
            getCurrentFrame: () => this.timeline.currentFrame,
            onEventsUpdated: (events) => {
                this.timeline._renderEventsTrack();
                this.plotter.render();
            },
            onSeekRequested: (frameIdx) => {
                this.timeline.seekFrame(frameIdx);
            }
        });
    }

    _attachEvents() {
        // File Open
        this.btnOpenFile.addEventListener('click', () => this.fileInput.click());
        this.fileInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) this.loadFile(file);
        });

        // Load Sample
        this.btnLoadSample.addEventListener('click', () => this.loadSampleTrial());

        // Drag & Drop
        window.addEventListener('dragover', (e) => {
            e.preventDefault();
            this.dropZone.classList.add('active');
        });
        window.addEventListener('dragleave', (e) => {
            if (e.relatedTarget === null) {
                this.dropZone.classList.remove('active');
            }
        });
        window.addEventListener('drop', (e) => {
            e.preventDefault();
            this.dropZone.classList.remove('active');
            if (e.dataTransfer.files.length > 0) {
                const file = e.dataTransfer.files[0];
                if (file.name.toLowerCase().endsWith('.c3d')) {
                    this.loadFile(file);
                } else {
                    alert('Please drop a valid .c3d file.');
                }
            }
        });

        // Viewport actions
        this.btnResetCam.addEventListener('click', () => this.viewer.resetCamera());
        this.selectCamPreset.addEventListener('change', (e) => {
            this.viewer.setCameraPreset(e.target.value);
        });

        let gridVisible = true;
        this.btnToggleGrid.addEventListener('click', () => {
            gridVisible = !gridVisible;
            this.viewer.toggleGrid(gridVisible);
            this.btnToggleGrid.classList.toggle('active', gridVisible);
        });

        let axesVisible = true;
        this.btnToggleAxes.addEventListener('click', () => {
            axesVisible = !axesVisible;
            this.viewer.toggleAxes(axesVisible);
            this.btnToggleAxes.classList.toggle('active', axesVisible);
        });

        let trajVisible = false;
        this.btnToggleTraj.addEventListener('click', () => {
            trajVisible = !trajVisible;
            this.viewer.toggleTrajectories(trajVisible);
            this.btnToggleTraj.classList.toggle('active', trajVisible);
        });

        // Plot Drawer actions
        this.btnTogglePlotter.addEventListener('click', () => {
            this._togglePlotDrawer();
        });
        this.btnClosePlotter.addEventListener('click', () => {
            this._closePlotDrawer();
        });
        this.btnFitROI.addEventListener('click', () => {
            this.plotter.fitROI();
        });
        this.btnAutoRange.addEventListener('click', () => {
            this.plotter.autoRange();
        });

        // Event Modal
        this.btnOpenEvents.addEventListener('click', () => {
            this.eventManager.show();
        });
    }

    _togglePlotDrawer() {
        const isHidden = this.plotDrawer.classList.contains('hidden');
        if (isHidden) {
            this._openPlotDrawer();
        } else {
            this._closePlotDrawer();
        }
    }

    _openPlotDrawer() {
        this.plotDrawer.classList.remove('hidden');
        this.btnTogglePlotter.classList.add('active');
        setTimeout(() => this.plotter.resize(), 50);
    }

    _closePlotDrawer() {
        this.plotDrawer.classList.add('hidden');
        this.btnTogglePlotter.classList.remove('active');
    }

    async loadFile(file) {
        this._showLoading(`Reading ${file.name}...`);
        try {
            const arrayBuffer = await file.arrayBuffer();
            this._parseAndLoad(arrayBuffer, file.name);
        } catch (err) {
            console.error('Error reading C3D file:', err);
            alert(`Failed to parse C3D file:\n${err.message}`);
        } finally {
            this._hideLoading();
        }
    }

    async loadSampleTrial() {
        this._showLoading('Loading sample C3D trial...');
        try {
            const resp = await fetch('sample/sample_trial.c3d');
            if (!resp.ok) throw new Error(`HTTP ${resp.status} - ${resp.statusText}`);
            const arrayBuffer = await resp.arrayBuffer();
            this._parseAndLoad(arrayBuffer, 'P01_PRE_L_REF.c3d');
        } catch (err) {
            console.error('Error loading sample trial:', err);
            alert(`Could not load sample trial:\n${err.message}\nMake sure to run via a local web server (e.g. python -m http.server).`);
        } finally {
            this._hideLoading();
        }
    }

    _parseAndLoad(arrayBuffer, fileName) {
        const trial = C3DParser.parse(arrayBuffer, fileName);
        this.trial = trial;

        // Update trial info badges
        this.lblTrialName.textContent = trial.fileName;
        this.lblTrialFrames.textContent = `${trial.pointFrameCount} frames`;
        this.lblTrialRate.textContent = `${trial.pointRate.toFixed(1)} Hz`;
        this.lblTrialMarkers.textContent = `${trial.markerNames.length} markers`;
        this.lblTrialAnalogs.textContent = `${trial.analogNames.length} channels`;

        // Update 3D viewport
        this.viewer.loadTrial(trial);

        // Update Data Explorer
        this.dataPanel.loadTrial(trial, this.viewer.markerColors);

        // Update Timeline
        this.timeline.loadTrial(trial);

        // Update Plotter
        this.plotter.loadTrial(trial);
        if (trial.markerNames.length > 0) {
            const firstMarker = trial.markerNames[0];
            this.viewer.selectMarker(firstMarker);
            this.dataPanel.selectMarker(firstMarker);
            this.plotter.plotMarker(firstMarker);
        }

        // Update Event Manager
        this.eventManager.loadTrial(trial);

        // Automatically show plot drawer
        this._openPlotDrawer();
    }

    _showLoading(text = 'Loading...') {
        this.loadingText.textContent = text;
        this.loadingOverlay.style.display = 'flex';
    }

    _hideLoading() {
        this.loadingOverlay.style.display = 'none';
    }
}

// Auto-instantiate on DOM load
window.addEventListener('DOMContentLoaded', () => {
    window.app = new C3DApp();
});
