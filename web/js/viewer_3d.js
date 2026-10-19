/**
 * 3D Biomechanics Viewport using Three.js
 * Renders 3D marker cloud, biomechanics ground grid, XYZ orientation triad,
 * raycasting/mouse picking, camera presets, and trajectory tails.
 */

export class Viewer3D {
    constructor(containerElement, options = {}) {
        this.container = containerElement;
        this.trial = null;
        this.currentFrame = 0;
        this.markerMeshes = new Map(); // name -> THREE.Mesh
        this.markerColors = new Map(); // name -> THREE.Color
        this.markerVisibility = new Map(); // name -> boolean
        this.selectedMarkerName = null;
        this.trajectoryLine = null;
        this.showTrajectories = false;
        this.onMarkerSelected = options.onMarkerSelected || (() => {});
        this.onMarkerHovered = options.onMarkerHovered || (() => {});

        this.defaultMarkerColor = 0x00d2ff; // Bright cyan/blue
        this.selectedMarkerColor = 0xffe600; // Bright yellow
        this.markerRadius = 14.0; // mm

        this._initScene();
        this._initLights();
        this._initGrid();
        this._initInteraction();
        this._startRenderLoop();

        window.addEventListener('resize', () => this.onWindowResize());
    }

    _initScene() {
        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0x121316);

        const width = this.container.clientWidth || 800;
        const height = this.container.clientHeight || 600;

        this.camera = new THREE.PerspectiveCamera(45, width / height, 10, 100000);
        // Biomechanics Z-up coordinate system
        this.camera.up.set(0, 0, 1);
        this.camera.position.set(1500, -2500, 1500);

        this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
        this.renderer.setSize(width, height);
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        this.renderer.shadowMap.enabled = true;
        this.container.appendChild(this.renderer.domElement);

        this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.08;
        this.controls.target.set(0, 0, 800);
        this.controls.maxDistance = 50000;
        this.controls.minDistance = 50;

