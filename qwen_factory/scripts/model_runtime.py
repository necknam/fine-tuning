"""Explicit, recorded linear-attention backend for the pinned Qwen runtime."""
import inspect
import os
import importlib.metadata


def configure(config):
    backend=config.get('runtime',{}).get('linear_attention_backend','installed')
    override=os.environ.get('QF_LINEAR_ATTENTION_BACKEND')
    if not override and backend=='torch_reference' and importlib.metadata.version('triton')=='3.6.0':
        override='installed'
    if override:
        if override!='installed' or importlib.metadata.version('triton')!='3.6.0':
            raise ValueError('Only the verified Triton 3.6 installed backend override is supported')
        config['runtime']={**config.get('runtime',{}),'requested_linear_attention_backend':config.get('runtime',{}).get('requested_linear_attention_backend',backend),'linear_attention_backend':override,'kernel_profile':'b200_triton360_verified'}
        backend=override
        print('LINEAR ATTENTION BACKEND: installed FLA / verified Triton 3.6.0',flush=True)
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
