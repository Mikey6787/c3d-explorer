/**
 * High-Performance Canvas Plotter
 * Graphs 3D marker trajectories (X/Y/Z) and analog channels.
 * Features:
 * - Dynamic vertical playhead cursor synchronized with timeline playback
 * - Vertical dashed lines for events with matching event colors
 * - Mouse hover crosshair & readout tooltip
 * - Fit to ROI and Auto-Range modes
 */

export class CanvasPlotter {
    constructor(canvasElement, tooltipElement, options = {}) {
        this.canvas = canvasElement;
        this.ctx = canvasElement.getContext('2d');
        this.tooltip = tooltipElement;
        this.trial = null;

        this.currentFrame = 0;
        this.viewStartFrame = 0;
        this.viewEndFrame = 100;
        this.trimStart = 0;
        this.trimEnd = 100;

        this.selectedMarker = null;
        this.selectedAnalog = null;
        this.isAnalogMode = false;

        this.padding = { top: 30, right: 30, bottom: 40, left: 60 };
        this.hoverPos = null;

        this.colors = {
            bg: '#181a20',
            grid: '#272b36',
            text: '#8a93a5',
            xCurve: '#ff5252', // X = Red
            yCurve: '#4cd964', // Y = Green
            zCurve: '#3a86ff', // Z = Blue
            analogCurve: '#ffb703', // Yellow
            cursor: '#00ffff', // Cyan playhead
            crosshair: '#555e70'
        };

        this._initEvents();
        window.addEventListener('resize', () => this.resize());
    }

    _initEvents() {
        this.canvas.addEventListener('mousemove', (e) => {
            const rect = this.canvas.getBoundingClientRect();
            this.hoverPos = {
                x: e.clientX - rect.left,
                y: e.clientY - rect.top,
                clientX: e.clientX,
                clientY: e.clientY
            };
            this.render();
        });

        this.canvas.addEventListener('mouseleave', () => {
            this.hoverPos = null;
            if (this.tooltip) this.tooltip.style.display = 'none';
            this.render();
        });
    }

    resize() {
        const dpr = window.devicePixelRatio || 1;
        const rect = this.canvas.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return;

        this.canvas.width = rect.width * dpr;
        this.canvas.height = rect.height * dpr;
        this.ctx.resetTransform();
        this.ctx.scale(dpr, dpr);
        this.render();
    }

    loadTrial(trial) {
        this.trial = trial;
        this.viewStartFrame = 0;
        this.viewEndFrame = Math.max(1, trial.pointFrameCount - 1);
        this.trimStart = 0;
        this.trimEnd = this.viewEndFrame;
        this.resize();
    }

    setTrimBounds(start, end) {
        this.trimStart = start;
        this.trimEnd = end;
    }

    fitROI() {
        this.viewStartFrame = this.trimStart;
        this.viewEndFrame = this.trimEnd;
        this.render();
    }

    autoRange() {
        if (!this.trial) return;
        this.viewStartFrame = 0;
        this.viewEndFrame = Math.max(1, this.trial.pointFrameCount - 1);
        this.render();
    }

    plotMarker(name) {
        this.selectedMarker = name;
        this.isAnalogMode = false;
        this.render();
    }

    plotAnalog(name) {
        this.selectedAnalog = name;
        this.isAnalogMode = true;
        this.render();
    }

    setFrame(frameIndex) {
        this.currentFrame = frameIndex;
        this.render();
    }

