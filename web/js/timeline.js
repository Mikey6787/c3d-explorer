/**
 * Interactive Timeline & Playback Controller
 * Handles playback loop (Play/Pause, Step, Loop, Speed), scrub slider,
 * 1-based frame display, event flags track, and Trim Start/End ROI bounds.
 */

export class TimelineController {
    constructor(containerElement, options = {}) {
        this.container = containerElement;
        this.trial = null;
        this.currentFrame = 0; // 0-based internal index
        this.totalFrames = 0;
        this.pointRate = 100.0;
        this.isPlaying = false;
        this.isLooping = true;
        this.playbackSpeed = 1.0;
        this.trimStart = 0;
        this.trimEnd = 0;

        this.onFrameChanged = options.onFrameChanged || (() => {});
        this.onTrimChanged = options.onTrimChanged || (() => {});

        this._lastTimestamp = 0;
        this._accumulator = 0;
        this._animationFrameId = null;

        this._buildUI();
        this._attachEvents();
    }

    _buildUI() {
        this.container.innerHTML = `
            <div class="timeline-controls-row">
                <div class="playback-buttons">
                    <button id="btn-first-frame" class="timeline-btn" title="First Frame (Home)">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M6 6h2v12H6zm3.5 6l8.5 6V6z"/></svg>
                    </button>
                    <button id="btn-step-prev" class="timeline-btn" title="Previous Frame (Left Arrow)">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M14 6l-6 6 6 6z"/></svg>
                    </button>
                    <button id="btn-play-pause" class="timeline-btn primary-btn" title="Play/Pause (Space)">
                        <svg id="icon-play" width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
                        <svg id="icon-pause" width="16" height="16" viewBox="0 0 24 24" fill="currentColor" style="display:none;"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
                    </button>
                    <button id="btn-step-next" class="timeline-btn" title="Next Frame (Right Arrow)">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M10 18l6-6-6-6z"/></svg>
                    </button>
                    <button id="btn-last-frame" class="timeline-btn" title="Last Frame (End)">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"/></svg>
                    </button>
                    <button id="btn-loop" class="timeline-btn active" title="Toggle Loop">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46C19.54 15.03 20 13.57 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74C4.46 8.97 4 10.43 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z"/></svg>
                    </button>
                </div>

                <div class="timeline-slider-wrapper">
                    <div class="slider-track-container">
                        <div id="trim-range-highlight" class="trim-range-highlight"></div>
                        <input type="range" id="timeline-scrubber" min="0" max="0" value="0" step="1" class="timeline-scrubber">
                    </div>
                    <div id="events-track" class="events-track"></div>
                </div>

                <div class="playback-meta">
                    <div class="frame-counter">
                        <span id="lbl-current-frame" class="active-val">1</span>
                        <span class="sep">/</span>
                        <span id="lbl-total-frames">1</span>
                    </div>
                    <div class="time-counter">
                        <span id="lbl-current-time" class="active-val">0.000s</span>
                        <span class="sep">/</span>
                        <span id="lbl-total-time">0.000s</span>
                    </div>
                    <div class="speed-select-wrapper">
                        <select id="select-speed" class="speed-select" title="Playback Speed">
                            <option value="0.1">0.1x</option>
                            <option value="0.25">0.25x</option>
                            <option value="0.5">0.5x</option>
                            <option value="1.0" selected>1.0x</option>
                            <option value="2.0">2.0x</option>
                        </select>
                    </div>
                </div>
            </div>
        `;

        this.btnPlayPause = this.container.querySelector('#btn-play-pause');
        this.iconPlay = this.container.querySelector('#icon-play');
        this.iconPause = this.container.querySelector('#icon-pause');
        this.btnStepPrev = this.container.querySelector('#btn-step-prev');
        this.btnStepNext = this.container.querySelector('#btn-step-next');
        this.btnFirst = this.container.querySelector('#btn-first-frame');
        this.btnLast = this.container.querySelector('#btn-last-frame');
        this.btnLoop = this.container.querySelector('#btn-loop');
        this.scrubber = this.container.querySelector('#timeline-scrubber');
        this.eventsTrack = this.container.querySelector('#events-track');
        this.trimHighlight = this.container.querySelector('#trim-range-highlight');
        this.lblCurrentFrame = this.container.querySelector('#lbl-current-frame');
        this.lblTotalFrames = this.container.querySelector('#lbl-total-frames');
        this.lblCurrentTime = this.container.querySelector('#lbl-current-time');
        this.lblTotalTime = this.container.querySelector('#lbl-total-time');
        this.selectSpeed = this.container.querySelector('#select-speed');
    }

