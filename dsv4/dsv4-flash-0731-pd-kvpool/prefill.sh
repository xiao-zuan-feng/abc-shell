#!/bin/bash

# ==============================================================================
# Environment Initialization
# ==============================================================================

# Network Configuration
nic_name="eth0"  # Example: "enp67s0f0np0"

# Prefer POD_IP if available, otherwise fallback to hostname
if [ -n "$POD_IP" ]; then
    local_ip=$POD_IP
else
    local_ip=`hostname -I | awk -F " " '{print $1}'`
fi

echo "Local IP: $local_ip"

# ==============================================================================
# Library & Memory Configuration
# ==============================================================================
export LD_PRELOAD=/usr/lib/aarch64-linux-gnu/libjemalloc.so.2:$LD_PRELOAD
export PYTORCH_NPU_ALLOC_CONF=expandable_segments:True

# ==============================================================================
# HCCL & Ascend NPU Configuration
# ==============================================================================
export HCCL_OP_EXPANSION_MODE="AIV"
export HCCL_EXEC_TIMEOUT=204
export HCCL_CONNECT_TIMEOUT=1200
export HCCL_INTRA_ROCE_ENABLE=1
export HCCL_RDMA_TIMEOUT=17
export HCCL_BUFFSIZE=1024
export ASCEND_CONNECT_TIMEOUT=30000
export ASCEND_TRANSFER_TIMEOUT=30000
export ACL_OP_INIT_MODE=1

# Network Interface Bindings
export HCCL_IF_IP=$local_ip
export GLOO_SOCKET_IFNAME=$nic_name
export TP_SOCKET_IFNAME=$nic_name
export HCCL_SOCKET_IFNAME=$nic_name

# ==============================================================================
# Python & OMP Configuration
# ==============================================================================
export OMP_PROC_BIND=false
export OMP_NUM_THREADS=10
export PYTHONHASHSEED=0
export PYTHONPATH=/workspace/scripts:$PYTHONPATH

# ==============================================================================
# Task Queue & Timeout Configuration
# ==============================================================================
export TASK_QUEUE_ENABLE=1
export VLLM_RPC_TIMEOUT=3600000
export VLLM_EXECUTE_MODEL_TIMEOUT_SECONDS=30000

# ==============================================================================
# Mooncake & KV Cache Configuration
# ==============================================================================
export MOONCAKE_CONFIG_PATH="/workspace/start-scripts/mooncake.json"

# ==============================================================================
# Device Visibility
# ==============================================================================
export ASCEND_RT_VISIBLE_DEVICES=$1

# ==============================================================================
# VLM Serve Command (Prefill Role)
# ==============================================================================
nohup vlm serve /workspace/model \
    --host 0.0.0.0 \
    --port "$2" \
    --data-parallel-size "$3" \
    --data-parallel-rank "$4" \
    --data-parallel-address "$5" \
    --data-parallel-rpc-port "$6" \
    --tensor-parallel-size "$7" \
    --enable-expert-parallel \
    --seed 1024 \
    --served-model-name /model \
    --max-model-len 900000 \
    --max-num-batched-tokens 8192 \
    --max-num-seqs 64 \
    --block-size 32 \
    --enforce-eager \
    --enable-prefix-caching \
    --no-disable-hybrid-kv-cache-manager \
    --trust-remote-code \
    --gpu-memory-utilization 0.9 \
    --quantization ascend \
    --model-loader-extra-config='{"enable_multithread_load": true, "num_threads": 128}' \
    --tokenizer-mode deepseek_v4 \
    --tool-call-parser deepseek_v4 \
    --enable-auto-tool-choice \
    --reasoning-parser deepseek_v4 \
    --additional-config '{
        "enable_cpu_binding": true,
        "enable_shared_expert_dp": true
    }' \
    --kv-transfer-config '{
        "kv_connector": "MultiConnector",
        "kv_role": "kv_producer",
        "kv_load_failure_policy": "recompute",
        "engine_id": "0",
        "kv_connector_extra_config": {
            "connectors": [
                {
                    "kv_connector": "MooncakeConnectorV1",
                    "kv_role": "kv_producer",
                    "kv_port": "30000",
                    "kv_connector_extra_config": {
                        "prefill": {
                            "dp_size": 2,
                            "tp_size": 4
                        },
                        "decode": {
                            "dp_size": 8,
                            "tp_size": 1
                        }
                    }
                },
                {
                    "kv_connector": "AscendStoreConnector",
                    "kv_role": "kv_producer",
                    "kv_connector_extra_config": {
                        "lookup_rpc_port": "0",
                        "load_async": true,
                        "backend": "mooncake"
                    }
                }
            ]
        }
    }' \
    --speculative-config '{"num_speculative_tokens": 7, "method": "dspark", "enforce_eager": true}'