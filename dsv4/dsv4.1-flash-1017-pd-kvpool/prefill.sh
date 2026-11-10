#!/usr/bin/env bash

unset https_proxy
unset http_proxy

NIC_NAME="<NETWORK_INTERFACE>"
LOCAL_IP="<PREFILL_NODE_IP>"
MODEL_PATH="<YOUR_MODEL_PATH>"
MOONCAKE_CONFIG_DIR="<MOONCAKE_CONFIG_DIR>"

export HCCL_IF_IP="$LOCAL_IP"
export GLOO_SOCKET_IFNAME="$NIC_NAME"
export TP_SOCKET_IFNAME="$NIC_NAME"
export HCCL_SOCKET_IFNAME="$NIC_NAME"
export VLLM_USE_V2_MODEL_RUNNER=0
export HCCL_INTRA_ROCE_ENABLE=1
export VLLM_ENGINE_READY_TIMEOUT_S=360000
export HCCL_CONNECT_TIMEOUT=1200
export HCCL_BUFFSIZE=1024
export TASK_QUEUE_ENABLE=1
export VLLM_RPC_TIMEOUT=3600000
export VLLM_EXECUTE_MODEL_TIMEOUT_SECONDS=30000
export HCCL_EXEC_TIMEOUT=204
export HCCL_OP_EXPANSION_MODE="AIV"
export PYTORCH_NPU_ALLOC_CONF=expandable_segments:True
export ASCEND_RT_VISIBLE_DEVICES=$1

# Parameters required by the Mooncake KV Cache Pool.
export PYTHONHASHSEED=0
export MOONCAKE_CONFIG_PATH="$MOONCAKE_CONFIG_DIR/mooncake.json"

vllm serve "$MODEL_PATH" \
    --host 0.0.0.0 \
    --port $2 \
    --data-parallel-size $3 \
    --data-parallel-rank $4 \
    --data-parallel-address $5 \
    --data-parallel-rpc-port $6 \
    --tensor-parallel-size $7 \
    --enable-expert-parallel \
    --seed 1024 \
    --served-model-name dsv41 \
    --max-model-len 1048576 \
    --max-num-batched-tokens 8192 \
    --max-num-seqs 16 \
    --speculative-config '{"num_speculative_tokens":5,"method":"dspark"}' \
    --trust-remote-code \
    --block-size 128 \
    --tokenizer-mode deepseek_v41 \
    --reasoning-parser deepseek_v41 \
    --tool-call-parser deepseek_v41 \
    --enable-auto-tool-choice \
    --safetensors-load-strategy lazy \
    --gpu-memory-utilization 0.9 \
    --quantization ascend \
    --enforce-eager \
    --enable-prefix-caching \
    --engram-config '{"cpu_offload":true,"dp_shared_memory":true}' \
    --additional-config '{
        "enable_cpu_binding":true,
        "enable_dsa_cp":true,
        "enable_flashcomm1":true,
        "enable_shared_expert_dp":true
    }' \
    --kv-transfer-config '{
        "kv_connector":"MultiConnector",
        "kv_role":"kv_producer",
        "kv_port":"30000",
        "engine_id":"0",
        "kv_connector_extra_config":{
            "connectors":[
                {
                    "kv_connector":"MooncakeHybridConnector",
                    "kv_role":"kv_producer",
                    "kv_port":"30000",
                    "kv_connector_extra_config":{
                        "prefill":{"dp_size":4,"tp_size":4},
                        "decode":{"dp_size":8,"tp_size":2}
                    }
                },
                {
                    "kv_connector":"AscendStoreConnector",
                    "kv_role":"kv_producer",
                    "kv_connector_extra_config":{
                        "lookup_rpc_port":"0",
                        "backend":"mooncake",
                        "use_layerwise":false
                    }
                }
            ]
        }
    }'