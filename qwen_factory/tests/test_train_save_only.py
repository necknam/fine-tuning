import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import control_pipeline
from local_evaluation_bundle import frozen_inputs
from cloud_evidence import canonical


class SaveOnlyTests(unittest.TestCase):
    def receipt(self):
        rows = [{'messages': [{'role': 'user', 'content': str(i)}]} for i in range(10)]
        body = ''.join(canonical(x) + '\n' for x in rows)
        cfg = {'live_evaluation': {'cohort_id': 'fixed', 'case_employee_ids': list(range(10))},
               'evaluation': {'sha256': 'template'}}
        receipt = dict(cohort_id='fixed', case_employee_ids=list(range(10)), template_sha256='template',
                       rows=rows, sha256=hashlib.sha256(body.encode()).hexdigest())
        return cfg, receipt, body

    def test_inputs_reuse_identical_bytes(self):
        cfg, receipt, body = self.receipt()
        self.assertEqual(frozen_inputs(cfg, receipt), body)

    def test_rejects_changed_profile_content(self):
        cfg, receipt, _ = self.receipt()
        receipt['rows'][0]['messages'][0]['content'] = 'different'
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            frozen_inputs(cfg, receipt)

    def test_rejects_cohort_or_assignment_substitution(self):
        for field, replacement in [('cohort_id', 'other'), ('case_employee_ids', [99]*10)]:
            cfg, receipt, _ = self.receipt()
            receipt[field] = replacement
            with self.assertRaises(ValueError):
                frozen_inputs(cfg, receipt)

    def test_rejects_missing_case_even_with_updated_hash(self):
        cfg, receipt, _ = self.receipt()
        receipt['rows'].pop()
        with self.assertRaisesRegex(ValueError, 'ten'):
            frozen_inputs(cfg, receipt)

    def test_save_only_pipeline_returns_before_freeze_or_generation(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root/'configs').mkdir()
            cfg = {'dataset_mode':'production', 'experiments':[{'artifacts':{'save_epochs':[2,5]}}]}
            (root/'configs/test.yaml').write_text(yaml.safe_dump(cfg), encoding='utf-8')
            record = {'run_id':'12345678-1234-4234-8234-123456789012', 'status':'REGISTERED'}
            snapshots = [{'trained_epoch':2}, {'trained_epoch':5}]
            engine = MagicMock()
            conn = engine.connect.return_value.__enter__.return_value
            conn.execute.return_value.mappings.return_value.one.return_value = record
            conn.execute.return_value.mappings.return_value.__iter__.return_value = iter(snapshots)
            with patch.object(control_pipeline, '__file__', str(root/'scripts/control_pipeline.py')), \
                 patch.object(control_pipeline, 'build_plans', return_value=[{'config_hash':'hash'}]), \
                 patch.object(control_pipeline, 'create_engine', return_value=engine), \
                 patch.object(control_pipeline.subprocess, 'run') as run, \
                 patch('local_evaluation_bundle.export_bundle', return_value={'generated_answers':0}) as export, \
                 patch('cloud_evaluation.freeze', side_effect=AssertionError('Must not create a new cohort')), \
                 patch.dict('os.environ', {'DATABASE_URL':'sqlite://', 'QF_GPU_LOCK_FD':''}), \
                 patch.object(sys, 'argv', ['control_pipeline.py','--config','configs/test.yaml','--train-save-only']):
                control_pipeline.main()
            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual(len(commands), 2)
            self.assertIn('scripts/db_registry.py', commands[0])
            self.assertIn('scripts/runpod_factory_sample.py', commands[1])
            self.assertIn('--execute', commands[1])
            export.assert_called_once()
            engine.dispose.assert_called_once()


if __name__ == '__main__':
    unittest.main()
