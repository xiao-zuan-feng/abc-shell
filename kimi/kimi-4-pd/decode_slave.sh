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
export HCCL_EXEC_TIMEOUT=204
# 网络配置
export HCCL_IF_IP=$local_ip
nic_name="eth0"
 
export GLOO_SOCKET_IFNAME=$nic_name
export TP_SOCKET_IFNAME=$nic_name
export HCCL_SOCKET_IFNAME=$nic_name
 
export LD_PRELOAD=/usr/lib/aarch64-linux-gnu/libjemalloc.so.2:$LD_PRELOAD
#export LD_PRELOAD="/usr/lib/aarch64-linux-gnu/libjemalloc.so.2${LD_PRELOAD:+:$LD_PRELOAD}"
export OMP_PROC_BIND=false
export OMP_NUM_THREADS=10
export PYTORCH_NPU_ALLOC_CONF=expandable_segments:True
export HCCL_BUFFSIZE=1100
export TASK_QUEUE_ENABLE=1
export HCCL_OP_EXPANSION_MODE="AIV"
export VLLM_USE_V1=1
export VLLM_VERSION=0.17.0
export ASCEND_RT_VISIBLE_DEVICES=0,1,2,3,4,5,6,7
export ASCEND_BUFFER_POOL=4:8
export LD_LIBRARY_PATH=/usr/local/Ascend/ascend-toolkit/latest/python/site-packages/mooncake:$LD_LIBRARY_PATH
 
 
# D节点开启MLAPO
export VLLM_ASCEND_ENABLE_MLAPO=1
export HCCL_INTRA_ROCE_ENABLE=1
export VLLM_NIXL_ABORT_REQUEST_TIMEOUT=600
 
vllm serve /workspace/model \
    --host 0.0.0.0 \
    --port 31026 \
    --data-parallel-size 8 \
    --data-parallel-address $master_ip \
    --data-parallel-rpc-port 2379 \
    --data-parallel-size-local 4 \
    --data-parallel-start-rank 4 \
    --tensor-parallel-size 2 \
    --enable-expert-parallel \
    --seed 1024 \
    --quantization ascend \
    --served-model-name kimi_k2.5 \
   --tool-call-parser kimi_k2 \
   --reasoning-parser kimi_k2 \
   --enable-auto-tool-choice \
   --chat-template /workspace/model/chat-template.jinja \
    --trust-remote-code \
    --max-num-seqs 16 \
    --max-model-len 133120 \
    --max-num-batched-tokens 64 \
    --gpu-memory-utilization 0.90 \
    --async-scheduling \
    --mm-processor-cache-gb 0 \
    --mm-encoder-tp-mode data \
    --compilation-config '{"cudagraph_mode": "FULL_DECODE_ONLY", "cudagraph_capture_sizes":[1,2,4,8,12,16]}' \
    --additional-config '{"recompute_scheduler_enable":true}' \
    --headless \
    --kv-transfer-config \
    '{"kv_connector": "MooncakeConnectorV1",
    "kv_role": "kv_consumer",
    "kv_port": "30100",
    "engine_id": "1",
    "kv_connector_module_path": "vllm_ascend.distributed.mooncake_connector",
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
    }' 