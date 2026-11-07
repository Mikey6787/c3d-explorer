"""Unit tests for PipelineExecutor and BatchProcessingDialog."""

import os
import sys
import shutil
import tempfile
import unittest
import numpy as np

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtWidgets import QApplication, QMessageBox
from core.data_models import C3DTrial, ForcePlatformData, C3DEvent
from core.c3d_writer import C3DWriter
from core.c3d_reader import C3DReader
from core.pipeline_manager import PipelineManager
from core.pipeline_executor import PipelineExecutor, TrialExecutionResult
from gui.batch_processing_dialog import BatchProcessingDialog
from gui.main_window import MainWindow

# Prevent blocking modals in tests
QMessageBox.information = lambda *args, **kwargs: QMessageBox.Ok
QMessageBox.warning = lambda *args, **kwargs: QMessageBox.Ok
QMessageBox.critical = lambda *args, **kwargs: QMessageBox.Ok
QMessageBox.question = lambda *args, **kwargs: QMessageBox.Yes

app = QApplication.instance() or QApplication(sys.argv)


class TestBatchProcessing(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

        # Create two sample C3D files
        self.trial1_path = os.path.join(self.temp_dir, "Subject01_Trial01.c3d")
        self.trial2_path = os.path.join(self.temp_dir, "Subject01_Trial02.c3d")

        t1 = C3DTrial(
            file_path=self.trial1_path,
            first_frame=1,
            last_frame=50,
            point_rate=100.0,
            point_frame_count=50,
            analog_rate=1000.0,
            analog_frame_count=500,
            analog_subsamples=10,
            markers={
                "LASI": np.ones((50, 3), dtype=np.float32) * 100.0,
                "RASI": np.ones((50, 3), dtype=np.float32) * 200.0,
                "OLD_MARKER": np.zeros((50, 3), dtype=np.float32),
            },
            analogs={
                "EMG_TA": np.sin(np.linspace(0, 10, 500)).astype(np.float32),
                "RAW_VOLTAGE": np.full(500, 2.5, dtype=np.float32),
            },
            analog_units={"EMG_TA": "mV", "RAW_VOLTAGE": "V"}
        )
        C3DWriter.save_c3d(t1, self.trial1_path)

        t2 = C3DTrial(
            file_path=self.trial2_path,
            first_frame=1,
            last_frame=60,
            point_rate=100.0,
            point_frame_count=60,
            analog_rate=1000.0,
            analog_frame_count=600,
            analog_subsamples=10,
            markers={
                "LASI": np.ones((60, 3), dtype=np.float32) * 120.0,
                "RASI": np.ones((60, 3), dtype=np.float32) * 220.0,
                "OLD_MARKER": np.zeros((60, 3), dtype=np.float32),
            },
            analogs={
                "EMG_TA": np.sin(np.linspace(0, 10, 600)).astype(np.float32),
                "RAW_VOLTAGE": np.full(600, 3.0, dtype=np.float32),
            },
            analog_units={"EMG_TA": "mV", "RAW_VOLTAGE": "V"}
        )
        C3DWriter.save_c3d(t2, self.trial2_path)

        # Create external per-trial marker files for 'MTJ'
        self.ext_dir = os.path.join(self.temp_dir, "external_data")
        os.makedirs(self.ext_dir, exist_ok=True)

        self.ext1_csv = os.path.join(self.ext_dir, "Subject01_Trial01_MTJ.csv")
        with open(self.ext1_csv, "w") as f:
            f.write("X,Y,Z\n")
            for _ in range(50):
                f.write("10.5,20.5,30.5\n")

        self.ext2_csv = os.path.join(self.ext_dir, "Subject01_Trial02_MTJ.csv")
        with open(self.ext2_csv, "w") as f:
            f.write("X,Y,Z\n")
            for _ in range(60):
                f.write("15.0,25.0,35.0\n")

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_pipeline_executor_intrinsic_operations(self):
        """Test executing intrinsic operations (average marker, filter, rename, delete) on multiple trials."""
        pm = PipelineManager()
        pm.record_create_average_marker(
            new_name="PELVIS_MID",
            parent1="LASI",
            parent2="RASI",
            weights=(0.5, 0.5)
        )
        pm.record_filter_markers(order=4, cutoff=6.0, sampling_rate=100.0)
        pm.record_rename_marker("OLD_MARKER", "RENAMED_MARKER")
        pm.record_filter_analog_channel("EMG_TA", method="Butterworth Low-pass", order=4, cutoff=20.0)
        pm.record_delete_analog_channels(["RAW_VOLTAGE"])

        xml_str = pm.to_xml_string()
        executor = PipelineExecutor(xml_str)
        self.assertEqual(len(executor.operations), 5)
        self.assertEqual(len(executor.get_external_file_requirements()), 0)

        out_dir = os.path.join(self.temp_dir, "processed")
        os.makedirs(out_dir, exist_ok=True)

        out1 = os.path.join(out_dir, "Subject01_Trial01_proc.c3d")
        res1 = executor.execute_file(self.trial1_path, out1)
        self.assertTrue(res1.success)
        self.assertEqual(res1.operations_count, 5)

        # Verify output trial 1
        t1_proc = C3DReader.read(out1)
        self.assertIn("PELVIS_MID", t1_proc.markers)
        # LASI was 100, RASI was 200 -> Average is 150
        np.testing.assert_allclose(t1_proc.markers["PELVIS_MID"][0], [150.0, 150.0, 150.0], rtol=1e-3)
        self.assertIn("RENAMED_MARKER", t1_proc.markers)
        self.assertNotIn("OLD_MARKER", t1_proc.markers)
        self.assertIn("EMG_TA", t1_proc.analogs)
        self.assertNotIn("RAW_VOLTAGE", t1_proc.analogs)

        out2 = os.path.join(out_dir, "Subject01_Trial02_proc.c3d")
        res2 = executor.execute_file(self.trial2_path, out2)
        self.assertTrue(res2.success)
        t2_proc = C3DReader.read(out2)
        # Trial 2 had LASI=120, RASI=220 -> Average is 170
        np.testing.assert_allclose(t2_proc.markers["PELVIS_MID"][0], [170.0, 170.0, 170.0], rtol=1e-3)

    def test_pipeline_executor_per_trial_external_file_matching(self):
        """Test intelligent auto-matching of per-trial external data files for marker MTJ."""
        pm = PipelineManager()
        pm.record_add_marker(
            name="MTJ",
            source_type="file",
            source_file="/original/dummy/path/Trial01_MTJ.csv"
        )
        xml_str = pm.to_xml_string()
        executor = PipelineExecutor(xml_str)

        reqs = executor.get_external_file_requirements()
        self.assertEqual(len(reqs), 1)
        self.assertEqual(reqs[0]["name"], "MTJ")

        # Test resolving external file
        matched1 = executor.resolve_external_file_for_trial(
            self.trial1_path, "MTJ", search_dirs=[self.ext_dir]
        )
        self.assertIsNotNone(matched1)
        self.assertEqual(os.path.basename(matched1), "Subject01_Trial01_MTJ.csv")

        matched2 = executor.resolve_external_file_for_trial(
            self.trial2_path, "MTJ", search_dirs=[self.ext_dir]
        )
        self.assertIsNotNone(matched2)
        self.assertEqual(os.path.basename(matched2), "Subject01_Trial02_MTJ.csv")

        # Execute file with external search directory
        out1 = os.path.join(self.temp_dir, "out1_ext.c3d")
        res1 = executor.execute_file(self.trial1_path, out1, search_dirs=[self.ext_dir])
        self.assertTrue(res1.success)

        t1_out = C3DReader.read(out1)
        self.assertIn("MTJ", t1_out.markers)
        self.assertEqual(len(t1_out.markers["MTJ"]), 50)
        np.testing.assert_allclose(t1_out.markers["MTJ"][0], [10.5, 20.5, 30.5], rtol=1e-3)

        out2 = os.path.join(self.temp_dir, "out2_ext.c3d")
        res2 = executor.execute_file(self.trial2_path, out2, search_dirs=[self.ext_dir])
        self.assertTrue(res2.success)

        t2_out = C3DReader.read(out2)
        self.assertIn("MTJ", t2_out.markers)
        self.assertEqual(len(t2_out.markers["MTJ"]), 60)
        np.testing.assert_allclose(t2_out.markers["MTJ"][0], [15.0, 25.0, 35.0], rtol=1e-3)

    def test_batch_processing_dialog_ui(self):
        """Test BatchProcessingDialog UI components, file queue, and pipeline recipe loading."""
        win = MainWindow()
        dlg = BatchProcessingDialog(main_window=win)

        self.assertEqual(dlg.windowTitle(), "Batch Processing")
        self.assertEqual(dlg.grp_external.title(), "2. Per-Trial External Data (CSV / Excel / TXT)")
        self.assertEqual(dlg.txt_ext_dir.placeholderText(), "Trial name_Marker name.xlsx/txt or csv")
        from gui.toggle_switch import ToggleSwitch
        self.assertIsInstance(dlg.chk_trim_roi, ToggleSwitch)
        self.assertEqual(dlg.chk_trim_roi.text(), "Apply ROI")
        self.assertTrue(dlg.chk_trim_roi.isChecked())
        self.assertFalse(hasattr(dlg, "chk_fallback"))

        # Add files to queue
        added1 = dlg._add_file_to_queue(self.trial1_path)
        added2 = dlg._add_file_to_queue(self.trial2_path)
        self.assertTrue(added1)
        self.assertTrue(added2)

        # Attempt to add duplicates (exact path and Unicode decomposed/NFD path)
        import unicodedata
        dup_exact = dlg._add_file_to_queue(self.trial1_path)
        dup_nfd = dlg._add_file_to_queue(unicodedata.normalize("NFD", self.trial1_path))
        self.assertFalse(dup_exact)
        self.assertFalse(dup_nfd)

        dlg._update_queue_ui()
        self.assertEqual(len(dlg.file_queue), 2)
        self.assertEqual(dlg.table_queue.rowCount(), 2)

        # Create temporary pipeline recipe XML
        recipe_path = os.path.join(self.temp_dir, "test_recipe.xml")
        pm = PipelineManager()
        pm.record_filter_markers(order=4, cutoff=5.0)
        pm.export_xml(recipe_path)

        # Load recipe into dialog
        dlg.txt_xml_path.setText(recipe_path)
        dlg._load_xml_file(recipe_path)
        self.assertEqual(len(dlg.executor.operations), 1)
        self.assertEqual(dlg.table_ops.rowCount(), 1)

        dlg.close()
        win.close()


if __name__ == "__main__":
    unittest.main()
