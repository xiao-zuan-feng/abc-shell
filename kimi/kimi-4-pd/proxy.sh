python vllm-ascend/examples/disaggregated_prefill_v1/load_balance_proxy_server_example.py \
    --host 0.0.0.0 \
    --port 8005 \
    --prefiller-hosts 102.34.56.78 \
    --prefiller-port 31025 \
    --decoder-hosts 102.34.56.79 \
    --decoder-ports 1026