    render() {
        const dpr = window.devicePixelRatio || 1;
        const width = this.canvas.width / dpr;
        const height = this.canvas.height / dpr;
        const ctx = this.ctx;

        ctx.clearRect(0, 0, width, height);

        if (!this.trial) {
            ctx.fillStyle = this.colors.text;
            ctx.font = '14px Inter, sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('No trial data loaded', width / 2, height / 2);
            return;
        }

        const plotArea = {
            x: this.padding.left,
            y: this.padding.top,
            w: Math.max(10, width - this.padding.left - this.padding.right),
            h: Math.max(10, height - this.padding.top - this.padding.bottom)
        };

        // Determine data series to draw
        let curves = [];
        let yMin = Infinity, yMax = -Infinity;

        if (!this.isAnalogMode && this.selectedMarker && this.trial.markers[this.selectedMarker]) {
            const raw = this.trial.markers[this.selectedMarker];
            const xSeries = [], ySeries = [], zSeries = [];
            const total = this.trial.pointFrameCount;

            for (let f = 0; f < total; f++) {
                const x = raw[f * 3];
                const y = raw[f * 3 + 1];
                const z = raw[f * 3 + 2];
                xSeries.push(x);
                ySeries.push(y);
                zSeries.push(z);

                if (f >= this.viewStartFrame && f <= this.viewEndFrame) {
                    if (!isNaN(x)) { yMin = Math.min(yMin, x); yMax = Math.max(yMax, x); }
                    if (!isNaN(y)) { yMin = Math.min(yMin, y); yMax = Math.max(yMax, y); }
                    if (!isNaN(z)) { yMin = Math.min(yMin, z); yMax = Math.max(yMax, z); }
                }
            }

            curves = [
                { name: `${this.selectedMarker} X`, color: this.colors.xCurve, data: xSeries },
                { name: `${this.selectedMarker} Y`, color: this.colors.yCurve, data: ySeries },
                { name: `${this.selectedMarker} Z`, color: this.colors.zCurve, data: zSeries }
            ];
        } else if (this.isAnalogMode && this.selectedAnalog && this.trial.analogs[this.selectedAnalog]) {
            const raw = this.trial.analogs[this.selectedAnalog];
            const subsamples = this.trial.analogSubsamples || 1;
            const data = [];
            const total = this.trial.pointFrameCount;

            for (let f = 0; f < total; f++) {
                const val = raw[f * subsamples] || 0;
                data.push(val);
                if (f >= this.viewStartFrame && f <= this.viewEndFrame) {
                    yMin = Math.min(yMin, val);
                    yMax = Math.max(yMax, val);
                }
            }

            curves = [{ name: this.selectedAnalog, color: this.colors.analogCurve, data }];
        }

        if (curves.length === 0 || yMin === Infinity) {
            yMin = -100;
            yMax = 100;
        }

        // Add 8% vertical margin
        const ySpan = (yMax - yMin) || 1.0;
        yMin -= ySpan * 0.08;
        yMax += ySpan * 0.08;

        const xSpan = Math.max(1, this.viewEndFrame - this.viewStartFrame);

        // Coordinate projection functions
        const projectX = (f) => plotArea.x + ((f - this.viewStartFrame) / xSpan) * plotArea.w;
        const projectY = (v) => plotArea.y + plotArea.h - ((v - yMin) / (yMax - yMin)) * plotArea.h;
        const unprojectX = (px) => this.viewStartFrame + ((px - plotArea.x) / plotArea.w) * xSpan;

        // 1. Draw Grid & Axes
        this._drawGrid(ctx, plotArea, xSpan, yMin, yMax, projectX, projectY);

        // 2. Draw Event Dashed Lines
        if (this.trial.events && this.trial.events.length > 0) {
            this._drawEventLines(ctx, plotArea, projectX);
        }

        // 3. Draw Curves
        curves.forEach(curve => {
            ctx.save();
            ctx.beginPath();
            ctx.rect(plotArea.x, plotArea.y, plotArea.w, plotArea.h);
            ctx.clip();

            ctx.strokeStyle = curve.color;
            ctx.lineWidth = 1.8;
            ctx.beginPath();

            let drawing = false;
            for (let f = this.viewStartFrame; f <= this.viewEndFrame; f++) {
                const val = curve.data[f];
                if (isNaN(val)) {
                    drawing = false;
                    continue;
                }
                const px = projectX(f);
                const py = projectY(val);

                if (!drawing) {
                    ctx.moveTo(px, py);
                    drawing = true;
                } else {
                    ctx.lineTo(px, py);
                }
            }
            ctx.stroke();
            ctx.restore();
        });

        // 4. Draw Playhead Vertical Line
        if (this.currentFrame >= this.viewStartFrame && this.currentFrame <= this.viewEndFrame) {
            const cursorX = projectX(this.currentFrame);
            ctx.save();
            ctx.strokeStyle = this.colors.cursor;
            ctx.lineWidth = 2.0;
            ctx.beginPath();
            ctx.moveTo(cursorX, plotArea.y);
            ctx.lineTo(cursorX, plotArea.y + plotArea.h);
            ctx.stroke();

            // Cursor top badge
            ctx.fillStyle = this.colors.cursor;
            ctx.beginPath();
            ctx.arc(cursorX, plotArea.y, 4, 0, Math.PI * 2);
            ctx.fill();
            ctx.restore();
        }

        // 5. Draw Curve Legend in top-left
        let legendX = plotArea.x + 10;
        curves.forEach(c => {
            ctx.fillStyle = c.color;
            ctx.beginPath();
            ctx.arc(legendX + 5, plotArea.y + 12, 4, 0, Math.PI * 2);
            ctx.fill();

            ctx.fillStyle = '#ffffff';
            ctx.font = '11px Inter, sans-serif';
            ctx.textAlign = 'left';
            ctx.fillText(c.name, legendX + 14, plotArea.y + 16);
            legendX += ctx.measureText(c.name).width + 30;
        });

        // 6. Handle Mouse Hover & Tooltip Readout
        if (this.hoverPos && this.hoverPos.x >= plotArea.x && this.hoverPos.x <= plotArea.x + plotArea.w) {
            const hoveredFrame = Math.round(unprojectX(this.hoverPos.x));
            const clampedFrame = Math.max(0, Math.min(this.trial.pointFrameCount - 1, hoveredFrame));
            const hoverScreenX = projectX(clampedFrame);

            // Crosshair vertical line
            ctx.save();
            ctx.strokeStyle = this.colors.crosshair;
            ctx.setLineDash([3, 3]);
            ctx.beginPath();
            ctx.moveTo(hoverScreenX, plotArea.y);
            ctx.lineTo(hoverScreenX, plotArea.y + plotArea.h);
            ctx.stroke();
            ctx.restore();

            // Show floating tooltip
            if (this.tooltip && curves.length > 0) {
                const time = (clampedFrame / (this.trial.pointRate || 100.0)).toFixed(3);
                let text = `<strong>Frame ${clampedFrame + 1} (${time}s)</strong><br/>`;
                curves.forEach(c => {
                    const val = c.data[clampedFrame];
                    const formatted = isNaN(val) ? 'NaN' : val.toFixed(2);
                    text += `<span style="color:${c.color}">●</span> ${c.name}: ${formatted}<br/>`;
                });

                this.tooltip.innerHTML = text;
                this.tooltip.style.display = 'block';
                this.tooltip.style.left = `${this.hoverPos.clientX + 14}px`;
                this.tooltip.style.top = `${this.hoverPos.clientY - 10}px`;
            }
        } else if (this.tooltip) {
            this.tooltip.style.display = 'none';
        }
    }

