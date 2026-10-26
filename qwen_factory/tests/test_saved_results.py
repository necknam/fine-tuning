import ast
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import pack_production_handoff as packaging

class SnapshotTests(unittest.TestCase):
    def load(self, data):
        source = ast.parse((ROOT/'scripts/current_experiment_dashboard.py').read_text(encoding='utf-8'))
        function = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == 'load_snapshot')
        scope = {'ROOT': ROOT, 'json': json}
        # Compile optimized to verify checks cannot disappear like assert statements.
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'snapshot', 'exec', optimize=2), scope)
        with patch.object(json, 'loads', return_value=data):
            return scope['load_snapshot']()

    def test_real_snapshot_is_structurally_bound(self):
        data = json.loads((ROOT/'dashboard/current_b200.json').read_text(encoding='utf-8'))
        self.assertIs(self.load(data), data)

    def test_optimized_mode_rejects_mismatched_execution(self):
        original = json.loads((ROOT/'dashboard/current_b200.json').read_text(encoding='utf-8'))
        for field in ('run_id', 'trained_epoch'):
            data = copy.deepcopy(original)
            data['epochs']['2']['cases'][0]['factory_manifest'][field] = 'wrong'
            with self.assertRaises(ValueError): self.load(data)
        data = copy.deepcopy(original)
        data['epochs']['2']['cases'][0]['test_sha256'] = 'wrong'
        with self.assertRaises(ValueError): self.load(data)

class PackagingTests(unittest.TestCase):
    def test_missing_input_preserves_previous_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'configs').mkdir()
            (root/'configs/hyperparameters.production.pinned.yaml').write_text('data: {}', encoding='utf-8')
            (root/'outputs').mkdir()
            archive = root/'outputs/gpu_production_handoff.zip'
            archive.write_bytes(b'previous verified archive')
            cfg = {'data': {k:'missing.jsonl' for k in ('train_file','validation_file','heldout_test_file','test_file')}}
            with patch.object(packaging.yaml,'safe_load',return_value=cfg), patch.object(packaging,'build_plans',return_value=[{'config_hash':'test'}]), patch.object(packaging,'report_input_info'):
                with self.assertRaisesRegex(ValueError,'Missing bundle input'): packaging.pack(root)
            self.assertEqual(archive.read_bytes(), b'previous verified archive')
