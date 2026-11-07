import sys
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
import numpy as np
from PySide6.QtWidgets import QApplication

from core.data_models import C3DTrial
from core.pipeline_executor import compute_harrington_hjc, PipelineExecutor
from core.pipeline_manager import PipelineManager
from gui.marker_tools_dialog import HipJointCenterDialog
from gui.main_window import MainWindow

app = QApplication.instance() or QApplication(sys.argv)

class TestHipJointCenter(unittest.TestCase):
    def setUp(self):
        # Create synthetic trial with pelvis markers in a standard right-handed frame:
        # +X: Right, +Y: Anterior, +Z: Superior
        # Pelvis center OP at (0, 0, 1000)
        # LASIS at (-120, 0, 1000), RASIS at (+120, 0, 1000) -> Pelvis Width PW = 240 mm
        # LPSIS at (-80, -131.5, 1000), RPSIS at (+80, -131.5, 1000)
        # Midpoint of PSIS SACRUM = (0, -131.5, 1000)
        # Pelvis depth PD = norm(SACRUM - OP) = 131.5 mm
        n_frames = 20
        self.trial = C3DTrial(
            file_path="mock_pelvis.c3d",
            first_frame=1,
            last_frame=n_frames,
            point_rate=100.0,
            point_frame_count=n_frames,
            analog_rate=1000.0,
            analog_frame_count=n_frames * 10,
            analog_subsamples=10,
            markers={
                "LASI": np.tile(np.array([-120.0, 0.0, 1000.0]), (n_frames, 1)),
                "RASI": np.tile(np.array([120.0, 0.0, 1000.0]), (n_frames, 1)),
                "LPSI": np.tile(np.array([-80.0, -131.5, 1000.0]), (n_frames, 1)),
                "RPSI": np.tile(np.array([80.0, -131.5, 1000.0]), (n_frames, 1)),
            }
        )

    def test_harrington_math_known_values(self):
        """Test compute_harrington_hjc against theoretical values from Harrington et al. (2006)."""
        lasi = self.trial.markers["LASI"]
        rasi = self.trial.markers["RASI"]
        lpsi = self.trial.markers["LPSI"]
        rpsi = self.trial.markers["RPSI"]

        rhjc, lhjc = compute_harrington_hjc(lasi, rasi, lpsi, rpsi)

        self.assertEqual(rhjc.shape, (20, 3))
        self.assertEqual(lhjc.shape, (20, 3))

        # Expected parameters:
        # PW = 240.0 mm
        # PD = 131.5 mm
        # diff_ml = 0.33 * 240.0 + 7.3 = 86.5 mm
        # diff_ap = -0.24 * 131.5 - 9.9 = -41.46 mm
        # diff_v  = -0.30 * 240.0 - 10.9 = -82.9 mm
        #
        # In this synthetic setup:
        # OP = (0, 0, 1000)
        # SACRUM = (0, -131.5, 1000)
        # IB = (RASIS - LASIS)/norm = (+1, 0, 0)
        # PROVV = (RASIS - SACRUM)/norm = (+120, +131.5, 0)/norm
        # KB = cross(IB, PROVV) / norm = (0, 0, 1) [Superior]
        # JB = cross(KB, IB) / norm = cross((0,0,1), (1,0,0)) = (0, 1, 0) [Anterior]
        #
        # Global RHJC = OP + diff_ml * IB + diff_ap * JB + diff_v * KB
        #             = (0, 0, 1000) + 86.5 * (1, 0, 0) + (-41.46) * (0, 1, 0) + (-82.9) * (0, 0, 1)
        #             = (+86.5, -41.46, 917.1)
        # Global LHJC = OP - diff_ml * IB + diff_ap * JB + diff_v * KB
        #             = (0, 0, 1000) - 86.5 * (1, 0, 0) + (-41.46) * (0, 1, 0) + (-82.9) * (0, 0, 1)
        #             = (-86.5, -41.46, 917.1)

        np.testing.assert_allclose(rhjc[0], [86.5, -41.46, 917.1], atol=1e-3)
        np.testing.assert_allclose(lhjc[0], [-86.5, -41.46, 917.1], atol=1e-3)

    def test_harrington_missing_frames(self):
        """Test compute_harrington_hjc handles zero or NaN frames safely."""
        lasi = self.trial.markers["LASI"].copy()
        rasi = self.trial.markers["RASI"].copy()
        lpsi = self.trial.markers["LPSI"].copy()
        rpsi = self.trial.markers["RPSI"].copy()

        # Mark frame 5 as untracked / zero
        lasi[5] = [0.0, 0.0, 0.0]
        # Mark frame 10 as NaN
        rasi[10] = [np.nan, np.nan, np.nan]

        rhjc, lhjc = compute_harrington_hjc(lasi, rasi, lpsi, rpsi)
        np.testing.assert_allclose(rhjc[5], [0.0, 0.0, 0.0])
        np.testing.assert_allclose(lhjc[5], [0.0, 0.0, 0.0])
        np.testing.assert_allclose(rhjc[10], [0.0, 0.0, 0.0])
        np.testing.assert_allclose(lhjc[10], [0.0, 0.0, 0.0])

    def test_dialog_landmark_autodetection(self):
        """Test HipJointCenterDialog automatically identifies pelvic landmarks."""
        dlg = HipJointCenterDialog(self.trial)
        self.assertEqual(dlg.combo_lasi.currentText(), "LASI")
        self.assertEqual(dlg.combo_rasi.currentText(), "RASI")
        self.assertEqual(dlg.combo_lpsi.currentText(), "LPSI")
        self.assertEqual(dlg.combo_rpsi.currentText(), "RPSI")
        self.assertEqual(dlg.txt_rhjc.text(), "RHJC")
        self.assertEqual(dlg.txt_lhjc.text(), "LHJC")

    def test_dialog_validation_and_creation(self):
        """Test HipJointCenterDialog emits markersCreated with valid trajectories."""
        dlg = HipJointCenterDialog(self.trial)
        dlg.txt_rhjc.setText("Right_HJC")
        dlg.txt_lhjc.setText("Left_HJC")

        results = []
        dlg.markersCreated.connect(lambda *args: results.append(args))
        dlg._calculate_and_create()

        self.assertEqual(len(results), 1)
        rhjc_name, rhjc_data, lhjc_name, lhjc_data, lasi_m, rasi_m, lpsi_m, rpsi_m = results[0]
        self.assertEqual(rhjc_name, "Right_HJC")
        self.assertEqual(lhjc_name, "Left_HJC")
        self.assertEqual(lasi_m, "LASI")
        self.assertEqual(rasi_m, "RASI")
        self.assertEqual(lpsi_m, "LPSI")
        self.assertEqual(rpsi_m, "RPSI")
        self.assertEqual(rhjc_data.shape, (20, 3))
        self.assertEqual(lhjc_data.shape, (20, 3))

    def test_main_window_integration_and_undo_redo(self):
        """Test MainWindow adds both HJC markers, supports single undo/redo macro, and records pipeline."""
        win = MainWindow()
        win.trial = self.trial
        win.pipeline_manager = PipelineManager()
        win.side_panel.load_trial(self.trial)

        rhjc_data, lhjc_data = compute_harrington_hjc(
            self.trial.markers["LASI"],
            self.trial.markers["RASI"],
            self.trial.markers["LPSI"],
            self.trial.markers["RPSI"]
        )

        win._on_hjc_markers_created(
            "RHJC", rhjc_data, "LHJC", lhjc_data,
            "LASI", "RASI", "LPSI", "RPSI"
        )

        # Both markers should be in trial
        self.assertIn("RHJC", win.trial.markers)
        self.assertIn("LHJC", win.trial.markers)

        # Pipeline should have recorded operation
        ops = win.pipeline_manager.operations
        self.assertTrue(any(op.action in ("CalculateHipJointCenter", "CalculateHJC") for op in ops))

        # Test single undo macro removes both markers together
        win.undo_stack.undo()
        self.assertNotIn("RHJC", win.trial.markers)
        self.assertNotIn("LHJC", win.trial.markers)

        # Test single redo macro restores both markers together
        win.undo_stack.redo()
        self.assertIn("RHJC", win.trial.markers)
        self.assertIn("LHJC", win.trial.markers)

    def test_pipeline_executor_headless_hjc(self):
        """Test headless pipeline execution of CalculateHipJointCenter."""
        pm = PipelineManager()
        pm.record_calculate_hjc(
            rhjc_name="RHJC_AUTO",
            lhjc_name="LHJC_AUTO",
            lasi_marker="LASI",
            rasi_marker="RASI",
            lpsi_marker="LPSI",
            rpsi_marker="RPSI"
        )
        xml_str = pm.to_xml_string()

        executor = PipelineExecutor(xml_str)
        self.assertEqual(len(executor.operations), 1)
        self.assertEqual(executor.operations[0].action, "CalculateHipJointCenter")

        fresh_trial = C3DTrial(
            file_path="mock_pelvis2.c3d",
            first_frame=1,
            last_frame=20,
            point_rate=100.0,
            point_frame_count=20,
            analog_rate=1000.0,
            analog_frame_count=200,
            analog_subsamples=10,
            markers={
                "LASI": self.trial.markers["LASI"].copy(),
                "RASI": self.trial.markers["RASI"].copy(),
                "LPSI": self.trial.markers["LPSI"].copy(),
                "RPSI": self.trial.markers["RPSI"].copy(),
            }
        )
        res = executor.execute_on_trial(fresh_trial)
        self.assertTrue(res.success)
        self.assertIn("RHJC_AUTO", fresh_trial.markers)
        self.assertIn("LHJC_AUTO", fresh_trial.markers)
        np.testing.assert_allclose(fresh_trial.markers["RHJC_AUTO"][0], [86.5, -41.46, 917.1], atol=1e-3)
        np.testing.assert_allclose(fresh_trial.markers["LHJC_AUTO"][0], [-86.5, -41.46, 917.1], atol=1e-3)

if __name__ == "__main__":
    unittest.main()
