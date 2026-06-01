#!/usr/bin/env bash
set -euo pipefail
 
unset ftp_proxy
unset https_proxy
unset http_proxy
rm -rf ~/ascend/log
 
#echo performance | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
#sysctl -w vm.swappiness=0
#sysctl -w kernel.numa_balancing=0
#sysctl kernel.sched_migration_cost_ns=50000
 
export VLLM_RPC_TIMEOUT=3600000
export VLLM_EXECUTE_MODEL_TIMEOUT_SECONDS=30000
export HCCL_CONNECT_TIMEOUT=500
 
# 网络配置
export HCCL_IF_IP=$local_ip
nic_name="eth0"
 
export GLOO_SOCKET_IFNAME=$nic_name
export TP_SOCKET_IFNAME=$nic_name
export HCCL_SOCKET_IFNAME=$nic_name
 
#export LD_PRELOAD=/usr/lib/aarch64-linux-gnu/libjemalloc.so.2:$LD_PRELOAD
#export LD_PRELOAD="/usr/lib/aarch64-linux-gnu/libjemalloc.so.2${LD_PRELOAD:+:$LD_PRELOAD}"
export HCCL_OP_EXPANSION_MODE="AIV"
export TASK_QUEUE_ENABLE=1
export ASCEND_BUFFER_POOL=4:8
export OMP_PROC_BIND=false
export OMP_NUM_THREADS=1
export PYTORCH_NPU_ALLOC_CONF="expandable_segments:True"
export VLLM_USE_V1=1
export VLLM_VERSION=0.17.0
 
export LD_LIBRARY_PATH=/usr/local/Ascend/ascend-toolkit/latest/python/site-packages/mooncake:$LD_LIBRARY_PATH
export LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH
 
export HCCL_BUFFSIZE=1024
 
export ASCEND_RT_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
 
# P节点开启FLASHCOMM1
export VLLM_ASCEND_ENABLE_FLASHCOMM1=1
export HCCL_INTRA_ROCE_ENABLE=1
export VLLM_NIXL_ABORT_REQUEST_TIMEOUT=600

# kvpool
export PYTHONHASHSEED=0
export MOONCAKE_CONFIG_PATH="/workspace/scripts/kimi-kvpool/mooncake.json"
export ACL_OP_INIT_MODE=1
export HCCL_RDMA_TIMEOUT=17
export ASCEND_CONNECT_TIMEOUT=10000
export ASCEND_TRANSFER_TIMEOUT=10000
 
vllm serve /workspace/model \
    --host 0.0.0.0 \
    --port 31025 \
    --data-parallel-size 2 \
    --data-parallel-address $master_ip \
    --data-parallel-rpc-port 2377 \
    --data-parallel-size-local 1 \
    --data-parallel-start-rank 0 \
    --tensor-parallel-size 8 \
    --enable-expert-parallel \
    --seed 1024 \
    --quantization ascend \
   --tool-call-parser kimi_k2 \
   --reasoning-parser kimi_k2 \
   --enable-auto-tool-choice \
   --chat-template /workspace/model/chat-template.jinja \
    --served-model-name kimi_k2.5 \
    --trust-remote-code \
    --max-num-seqs 16 \
    --max-model-len 133120 \
    --max-num-batched-tokens 8192 \
    --gpu-memory-utilization 0.9 \
    --enforce-eager \
   --enable-prefix-caching \
   --enable-chunked-prefill \
    --kv-transfer-config \
    '{
    "kv_connector": "MultiConnector",
    "kv_role": "kv_producer",
    "engine_id": "0",
    "kv_connector_module_path": "vllm_ascend.distributed.mooncake_connector",
    "kv_connector_extra_config": {
        "connectors": [
            {
                "kv_connector": "MooncakeConnectorV1",
                "kv_role": "kv_producer",
                "kv_port": "30000",
                "kv_connector_extra_config": {
                    "prefill": {
                        "dp_size": 2,
                        "tp_size": 8
                    },
                    "decode": {
                        "dp_size": 8,
                        "tp_size": 2
                    }
                }
            },
            {
                "kv_connector": "AscendStoreConnector",
                "kv_role": "kv_producer",
                "kv_connector_extra_config": {
                    "lookup_rpc_port":"0",
                    "backend": "mooncake"
                }
            }
        ]
    }
    }'