#!/bin/bash

# ==============================================================================
# Environment Cleanup & Initialization
# ==============================================================================
unset ftp_proxy
unset https_proxy
unset http_proxy
rm -rf ~/ascend/log

# ==============================================================================
# Network Configuration
# ==============================================================================
nic_name="eth0"  # Example: "enp67s0f0np0"
# local_ip=`hostname -I|awk -F " " '{print$1}'`
local_ip=$POD_IP
echo "Local IP:$local_ip"

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
export PYTORCH_NPU_ALLOC_CONF=expandable_segments:True

# ==============================================================================
# Task Queue & Timeout Configuration
# ==============================================================================
export TASK_QUEUE_ENABLE=1
export VLIM_RPC_TIMEOUT=3600000
export VLIM_EXECUTE_MODEL_TIMEOUT_SECONDS=30000

# ==============================================================================
# Mooncake & KV Cache Configuration
# ==============================================================================
export MOONCAKE_CONFIG_PATH="/workspace/start-scripts/mooncake.json"
export ACL_OP_INIT_MODE=1

# ==============================================================================
# Device Visibility
# ==============================================================================
export ASCEND_RT_VISIBLE_DEVICES=$1

# ==============================================================================
# VLM Serve Command
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
    --max-num-batched-tokens 384 \
    --max-num-seqs 48 \
    --block-size 32 \
    --no-disable-hybrid-kv-cache-manager \
    --no-enable-prefix-caching \
    --trust-remote-code \
    --gpu-memory-utilization 0.9 \
    --quantization ascend \
    --model-loader-extra-config='{"enable_multithread_load": true, "num_threads": 128}' \
    --tokenizer-mode deepseek_v4 \
    --tool-call-parser deepseek_v4 \
    --enable-auto-tool-choice \
    --reasoning-parser deepseek_v4 \
    --compilation-config '{"cudagraph_mode": "FULL_DECODE_ONLY"}' \
    --kv-transfer-config '{
        "kv_connector": "MultiConnector",
        "kv_role": "kv_consumer",
        "kv_load_failure_policy": "recompute",
        "engine_id": "1",
        "kv_connector_extra_config": {
            "connectors": [
                {
                    "kv_connector": "MooncakeConnectorV1",
                    "kv_role": "kv_consumer",
                    "kv_port": "30100",
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
                    "kv_role": "kv_consumer",
                    "kv_connector_extra_config": {
                        "lookup_rpc_port": "0",
                        "load_async": true,
                        "backend": "mooncake"
                    }
                }
            ]
        }
    }' \
    --additional-config '{
        "ascend_compilation_config": {
            "enable_npugraph_ex": true,
            "enable_static_kernel": false
        },
        "enable_cpu_binding": true,
        "multistream_overlap_shared_expert": true,
        "recompute_scheduler_enable": true
    }' \
    --speculative-config '{"num_speculative_tokens": 7, "method": "dspark", "enforce_eager": true}'