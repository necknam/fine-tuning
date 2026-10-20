import ast,json,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
tree=ast.parse((ROOT/'scripts/runpod_factory_sample.py').read_text(encoding='utf-8-sig'))
node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='encode_all')
scope={'json':json};exec(compile(ast.Module(body=[node],type_ignores=[]),'encode_all','exec'),scope)
encode=scope['encode_all']

class Tokenizer:
 def apply_chat_template(self,messages,*,add_generation_prompt,**kw):
  ids=[]
  for m in messages:ids += [1 if m['role']=='user' else 2, *[ord(c) for c in m['content']], 3]
  return ids+[2] if add_generation_prompt else ids

class LossTests(unittest.TestCase):
 def call(self,rows,policy='final_assistant_only',limit=1000,tokenizer=None):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'data.jsonl';p.write_text('\n'.join(json.dumps(r) for r in rows),encoding='utf-8')
   return encode(p,tokenizer or Tokenizer(),limit,loss_policy=policy)
 def test_prompt_mask_and_answer_supervision(self):
  rows=self.call([{'messages':[{'role':'user','content':'q'},{'role':'assistant','content':'a'}]}])
  self.assertEqual(rows[0]['labels'],[-100,-100,-100,-100,ord('a'),3])
 def test_multiturn_history_is_context_only(self):
  messages=[{'role':'user','content':'q'},{'role':'assistant','content':'a'},{'role':'user','content':'r'},{'role':'assistant','content':'b'}]
  labels=self.call([{'messages':messages}])[0]['labels']
  self.assertEqual(labels[:-2],[-100]*10);self.assertEqual(labels[-2:],[ord('b'),3])
 def test_sample_legacy_loss_is_preserved(self):
  row=self.call([{'messages':[{'role':'user','content':'q'},{'role':'assistant','content':'a'}]}],'all_tokens')[0]
  self.assertEqual(row['labels'],row['input_ids'])
 def test_length_overflow_is_rejected(self):
  with self.assertRaisesRegex(ValueError,'no truncation'):
   self.call([{'messages':[{'role':'user','content':'long'},{'role':'assistant','content':'a'}]}],limit=1)
 def test_empty_answer_is_rejected(self):
  with self.assertRaisesRegex(ValueError,'Empty assistant'):
   self.call([{'messages':[{'role':'user','content':'q'},{'role':'assistant','content':''}]}])
 def test_prefix_mismatch_is_rejected(self):
  class Bad(Tokenizer):
   def apply_chat_template(self,messages,**kw):return [99] if kw['add_generation_prompt'] else super().apply_chat_template(messages,**kw)
  with self.assertRaisesRegex(ValueError,'prefix mismatch'):
   self.call([{'messages':[{'role':'user','content':'q'},{'role':'assistant','content':'a'}]}],tokenizer=Bad())

if __name__=='__main__':unittest.main()
