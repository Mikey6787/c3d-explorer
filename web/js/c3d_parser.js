/**
 * C3D Binary File Parser (Client-Side, Zero Dependencies)
 * Reads standard C3D motion capture files directly into JavaScript typed arrays.
 * Supports Intel (PC) and DEC formats, floating-point and scaled integer coordinates,
 * analog channels, and events.
 */

export class C3DParser {
    static getEventColor(label = '', context = '') {
        const norm = (label + ' ' + context).toLowerCase();
        if (norm.includes('right') || norm.startsWith('r_')) {
            if (norm.includes('strike') || norm.includes('contact') || norm.includes('hs')) {
                return '#E53935'; // Vivid Red (Right Foot Strike)
            } else if (norm.includes('off') || norm.includes('to')) {
                return '#FB8C00'; // Orange (Right Foot Off)
            }
            return '#FF7043';
        } else if (norm.includes('left') || norm.startsWith('l_')) {
            if (norm.includes('strike') || norm.includes('contact') || norm.includes('hs')) {
                return '#1E88E5'; // Vivid Blue (Left Foot Strike)
            } else if (norm.includes('off') || norm.includes('to')) {
                return '#00ACC1'; // Cyan (Left Foot Off)
            }
            return '#42A5F5';
        } else {
            if (norm.includes('start')) return '#43A047'; // Green
            if (norm.includes('end') || norm.includes('stop')) return '#8E24AA'; // Purple
            return '#FDD835'; // Amber
        }
    }

