import json,os
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock,patch

from src.finetuning.curation_core import review_response_format,bind_review_quotes,validate_review,DIMENSIONS
from src.finetuning.export_finetuning_dataset import call_llm_with_retry
from src.clients import llm_adapter as module


class StructuredReviewTests(TestCase):
    def adapter(self,content='{}',finish='stop',refusal=None):
        message=SimpleNamespace(content=content,refusal=refusal)
        response=SimpleNamespace(choices=[SimpleNamespace(message=message,finish_reason=finish)],usage=None)
        create=Mock(return_value=response)
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with patch.dict(os.environ,{'OPENAI_API_KEY':'test-fixture-only','OPENAI_MODEL':'gpt-5-mini'}),patch.object(module,'OpenAI',return_value=client):
            adapter=module.LLMAdapter()
        adapter.reasoning_effort='low'
        return adapter,create

    def test_schema_rejects_unknown_quotes_extra_fields_and_score_types(self):
        import jsonschema
        fmt=review_response_format({'answer':'실제 답변','next_step':'확인할 문서'})
        schema=fmt['json_schema']['schema'];jsonschema.Draft202012Validator.check_schema(schema)
        value={'scores':{k:4 for k in DIMENSIONS},'verdict':'pass','issues':[],'reason':'대조 완료'}
        jsonschema.validate(value,schema)
        value['issues']=[{'quote_id':'A9999','reason':'없는 인용'}]
        with self.assertRaises(jsonschema.ValidationError):jsonschema.validate(value,schema)
        value['issues']=[];value['secret_extra']='extra'
        with self.assertRaises(jsonschema.ValidationError):jsonschema.validate(value,schema)
        del value['secret_extra'];value['scores'][DIMENSIONS[0]]=True
        with self.assertRaises(jsonschema.ValidationError):jsonschema.validate(value,schema)

    def test_schema_reaches_sdk_and_refusal_or_truncation_never_counts_as_success(self):
        fmt=review_response_format({'answer':'실제 답변'})
        adapter,create=self.adapter();adapter._call_openai([],0.25,response_format=fmt)
        self.assertEqual(create.call_args.kwargs['response_format'],fmt)
        self.assertNotIn('temperature',create.call_args.kwargs)
        for finish,refusal,code in [('length',None,'INCOMPLETE'),('stop','refused','REFUSAL')]:
            adapter,_=self.adapter(finish=finish,refusal=refusal)
            with self.assertRaisesRegex(RuntimeError,code):adapter._call_openai([],0.25,response_format=fmt)

    def test_structured_failure_never_silently_uses_local_provider(self):
        adapter,_=self.adapter();adapter.local_llm_base_url='http://not-called';adapter.local_llm_model='qwen'
        adapter._call_openai=Mock(side_effect=ValueError('unit failure'));adapter._call_local_qwen=Mock(return_value='{}')
        response=adapter.generate([],response_format=review_response_format({'answer':'실제 답변'}))
        self.assertFalse(response.success);adapter._call_local_qwen.assert_not_called()
        adapter,_=self.adapter();adapter._call_openai=Mock(return_value='{}')
        self.assertTrue(adapter.generate([]).success)
        adapter._call_openai.assert_called_once_with([],0.5)

    def test_retry_forwards_schema_but_keeps_semantic_checks(self):
        fmt=review_response_format({'answer':'실제 답변'})
        adapter=SimpleNamespace(generate=Mock(return_value=SimpleNamespace(success=True,content='{}',provider='openai',model='gpt-5-mini')))
        call_llm_with_retry(adapter,'policy','input',json.loads,lambda value:None,response_format=fmt)
        self.assertEqual(adapter.generate.call_args.kwargs['response_format'],fmt)
        self.assertEqual(adapter.generate.call_args.kwargs['force_provider'],'openai')
        value={'scores':{k:5 for k in DIMENSIONS},'verdict':'pass',
               'issues':[{'quote_id':'A0001','reason':'해결되지 않은 문제'}],'reason':'판정 모순'}
        bind_review_quotes(value,{'answer':'실제 답변'})
        with self.assertRaisesRegex(ValueError,'PASS_CONTRADICTION'):validate_review(value,{'answer':'실제 답변'})

    def test_schema_provider_failures_are_explicit_and_not_retried_as_json(self):
        fmt=review_response_format({'answer':'실제 답변'})
        adapter=SimpleNamespace(generate=Mock(return_value=SimpleNamespace(success=False,
            metadata={'failures':[{'code':'INVALID_REQUEST','message':'do not expose'}]})))
        with self.assertRaisesRegex(RuntimeError,'STRUCTURED_REVIEW_PROVIDER_FAILURE:INVALID_REQUEST'):
            call_llm_with_retry(adapter,'policy','input',json.loads,lambda value:None,response_format=fmt)
        self.assertEqual(adapter.generate.call_count,1)
