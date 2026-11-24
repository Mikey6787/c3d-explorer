"""Unit and integration tests for OpenSim Export (.trc, _grf.mot, _grf.xml)."""

import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
from PySide6.QtWidgets import QApplication

from core.data_models import C3DTrial, ForcePlatformData
from core.opensim_exporter import (
    COORDINATE_PRESETS,
    ExternalForceConfig,
    build_axis_transform_matrix,
    export_trial_to_opensim,
    parse_external_loads_xml,
)
from gui.opensim_export_dialog import BatchRule, OpenSimBatchWorker, OpenSimExportDialog
from gui.toggle_switch import ToggleSwitch


class TestOpenSimExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def _make_sample_trial(self) -> C3DTrial:
        # 5 marker frames at 100 Hz, 50 analog frames at 1000 Hz (10 subsamples)
        m1 = np.array([
            [100.0, 200.0, 1000.0],
            [110.0, 210.0, 1010.0],
            [np.nan, np.nan, np.nan],
            [130.0, 230.0, 1030.0],
            [140.0, 240.0, 1040.0],
        ], dtype=np.float32)

        forces = np.zeros((50, 3), dtype=np.float32)
        forces[:, 0] = 10.0
        forces[:, 1] = 20.0
        forces[:, 2] = 700.0

        cop = np.zeros((50, 3), dtype=np.float32)
        cop[:, 0] = 500.0  # mm -> 0.5 m
        cop[:, 1] = 250.0  # mm -> 0.25 m
        cop[:, 2] = 0.0

        moments = np.zeros((50, 3), dtype=np.float32)
        moments[:, 2] = 5000.0  # N.mm -> 5.0 N.m

        fp = ForcePlatformData(
            id=1,
            type=4,
            corners=np.zeros((3, 4), dtype=np.float32),
            origin=np.zeros(3, dtype=np.float32),
            forces=forces,
            moments=moments,
            cop=cop,
        )
        return C3DTrial(
            file_path="/tmp/jump_trial.c3d",
            first_frame=1,
            last_frame=5,
            point_rate=100.0,
            point_frame_count=5,
            analog_rate=1000.0,
            analog_frame_count=50,
            analog_subsamples=10,
            markers={"C7": m1},
            marker_units="mm",
            force_platforms=[fp],
        )

    def test_export_trc_mot_xml_z_up_to_opensim_y_up(self):
        trial = self._make_sample_trial()
        ax, ay, az = COORDINATE_PRESETS["Lab Z-Up, X-Forward (Vicon/Qualisys -> OpenSim Y-Up)"]
        R = build_axis_transform_matrix(ax, ay, az)

        ef_cfg = [
            ExternalForceConfig(
                name="ExternalForce_1",
                is_disabled=False,
                applied_to_body="calcn_l",
                force_expressed_in_body="ground",
                point_expressed_in_body="ground",
                force_identifier="ground_force_1_v",
                point_identifier="ground_force_1_p",
                torque_identifier="ground_torque_1_",
                plate_index=0,
            )
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            out = export_trial_to_opensim(
                trial=trial,
                output_dir=tmpdir,
                base_name="jump_01",
                transform_matrix=R,
                trc_units="mm",
                export_grf=True,
                external_forces=ef_cfg,
            )
            self.assertIn("trc", out)
            self.assertIn("mot", out)
            self.assertIn("xml", out)

            # Verify .trc
            with open(out["trc"], "r", encoding="utf-8") as f:
                trc_lines = f.read().splitlines()
            self.assertTrue(trc_lines[0].startswith("PathFileType\t4\t(X/Y/Z)\tjump_01.trc"))
            self.assertIn("100\t100\t5\t1\tmm\t100\t1\t5", trc_lines[2])
            # Frame 1: Lab (100, 200, 1000) -> OpenSim (100, 1000, -200)
            row0 = trc_lines[6].split("\t")
            self.assertEqual(row0[0], "1")
            self.assertAlmostEqual(float(row0[2]), 100.0, places=4)
            self.assertAlmostEqual(float(row0[3]), 1000.0, places=4)
            self.assertAlmostEqual(float(row0[4]), -200.0, places=4)
            # Frame 3 (NaN) -> blank fields
            row2 = trc_lines[8].split("\t")
            self.assertEqual(row2[2:], ["", "", ""])

            # Verify .mot
            with open(out["mot"], "r", encoding="utf-8") as f:
                mot_lines = f.read().splitlines()
            self.assertEqual(mot_lines[1], "version=1")
            self.assertEqual(mot_lines[2], "nRows=50")
            self.assertEqual(mot_lines[3], "nColumns=10")
            self.assertEqual(mot_lines[5], "endheader")
            cols = mot_lines[6].split("\t")
            self.assertEqual(
                cols,
                [
                    "time",
                    "ground_force_1_vx", "ground_force_1_vy", "ground_force_1_vz",
                    "ground_force_1_px", "ground_force_1_py", "ground_force_1_pz",
                    "ground_torque_1_x", "ground_torque_1_y", "ground_torque_1_z",
                ],
            )
            vals0 = [float(v) for v in mot_lines[7].split("\t")]
            # Force Lab (10, 20, 700) -> OpenSim (10, 700, -20)
            self.assertAlmostEqual(vals0[1], 10.0, places=4)
            self.assertAlmostEqual(vals0[2], 700.0, places=4)
            self.assertAlmostEqual(vals0[3], -20.0, places=4)
            # COP Lab (500, 250, 0) mm -> (0.5, 0.25, 0) m -> OpenSim (0.5, 0, -0.25) m
            self.assertAlmostEqual(vals0[4], 0.5, places=4)
            self.assertAlmostEqual(vals0[5], 0.0, places=4)
            self.assertAlmostEqual(vals0[6], -0.25, places=4)

            # Verify .xml
            tree = ET.parse(out["xml"])
            root = tree.getroot()
            self.assertEqual(root.findtext(".//ExternalLoads/datafile").strip(), "jump_01_grf.mot")
            self.assertEqual(root.findtext(".//ExternalForce/applied_to_body").strip(), "calcn_l")
            self.assertEqual(root.findtext(".//ExternalForce/force_identifier").strip(), "ground_force_1_v")

    def test_parse_sample_xml_if_present(self):
        sample_path = "/Users/mikey/Desktop/GRF_sample.xml"
        if os.path.exists(sample_path):
            cfgs = parse_external_loads_xml(sample_path)
            self.assertEqual(len(cfgs), 1)
            self.assertEqual(cfgs[0].applied_to_body, "calcn_l")
            self.assertEqual(cfgs[0].force_identifier, "ground_force_1_v")

    def test_dialog_ui_and_roi(self):
        trial = self._make_sample_trial()
        dlg = OpenSimExportDialog(trial=trial, trim_range=(1, 3))
        self.assertTrue(dlg.chk_export_grf.isChecked())
        self.assertTrue(dlg.chk_use_roi.isChecked())
        self.assertEqual(dlg.table_forces.rowCount(), 1)
        self.assertEqual(dlg.table_forces.columnCount(), 4)
        dis_toggle = dlg.table_forces.cellWidget(0, 3).findChild(ToggleSwitch)
        self.assertIsNotNone(dis_toggle)
        dis_toggle.setChecked(True)
        forces = dlg.get_external_forces()
        self.assertEqual(forces[0].force_identifier, "ground_force_1_v")
        self.assertTrue(forces[0].is_disabled)

        # Test conditional batch rules
        dlg._add_batch_rule("_L_", export_grf=True, forces=[
            ExternalForceConfig(name="ExternalForce_1", applied_to_body="calcn_l", plate_index=0)
        ])
        dlg._add_batch_rule("static", export_grf=False, forces=[])
        rules = dlg.get_batch_rules()
        self.assertEqual(len(rules), 2)

        worker = OpenSimBatchWorker(
            files=[], output_dir="", same_as_input=True,
            transform_matrix=dlg.get_transform_matrix(), trc_units="mm",
            export_grf=True, external_forces=forces, rules=rules
        )
        use_grf_l, ef_l, pat_l = worker._resolve_settings_for_file("P01_PRE_L_BML_01.c3d")
        self.assertTrue(use_grf_l)
        self.assertEqual(pat_l, "_L_")
        self.assertEqual(ef_l[0].applied_to_body, "calcn_l")

        use_grf_s, _ef_s, pat_s = worker._resolve_settings_for_file("P01_Static_01.c3d")
        self.assertFalse(use_grf_s)
        self.assertEqual(pat_s, "static")

        dlg.close()


if __name__ == "__main__":
    unittest.main()
