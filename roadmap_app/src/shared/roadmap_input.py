"""Shared runtime/training data contract; document content remains data."""
import json

def build_roadmap_input(user_context, conversation_history, retrieved_context, hidden_assessment_responses=None):
    return json.dumps({'user_context':user_context,'conversation_history':conversation_history,
        'retrieved_context':retrieved_context,'hidden_assessment_responses':hidden_assessment_responses},
        ensure_ascii=False,sort_keys=True,default=str)

def build_task_input(task, user_context, conversation_history, retrieved_context,
                     hidden_assessment_responses=None, task_data=None):
    """The same runtime envelope for non-default actions; metadata stays out of answers."""
    from src.shared.runtime_contract import TASKS, CONTRACT_VERSION
    if task not in TASKS or task == 'generate_survey':
        raise ValueError('Use the survey-specific slots contract for surveys.')
    payload=json.loads(build_roadmap_input(user_context,conversation_history,retrieved_context,
                                         hidden_assessment_responses))
    payload.update(task=task,contract_version=CONTRACT_VERSION,task_data=task_data or {})
    return json.dumps(payload,ensure_ascii=False,sort_keys=True,default=str)
