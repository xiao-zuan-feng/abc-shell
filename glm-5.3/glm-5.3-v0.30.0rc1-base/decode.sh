export VLLM_EXECUTE_MODEL_TIMEOUT_SECONDS=30000
export HCCL_EXEC_TIMEOUT=1800
export HCCL_CONNECT_TIMEOUT=1800
export ASCEND_TRANSFER_TIMEOUT=10000

local_ip=$8
nic_name=$(ifconfig | grep -B1 "inet.*$local_ip" | head -1 | awk '{print $1}' | sed 's/://')

export VLLM_HOST_IP=$local_ip
export HCCL_IF_IP=$local_ip
export GLOO_SOCKET_IFNAME=$nic_name
export TP_SOCKET_IFNAME=$nic_name
export HCCL_SOCKET_IFNAME=$nic_name

export LD_LIBRARY_PATH=/usr/local/python3.12.13/lib:/usr/local/lib:$LD_LIBRARY_PATH

export HCCL_BUFFSIZE=1024
export HCCL_OP_EXPANSION_MODE="AIV"

export PYTORCH_NPU_ALLOC_CONF=expandable_segments:True
export TASK_QUEUE_ENABLE=1

export VLLM_USE_V2_MODEL_RUNNER=0

export ASCEND_RT_VISIBLE_DEVICES=$1

export PYTHONHASHSEED=0
export ACL_OP_INIT_MODE=1

export ASCEND_LOCAL_COMM_RES='{"version":"1.2"}'

vllm serve /mnt/share/weight/GLM-5.3-w8a8c8 \
    --host 0.0.0.0 \
    --port $2 \
    --data-parallel-size $3 \
    --data-parallel-rank $4 \
    --data-parallel-address $5 \
    --data-parallel-rpc-port $6 \
    --tensor-parallel-size $7 \
    --enable-expert-parallel \
    --enable-chunked-prefill \
    --enable-prefix-caching \
    --seed 1024 \
    --served-model-name glm5 \
    --max-model-len 128000 \
    --max-num-batched-tokens 256 \
    --trust-remote-code \
    --max-num-seqs 64 \
    --gpu-memory-utilization 0.92 \
    --async-scheduling \
    --quantization ascend \
    --safetensors-load-strategy 'prefetch' \
    --enable-auto-tool-choice \
    --tool-call-parser glm47 \
    --reasoning-parser glm47 \
    --kv-cache-dtype int8 \
    --attention_config.indexer_kv_dtype int8 \
    --additional-config '{
        "recompute_scheduler_enable": true
    }' \
    --speculative-config '{"num_speculative_tokens": 5,  "method":"deepseek_mtp","enforce_eager":true}' \
    --compilation-config '{"cudagraph_mode": "FULL_DECODE_ONLY"}' \
    --kv-transfer-config '{
        "kv_connector": "MultiConnector",
        "kv_role": "kv_consumer",
        "kv_port": "30200",
        "engine_id": "0",
        "kv_connector_extra_config": {
            "connectors":[
            {
                "kv_connector": "MooncakeConnectorV2",
                "kv_role": "kv_consumer",
                "kv_port": "30200",
                "kv_connector_extra_config": {
                    "use_ascend_direct": true,
                    "prefill": {"dp_size": 1, "pp_size": 2, "tp_size": 16, "pp_layer_partition": "41,37"},
                    "decode": { "dp_size": 16, "tp_size": 2}
                }
            },
            {
                "kv_connector": "AscendStoreConnector",
                "kv_role": "kv_consumer",
                "kv_connector_extra_config": {
                    "lookup_rpc_port":"0",
                    "backend": "memcache",
                    "use_layerwise": false
                }
            }
            ]
        }
    }'

