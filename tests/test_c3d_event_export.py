import os
import sys
import tempfile
import struct
import numpy as np

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.c3d_reader import C3DReader
from core.c3d_writer import C3DWriter, make_c3d_4char_label
from core.data_models import C3DTrial, C3DEvent


def test_4char_label_generation():
    print("Testing 4-character label generation...", flush=True)
    assert make_c3d_4char_label("Foot Strike", "Right") == "RHS "
    assert make_c3d_4char_label("Foot Off", "Left") == "LTO "
    assert make_c3d_4char_label("Heel Strike", "Right") == "RHS "
    assert make_c3d_4char_label("Toe Off", "Left") == "LTO "
    assert make_c3d_4char_label("Contact", "General") == "FS  "
    assert make_c3d_4char_label("Start", "General") == "STRT"
    assert make_c3d_4char_label("Stop", "General") == "STOP"
    assert make_c3d_4char_label("Jump", "General") == "Jump"
    assert make_c3d_4char_label("R_HeelStrike", "Right") == "RHS "
    print("4-character label generation verified!", flush=True)


def test_binary_header_and_parameter_sync():
    print("Testing binary header and parameter synchronization upon export...", flush=True)
    sample_path = "web/sample/sample_trial.c3d"
    trial = C3DReader.read(sample_path)

    # Add multiple test events with various contexts, descriptions, and subjects
    test_events = [
        C3DEvent(name="Foot Strike", context="Right", frame=15, time=15 / trial.point_rate, description="Initial right contact", subject="Runner1"),
        C3DEvent(name="Foot Off", context="Right", frame=45, time=45 / trial.point_rate, description="Right toe off", subject="Runner1"),
        C3DEvent(name="Foot Strike", context="Left", frame=65, time=65 / trial.point_rate, description="", subject=""),
        C3DEvent(name="Foot Off", context="Left", frame=95, time=95 / trial.point_rate, description="Left toe off", subject="Runner1"),
    ]
    trial.events = test_events

    with tempfile.NamedTemporaryFile(suffix=".c3d", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        # Export C3D
        C3DWriter.save_c3d(trial, tmp_path)

        # 1. Inspect raw binary header (Bytes 298 - 468)
        # Word 151 must be 0 to prevent dual-interpreting readers (BTK, Mokka) from creating duplicate General-context events
        with open(tmp_path, "rb") as f:
            raw = f.read(512)

        word_150 = struct.unpack("<h", raw[298:300])[0]
        word_151 = struct.unpack("<h", raw[300:302])[0]
        word_152 = struct.unpack("<h", raw[302:304])[0]

        assert word_150 == 12345, f"Word 150 must be 12345 (4-char flag), got {word_150}"
        assert word_151 == 0, f"Word 151 must be 0 (preventing Mokka duplicates), got {word_151}"
        assert word_152 == 0, f"Word 152 must be 0 (reserved), got {word_152}"

        print("Binary header words 150-152 verified (Word 151 = 0)!", flush=True)

        # 2. Re-read using C3DReader and verify full event model fidelity
        reloaded = C3DReader.read(tmp_path)
        assert len(reloaded.events) == 4, f"Expected 4 events in reloaded trial, got {len(reloaded.events)}"

        for orig, reloaded_ev in zip(test_events, reloaded.events):
            assert reloaded_ev.name in (orig.name, orig.name.replace(" ", "_")), f"Name mismatch: {reloaded_ev.name} vs {orig.name}"
            assert reloaded_ev.context == orig.context, f"Context mismatch: {reloaded_ev.context} vs {orig.context}"
            assert abs(reloaded_ev.time - orig.time) < 1e-4, f"Time mismatch: {reloaded_ev.time} vs {orig.time}"
            assert reloaded_ev.frame == orig.frame, f"Frame mismatch: {reloaded_ev.frame} vs {orig.frame}"

        print("Full event re-reading and model fidelity verified!", flush=True)

    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_event_deduplication():
    print("Testing event deduplication (eliminating LHS/LTO General duplicates)...", flush=True)
    sample_path = "web/sample/sample_trial.c3d"
    trial = C3DReader.read(sample_path)

    # Simulate user having both specific and duplicate General-context events
    trial.events = [
        C3DEvent(name="Foot strike", context="Left", frame=15, time=15 / trial.point_rate, description="Left strike"),
        C3DEvent(name="LHS", context="General", frame=15, time=15 / trial.point_rate, description=""),
        C3DEvent(name="Left foot off", context="Left", frame=45, time=45 / trial.point_rate, description="Left off"),
        C3DEvent(name="LTO", context="General", frame=45, time=45 / trial.point_rate, description=""),
        C3DEvent(name="Foot strike", context="Right", frame=75, time=75 / trial.point_rate, description="Right strike"),
        C3DEvent(name="RHS", context="General", frame=75, time=75 / trial.point_rate, description=""),
    ]

    with tempfile.NamedTemporaryFile(suffix=".c3d", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        # Save trial
        C3DWriter.save_c3d(trial, tmp_path)

        # Read back
        reloaded = C3DReader.read(tmp_path)

        # Should only have 3 events, NOT 6!
        assert len(reloaded.events) == 3, f"Expected 3 deduplicated events, got {len(reloaded.events)}"

        ev_contexts = [e.context for e in reloaded.events]
        ev_names = [e.name for e in reloaded.events]

        assert "General" not in ev_contexts, f"General context duplicate remained: {ev_contexts}"
        assert ev_contexts == ["Left", "Left", "Right"]
        assert ev_names[0] in ("Foot strike", "Foot_strike")
        assert ev_names[1] in ("Left foot off", "Left_foot_off", "foot off", "foot_off")
        assert ev_names[2] in ("Foot strike", "Foot_strike")

        print("Event deduplication verified successfully! No General/abbreviation duplicates remain.", flush=True)

    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_header_only_events_fallback():
    print("Testing header-only events fallback reading...", flush=True)
    sample_path = "web/sample/sample_trial.c3d"

    # Create a C3D file that has NO EVENT parameter group, only header events
    with tempfile.NamedTemporaryFile(suffix=".c3d", delete=False) as tmp:
        header_only_c3d = tmp.name

    try:
        import ezc3d
        c = ezc3d.c3d(sample_path)
        if "EVENT" in c["parameters"]:
            del c["parameters"]["EVENT"]
        c.write(header_only_c3d)

        # Manually inject header events into words 150-234
        with open(header_only_c3d, "r+b") as fp:
            fp.seek(298)
            fp.write(struct.pack("<H", 12345))
            fp.write(struct.pack("<H", 2))
            fp.write(struct.pack("<H", 0))
            # 2 times: 0.15s, 0.40s
            fp.write(struct.pack("<f", 0.15))
            fp.write(struct.pack("<f", 0.40))
            for _ in range(16):
                fp.write(struct.pack("<f", 0.0))
            for _ in range(18):
                fp.write(b"\x00")
            fp.write(struct.pack("<H", 0))
            # 2 labels: RHS , LTO
            fp.write(b"RHS ")
            fp.write(b"LTO ")
            for _ in range(16):
                fp.write(b"    ")

        # Now read using C3DReader (must fallback to reading header events)
        loaded = C3DReader.read(header_only_c3d)
        assert len(loaded.events) == 2, f"Expected 2 header fallback events, got {len(loaded.events)}"
        assert loaded.events[0].name == "RHS"
        assert loaded.events[0].context == "Right"
        assert abs(loaded.events[0].time - 0.15) < 1e-4
        assert loaded.events[1].name == "LTO"
        assert loaded.events[1].context == "Left"
        assert abs(loaded.events[1].time - 0.40) < 1e-4

        print("Header-only events fallback reading verified successfully!", flush=True)

    finally:
        if os.path.exists(header_only_c3d):
            os.remove(header_only_c3d)


def test_trimmed_event_positioning_and_mokka_sync():
    print("Testing trimmed event positioning and Mokka/BTK ruler alignment...", flush=True)
    sample_path = "web/sample/sample_trial.c3d"
    trial = C3DReader.read(sample_path)
    orig_first = trial.first_frame  # 1846

    # Add an event at relative frame 40 (inside trim range [20, 80])
    ev = C3DEvent(name="Foot Strike", context="Left", frame=40, time=40 / trial.point_rate)
    trial.events = [ev]

    with tempfile.NamedTemporaryFile(suffix=".c3d", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        # Trim trial from frame 20 to 80 (61 frames)
        C3DWriter.save_c3d(trial, tmp_path, start_frame=20, end_frame=80)

        # 1. Inspect with ezc3d to verify low-level C3D parameter synchronization
        import ezc3d
        c = ezc3d.c3d(tmp_path)
        new_first = c["header"]["points"]["first_frame"]
        new_last = c["header"]["points"]["last_frame"]

        assert new_first == orig_first + 20, f"Expected first_frame {orig_first + 20}, got {new_first}"
        assert new_last == orig_first + 80, f"Expected last_frame {orig_first + 80}, got {new_last}"

        # If TRIAL group exists, check ACTUAL_START_FIELD and ACTUAL_END_FIELD
        if "TRIAL" in c["parameters"] and "ACTUAL_START_FIELD" in c["parameters"]["TRIAL"]:
            lsb, hsb = c["parameters"]["TRIAL"]["ACTUAL_START_FIELD"]["value"]
            trial_start = (hsb << 16) | lsb
            assert trial_start == new_first, f"TRIAL:ACTUAL_START_FIELD mismatch: {trial_start} vs {new_first}"

        # 2. Check event time and Mokka / BTK ruler position
        ev_times = c["parameters"]["EVENT"]["TIMES"]["value"]
        t_sec = ev_times[0, 0] * 60.0 + ev_times[1, 0]

        # In Mokka / BTK: frame = floor(time * point_rate + 1.5)
        mokka_frame = int(np.floor(t_sec * trial.point_rate + 1.5))
        expected_mokka_frame = new_first + (40 - 20)  # Ruler frame 1886
        assert mokka_frame == expected_mokka_frame, f"Mokka frame mismatch: {mokka_frame} vs expected {expected_mokka_frame}"
        print(f"Mokka / BTK ruler position verified at ruler frame {mokka_frame} (+20 frames into cut)!", flush=True)

        # 3. Check C3DReader reading of trimmed file
        reloaded = C3DReader.read(tmp_path)
        assert len(reloaded.events) == 1, f"Expected 1 event, got {len(reloaded.events)}"
        assert reloaded.events[0].frame == 20, f"Expected relative frame 20, got {reloaded.events[0].frame}"
        assert abs(reloaded.events[0].time - 20 / trial.point_rate) < 1e-4, f"Time mismatch: {reloaded.events[0].time}"
        print("C3DReader trimmed event frame and time verified perfectly!", flush=True)

    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


if __name__ == "__main__":
    test_4char_label_generation()
    test_binary_header_and_parameter_sync()
    test_event_deduplication()
    test_trimmed_event_positioning_and_mokka_sync()
    test_header_only_events_fallback()
    print("\nALL C3D EVENT EXPORT AND PERSISTENCE TESTS PASSED!", flush=True)
