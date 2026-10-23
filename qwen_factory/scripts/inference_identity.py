"""Keep immutable training identity separate from verified runtime annotations."""
import copy
import tempfile
from pathlib import Path
import yaml
from db_registry import build_plans, sample_mode


def validate(root, config_path, cfg, manifest, runtime, output):
    plan = build_plans(root, config_path, sample_mode(cfg))[0]
    if plan['config_hash'] == manifest['config_hash']:
        return
    saved_path = Path(output) / 'config.yaml'
    saved = yaml.safe_load(saved_path.read_text(encoding='utf-8-sig'))
    saved_plan = build_plans(root, saved_path, sample_mode(saved))[0]
    if saved_plan['config_hash'] != manifest['config_hash']:
        raise ValueError('Stored training config does not match adapter')
    original = saved.get('runtime', {})
    expected = dict(original, requested_linear_attention_backend=original.get('linear_attention_backend'),
                    linear_attention_backend='installed', kernel_profile='b200_triton360_verified')
    if (original.get('linear_attention_backend') != 'torch_reference'
            or cfg.get('runtime') != expected
            or runtime.get('execution_backend') != expected
            or runtime.get('packages', {}).get('triton') != '3.6.0'):
        raise ValueError('Unverified inference runtime identity change')
    normalized = copy.deepcopy(cfg)
    normalized['runtime'] = original
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'normalized_training_identity.yaml'
        path.write_text(yaml.safe_dump(normalized, allow_unicode=True), encoding='utf-8')
        checked = build_plans(root, path, sample_mode(normalized))[0]
    if checked['config_hash'] != manifest['config_hash']:
        raise ValueError('Adapter belongs to different training data or experiment')
