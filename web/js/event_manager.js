/**
 * Event Manager Modal / Dialog
 * Allows viewing, adding, editing, and deleting C3D events.
 */

import { C3DParser } from './c3d_parser.js';

export class EventManager {
    constructor(modalElement, options = {}) {
        this.modal = modalElement;
        this.trial = null;
        this.getCurrentFrame = options.getCurrentFrame || (() => 0);
        this.onEventsUpdated = options.onEventsUpdated || (() => {});
        this.onSeekRequested = options.onSeekRequested || (() => {});

        this._buildUI();
    }

    _buildUI() {
        this.modal.innerHTML = `
            <div class="modal-backdrop"></div>
            <div class="modal-dialog">
                <div class="modal-header">
                    <h3 class="modal-title">Event Manager</h3>
                    <button class="modal-close-btn">&times;</button>
                </div>
                <div class="modal-body">
                    <div class="event-form-row">
                        <input type="text" id="ev-input-name" placeholder="Event Name (e.g. Foot Strike)" class="form-input">
                        <select id="ev-select-context" class="form-select">
                            <option value="General">General</option>
                            <option value="Right">Right</option>
                            <option value="Left">Left</option>
                        </select>
                        <input type="number" id="ev-input-frame" placeholder="Frame (1-based)" class="form-input" style="width: 110px;">
                        <button id="btn-add-event" class="btn-primary-sm">+ Add Event</button>
                    </div>

                    <div class="table-container">
                        <table class="event-table">
                            <thead>
                                <tr>
                                    <th>Color</th>
                                    <th>Name</th>
                                    <th>Context</th>
                                    <th>Frame</th>
                                    <th>Time</th>
                                    <th>Action</th>
                                </tr>
                            </thead>
                            <tbody id="event-table-body">
                                <tr><td colspan="6" class="text-center">No events in this trial</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        `;

        this.backdrop = this.modal.querySelector('.modal-backdrop');
        this.closeBtn = this.modal.querySelector('.modal-close-btn');
        this.tableBody = this.modal.querySelector('#event-table-body');
        this.inputName = this.modal.querySelector('#ev-input-name');
        this.selectContext = this.modal.querySelector('#ev-select-context');
        this.inputFrame = this.modal.querySelector('#ev-input-frame');
        this.btnAdd = this.modal.querySelector('#btn-add-event');

        this.backdrop.addEventListener('click', () => this.hide());
        this.closeBtn.addEventListener('click', () => this.hide());

        this.btnAdd.addEventListener('click', () => this._handleAddEvent());
    }

    loadTrial(trial) {
        this.trial = trial;
        this.renderTable();
    }

    show() {
        if (!this.trial) return;
        const curFrame0 = this.getCurrentFrame();
        this.inputFrame.value = (curFrame0 + 1).toString();
        this.inputName.value = '';
        this.renderTable();
        this.modal.style.display = 'flex';
    }

    hide() {
        this.modal.style.display = 'none';
    }

    renderTable() {
        if (!this.trial || !this.trial.events || this.trial.events.length === 0) {
            this.tableBody.innerHTML = '<tr><td colspan="6" class="text-center" style="padding: 20px; color: #777;">No events defined</td></tr>';
            return;
        }

        this.tableBody.innerHTML = '';
        this.trial.events.forEach((ev, idx) => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><span class="event-color-dot" style="background-color: ${ev.iconColor};"></span></td>
                <td><strong>${ev.name}</strong></td>
                <td><span class="badge-context context-${ev.context.toLowerCase()}">${ev.context || 'General'}</span></td>
                <td>Frame ${ev.displayFrame}</td>
                <td>${ev.time.toFixed(3)}s</td>
                <td>
                    <button class="btn-xs btn-seek" title="Jump to frame">Seek</button>
                    <button class="btn-xs btn-delete" title="Delete event">Delete</button>
                </td>
            `;

            tr.querySelector('.btn-seek').addEventListener('click', () => {
                this.onSeekRequested(ev.frame);
                this.hide();
            });

            tr.querySelector('.btn-delete').addEventListener('click', () => {
                this.trial.events.splice(idx, 1);
                this.renderTable();
                this.onEventsUpdated(this.trial.events);
            });

            this.tableBody.appendChild(tr);
        });
    }

    _handleAddEvent() {
        const name = this.inputName.value.trim();
        if (!name) {
            alert('Please enter an event name.');
            return;
        }

        const displayFrame = parseInt(this.inputFrame.value, 10);
        if (isNaN(displayFrame) || displayFrame < 1 || displayFrame > this.trial.pointFrameCount) {
            alert(`Frame must be between 1 and ${this.trial.pointFrameCount}`);
            return;
        }

        const frame0 = displayFrame - 1;
        const context = this.selectContext.value;
        const time = this.trial.pointRate > 0 ? (frame0 / this.trial.pointRate) : 0;
        const iconColor = C3DParser.getEventColor(name, context);

        const newEvent = {
            name,
            context,
            time,
            frame: frame0,
            displayFrame,
            iconColor
        };

        this.trial.events.push(newEvent);
        this.trial.events.sort((a, b) => a.time - b.time);

        this.inputName.value = '';
        this.renderTable();
        this.onEventsUpdated(this.trial.events);
    }
}
