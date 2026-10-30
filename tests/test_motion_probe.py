"""Encoded synthetic fixtures: object action vs static zoom/subtitle movement."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from motion_probe import probe_motion

try:
    import av
    import cv2
    import numpy as np
except ImportError:
    av = cv2 = np = None


@unittest.skipIf(av is None, "optional motion dependencies unavailable; not a motion pass")
class MotionProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.spec = dict(window_s=[0.1, 1.9], roi=[0.05, 0.05, 0.95, 0.78], samples=5,
                        pixel_delta=12, min_changed_fraction=0.012, min_pairs=2, min_alignment_correlation=0.65)
        for mode in ("static", "zoom", "subtitles", "action", "blank"):
            cls.encode(mode)

    @classmethod
    def encode(cls, mode):
        width, height, count = 320, 240, 48
        background = np.full((height, width, 3), 35, np.uint8)
        for x in range(0, width, 20):
            cv2.line(background, (x, 0), (x, height), (110, 110, 110), 1)
        for y in range(0, height, 25):
            cv2.line(background, (0, y), (width, y), (95, 95, 95), 1)
        cv2.rectangle(background, (100, 25), (220, 175), (75, 120, 150), 2)
        path = cls.root / (mode + ".mp4")
        with av.open(str(path), "w") as container:
            stream = container.add_stream("mpeg4", rate=24)
            stream.width, stream.height, stream.pix_fmt = width, height, "yuv420p"
            stream.bit_rate = 2_000_000
            for index in range(count):
                frame = background.copy()
                if mode == "blank":
                    frame[:] = 0
                elif mode == "action":
                    x = 95 + round(index * 1.8)
                    cv2.rectangle(frame, (x, 60), (x+36, 135), (245, 245, 245), -1)
                elif mode == "zoom":
                    matrix = cv2.getRotationMatrix2D((width/2, height/2), 0, 1 + 0.04*index/count)
                    frame = cv2.warpAffine(frame, matrix, (width, height))
                elif mode == "subtitles":
                    cv2.putText(frame, str(index), (80, 225), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                for packet in stream.encode(av.VideoFrame.from_ndarray(frame, format="rgb24")):
                    container.mux(packet)
            for packet in stream.encode():
                container.mux(packet)

    def test_static_pan_zoom_and_captions_do_not_satisfy_object_action(self):
        for name in ("static", "zoom", "subtitles"):
            with self.subTest(name=name):
                report = probe_motion(self.root / (name + ".mp4"), self.spec)
                self.assertEqual(report["status"], "failed", report)

    def test_actual_object_motion_passes_screening(self):
        report = probe_motion(self.root / "action.mp4", self.spec)
        self.assertEqual(report["status"], "passed", report)

    def test_unalignable_region_never_passes(self):
        self.assertEqual(probe_motion(self.root / "blank.mp4", self.spec)["status"], "unknown")

    def test_end_beyond_video_never_clones_last_frame(self):
        spec = dict(self.spec, window_s=[0.1, 5.0])
        self.assertEqual(probe_motion(self.root / "action.mp4", spec)["status"], "unknown")

    def test_bad_region_rejected(self):
        with self.assertRaises(ValueError):
            probe_motion(self.root / "action.mp4", dict(self.spec, roi=[0, 0, 0.01, 0.01]))


if __name__ == "__main__":
    unittest.main()