    _drawGrid(ctx, area, xSpan, yMin, yMax, projectX, projectY) {
        ctx.strokeStyle = this.colors.grid;
        ctx.lineWidth = 1;
        ctx.fillStyle = this.colors.text;
        ctx.font = '10px Inter, sans-serif';

        // Vertical lines & frame labels
        const numVTicks = 8;
        const fStep = Math.max(1, Math.round(xSpan / numVTicks));
        ctx.textAlign = 'center';

        for (let f = this.viewStartFrame; f <= this.viewEndFrame; f += fStep) {
            const px = projectX(f);
            ctx.beginPath();
            ctx.moveTo(px, area.y);
            ctx.lineTo(px, area.y + area.h);
            ctx.stroke();

            // 1-based frame label
            ctx.fillText((f + 1).toString(), px, area.y + area.h + 16);
        }

        // Horizontal lines & value labels
        const numHTicks = 6;
        const yValStep = (yMax - yMin) / numHTicks;
        ctx.textAlign = 'right';

        for (let i = 0; i <= numHTicks; i++) {
            const val = yMin + i * yValStep;
            const py = projectY(val);
            ctx.beginPath();
            ctx.moveTo(area.x, py);
            ctx.lineTo(area.x + area.w, py);
            ctx.stroke();

            ctx.fillText(val.toFixed(1), area.x - 8, py + 3);
        }
    }

    _drawEventLines(ctx, area, projectX) {
        ctx.save();
        ctx.setLineDash([4, 4]);
        ctx.lineWidth = 1.4;

        this.trial.events.forEach(ev => {
            if (ev.frame >= this.viewStartFrame && ev.frame <= this.viewEndFrame) {
                const px = projectX(ev.frame);
                ctx.strokeStyle = ev.iconColor || '#FF9800';
                ctx.beginPath();
                ctx.moveTo(px, area.y);
                ctx.lineTo(px, area.y + area.h);
                ctx.stroke();

                // Draw event label near bottom
                ctx.save();
                ctx.setLineDash([]);
                ctx.fillStyle = ev.iconColor || '#FF9800';
                ctx.font = 'bold 9px Inter, sans-serif';
                ctx.textAlign = 'center';
                ctx.fillText(ev.name, px, area.y + area.h - 6);
                ctx.restore();
            }
        });

        ctx.restore();
    }
}
