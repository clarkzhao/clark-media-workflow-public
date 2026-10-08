"""CPU-only checks for dependency isolation and batch preflight."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import local_voice


class PreflightTests(unittest.TestCase):
    def test_only_selected_engine_is_required(self):
        for engine, selected, absent in [('voxcpm2', 'voxcpm', 'qwen-tts'),
                                         ('qwen3', 'qwen-tts', 'voxcpm')]:
            def version(name):
                if name == absent:
                    raise importlib.metadata.PackageNotFoundError(name)
                return 'test'
            with patch.object(local_voice.importlib.metadata, 'version', side_effect=version):
                result = local_voice.dependency_versions(engine)
                self.assertIn(selected, result)
                self.assertNotIn(absent, result)

    def test_batch_paths_and_conflicts_before_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'model').mkdir()
            (root/'line.txt').write_text('test', encoding='utf-8')
            batch = root/'jobs.json'
            row = {'text': 'line.txt', 'output': 'audio/one.wav'}
            batch.write_text(json.dumps([row]), encoding='utf-8')
            args = argparse.Namespace(batch=batch, reference=root/'ref.wav',
                transcript=root/'ref.txt', model=root/'model')
            parser = argparse.ArgumentParser()
            jobs, manifest = local_voice.prepare_jobs(args, parser)
            self.assertEqual(jobs[0][2], root/'audio/one.wav')
            self.assertEqual(manifest, root/'jobs.model.json')
            for rows in [[row, row], [{'text': 'line.txt', 'output': 'model/one.wav'}],
                         [{'text': 'line.txt', 'output': 'ref.wav'}]]:
                batch.write_text(json.dumps(rows), encoding='utf-8')
                with self.assertRaises(SystemExit):
                    local_voice.prepare_jobs(args, parser)
            self.assertFalse((root/'audio').exists())


if __name__ == '__main__':
    unittest.main()
