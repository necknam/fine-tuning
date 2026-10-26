"""Display recorded training settings without inventing missing values."""
import re

def summary(cfg, manifest):
    cfg = cfg or {}
    recipe = (cfg.get('experiments') or [{}])[0] or {}
    training = recipe.get('training') or {}
    lora = recipe.get('lora') or {}
    name = recipe.get('recipe_name') or str(manifest.get('run_id', '미기록'))[:8]
    preset = re.search(r'(?:^|_)(P\d{2})(?:_|$)', name)
    batch = training.get('per_device_train_batch_size')
    accumulation = training.get('gradient_accumulation_steps')
    value = lambda x: '미기록' if x is None else x
    return {
        '실험': preset.group(1) if preset else name,
        '학습률': format(training['learning_rate'], '.6g') if training.get('learning_rate') is not None else '미기록',
        'LoRA r': value(lora.get('r')),
        'LoRA α': value(lora.get('lora_alpha')),
        'Dropout': value(lora.get('lora_dropout')),
        '배치': value(batch),
        '누적': value(accumulation),
        '유효 배치': batch * accumulation if isinstance(batch, int) and isinstance(accumulation, int) else '미기록',
        '최대 토큰': value(training.get('max_length')),
        '정밀도': 'BF16' if training.get('bf16') is True else '미기록',
        '기본모델 양자화': '4bit' if (cfg.get('quantization') or {}).get('load_in_4bit') is True else '없음' if (cfg.get('quantization') or {}).get('load_in_4bit') is False else '미기록',
        '옵티마이저': value(training.get('optim')),
        '스케줄': value(training.get('lr_scheduler_type')),
        'Warmup 비율': value(training.get('warmup_ratio')),
        'Weight decay': value(training.get('weight_decay')),
        'Seed': value(training.get('seed')),
        '저장 에폭': value(manifest.get('trained_epoch')),
        '원본 실험명': name,
    }