    _attachEvents() {
        this.btnPlayPause.addEventListener('click', () => this.togglePlayPause());
        this.btnStepPrev.addEventListener('click', () => this.stepFrame(-1));
        this.btnStepNext.addEventListener('click', () => this.stepFrame(1));
        this.btnFirst.addEventListener('click', () => this.seekFrame(this.trimStart));
        this.btnLast.addEventListener('click', () => this.seekFrame(this.trimEnd));

        this.btnLoop.addEventListener('click', () => {
            this.isLooping = !this.isLooping;
            this.btnLoop.classList.toggle('active', this.isLooping);
        });

        this.selectSpeed.addEventListener('change', (e) => {
            this.playbackSpeed = parseFloat(e.target.value) || 1.0;
        });

        this.scrubber.addEventListener('input', (e) => {
            this.seekFrame(parseInt(e.target.value, 10));
        });

        // Global keyboard shortcuts
        window.addEventListener('keydown', (e) => {
            // Ignore if active in input / textarea
            if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) return;

            if (e.code === 'Space') {
                e.preventDefault();
                this.togglePlayPause();
            } else if (e.code === 'ArrowLeft') {
                e.preventDefault();
                this.stepFrame(-1);
            } else if (e.code === 'ArrowRight') {
                e.preventDefault();
                this.stepFrame(1);
            } else if (e.code === 'Home') {
                e.preventDefault();
                this.seekFrame(this.trimStart);
            } else if (e.code === 'End') {
                e.preventDefault();
                this.seekFrame(this.trimEnd);
            }
        });
    }

    loadTrial(trial) {
        this.pause();
        this.trial = trial;
        this.totalFrames = trial.pointFrameCount;
        this.pointRate = trial.pointRate || 100.0;
        this.currentFrame = 0;
        this.trimStart = 0;
        this.trimEnd = Math.max(0, this.totalFrames - 1);

        this.scrubber.min = 0;
        this.scrubber.max = Math.max(0, this.totalFrames - 1);
        this.scrubber.value = 0;

        this.lblTotalFrames.textContent = this.totalFrames.toString();
        const totalDuration = this.pointRate > 0 ? (this.totalFrames / this.pointRate) : 0;
        this.lblTotalTime.textContent = totalDuration.toFixed(3) + 's';

        this._renderEventsTrack();
        this._updateTrimHighlight();
        this.updateUI();
    }

    _renderEventsTrack() {
        this.eventsTrack.innerHTML = '';
        if (!this.trial || !this.trial.events || this.trial.events.length === 0 || this.totalFrames <= 1) return;

        this.trial.events.forEach((ev, idx) => {
            const pct = (ev.frame / (this.totalFrames - 1)) * 100;
            const markerEl = document.createElement('div');
            markerEl.className = 'event-marker-badge';
            markerEl.style.left = `${pct}%`;
            markerEl.style.backgroundColor = ev.iconColor || '#FF9800';
            markerEl.title = `${ev.context ? ev.context + ': ' : ''}${ev.name}\nFrame: ${ev.displayFrame}\nTime: ${ev.time.toFixed(3)}s`;

            markerEl.addEventListener('click', (e) => {
                e.stopPropagation();
                this.seekFrame(ev.frame);
            });

            // Context menu to snap trim bounds to event
            markerEl.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                this._showEventContextMenu(e.clientX, e.clientY, ev);
            });

            this.eventsTrack.appendChild(markerEl);
        });
    }

    _showEventContextMenu(x, y, ev) {
        const oldMenu = document.getElementById('timeline-ctx-menu');
        if (oldMenu) oldMenu.remove();

        const menu = document.createElement('div');
        menu.id = 'timeline-ctx-menu';
        menu.className = 'custom-ctx-menu';
        menu.style.left = `${x}px`;
        menu.style.top = `${y}px`;

        menu.innerHTML = `
            <div class="ctx-title">${ev.context ? ev.context + ': ' : ''}${ev.name} (Frame ${ev.displayFrame})</div>
            <div class="ctx-item" id="ctx-trim-start">Trim Start Here</div>
            <div class="ctx-item" id="ctx-trim-end">Trim End Here</div>
            <div class="ctx-item" id="ctx-reset-trim">Reset Trim to Full Range</div>
        `;

        document.body.appendChild(menu);

        menu.querySelector('#ctx-trim-start').addEventListener('click', () => {
            this.setTrimBounds(ev.frame, this.trimEnd);
            menu.remove();
        });

        menu.querySelector('#ctx-trim-end').addEventListener('click', () => {
            this.setTrimBounds(this.trimStart, ev.frame);
            menu.remove();
        });

        menu.querySelector('#ctx-reset-trim').addEventListener('click', () => {
            this.setTrimBounds(0, Math.max(0, this.totalFrames - 1));
            menu.remove();
        });

        const closeMenu = (e) => {
            if (!menu.contains(e.target)) {
                menu.remove();
                document.removeEventListener('click', closeMenu);
            }
        };
        setTimeout(() => document.addEventListener('click', closeMenu), 50);
    }

    setTrimBounds(start, end) {
        this.trimStart = Math.max(0, Math.min(this.totalFrames - 1, start));
        this.trimEnd = Math.max(this.trimStart, Math.min(this.totalFrames - 1, end));
        this._updateTrimHighlight();
        this.onTrimChanged(this.trimStart, this.trimEnd);
    }

    _updateTrimHighlight() {
        if (this.totalFrames <= 1) {
            this.trimHighlight.style.display = 'none';
            return;
        }
        this.trimHighlight.style.display = 'block';
        const startPct = (this.trimStart / (this.totalFrames - 1)) * 100;
        const widthPct = ((this.trimEnd - this.trimStart) / (this.totalFrames - 1)) * 100;
        this.trimHighlight.style.left = `${startPct}%`;
        this.trimHighlight.style.width = `${widthPct}%`;
    }

    togglePlayPause() {
        if (this.isPlaying) {
            this.pause();
        } else {
            this.play();
        }
    }

    play() {
        if (!this.trial || this.totalFrames <= 0) return;
        this.isPlaying = true;
        this.iconPlay.style.display = 'none';
        this.iconPause.style.display = 'inline-block';
        this.btnPlayPause.classList.add('playing');

        if (this.currentFrame >= this.trimEnd) {
            this.currentFrame = this.trimStart;
        }

        this._lastTimestamp = performance.now();
        this._accumulator = 0;
        this._loop();
    }

    pause() {
        this.isPlaying = false;
        this.iconPlay.style.display = 'inline-block';
        this.iconPause.style.display = 'none';
        this.btnPlayPause.classList.remove('playing');
        if (this._animationFrameId) {
            cancelAnimationFrame(this._animationFrameId);
            this._animationFrameId = null;
        }
    }

    _loop() {
        if (!this.isPlaying) return;

        const now = performance.now();
        const dt = (now - this._lastTimestamp) / 1000.0;
        this._lastTimestamp = now;

        const frameDuration = (1.0 / this.pointRate) / this.playbackSpeed;
        this._accumulator += dt;

        while (this._accumulator >= frameDuration) {
            this._accumulator -= frameDuration;
            this.currentFrame++;

            if (this.currentFrame > this.trimEnd) {
                if (this.isLooping) {
                    this.currentFrame = this.trimStart;
                } else {
                    this.currentFrame = this.trimEnd;
                    this.pause();
                    this.updateUI();
                    this.onFrameChanged(this.currentFrame);
                    return;
                }
            }
        }

        this.updateUI();
        this.onFrameChanged(this.currentFrame);
        this._animationFrameId = requestAnimationFrame(() => this._loop());
    }

    stepFrame(delta) {
        this.pause();
        this.seekFrame(this.currentFrame + delta);
    }

    seekFrame(frameIndex) {
        if (this.totalFrames <= 0) return;
        const target = Math.max(0, Math.min(this.totalFrames - 1, frameIndex));
        this.currentFrame = target;
        this.updateUI();
        this.onFrameChanged(this.currentFrame);
    }

    updateUI() {
        this.scrubber.value = this.currentFrame;
        // 1-based display: frameIndex + 1
        this.lblCurrentFrame.textContent = (this.currentFrame + 1).toString();
        const curTime = this.pointRate > 0 ? (this.currentFrame / this.pointRate) : 0;
        this.lblCurrentTime.textContent = curTime.toFixed(3) + 's';
    }
}
