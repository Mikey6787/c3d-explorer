"""Unit tests for Pipeline XML export and PipelineManager."""

import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import numpy as np

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QUndoStack, QColor

from core.data_models import C3DTrial, C3DEvent, ForcePlatformData
from core.pipeline_manager import PipelineManager, PipelineStep
from gui.undo_commands import (
    AddMarkerCommand, FilterMarkersCommand, RenameMarkerCommand,
    DeleteMarkerCommand, AddAnalogChannelCommand, FilterAnalogChannelCommand
)
from gui.main_window import MainWindow

# Prevent blocking popups in tests
QMessageBox.information = lambda *args, **kwargs: QMessageBox.Ok
QMessageBox.critical = lambda *args, **kwargs: QMessageBox.Ok
QMessageBox.question = lambda *args, **kwargs: QMessageBox.Yes
QMessageBox.warning = lambda *args, **kwargs: QMessageBox.Ok

app = QApplication.instance() or QApplication(sys.argv)


class TestPipelineExport(unittest.TestCase):
    def setUp(self):
        self.trial = C3DTrial(
            file_path="/mock/path/test_gait.c3d",
            first_frame=1,
            last_frame=100,
            point_rate=120.0,
            point_frame_count=100,
            analog_rate=1200.0,
            analog_frame_count=1000,
            analog_subsamples=10,
            markers={
                "LASI": np.ones((100, 3)),
                "RASI": np.ones((100, 3)) * 2,
                "SACR": np.ones((100, 3)) * 3,
            },
            analogs={
                "EMG_TA": np.sin(np.linspace(0, 10, 1000)),
                "FP1_Fz": np.full(1000, -750.0),
            },
            analog_units={
                "EMG_TA": "mV",
                "FP1_Fz": "N",
            },
            events=[
                C3DEvent(name="Foot Strike", time=0.25, frame=30, context="Left", subject="Subject01", description="Heel contact"),
                C3DEvent(name="Toe Off", time=0.65, frame=78, context="Left", subject="Subject01", description="Toe off"),
            ],
            force_platforms=[
                ForcePlatformData(id=1, type=2, corners=np.zeros((3, 4)), origin=np.zeros(3))
            ]
        )

    def test_pipeline_manager_operations_and_xml_export(self):
        pm = PipelineManager()
        pm.set_trial(self.trial, self.trial.file_path)

        # 1. Record various operations
        pm.record_create_average_marker(
            new_name="PELVIS_MID",
            parent1="LASI",
            parent2="RASI",
            weights=(0.5, 0.5),
            color_rgba=(0.2, 0.8, 0.2, 1.0)
        )

        pm.record_add_marker(
            name="VIRTUAL_KNEE",
            source_type="file",
            source_file="/path/to/imported_knee.csv",
            color_rgba=(1.0, 0.5, 0.0, 1.0),
            frame_count=100
        )
        pm.record_create_centroid_marker("Pelvis_Centroid", ["LASI", "RASI", "SACR"])

        pm.record_filter_markers(
            order=4,
            cutoff=6.0,
            sampling_rate=120.0,
            zero_phase=True,
            markers_count=3
        )

        pm.record_rename_marker("SACR", "L_SACR")

        pm.record_add_analog_channel(
            name="EMG_SOL",
            unit="mV",
            sampling_rate=1200.0,
            source_type="file",
            source_file="/path/to/emg_soleus.csv",
            frame_count=1000
        )

        pm.record_filter_analog_channel(
            channel_name="EMG_TA",
            filter_method="Butterworth Low-pass",
            order=4,
            cutoff=20.0,
            sampling_rate=1200.0
        )

        pm.record_trim_range(start_frame=10, end_frame=90, point_rate=120.0)

        # 2. Export XML to temp file
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            settings = {
                "theme": "Biomech Slate",
                "show_grid": True,
                "marker_size": 14.0,
                "show_force_plates": True,
                "z_up": True
            }
            trim_info = {
                "StartFrame": 10,
                "EndFrame": 90,
                "PointRate": 120.0,
                "IsTrimmed": True
            }

            success = pm.export_xml(tmp_path, trial=self.trial, settings=settings, trim_info=trim_info)
            self.assertTrue(success)
            self.assertTrue(os.path.exists(tmp_path))

            # 3. Parse and validate XML
            tree = ET.parse(tmp_path)
            root = tree.getroot()
            self.assertEqual(root.tag, "C3DExplorerPipeline")
            self.assertEqual(root.attrib.get("version"), "1.0")
            self.assertEqual(root.attrib.get("software"), "C3D Explorer")

            # Check sections
            trial_info = root.find("TrialInformation")
            self.assertIsNotNone(trial_info)
            self.assertEqual(trial_info.find("PointFrameCount").text, "100")
            self.assertEqual(trial_info.find("PointRate").text, "120.00")
            self.assertEqual(trial_info.find("AnalogFrameCount").text, "1000")

            workstation = root.find("WorkstationSettings")
            self.assertIsNotNone(workstation)
            self.assertEqual(workstation.find("Display/Theme").text, "Biomech Slate")
            self.assertEqual(workstation.find("GroundGrid/Visible").text, "true")

            operations = root.find("PipelineOperations")
            self.assertIsNotNone(operations)
            steps = operations.findall("Operation")
            self.assertGreaterEqual(len(steps), 7)

            actions = [s.attrib.get("action") for s in steps]
            self.assertIn("CreateAverageMarker", actions)
            self.assertIn("CreateCentroidMarker", actions)
            self.assertIn("AddMarker", actions)
            self.assertIn("FilterMarkers", actions)
            self.assertIn("RenameMarker", actions)
            self.assertIn("AddAnalogChannel", actions)
            self.assertIn("FilterAnalogChannel", actions)
            self.assertIn("SetRegionOfInterest", actions)

            # Check Trial Inventory
            inventory = root.find("TrialInventory")
            self.assertIsNotNone(inventory)
            markers_elem = inventory.find("Markers")
            self.assertIsNotNone(markers_elem)
            marker_names = [m.attrib.get("name") for m in markers_elem.findall("Marker")]
            self.assertIn("LASI", marker_names)
            self.assertIn("RASI", marker_names)

            analogs_elem = inventory.find("AnalogChannels")
            self.assertIsNotNone(analogs_elem)
            ch_names = [c.attrib.get("name") for c in analogs_elem.findall("Channel")]
            self.assertIn("EMG_TA", ch_names)
            self.assertIn("FP1_Fz", ch_names)

            events_elem = inventory.find("Events")
            self.assertIsNotNone(events_elem)
            ev_names = [e.attrib.get("name") for e in events_elem.findall("Event")]
            self.assertIn("Foot Strike", ev_names)

        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_sync_with_undo_stack(self):
        pm = PipelineManager()
        pm.set_trial(self.trial, self.trial.file_path)

        win = MainWindow()
        win.trial = self.trial
        win.side_panel.load_trial(self.trial)
        stack = win.undo_stack

        # Add Marker Command
        cmd1 = AddMarkerCommand(
            main_window=win,
            trial=self.trial,
            name="TEST_MARKER",
            data=np.zeros((100, 3)),
            source_type="file",
            source_file="/mock/file.csv"
        )
        stack.push(cmd1)

        # Filter Markers Command
        cmd2 = FilterMarkersCommand(
            main_window=win,
            trial=self.trial,
            order=4,
            cutoff=8.0,
            old_markers={},
            new_markers={},
            fs=120.0,
            zero_phase=True
        )
        stack.push(cmd2)

        # Rename Marker Command
        cmd3 = RenameMarkerCommand(
            main_window=win,
            trial=self.trial,
            old_name="LASI",
            new_name="L_ASIS"
        )
        stack.push(cmd3)

        # Sync
        pm.sync_with_undo_stack(stack)
        win.close()

        actions = [s.action for s in pm.operations]
        self.assertIn("AddMarker", actions)
        self.assertIn("FilterMarkers", actions)
        self.assertIn("RenameMarker", actions)

    def test_main_window_export_pipeline_menu_action(self):
        win = MainWindow()
        win.trial = self.trial
        win.current_file_path = self.trial.file_path

        # Find Export Pipeline action in menu
        file_menu = None
        for action in win.menuBar().actions():
            if action.menu() and "File" in action.text():
                file_menu = action.menu()
                break

        self.assertIsNotNone(file_menu, "File menu should exist")

        export_menu = None
        for action in file_menu.actions():
            if action.menu() and "Export" in action.text():
                export_menu = action.menu()
                break

        self.assertIsNotNone(export_menu, "Export submenu should exist")

        pipeline_action = None
        for action in export_menu.actions():
            if "Pipeline" in action.text():
                pipeline_action = action
                break

        self.assertIsNotNone(pipeline_action, "Export Pipeline action should exist in Export submenu")
        self.assertEqual(pipeline_action.text(), "Export Pipeline (XML)...")

        # Test direct export via pipeline_manager
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            settings = win._collect_current_app_settings()
            win.pipeline_manager.export_xml(tmp_path, trial=win.trial, settings=settings)
            self.assertTrue(os.path.exists(tmp_path))
            tree = ET.parse(tmp_path)
            root = tree.getroot()
            self.assertEqual(root.tag, "C3DExplorerPipeline")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            win.close()


if __name__ == "__main__":
    unittest.main()
