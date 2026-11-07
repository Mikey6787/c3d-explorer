"""
Pipeline Manager and XML Exporter for C3D Explorer.

Tracks and records all operations, trial modifications, settings, and inventories,
and exports them to a comprehensive, well-structured XML Pipeline file.
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
import os
import datetime
import xml.etree.ElementTree as ET
import xml.dom.minidom as minidom
import numpy as np

from core.data_models import C3DTrial, C3DEvent


@dataclass
class PipelineStep:
    """Represents a single discrete operation or modification applied to the trial."""
    action: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )


class PipelineManager:
    """
    Manages the session pipeline of operations, modifications, and workstation settings,
    and provides functionality to export everything to a formatted XML file.
    """

    def __init__(self, trial: Optional[C3DTrial] = None, source_path: str = ""):
        self.trial: Optional[C3DTrial] = trial
        self.source_path: str = source_path
        self.operations: List[PipelineStep] = []
        self._logged_command_signatures: set = set()

    def set_trial(self, trial: Optional[C3DTrial], source_path: str = ""):
        """Reset or initialize with a new trial."""
        self.trial = trial
        self.source_path = source_path or (trial.file_path if trial else "")
        self.operations.clear()
        self._logged_command_signatures.clear()

    # --------------------------------------------------------------------------
    # Explicit Operation Recording
    # --------------------------------------------------------------------------
    def record_operation(self, action: str, description: str, parameters: Optional[Dict[str, Any]] = None) -> PipelineStep:
        """Record an arbitrary pipeline step."""
        step = PipelineStep(
            action=action,
            description=description,
            parameters=parameters or {}
        )
        self.operations.append(step)
        return step

    def record_create_average_marker(
        self,
        new_name: str,
        parent1: str,
        parent2: str,
        weights: Tuple[float, float] = (0.5, 0.5),
        color_rgba: Optional[tuple] = None
    ) -> PipelineStep:
        """Record creation of a virtual / average marker between two existing markers."""
        params = {
            "NewMarkerName": new_name,
            "SourceMarker1": parent1,
            "SourceMarker2": parent2,
            "Weight1": weights[0],
            "Weight2": weights[1],
            "Formula": f"({parent1} * {weights[0]}) + ({parent2} * {weights[1]})",
        }
        if color_rgba is not None:
            params["ColorRGBA"] = ", ".join(f"{c:.3f}" for c in color_rgba)

        desc = f"Created average virtual marker '{new_name}' from '{parent1}' and '{parent2}'"
        return self.record_operation("CreateAverageMarker", desc, params)

    def record_create_centroid_marker(
        self,
        new_name: str,
        source_markers: List[str],
        color_rgba: Optional[tuple] = None
    ) -> PipelineStep:
        """Record creation of a centroid marker computed from multiple source markers."""
        src_str = ", ".join(source_markers)
        params = {
            "NewMarkerName": new_name,
            "SourceMarkers": src_str,
            "Formula": f"Centroid({src_str})",
            "MarkerCount": len(source_markers),
        }
        if color_rgba is not None:
            params["ColorRGBA"] = ", ".join(f"{c:.3f}" for c in color_rgba)

        desc = f"Created centroid marker '{new_name}' from {len(source_markers)} markers: {src_str}"
        return self.record_operation("CreateCentroidMarker", desc, params)

    def record_calculate_hjc(
        self,
        rhjc_name: str,
        lhjc_name: str,
        lasi_marker: str,
        rasi_marker: str,
        lpsi_marker: str,
        rpsi_marker: str
    ) -> PipelineStep:
        """Record calculation of Harrington Hip Joint Centers."""
        params = {
            "RightHJCName": rhjc_name,
            "LeftHJCName": lhjc_name,
            "LASIMarker": lasi_marker,
            "RASIMarker": rasi_marker,
            "LPSIMarker": lpsi_marker,
            "RPSIMarker": rpsi_marker,
            "Method": "Harrington et al. (2006)",
        }
        desc = (
            f"Calculated Hip Joint Centers '{rhjc_name}' and '{lhjc_name}' via Harrington (2006) "
            f"from {lasi_marker}, {rasi_marker}, {lpsi_marker}, {rpsi_marker}"
        )
        return self.record_operation("CalculateHipJointCenter", desc, params)

    def record_add_marker(
        self,
        name: str,
        source_type: str = "manual",
        source_file: str = "",
        default_coords: Optional[Tuple[float, float, float]] = None,
        color_rgba: Optional[tuple] = None,
        frame_count: Optional[int] = None
    ) -> PipelineStep:
        """Record addition of a new marker (either imported from file or specified manually)."""
        params: Dict[str, Any] = {
            "MarkerName": name,
            "SourceType": source_type,
        }
        if source_file:
            params["SourceFile"] = source_file
        if default_coords is not None:
            params["DefaultCoordinates"] = {
                "X": default_coords[0],
                "Y": default_coords[1],
                "Z": default_coords[2]
            }
        if color_rgba is not None:
            params["ColorRGBA"] = ", ".join(f"{c:.3f}" for c in color_rgba)
        if frame_count is not None:
            params["FrameCount"] = frame_count

        if source_type.lower() == "file":
            desc = f"Added marker '{name}' imported from file: {os.path.basename(source_file)}"
        else:
            desc = f"Added custom marker '{name}'"

        return self.record_operation("AddMarker", desc, params)

    def record_filter_markers(
        self,
        order: int,
        cutoff: float,
        sampling_rate: Optional[float] = None,
        zero_phase: bool = True,
        target: str = "All",
        markers_count: Optional[int] = None
    ) -> PipelineStep:
        """Record Butterworth low-pass filtering on markers."""
        fs = sampling_rate if sampling_rate is not None else (self.trial.point_rate if self.trial and self.trial.point_rate > 0 else 100.0)
        params = {
            "FilterType": "Butterworth Low-pass",
            "Order": order,
            "CutoffFrequency_Hz": cutoff,
            "SamplingRate_Hz": fs,
            "ZeroPhase": zero_phase,
            "Target": target,
        }
        if markers_count is not None:
            params["MarkersCount"] = markers_count

        desc = f"Filtered marker trajectories (Butterworth Order {order}, Cutoff {cutoff:.1f} Hz, Zero-phase: {zero_phase})"
        return self.record_operation("FilterMarkers", desc, params)

    def record_rename_marker(self, old_name: str, new_name: str) -> PipelineStep:
        """Record marker rename."""
        params = {
            "OldName": old_name,
            "NewName": new_name,
        }
        desc = f"Renamed marker '{old_name}' \u2192 '{new_name}'"
        return self.record_operation("RenameMarker", desc, params)

    def record_delete_markers(self, names: List[str]) -> PipelineStep:
        """Record marker deletion."""
        params = {
            "DeletedMarkers": list(names),
            "Count": len(names),
        }
        desc = f"Deleted marker(s): {', '.join(names)}"
        return self.record_operation("DeleteMarkers", desc, params)

    def record_change_marker_color(self, names: List[str], color_rgba: Optional[tuple]) -> PipelineStep:
        """Record marker custom color change or reset."""
        params = {
            "Markers": list(names),
            "ColorRGBA": ", ".join(f"{c:.3f}" for c in color_rgba) if color_rgba else "Reset to Default",
        }
        desc = f"Changed display color for {len(names)} marker(s)" if color_rgba else f"Reset color for {len(names)} marker(s)"
        return self.record_operation("ChangeMarkerColor", desc, params)

    def record_add_analog_channel(
        self,
        channel_name: Optional[str] = None,
        unit: str = "V",
        sampling_rate: Optional[float] = None,
        source_type: str = "manual",
        source_file: str = "",
        filter_details: Optional[Dict[str, Any]] = None,
        frame_count: Optional[int] = None,
        name: Optional[str] = None
    ) -> PipelineStep:
        """Record addition of a new analog channel."""
        ch_name = channel_name or name or ""
        params: Dict[str, Any] = {
            "ChannelName": ch_name,
            "Unit": unit,
            "SourceType": source_type,
        }
        if sampling_rate is not None:
            params["SamplingRate_Hz"] = sampling_rate
        if source_file:
            params["SourceFile"] = source_file
        if filter_details:
            params["Processing"] = filter_details
        if frame_count is not None:
            params["FrameCount"] = frame_count

        desc = f"Added analog channel '{ch_name}' ({unit})"
        return self.record_operation("AddAnalogChannel", desc, params)

    def record_filter_analog_channel(
        self,
        channel_name: str,
        method: Optional[str] = None,
        order: Optional[int] = None,
        cutoff: Optional[Any] = None,
        sampling_rate: Optional[float] = None,
        extra_params: Optional[Dict[str, Any]] = None,
        filter_method: Optional[str] = None
    ) -> PipelineStep:
        """Record filtering applied to an existing analog channel."""
        meth = method or filter_method or "Filtered"
        params: Dict[str, Any] = {
            "ChannelName": channel_name,
            "Method": meth,
        }
        if order is not None:
            params["Order"] = order
        if cutoff is not None:
            params["Cutoff"] = cutoff
        if sampling_rate is not None:
            params["SamplingRate_Hz"] = sampling_rate
        if extra_params:
            params.update(extra_params)

        desc = f"Applied filter '{method}' to analog channel '{channel_name}'"
        return self.record_operation("FilterAnalogChannel", desc, params)

    def record_emg_custom_filter(
        self,
        channels: List[str],
        bp_low: float = 20.0,
        bp_high: float = 400.0,
        lp_cutoff: float = 20.0,
        order: int = 4,
        overwrite: bool = True
    ) -> PipelineStep:
        """Record 2-step EMG custom signal processing (Bandpass + Rectification + Lowpass)."""
        params = {
            "Channels": list(channels),
            "BandpassLow_Hz": float(bp_low),
            "BandpassHigh_Hz": float(bp_high),
            "LowpassCutoff_Hz": float(lp_cutoff),
            "Order": int(order),
            "Overwrite": bool(overwrite),
        }
        desc = f"Applied EMG Custom Filter ({len(channels)} channels, BP: {bp_low:.0f}–{bp_high:.0f} Hz, Rectified, LP: {lp_cutoff:.0f} Hz)"
        return self.record_operation("EMGCustomFilter", desc, params)

    def record_rename_analog_channel(self, old_name: str, new_name: str) -> PipelineStep:
        """Record analog channel rename."""
        params = {
            "OldName": old_name,
            "NewName": new_name,
        }
        desc = f"Renamed analog channel '{old_name}' \u2192 '{new_name}'"
        return self.record_operation("RenameAnalogChannel", desc, params)

    def record_delete_analog_channels(self, names: List[str]) -> PipelineStep:
        """Record analog channel deletion."""
        params = {
            "DeletedChannels": list(names),
            "Count": len(names),
        }
        desc = f"Deleted analog channel(s): {', '.join(names)}"
        return self.record_operation("DeleteAnalogChannels", desc, params)

    def record_add_event(self, event: C3DEvent) -> PipelineStep:
        """Record event addition."""
        params = {
            "Name": event.name,
            "Context": event.context,
            "Frame": event.frame,
            "Time_s": round(event.time, 4),
            "Subject": event.subject,
            "Description": event.description,
            "EventID": event.event_id,
            "Color": event.icon_color,
        }
        desc = f"Added event '{event.display_name}' at frame {event.frame} ({event.time:.3f}s)"
        return self.record_operation("AddEvent", desc, params)

    def record_delete_events(self, events: List[C3DEvent]) -> PipelineStep:
        """Record event deletion."""
        params = {
            "Events": [f"{e.display_name} (frame {e.frame})" for e in events],
            "Count": len(events),
        }
        desc = f"Deleted {len(events)} event(s)"
        return self.record_operation("DeleteEvents", desc, params)

    def record_edit_event(self, old_ev: C3DEvent, new_ev: C3DEvent) -> PipelineStep:
        """Record event modification."""
        params = {
            "Original": {
                "Name": old_ev.name, "Context": old_ev.context,
                "Frame": old_ev.frame, "Time_s": round(old_ev.time, 4)
            },
            "Updated": {
                "Name": new_ev.name, "Context": new_ev.context,
                "Frame": new_ev.frame, "Time_s": round(new_ev.time, 4),
                "Subject": new_ev.subject, "Description": new_ev.description
            }
        }
        desc = f"Edited event '{new_ev.display_name}' (frame {new_ev.frame})"
        return self.record_operation("EditEvent", desc, params)

    def record_clear_events(self, cleared_count: int) -> PipelineStep:
        """Record clearing of all events."""
        params = {"ClearedCount": cleared_count}
        desc = f"Cleared all {cleared_count} events from trial"
        return self.record_operation("ClearEvents", desc, params)

    def record_trim_range(self, start_frame: int, end_frame: int, point_rate: float) -> PipelineStep:
        """Record region of interest / trim adjustment."""
        duration_s = (end_frame - start_frame + 1) / point_rate if point_rate > 0 else 0.0
        params = {
            "StartFrame": start_frame,
            "EndFrame": end_frame,
            "TotalFrames": end_frame - start_frame + 1,
            "StartTime_s": round(start_frame / point_rate, 4) if point_rate > 0 else 0.0,
            "EndTime_s": round(end_frame / point_rate, 4) if point_rate > 0 else 0.0,
            "Duration_s": round(duration_s, 4),
        }
        desc = f"Configured Region of Interest (ROI): Frames {start_frame} to {end_frame} ({duration_s:.3f}s)"
        return self.record_operation("SetRegionOfInterest", desc, params)

    def record_configure_force_plate(
        self,
        description: str,
        params: Optional[Dict[str, Any]] = None
    ) -> PipelineStep:
        """Record Force Plate calculation / configuration."""
        return self.record_operation("ConfigureForcePlate", description, params or {})

    # --------------------------------------------------------------------------
    # QUndoStack Synchronization
    # --------------------------------------------------------------------------
    def sync_with_undo_stack(self, undo_stack) -> None:
        """
        Inspect the QUndoStack to extract any user commands that might have been
        pushed directly without explicit record_* calls.
        """
        if not undo_stack or not hasattr(undo_stack, 'count'):
            return

        current_idx = undo_stack.index()
        for i in range(current_idx):
            cmd = undo_stack.command(i)
            if not cmd:
                continue

            cmd_id = getattr(cmd, 'id', lambda: -1)()
            cmd_text = cmd.text()
            sig = f"{type(cmd).__name__}_{cmd_text}_{i}"
            if sig in self._logged_command_signatures:
                continue
            self._logged_command_signatures.add(sig)

            # Map command types to pipeline operations if not already captured
            cmd_cls = type(cmd).__name__
            if cmd_cls == "AddMarkerCommand":
                # Check if this marker is already logged
                name = getattr(cmd, "name", "")
                if not any(s.parameters.get("MarkerName") == name or s.parameters.get("NewMarkerName") == name for s in self.operations):
                    st = getattr(cmd, "source_type", "manual")
                    sf = getattr(cmd, "source_file", "")
                    color = getattr(cmd, "color_rgba", None)
                    p1 = getattr(cmd, "parent_marker1", None)
                    p2 = getattr(cmd, "parent_marker2", None)
                    if p1 and p2:
                        self.record_create_average_marker(name, p1, p2, color_rgba=color)
                    else:
                        self.record_add_marker(name, source_type=st, source_file=sf, color_rgba=color)

            elif cmd_cls == "FilterMarkersCommand":
                order = getattr(cmd, "order", 4)
                cutoff = getattr(cmd, "cutoff", 6.0)
                fs = getattr(cmd, "fs", getattr(self.trial, "point_rate", 100.0) if self.trial else 100.0)
                if not any(s.action in ("FilterMarkers", "FilterMarker") and s.parameters.get("CutoffFrequency_Hz") == cutoff for s in self.operations):
                    self.record_filter_markers(order, cutoff, fs)

            elif cmd_cls == "RenameMarkerCommand":
                old_n = getattr(cmd, "old_name", "")
                new_n = getattr(cmd, "new_name", "")
                if old_n and new_n and not any(s.parameters.get("OldName") == old_n for s in self.operations):
                    self.record_rename_marker(old_n, new_n)

            elif cmd_cls in ("DeleteMarkerCommand", "DeleteMarkersCommand"):
                names = getattr(cmd, "marker_names", [getattr(cmd, "name", "")])
                names = [n for n in names if n]
                if names:
                    self.record_delete_markers(names)

            elif cmd_cls == "ChangeMarkerColorCommand":
                names = getattr(cmd, "marker_names", [])
                rgba = getattr(cmd, "new_rgba", None)
                if names:
                    self.record_change_marker_color(names, rgba)

            elif cmd_cls == "AddAnalogChannelCommand":
                ch_name = getattr(cmd, "channel_name", "")
                unit = getattr(cmd, "unit", "V")
                rate = getattr(self.trial, "analog_rate", 1000.0) if self.trial else 1000.0
                st = getattr(cmd, "source_type", "manual")
                sf = getattr(cmd, "source_file", "")
                if ch_name and not any(s.parameters.get("ChannelName") == ch_name for s in self.operations):
                    self.record_add_analog_channel(ch_name, unit, rate, source_type=st, source_file=sf)

            elif cmd_cls == "FilterAnalogChannelCommand":
                ch_name = getattr(cmd, "channel_name", "")
                method = getattr(cmd, "filter_method", "Butterworth")
                if ch_name:
                    self.record_filter_analog_channel(ch_name, method)

            elif cmd_cls == "FilterMultipleAnalogChannelsCommand":
                chs = getattr(cmd, "channels", [])
                det = getattr(cmd, "details", {})
                if det.get("Action") == "EMGCustomFilter" or getattr(cmd, "method", "") == "EMG custom":
                    bp_low = det.get("BandpassLow_Hz", 20.0)
                    bp_high = det.get("BandpassHigh_Hz", 400.0)
                    lp_cut = det.get("LowpassCutoff_Hz", 20.0)
                    ordr = det.get("Order", 4)
                    overwrite = det.get("Overwrite", True)
                    if not any(s.action == "EMGCustomFilter" and s.parameters.get("Channels") == chs for s in self.operations):
                        self.record_emg_custom_filter(chs, bp_low, bp_high, lp_cut, ordr, overwrite)
                else:
                    for ch in chs:
                        if not any(s.action == "FilterAnalogChannel" and s.parameters.get("ChannelName") == ch for s in self.operations):
                            self.record_filter_analog_channel(
                                channel_name=ch,
                                filter_method=getattr(cmd, "method", "Butterworth"),
                                order=det.get("Order", 4),
                                cutoff=det.get("Cutoff", 20.0),
                                sampling_rate=det.get("SamplingRate_Hz", 1000.0)
                            )

            elif cmd_cls == "AddMultipleAnalogChannelsCommand":
                for ch in getattr(cmd, "channels", []):
                    if not any(s.action == "AddAnalogChannel" and s.parameters.get("ChannelName") == ch for s in self.operations):
                        unit = getattr(cmd, "unit_dict", {}).get(ch, "V")
                        rate = getattr(self.trial, "analog_rate", 1000.0) if self.trial else 1000.0
                        self.record_add_analog_channel(ch, unit, rate, source_type="filtered")

            elif cmd_cls == "RenameAnalogChannelCommand":
                old_n = getattr(cmd, "old_name", "")
                new_n = getattr(cmd, "new_name", "")
                if old_n and new_n:
                    self.record_rename_analog_channel(old_n, new_n)

            elif cmd_cls == "DeleteAnalogChannelsCommand":
                names = getattr(cmd, "channel_names", [])
                if names:
                    self.record_delete_analog_channels(names)

            elif cmd_cls == "AddEventCommand":
                ev = getattr(cmd, "event", None)
                if ev and isinstance(ev, C3DEvent):
                    if not any(s.action == "AddEvent" and s.parameters.get("Name") == ev.name and s.parameters.get("Frame") == ev.frame for s in self.operations):
                        self.record_add_event(ev)

            elif cmd_cls in ("DeleteEventCommand", "DeleteEventsCommand"):
                evs = getattr(cmd, "events", [getattr(cmd, "event", None)])
                evs = [e for e in evs if e is not None]
                if evs:
                    self.record_delete_events(evs)

            elif cmd_cls == "EditEventCommand":
                old_ev = getattr(cmd, "old_event", None)
                new_ev = getattr(cmd, "new_event", None)
                if old_ev and new_ev:
                    self.record_edit_event(old_ev, new_ev)

            elif cmd_cls == "ClearEventsCommand":
                saved = getattr(cmd, "saved_events", [])
                self.record_clear_events(len(saved))

            elif cmd_cls == "EventsBatchCommand":
                old_evs = getattr(cmd, "old_events", [])
                new_evs = getattr(cmd, "new_events", [])
                params = {
                    "OldEventsCount": len(old_evs),
                    "NewEventsCount": len(new_evs),
                    "Events": [f"{e.display_name} (frame {e.frame})" for e in new_evs]
                }
                desc = f"Batch updated events (count: {len(new_evs)})"
                self.record_operation("BatchModifyEvents", desc, params)

            elif cmd_cls == "ConfigureForcePlateCommand":
                desc = getattr(cmd, "description", "Configure Force Plate")
                params = getattr(cmd, "pipeline_params", {})
                self.record_configure_force_plate(desc, params)

    # --------------------------------------------------------------------------
    # XML Generation
    # --------------------------------------------------------------------------
    def generate_xml_element(
        self,
        trial: Optional[C3DTrial] = None,
        settings: Optional[Dict[str, Any]] = None,
        trim_info: Optional[Dict[str, Any]] = None
    ) -> ET.Element:
        """
        Build the complete XML element tree representing the trial, settings,
        pipeline operations history, and current data inventory.
        """
        tr = trial or self.trial
        source_f = self.source_path or (tr.file_path if tr else "")
        now_str = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        root = ET.Element("C3DExplorerPipeline", {
            "version": "1.0",
            "software": "C3D Explorer",
            "created": now_str,
        })

        # ----------------------------------------------------------------------
        # 1. Trial Metadata
        # ----------------------------------------------------------------------
        trial_elem = ET.SubElement(root, "TrialInformation")
        if tr:
            ET.SubElement(trial_elem, "FilePath").text = source_f
            ET.SubElement(trial_elem, "FileName").text = os.path.basename(source_f) if source_f else ""
            ET.SubElement(trial_elem, "FirstFrame").text = str(tr.first_frame)
            ET.SubElement(trial_elem, "LastFrame").text = str(tr.last_frame)
            ET.SubElement(trial_elem, "PointFrameCount").text = str(tr.point_frame_count)
            ET.SubElement(trial_elem, "PointRate", {"unit": "Hz"}).text = f"{tr.point_rate:.2f}"
            ET.SubElement(trial_elem, "Duration", {"unit": "seconds"}).text = f"{tr.duration_seconds:.3f}"
            ET.SubElement(trial_elem, "MarkerUnits").text = str(tr.marker_units or "mm")
            ET.SubElement(trial_elem, "AnalogRate", {"unit": "Hz"}).text = f"{tr.analog_rate:.2f}"
            ET.SubElement(trial_elem, "AnalogFrameCount").text = str(tr.analog_frame_count)
            ET.SubElement(trial_elem, "AnalogSubsamples").text = str(tr.analog_subsamples)
            ET.SubElement(trial_elem, "MarkersCount").text = str(len(tr.markers))
            ET.SubElement(trial_elem, "AnalogChannelsCount").text = str(len(tr.analogs))
            ET.SubElement(trial_elem, "ForcePlatformsCount").text = str(len(tr.force_platforms))
            ET.SubElement(trial_elem, "EventsCount").text = str(len(tr.events))
        else:
            ET.SubElement(trial_elem, "Status").text = "No trial loaded"

        # ----------------------------------------------------------------------
        # 2. Workstation Settings
        # ----------------------------------------------------------------------
        cfg = settings or {}
        settings_elem = ET.SubElement(root, "WorkstationSettings")

        # Display settings
        disp_elem = ET.SubElement(settings_elem, "Display")
        ET.SubElement(disp_elem, "Theme").text = str(cfg.get("theme", "Biomech Dark"))
        bg_val = cfg.get("viewport_bg")
        ET.SubElement(disp_elem, "ViewportBackground", {
            "choice": str(cfg.get("viewport_bg_choice", "Theme Default"))
        }).text = str(bg_val) if bg_val else "Theme Default"
        ET.SubElement(disp_elem, "PlotAntialiasing", {
            "enabled": str(bool(cfg.get("plot_antialias", False))).lower()
        })
        ET.SubElement(disp_elem, "TimelineDisplayMode").text = str(cfg.get("timeline_display_mode", "frame"))

        # Coordinate System settings
        cs_elem = ET.SubElement(settings_elem, "CoordinateSystem")
        is_z_up = bool(cfg.get("z_up", True))
        ET.SubElement(cs_elem, "UpAxis").text = "Z" if is_z_up else "Y"
        ET.SubElement(cs_elem, "GroundPlane").text = "XY" if is_z_up else "XZ"
        ET.SubElement(cs_elem, "GlobalAxesVisible").text = str(bool(cfg.get("show_global_axes", True))).lower()
        ET.SubElement(cs_elem, "AxisLength", {"unit": "mm"}).text = str(cfg.get("axis_length", 320.0))
        ET.SubElement(cs_elem, "AxisThickness", {"unit": "px"}).text = str(cfg.get("axis_line_width", 2.0))
        ET.SubElement(cs_elem, "ForcePlateLocalAxesVisible").text = str(bool(cfg.get("show_plate_axes", True))).lower()
        ET.SubElement(cs_elem, "GroundRotation", {"unit": "deg"}).text = str(cfg.get("ground_rotation", 0.0))

        # Ground Grid
        grid_elem = ET.SubElement(settings_elem, "GroundGrid")
        ET.SubElement(grid_elem, "Visible").text = str(bool(cfg.get("show_grid", True))).lower()
        ET.SubElement(grid_elem, "Spacing", {"unit": "mm"}).text = str(cfg.get("grid_spacing", 500.0))

        # Visual Elements (Markers, Force Plates, GRF)
        vis_elem = ET.SubElement(settings_elem, "VisualElements")
        ET.SubElement(vis_elem, "MarkersVisible").text = str(bool(cfg.get("show_markers", True))).lower()
        ET.SubElement(vis_elem, "MarkerRadius", {"unit": "mm"}).text = str(cfg.get("marker_size", 8.0))
        m_col = cfg.get("marker_color", [1.0, 1.0, 1.0, 1.0])
        ET.SubElement(vis_elem, "DefaultMarkerColor", {
            "name": str(cfg.get("marker_color_name") or "White")
        }).text = ", ".join(f"{c:.2f}" for c in m_col) if isinstance(m_col, (list, tuple)) else str(m_col)

        ET.SubElement(vis_elem, "ForcePlatesVisible").text = str(bool(cfg.get("show_force_plates", True))).lower()
        ET.SubElement(vis_elem, "GRFVectorsVisible").text = str(bool(cfg.get("show_grf_vectors", True))).lower()
        ET.SubElement(vis_elem, "GRFVectorScale").text = str(cfg.get("grf_vector_scale", 1.0))
        ET.SubElement(vis_elem, "GRFThreshold", {"unit": "N"}).text = str(cfg.get("grf_threshold_n", 10.0))
        grf_col = cfg.get("grf_color", [1.0, 0.35, 0.08, 1.0])
        ET.SubElement(vis_elem, "GRFColor", {
            "name": str(cfg.get("grf_color_name") or "Orange")
        }).text = ", ".join(f"{c:.2f}" for c in grf_col) if isinstance(grf_col, (list, tuple)) else str(grf_col)

        # Playback settings
        pb_elem = ET.SubElement(settings_elem, "Playback")
        ET.SubElement(pb_elem, "DefaultSpeed").text = str(cfg.get("default_speed", "1.0x (Real-time)"))
        ET.SubElement(pb_elem, "LoopMode").text = str(bool(cfg.get("loop", True))).lower()

        # Region of Interest (Trim)
        t_info = trim_info or {}
        is_trimmed = bool(t_info.get("is_trimmed", False))
        roi_elem = ET.SubElement(settings_elem, "RegionOfInterest", {"active": str(is_trimmed).lower()})
        start_f = int(t_info.get("trim_start_frame", 0))
        end_f = int(t_info.get("trim_end_frame", tr.point_frame_count - 1 if tr else 0))
        prate = float(tr.point_rate) if tr and tr.point_rate > 0 else 100.0
        ET.SubElement(roi_elem, "TrimStartFrame").text = str(start_f)
        ET.SubElement(roi_elem, "TrimEndFrame").text = str(end_f)
        ET.SubElement(roi_elem, "TrimStartTime", {"unit": "seconds"}).text = f"{start_f / prate:.3f}"
        ET.SubElement(roi_elem, "TrimEndTime", {"unit": "seconds"}).text = f"{end_f / prate:.3f}"
        ET.SubElement(roi_elem, "TrimDuration", {"unit": "seconds"}).text = f"{(end_f - start_f + 1) / prate:.3f}"

        # ----------------------------------------------------------------------
        # 3. Pipeline Operations (History / Audit Trail)
        # ----------------------------------------------------------------------
        ops_elem = ET.SubElement(root, "PipelineOperations", {
            "count": str(len(self.operations))
        })

        for idx, step in enumerate(self.operations, start=1):
            step_elem = ET.SubElement(ops_elem, "Operation", {
                "id": str(idx),
                "action": step.action,
                "timestamp": step.timestamp
            })
            ET.SubElement(step_elem, "Description").text = step.description

            params_elem = ET.SubElement(step_elem, "Parameters")
            self._dict_to_xml(step.parameters, params_elem)

        # ----------------------------------------------------------------------
        # 4. Current Trial Inventory
        # ----------------------------------------------------------------------
        if tr:
            inv_elem = ET.SubElement(root, "TrialInventory")

            # Markers Inventory
            markers_elem = ET.SubElement(inv_elem, "Markers", {
                "count": str(len(tr.markers)),
                "unit": str(tr.marker_units or "mm")
            })
            for m_name, arr in tr.markers.items():
                m_sub = ET.SubElement(markers_elem, "Marker", {"name": m_name})
                ET.SubElement(m_sub, "FrameCount").text = str(len(arr))
                # Count valid vs missing (0,0,0 or NaN)
                if arr is not None and len(arr) > 0:
                    missing = np.all(arr == 0, axis=1) | np.isnan(arr).any(axis=1)
                    valid_cnt = int(np.sum(~missing))
                    missing_cnt = int(np.sum(missing))
                    ET.SubElement(m_sub, "ValidFrames").text = str(valid_cnt)
                    ET.SubElement(m_sub, "MissingFrames").text = str(missing_cnt)

            # Analog Channels Inventory
            analogs_elem = ET.SubElement(inv_elem, "AnalogChannels", {
                "count": str(len(tr.analogs)),
                "sample_rate_hz": f"{tr.analog_rate:.2f}"
            })
            for ch_name, arr in tr.analogs.items():
                unit = tr.analog_units.get(ch_name, "V")
                ch_sub = ET.SubElement(analogs_elem, "Channel", {
                    "name": ch_name,
                    "unit": unit
                })
                ET.SubElement(ch_sub, "SampleCount").text = str(len(arr))
                if arr is not None and len(arr) > 0:
                    try:
                        valid_data = arr[~np.isnan(arr)]
                        if len(valid_data) > 0:
                            ET.SubElement(ch_sub, "Min").text = f"{float(np.min(valid_data)):.4f}"
                            ET.SubElement(ch_sub, "Max").text = f"{float(np.max(valid_data)):.4f}"
                            ET.SubElement(ch_sub, "Mean").text = f"{float(np.mean(valid_data)):.4f}"
                            ET.SubElement(ch_sub, "RMS").text = f"{float(np.sqrt(np.mean(valid_data ** 2))):.4f}"
                    except Exception:
                        pass

            # Force Platforms Inventory
            if tr.force_platforms:
                fp_elem = ET.SubElement(inv_elem, "ForcePlatforms", {
                    "count": str(len(tr.force_platforms))
                })
                for fp in tr.force_platforms:
                    p_sub = ET.SubElement(fp_elem, "Platform", {
                        "id": str(fp.id),
                        "type": str(fp.type)
                    })
                    ET.SubElement(p_sub, "Width", {"unit": "mm"}).text = f"{fp.width:.2f}"
                    ET.SubElement(p_sub, "Length", {"unit": "mm"}).text = f"{fp.length:.2f}"
                    if fp.origin is not None and len(fp.origin) == 3:
                        ET.SubElement(p_sub, "Origin").text = (
                            f"{fp.origin[0]:.2f}, {fp.origin[1]:.2f}, {fp.origin[2]:.2f}"
                        )
                    if fp.corners is not None and fp.corners.shape == (3, 4):
                        corners_elem = ET.SubElement(p_sub, "Corners")
                        for ci in range(4):
                            ET.SubElement(corners_elem, "Corner", {"index": str(ci + 1)}).text = (
                                f"{fp.corners[0, ci]:.2f}, {fp.corners[1, ci]:.2f}, {fp.corners[2, ci]:.2f}"
                            )

            # Events Inventory
            if tr.events:
                evs_elem = ET.SubElement(inv_elem, "Events", {
                    "count": str(len(tr.events))
                })
                for ev in tr.events:
                    ev_sub = ET.SubElement(evs_elem, "Event", {
                        "name": ev.name,
                        "context": ev.context or "General"
                    })
                    ET.SubElement(ev_sub, "Frame").text = str(ev.frame)
                    ET.SubElement(ev_sub, "Time", {"unit": "seconds"}).text = f"{ev.time:.4f}"
                    if ev.subject:
                        ET.SubElement(ev_sub, "Subject").text = ev.subject
                    if ev.description:
                        ET.SubElement(ev_sub, "Description").text = ev.description
                    if ev.icon_color:
                        ET.SubElement(ev_sub, "Color").text = ev.icon_color

        return root

    def export_xml(
        self,
        filepath: str,
        trial: Optional[C3DTrial] = None,
        settings: Optional[Dict[str, Any]] = None,
        trim_info: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Build and write the formatted XML document to the given filepath.
        Returns True on success, raises exception on error.
        """
        root = self.generate_xml_element(trial=trial, settings=settings, trim_info=trim_info)

        # Indent using standard ElementTree.indent (Python 3.9+)
        try:
            ET.indent(root, space="  ", level=0)
            raw_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        except Exception:
            # Fallback to minidom pretty-printing
            rough_string = ET.tostring(root, "utf-8")
            reparsed = minidom.parseString(rough_string)
            raw_xml = reparsed.toprettyxml(indent="  ", encoding="utf-8")

        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "wb") as f:
            f.write(raw_xml)

        return True

    def to_xml_string(
        self,
        trial: Optional[C3DTrial] = None,
        settings: Optional[Dict[str, Any]] = None,
        trim_info: Optional[Dict[str, Any]] = None
    ) -> str:
        """Serialize current pipeline to formatted XML string."""
        root = self.generate_xml_element(trial=trial, settings=settings, trim_info=trim_info)
        try:
            ET.indent(root, space="  ", level=0)
            return ET.tostring(root, encoding="utf-8").decode("utf-8")
        except Exception:
            rough_string = ET.tostring(root, "utf-8")
            reparsed = minidom.parseString(rough_string)
            return reparsed.toprettyxml(indent="  ")

    def _dict_to_xml(self, d: Dict[str, Any], parent: ET.Element):
        """Recursively serialize dictionary entries to clean XML child elements."""
        for k, v in d.items():
            tag = str(k).replace(" ", "_")
            if isinstance(v, dict):
                sub = ET.SubElement(parent, tag)
                self._dict_to_xml(v, sub)
            elif isinstance(v, (list, tuple)):
                sub = ET.SubElement(parent, tag)
                if all(isinstance(item, (int, float, str)) for item in v):
                    sub.text = ", ".join(str(item) for item in v)
                else:
                    for item in v:
                        item_elem = ET.SubElement(sub, "Item")
                        if isinstance(item, dict):
                            self._dict_to_xml(item, item_elem)
                        else:
                            item_elem.text = str(item)
            elif isinstance(v, (bool, np.bool_)):
                ET.SubElement(parent, tag).text = str(v).lower()
            elif isinstance(v, float):
                ET.SubElement(parent, tag).text = f"{v:.4f}" if abs(v) < 100000 else f"{v}"
            else:
                ET.SubElement(parent, tag).text = str(v)
