import copy
import sys
from pathlib import Path
import tempfile
import unittest
import yaml
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from db_registry import build_plans
from inference_identity import validate


class InferenceIdentityTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.output=Path(self.folder.name)
        source=ROOT/'configs/hyperparameters.compare.reviewed_v4_full1500.yaml'
        self.cfg=yaml.safe_load(source.read_text(encoding='utf-8'))
        (self.output/'config.yaml').write_text(yaml.safe_dump(self.cfg),encoding='utf-8')
        self.manifest={'config_hash':build_plans(ROOT,source,False)[0]['config_hash']}
        self.expected=dict(self.cfg['runtime'],requested_linear_attention_backend='torch_reference',
                           linear_attention_backend='installed',kernel_profile='b200_triton360_verified')
        self.runtime={'execution_backend':self.expected,'packages':{'triton':'3.6.0'}}

    def check(self,cfg,runtime=None):
        path=self.output/'eval.yaml'
        path.write_text(yaml.safe_dump(cfg),encoding='utf-8')
        return validate(ROOT,path,cfg,self.manifest,runtime or self.runtime,self.output)

    def test_original_training_config_remains_valid(self):
        self.check(self.cfg)

    def test_verified_runtime_annotation_does_not_change_training_identity(self):
        cfg=copy.deepcopy(self.cfg);cfg['runtime']=self.expected
        self.check(cfg)

    def test_changed_learning_rate_is_still_rejected(self):
        cfg=copy.deepcopy(self.cfg);cfg['runtime']=self.expected
        cfg['experiments'][0]['training']['learning_rate']=0.0009
        with self.assertRaises(ValueError):self.check(cfg)

    def test_unverified_backend_is_rejected(self):
        cfg=copy.deepcopy(self.cfg);cfg['runtime']=dict(self.expected,linear_attention_backend='other')
        with self.assertRaises(ValueError):self.check(cfg)

    def test_runtime_without_verified_package_is_rejected(self):
        cfg=copy.deepcopy(self.cfg);cfg['runtime']=self.expected
        with self.assertRaises(ValueError):self.check(cfg,{'execution_backend':self.expected,'packages':{'triton':'3.4.0'}})
