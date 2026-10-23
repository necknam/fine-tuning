import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import model_runtime


class BackendSelectionTests(unittest.TestCase):
    def test_repaired_version_uses_fast_backend_and_records_requested_policy(self):
        cfg={'runtime':{'linear_attention_backend':'torch_reference'}}
        with patch.dict('os.environ',{},clear=True),patch('model_runtime.importlib.metadata.version',return_value='3.6.0'):
            model_runtime.configure(cfg)
        self.assertEqual(cfg['runtime']['linear_attention_backend'],'installed')
        self.assertEqual(cfg['runtime']['requested_linear_attention_backend'],'torch_reference')

    def test_repeated_override_does_not_change_recorded_policy(self):
        cfg={'runtime':{'linear_attention_backend':'torch_reference'}}
        with patch.dict('os.environ',{'QF_LINEAR_ATTENTION_BACKEND':'installed'},clear=True),patch('model_runtime.importlib.metadata.version',return_value='3.6.0'):
            model_runtime.configure(cfg);first=dict(cfg['runtime']);model_runtime.configure(cfg)
        self.assertEqual(cfg['runtime'],first)

    def test_override_rejects_unverified_compiler_version(self):
        with patch.dict('os.environ',{'QF_LINEAR_ATTENTION_BACKEND':'installed'},clear=True),patch('model_runtime.importlib.metadata.version',return_value='3.4.0'):
            with self.assertRaises(ValueError):model_runtime.configure({'runtime':{'linear_attention_backend':'torch_reference'}})

if __name__=='__main__':unittest.main()
