"""Explicit, recorded linear-attention backend for the pinned Qwen runtime."""
import inspect


def configure(config):
    backend=config.get('runtime',{}).get('linear_attention_backend','installed')
    if backend=='installed':return
    if backend!='torch_reference':raise ValueError('Unsupported linear attention backend')
    from transformers.models.qwen3_5 import modeling_qwen3_5 as module
    function=inspect.unwrap(module.torch_chunk_gated_delta_rule)
    if function.__module__!=module.__name__:
        raise ValueError('Pinned reference implementation unavailable')
    module.torch_chunk_gated_delta_rule=function
    # Use the matching native recurrence during autoregressive generation, too.
    module.torch_recurrent_gated_delta_rule=inspect.unwrap(module.torch_recurrent_gated_delta_rule)
    print('LINEAR ATTENTION BACKEND: transformers PyTorch reference (explicit configuration)',flush=True)
