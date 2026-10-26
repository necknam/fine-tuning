import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import runtime_migration as migration


class RuntimeMigrationTests(unittest.TestCase):
    def setup_case(self, root):
        output=root/'run';checkpoint=output/'checkpoints'/'checkpoint-50';checkpoint.mkdir(parents=True)
        names=('adapter_model.safetensors','optimizer.pt','scheduler.pt','trainer_state.json','rng_state.pth')
        for name in names:(checkpoint/name).write_bytes(name.encode())
        previous={'config_hash':'unchanged','model':{'revision':'pinned'},'loss':'assistant_only','pipeline':'production','cuda':'12.8','packages':{'torch':'2.8.0','triton':'3.4.0'}}
        current={**previous,'packages':{'torch':'2.8.0','triton':'3.6.0'}}
        probe=root/'probe.json';probe.write_text(json.dumps({'passed':True,'triton':'3.6.0','tests':[{'finite_forward_backward':True},{'finite_forward_backward':True}]}))
        receipt={'previous_runtime':previous,'next_runtime':current,'probe_path':str(probe),'probe_sha256':migration.digest(probe),'checkpoint':'checkpoints/checkpoint-50','checkpoint_sha256':{n:migration.digest(checkpoint/n) for n in names},'restart_training':False}
        path=root/'receipt.json';path.write_text(json.dumps(receipt))
        return output,checkpoint,previous,current,path

    def test_preserves_history_and_validates_full_checkpoint(self):
        with tempfile.TemporaryDirectory() as d:
            output,_,old,new,receipt=self.setup_case(Path(d))
            with patch.dict(os.environ,{'QF_RUNTIME_MIGRATION_RECEIPT':str(receipt)}):migration.accept(output,old,new)
            self.assertEqual(json.loads((output/'runtime_manifest.json').read_text()),new)
            self.assertEqual(len(list((output/'runtime_history').glob('*.json'))),1)

    def test_rejects_changed_checkpoint(self):
        with tempfile.TemporaryDirectory() as d:
            output,cp,old,new,receipt=self.setup_case(Path(d));(cp/'optimizer.pt').write_bytes(b'changed')
            with patch.dict(os.environ,{'QF_RUNTIME_MIGRATION_RECEIPT':str(receipt)}):
                with self.assertRaisesRegex(ValueError,'Checkpoint changed'):migration.accept(output,old,new)
            self.assertFalse((output/'runtime_manifest.json').exists())

    def test_rejects_unrelated_runtime_changes(self):
        with tempfile.TemporaryDirectory() as d:
            output,_,old,new,receipt=self.setup_case(Path(d));new['model']={'revision':'different'}
            content=json.loads(receipt.read_text());content['next_runtime']=new;receipt.write_text(json.dumps(content))
            with patch.dict(os.environ,{'QF_RUNTIME_MIGRATION_RECEIPT':str(receipt)}):
                with self.assertRaisesRegex(ValueError,'cannot change model'):migration.accept(output,old,new)

if __name__=='__main__':unittest.main()