    /**
     * Parse an ArrayBuffer containing a .c3d file
     * @param {ArrayBuffer} buffer
     * @param {string} fileName
     * @returns {Object} Parsed trial data
     */
    static parse(buffer, fileName = 'trial.c3d') {
        const view = new DataView(buffer);
        if (buffer.byteLength < 512) {
            throw new Error('Invalid C3D file: buffer too small (< 512 bytes).');
        }

        // --- 1. Parse Header ---
        const paramBlock = view.getUint8(0);
        const key = view.getUint8(1);
        if (key !== 0x50 && key !== 80) {
            throw new Error(`Invalid C3D signature: expected 0x50, got 0x${key.toString(16)}`);
        }

        const littleEndian = true;
        const numPoints = view.getUint16(2, littleEndian);
        const totalAnalog = view.getUint16(4, littleEndian);
        const firstFrame = view.getUint16(6, littleEndian);
        const lastFrame = view.getUint16(8, littleEndian);
        const maxGap = view.getUint16(10, littleEndian);
        const scaleFactor = view.getFloat32(12, littleEndian);
        const dataStartBlock = view.getUint16(16, littleEndian);
        const analogSubsamples = view.getUint16(18, littleEndian);
        const pointRate = view.getFloat32(20, littleEndian);

        const pointFrameCount = Math.max(0, lastFrame >= firstFrame ? lastFrame - firstFrame + 1 : 0);
        const analogChannels = analogSubsamples > 0 ? Math.floor(totalAnalog / analogSubsamples) : 0;
        const analogRate = pointRate * analogSubsamples;
        const analogFrameCount = pointFrameCount * analogSubsamples;

        // --- 2. Parse Parameter Section ---
        const paramStartPos = (paramBlock - 1) * 512;
        const params = {};
        const groups = {};

        if (paramStartPos < buffer.byteLength) {
            let pos = paramStartPos;
            const pBlock = view.getUint8(pos);
            const pReserved = view.getUint8(pos + 1);
            const pCount = view.getUint8(pos + 2);
            const pProc = view.getUint8(pos + 3); // 84=Intel, 85=DEC, 86=MIPS
            pos += 4;

            while (pos < buffer.byteLength - 2) {
                const rawNameLen = view.getInt8(pos);
                pos += 1;
                if (rawNameLen === 0) break;

                const nameLen = Math.abs(rawNameLen);
                const groupId = view.getInt8(pos);
                pos += 1;

                let name = '';
                for (let i = 0; i < nameLen; i++) {
                    name += String.fromCharCode(view.getUint8(pos + i));
                }
                name = name.toUpperCase().trim();
                pos += nameLen;

                const nextOffset = view.getInt16(pos, littleEndian);
                const nextPos = pos + nextOffset;
                pos += 2;

                if (groupId < 0) {
                    // Group Record
                    const gid = Math.abs(groupId);
                    const descLen = view.getUint8(pos);
                    pos += 1;
                    let desc = '';
                    for (let i = 0; i < descLen; i++) {
                        desc += String.fromCharCode(view.getUint8(pos + i));
                    }
                    groups[gid] = name;
                    if (!params[name]) params[name] = {};
                } else {
                    // Parameter Record
                    const gname = groups[groupId] || `GROUP_${groupId}`;
                    if (!params[gname]) params[gname] = {};

                    const dataType = view.getInt8(pos);
                    pos += 1;
                    const numDims = view.getUint8(pos);
                    pos += 1;
                    const dims = [];
                    let totalElements = 1;
                    for (let d = 0; d < numDims; d++) {
                        const dimVal = view.getUint8(pos + d);
                        dims.push(dimVal);
                        totalElements *= dimVal;
                    }
                    pos += numDims;

                    let paramData = null;
                    if (dataType === -1) {
                        // Character string(s)
                        if (numDims === 0) {
                            paramData = '';
                        } else if (numDims === 1) {
                            let str = '';
                            for (let i = 0; i < dims[0]; i++) {
                                str += String.fromCharCode(view.getUint8(pos + i));
                            }
                            paramData = str.trim();
                        } else if (numDims === 2) {
                            const charLen = dims[0];
                            const count = dims[1];
                            const strings = [];
                            for (let c = 0; c < count; c++) {
                                let str = '';
                                for (let i = 0; i < charLen; i++) {
                                    str += String.fromCharCode(view.getUint8(pos + c * charLen + i));
                                }
                                strings.push(str.trim());
                            }
                            paramData = strings;
                        } else {
                            paramData = [];
                        }
                    } else if (dataType === 1) {
                        // Byte / Int8
                        paramData = [];
                        for (let i = 0; i < totalElements; i++) {
                            paramData.push(view.getInt8(pos + i));
                        }
                    } else if (dataType === 2) {
                        // Int16
                        paramData = [];
                        for (let i = 0; i < totalElements; i++) {
                            paramData.push(view.getInt16(pos + i * 2, littleEndian));
                        }
                    } else if (dataType === 4) {
                        // Float32
                        paramData = [];
                        for (let i = 0; i < totalElements; i++) {
                            paramData.push(view.getFloat32(pos + i * 4, littleEndian));
                        }
                    }

                    params[gname][name] = {
                        dataType,
                        dims,
                        data: paramData
                    };
                }

                if (nextOffset === 0) break;
                pos = nextPos;
            }
        }

        // --- 3. Extract Marker Names and Units ---
        let markerNames = [];
        if (params['POINT'] && params['POINT']['LABELS']) {
            const rawLabels = params['POINT']['LABELS'].data;
            if (Array.isArray(rawLabels)) {
                markerNames = rawLabels.filter(lbl => lbl.length > 0);
            }
        }
        if (markerNames.length === 0) {
            for (let i = 0; i < numPoints; i++) {
                markerNames.push(`Marker_${i + 1}`);
            }
        }

        let markerUnits = 'mm';
        if (params['POINT'] && params['POINT']['UNITS']) {
            const unitsVal = params['POINT']['UNITS'].data;
            if (typeof unitsVal === 'string') markerUnits = unitsVal;
            else if (Array.isArray(unitsVal) && unitsVal.length > 0) markerUnits = unitsVal[0];
        }

        // --- 4. Extract Analog Channel Names ---
        let analogNames = [];
        if (params['ANALOG'] && params['ANALOG']['LABELS']) {
            const rawLabels = params['ANALOG']['LABELS'].data;
            if (Array.isArray(rawLabels)) {
                analogNames = rawLabels.slice(0, analogChannels);
            }
        }
        if (analogNames.length === 0) {
            for (let i = 0; i < analogChannels; i++) {
                analogNames.push(`Channel_${(i + 1).toString().padStart(2, '0')}`);
            }
        }

        // Analog scaling factors
        let genScale = 1.0;
        if (params['ANALOG'] && params['ANALOG']['GEN_SCALE'] && params['ANALOG']['GEN_SCALE'].data) {
            genScale = Array.isArray(params['ANALOG']['GEN_SCALE'].data) 
                ? params['ANALOG']['GEN_SCALE'].data[0] 
                : params['ANALOG']['GEN_SCALE'].data;
        }
        let channelScales = new Float32Array(analogChannels).fill(1.0);
        if (params['ANALOG'] && params['ANALOG']['SCALE'] && Array.isArray(params['ANALOG']['SCALE'].data)) {
            params['ANALOG']['SCALE'].data.slice(0, analogChannels).forEach((sc, idx) => {
                channelScales[idx] = sc;
            });
        }
        let channelOffsets = new Float32Array(analogChannels).fill(0.0);
        if (params['ANALOG'] && params['ANALOG']['OFFSET'] && Array.isArray(params['ANALOG']['OFFSET'].data)) {
            params['ANALOG']['OFFSET'].data.slice(0, analogChannels).forEach((off, idx) => {
                channelOffsets[idx] = off;
            });
        }

        // --- 5. Extract Events ---
        const events = [];
        if (params['EVENT']) {
            const evUsed = params['EVENT']['USED'] ? (Array.isArray(params['EVENT']['USED'].data) ? params['EVENT']['USED'].data[0] : params['EVENT']['USED'].data) : 0;
            const evLabels = params['EVENT']['LABELS'] ? params['EVENT']['LABELS'].data : [];
            const evContexts = params['EVENT']['CONTEXTS'] ? params['EVENT']['CONTEXTS'].data : [];
            const evTimes = params['EVENT']['TIMES'] ? params['EVENT']['TIMES'].data : [];
            const count = evUsed > 0 ? evUsed : (Array.isArray(evLabels) ? evLabels.length : 0);

            for (let i = 0; i < count; i++) {
                const name = Array.isArray(evLabels) && evLabels[i] ? evLabels[i].trim() : `Event_${i + 1}`;
                const context = Array.isArray(evContexts) && evContexts[i] ? evContexts[i].trim() : '';
                let time = 0.0;
                if (Array.isArray(evTimes)) {
                    time = evTimes[i * 2] !== undefined ? evTimes[i * 2] : (evTimes[i] || 0.0);
                }
                const frame = Math.max(0, Math.round(time * pointRate));
                const color = C3DParser.getEventColor(name, context);
                events.push({
                    name,
                    context,
                    time,
                    frame, // 0-based frame index relative to trial
                    displayFrame: frame + 1, // 1-based frame for display
                    iconColor: color
                });
            }
        }

        // Also check header events if no parameter events found
        if (events.length === 0 && buffer.byteLength >= 512) {
            const evHeaderSupport = view.getUint16(298, littleEndian);
            const evHeaderCount = view.getUint16(300, littleEndian);
            if (evHeaderCount > 0 && evHeaderCount <= 18) {
                let timeOffset = 304;
                let flagOffset = 376;
                let labelOffset = 394;
                for (let i = 0; i < evHeaderCount; i++) {
                    const time = view.getFloat32(timeOffset + i * 4, littleEndian);
                    let lbl = '';
                    for (let c = 0; c < 4; c++) {
                        const code = view.getUint8(labelOffset + i * 4 + c);
                        if (code > 32) lbl += String.fromCharCode(code);
                    }
                    lbl = lbl.trim() || `Event_${i + 1}`;
                    const frame = Math.max(0, Math.round(time * pointRate));
                    events.push({
                        name: lbl,
                        context: 'General',
                        time,
                        frame,
                        displayFrame: frame + 1,
                        iconColor: C3DParser.getEventColor(lbl, 'General')
                    });
                }
            }
        }

        // Sort events chronologically
        events.sort((a, b) => a.time - b.time);

        // --- 6. Parse 3D Marker & Analog Data ---
        const isFloatingPoint = scaleFactor < 0;
        const absScale = Math.abs(scaleFactor);
        const dataOffset = (dataStartBlock - 1) * 512;

        const markers = {};
        const residuals = {};
        markerNames.forEach(name => {
            markers[name] = new Float32Array(pointFrameCount * 3);
            residuals[name] = new Float32Array(pointFrameCount);
        });

        const analogs = {};
        analogNames.forEach(name => {
            analogs[name] = new Float32Array(analogFrameCount);
        });

        let curPos = dataOffset;
        const bytesPerMarker = isFloatingPoint ? 16 : 8;
        const bytesPerAnalogSample = 2; // Signed 16-bit integers
        const bytesPerFrame = (numPoints * bytesPerMarker) + (totalAnalog * bytesPerAnalogSample);

        for (let f = 0; f < pointFrameCount; f++) {
            if (curPos + bytesPerFrame > buffer.byteLength) {
                console.warn(`Reached end of buffer at frame ${f} of ${pointFrameCount}`);
                break;
            }

            // 1. Read Markers for this frame
            for (let m = 0; m < numPoints; m++) {
                const name = markerNames[m];
                if (!name) {
                    curPos += bytesPerMarker;
                    continue;
                }

                let x, y, z, res;
                if (isFloatingPoint) {
                    x = view.getFloat32(curPos, littleEndian);
                    y = view.getFloat32(curPos + 4, littleEndian);
                    z = view.getFloat32(curPos + 8, littleEndian);
                    res = view.getFloat32(curPos + 12, littleEndian);
                    curPos += 16;
                } else {
                    x = view.getInt16(curPos, littleEndian) * absScale;
                    y = view.getInt16(curPos + 2, littleEndian) * absScale;
                    z = view.getInt16(curPos + 4, littleEndian) * absScale;
                    res = view.getUint8(curPos + 6); // residual
                    curPos += 8;
                }

                const idx = f * 3;
                if (res < 0 || isNaN(x) || isNaN(y) || isNaN(z)) {
                    markers[name][idx] = NaN;
                    markers[name][idx + 1] = NaN;
                    markers[name][idx + 2] = NaN;
                    residuals[name][f] = -1.0;
                } else {
                    markers[name][idx] = x;
                    markers[name][idx + 1] = y;
                    markers[name][idx + 2] = z;
                    residuals[name][f] = res;
                }
            }

            // 2. Read Analog Subsamples for this frame
            for (let s = 0; s < analogSubsamples; s++) {
                const analogFrameIdx = f * analogSubsamples + s;
                for (let c = 0; c < analogChannels; c++) {
                    const chName = analogNames[c];
                    const rawVal = view.getInt16(curPos, littleEndian);
                    curPos += 2;
                    if (chName && analogs[chName]) {
                        const scaled = (rawVal - channelOffsets[c]) * channelScales[c] * genScale;
                        analogs[chName][analogFrameIdx] = scaled;
                    }
                }
            }
        }

        return {
            fileName,
            firstFrame,
            lastFrame,
            pointRate,
            pointFrameCount,
            analogRate,
            analogFrameCount,
            analogSubsamples,
            markerUnits,
            scaleFactor,
            markerNames,
            markers,
            residuals,
            analogNames,
            analogs,
            events,
            params
        };
    }
}