        // Container group for trial data
        this.trialGroup = new THREE.Group();
        this.scene.add(this.trialGroup);
    }

    _initLights() {
        const ambient = new THREE.AmbientLight(0xffffff, 0.7);
        this.scene.add(ambient);

        const dirLight1 = new THREE.DirectionalLight(0xffffff, 0.8);
        dirLight1.position.set(2000, -2000, 3000);
        this.scene.add(dirLight1);

        const dirLight2 = new THREE.DirectionalLight(0x88bbff, 0.4);
        dirLight2.position.set(-2000, 2000, 1000);
        this.scene.add(dirLight2);
    }

    _initGrid() {
        // Ground grid in XY plane at Z = 0
        const size = 6000; // 6 meters
        const divisions = 60; // 100mm per grid line
        const gridHelper = new THREE.GridHelper(size, divisions, 0x3a4050, 0x222630);
        // Rotate GridHelper (which is in XZ) to be in XY (Z-up)
        gridHelper.rotation.x = Math.PI / 2;
        gridHelper.position.set(0, 0, 0);
        this.gridHelper = gridHelper;
        this.scene.add(gridHelper);

        // Coordinate axes triad (X=Red, Y=Green, Z=Blue)
        this.axesHelper = new THREE.AxesHelper(400);
        this.scene.add(this.axesHelper);
    }

    _initInteraction() {
        this.raycaster = new THREE.Raycaster();
        this.mouse = new THREE.Vector2();
        this.hoveredMarker = null;

        const dom = this.renderer.domElement;
        let downPos = { x: 0, y: 0 };

        dom.addEventListener('pointerdown', (e) => {
            downPos = { x: e.clientX, y: e.clientY };
        });

        dom.addEventListener('pointermove', (e) => {
            const rect = dom.getBoundingClientRect();
            this.mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
            this.mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
            this._checkHover(e.clientX, e.clientY);
        });

        dom.addEventListener('pointerup', (e) => {
            const dist = Math.hypot(e.clientX - downPos.x, e.clientY - downPos.y);
            if (dist < 5) {
                // Click
                this._checkClick();
            }
        });
    }

    _checkHover(screenX, screenY) {
        if (!this.trial || this.markerMeshes.size === 0) return;
        this.raycaster.setFromCamera(this.mouse, this.camera);
        const visibleMeshes = Array.from(this.markerMeshes.values()).filter(m => m.visible);
        const intersects = this.raycaster.intersectObjects(visibleMeshes);

        if (intersects.length > 0) {
            const hitMesh = intersects[0].object;
            const markerName = hitMesh.userData.markerName;
            this.renderer.domElement.style.cursor = 'pointer';
            this.onMarkerHovered(markerName, screenX, screenY, hitMesh.position);
        } else {
            this.renderer.domElement.style.cursor = 'default';
            this.onMarkerHovered(null);
        }
    }

    _checkClick() {
        if (!this.trial || this.markerMeshes.size === 0) return;
        this.raycaster.setFromCamera(this.mouse, this.camera);
        const visibleMeshes = Array.from(this.markerMeshes.values()).filter(m => m.visible);
        const intersects = this.raycaster.intersectObjects(visibleMeshes);

        if (intersects.length > 0) {
            const hitMesh = intersects[0].object;
            const markerName = hitMesh.userData.markerName;
            this.selectMarker(markerName);
        } else {
            this.selectMarker(null);
        }
    }

    loadTrial(trial) {
        this.trial = trial;
        this.currentFrame = 0;
        this.clearTrial();

        // Marker geometry - shared sphere
        const sphereGeo = new THREE.SphereGeometry(this.markerRadius, 24, 24);

        // Calculate centroid of all valid markers in the first 10 frames to center camera
        let sumX = 0, sumY = 0, sumZ = 0, count = 0;
        const checkFrames = Math.min(10, trial.pointFrameCount);

        trial.markerNames.forEach((name, idx) => {
            // Assign distinct color palette
            const hue = (idx * 137.5) % 360; // Golden angle distribution
            const initialColor = new THREE.Color(`hsl(${hue}, 80%, 60%)`);
            this.markerColors.set(name, initialColor);
            this.markerVisibility.set(name, true);

            const mat = new THREE.MeshStandardMaterial({
                color: initialColor,
                roughness: 0.3,
                metalness: 0.1,
                emissive: initialColor.clone().multiplyScalar(0.2)
            });

            const mesh = new THREE.Mesh(sphereGeo, mat);
            mesh.userData = { markerName: name };
            this.markerMeshes.set(name, mesh);
            this.trialGroup.add(mesh);

            // Accumulate positions for framing
            const coords = trial.markers[name];
            if (coords) {
                for (let f = 0; f < checkFrames; f++) {
                    const x = coords[f * 3];
                    const y = coords[f * 3 + 1];
                    const z = coords[f * 3 + 2];
                    if (!isNaN(x) && !isNaN(y) && !isNaN(z)) {
                        sumX += x;
                        sumY += y;
                        sumZ += z;
                        count++;
                    }
                }
            }
        });

        // Update to initial frame
        this.setFrame(0);

        // Center camera on data
        if (count > 0) {
            const centerX = sumX / count;
            const centerY = sumY / count;
            const centerZ = sumZ / count;
            this.controls.target.set(centerX, centerY, centerZ);
            this.camera.position.set(centerX + 1500, centerY - 2500, centerZ + 1200);
            this.controls.update();

            // Adjust ground grid near trial centroid
            this.gridHelper.position.set(centerX, centerY, 0);
        }
    }

    clearTrial() {
        // Remove existing marker meshes
        this.markerMeshes.forEach(mesh => {
            this.trialGroup.remove(mesh);
            if (mesh.geometry) mesh.geometry.dispose();
            if (mesh.material) mesh.material.dispose();
        });
        this.markerMeshes.clear();
        this.markerColors.clear();
        this.markerVisibility.clear();
        this.selectedMarkerName = null;
        this._removeTrajectoryLine();
    }

    setFrame(frameIndex) {
        if (!this.trial) return;
        this.currentFrame = Math.max(0, Math.min(this.trial.pointFrameCount - 1, frameIndex));

        this.markerMeshes.forEach((mesh, name) => {
            const coords = this.trial.markers[name];
            const isVisible = this.markerVisibility.get(name) !== false;

            if (!coords || !isVisible) {
                mesh.visible = false;
                return;
            }

            const idx = this.currentFrame * 3;
            const x = coords[idx];
            const y = coords[idx + 1];
            const z = coords[idx + 2];

            if (isNaN(x) || isNaN(y) || isNaN(z)) {
                mesh.visible = false;
            } else {
                mesh.visible = true;
                mesh.position.set(x, y, z);
            }
        });

        if (this.showTrajectories && this.selectedMarkerName) {
            this._updateTrajectoryLine();
        }
    }

    selectMarker(name) {
        this.selectedMarkerName = name;

        // Update colors
        this.markerMeshes.forEach((mesh, mName) => {
            const isSelected = mName === name;
            const baseColor = this.markerColors.get(mName) || new THREE.Color(this.defaultMarkerColor);
            const activeColor = isSelected ? new THREE.Color(this.selectedMarkerColor) : baseColor;

            mesh.material.color.copy(activeColor);
            mesh.material.emissive.copy(activeColor.clone().multiplyScalar(isSelected ? 0.6 : 0.2));
            mesh.scale.setScalar(isSelected ? 1.35 : 1.0);
        });

        if (name && this.showTrajectories) {
            this._createTrajectoryLine(name);
        } else {
            this._removeTrajectoryLine();
        }

        this.onMarkerSelected(name);
    }

    setMarkerColor(name, hexColor) {
        const color = new THREE.Color(hexColor);
        this.markerColors.set(name, color);
        const mesh = this.markerMeshes.get(name);
        if (mesh) {
            if (name !== this.selectedMarkerName) {
                mesh.material.color.copy(color);
                mesh.material.emissive.copy(color.clone().multiplyScalar(0.2));
            }
        }
    }

    setMarkerVisibility(name, visible) {
        this.markerVisibility.set(name, visible);
        const mesh = this.markerMeshes.get(name);
        if (mesh) {
            mesh.visible = visible;
        }
    }

    setAllMarkersVisibility(visible) {
        this.markerVisibility.forEach((_, name) => {
            this.markerVisibility.set(name, visible);
        });
        this.setFrame(this.currentFrame);
    }

    toggleTrajectories(show) {
        this.showTrajectories = show;
        if (show && this.selectedMarkerName) {
            this._createTrajectoryLine(this.selectedMarkerName);
        } else {
            this._removeTrajectoryLine();
        }
    }

    _createTrajectoryLine(name) {
        this._removeTrajectoryLine();
        if (!this.trial || !this.trial.markers[name]) return;

        const coords = this.trial.markers[name];
        const points = [];
        for (let f = 0; f < this.trial.pointFrameCount; f++) {
            const x = coords[f * 3];
            const y = coords[f * 3 + 1];
            const z = coords[f * 3 + 2];
            if (!isNaN(x) && !isNaN(y) && !isNaN(z)) {
                points.push(new THREE.Vector3(x, y, z));
            }
        }

        if (points.length < 2) return;
        const geometry = new THREE.BufferGeometry().setFromPoints(points);
        const material = new THREE.LineBasicMaterial({
            color: 0xffaa00,
            linewidth: 2,
            transparent: true,
            opacity: 0.75
        });

        this.trajectoryLine = new THREE.Line(geometry, material);
        this.trialGroup.add(this.trajectoryLine);
    }

    _removeTrajectoryLine() {
        if (this.trajectoryLine) {
            this.trialGroup.remove(this.trajectoryLine);
            if (this.trajectoryLine.geometry) this.trajectoryLine.geometry.dispose();
            if (this.trajectoryLine.material) this.trajectoryLine.material.dispose();
            this.trajectoryLine = null;
        }
    }

    _updateTrajectoryLine() {
        if (this.selectedMarkerName && !this.trajectoryLine) {
            this._createTrajectoryLine(this.selectedMarkerName);
        }
    }

    // Camera Presets
    setCameraPreset(viewName) {
        if (!this.controls) return;
        const target = this.controls.target;
        const dist = 3000;

        switch (viewName.toLowerCase()) {
            case 'front': // Looking along +Y
                this.camera.position.set(target.x, target.y - dist, target.z);
                this.camera.up.set(0, 0, 1);
                break;
            case 'back': // Looking along -Y
                this.camera.position.set(target.x, target.y + dist, target.z);
                this.camera.up.set(0, 0, 1);
                break;
            case 'right': // Looking along -X (from right side)
                this.camera.position.set(target.x + dist, target.y, target.z);
                this.camera.up.set(0, 0, 1);
                break;
            case 'left': // Looking along +X (from left side)
                this.camera.position.set(target.x - dist, target.y, target.z);
                this.camera.up.set(0, 0, 1);
                break;
            case 'top': // Looking down from +Z
                this.camera.position.set(target.x, target.y + 0.001, target.z + dist);
                this.camera.up.set(0, 1, 0);
                break;
            case 'isometric':
            default:
                this.camera.position.set(target.x + dist * 0.7, target.y - dist * 0.7, target.z + dist * 0.5);
                this.camera.up.set(0, 0, 1);
                break;
        }
        this.controls.update();
    }

    resetCamera() {
        this.setCameraPreset('isometric');
    }

    toggleGrid(visible) {
        if (this.gridHelper) this.gridHelper.visible = visible;
    }

    toggleAxes(visible) {
        if (this.axesHelper) this.axesHelper.visible = visible;
    }

    onWindowResize() {
        const width = this.container.clientWidth;
        const height = this.container.clientHeight;
        if (width === 0 || height === 0) return;

        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(width, height);
    }

    _startRenderLoop() {
        const animate = () => {
            requestAnimationFrame(animate);
            if (this.controls) this.controls.update();
            this.renderer.render(this.scene, this.camera);
        };
        animate();
    }
}
