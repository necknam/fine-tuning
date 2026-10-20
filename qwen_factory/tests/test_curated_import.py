import json,hashlib,unittest,tempfile
from pathlib import Path
from prepare_data import import_curated_release


class CuratedImportTests(unittest.TestCase):
    def fixture(self,path):
        path.mkdir();provenance=[];files={}
        for split,count in {'train':1200,'validation':150,'test':150}.items():
            rows=[]
            for i in range(count):
                row={'messages':[{'role':'user','content':f'{split} prompt {i}'},{'role':'assistant','content':'answer'}]}
                rows.append(json.dumps(row));provenance.append({'id':f'{split}-{i}','split':split,'family_id':split,
                  'sha256':hashlib.sha256(json.dumps(row,ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest()})
            (path/f'sft_{split}.jsonl').write_text('\n'.join(rows)+'\n',encoding='utf-8')
        (path/'provenance.jsonl').write_text('\n'.join(json.dumps(p) for p in provenance)+'\n',encoding='utf-8')
        (path/'sample_review.json').write_text('{}',encoding='utf-8')
        for f in path.iterdir():files[f.name]=hashlib.sha256(f.read_bytes()).hexdigest()
        (path/'manifest.json').write_text(json.dumps({'selected':1500,'split_counts':{'train':1200,'validation':150,'test':150},'files_sha256':files}),encoding='utf-8')

    def test_preserves_splits_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'release';self.fixture(source)
            report=import_curated_release(source,root/'factory')
            self.assertFalse(report['reshuffled']);self.assertFalse(report['training_started'])
            self.assertEqual((Path(report['target'])/'train.jsonl').read_bytes(),(source/'sft_train.jsonl').read_bytes())
            with self.assertRaisesRegex(ValueError,'exists'):import_curated_release(source,root/'factory')

    def test_rejects_tampering_before_creating_destination(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'release';self.fixture(source)
            (source/'sft_test.jsonl').write_text('changed',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):import_curated_release(source,root/'factory')
            self.assertFalse((root/'factory/data').exists())
