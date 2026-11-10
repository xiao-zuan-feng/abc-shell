export OMP_PROC_BIND=false
export OMP_NUM_THREADS=10
export PYTORCH_NPU_ALLOC_CONF=expandable_segments:True
export LD_PRELOAD=/usr/lib/aarch64-linux-gnu/libjemalloc.so.2:$LD_PRELOAD
export HCCL_BUFFSIZE=1024
export VLIM_ASCEND_APPLY_DSV4_PATCH=1
export VLIM_ASCEND_ENABLE_FLASHCOMM1=1
export TASK_QUEUE_ENABLE=1
export HCCL_OP_EXPANSION_MODE="AIV"
export PYTHONPATH=/workspace/scripts:$PYTHONPATH

vllm serve /workspace/model \
    --max_model_len 1000000 \
    --max-num-batched-tokens 8192 \
    --served-model-name /model \
    --gpu-memory-utilization 0.95 \
    --max-num-seqs 16 \
    --data-parallel-size 1 \
    --tensor-parallel-size 8 \
    --enable-expert-parallel \
    --tokenizer-mode deepseek_v4 \
    --tool-call-parser deepseek_v4 \
    --enable-auto-tool-choice \
    --reasoning-parser deepseek_v4 \
    --enable-prefix-caching \
    --model-loader-extra-config='{"enable_multithread_load": true, "num_threads": 128}' \
    --quantization ascend \
    --port 8005 \
    --block-size 32 \
    --enable-prompt-tokens-details \
    --no-disable-hybrid-kv-cache-manager \
    --compilation-config '{"cudagraph_mode": "FULL_DECODE_ONLY"}' \
    --async-scheduling \
    --default-chat-template-kwargs '{"enable_thinking":true}' \
    --speculative-config '{"num_speculative_tokens":7,"method": "dspark","enforce_eager": true}' \
    --additional-config '
{
    "ascend_compilation_config":{
        "enable_npugraph_ex":true,
        "enable_static_kernel":false
    },
    "enable_cpu_binding": true,
    "enable_dsa_cp": true,
    "multistream_overlap_shared_expert":true
}'