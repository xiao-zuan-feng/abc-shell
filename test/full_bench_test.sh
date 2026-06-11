# 测试背景
为了摸测模型在不同输入和不同并发条件下的极限性能而开发的自动化测试脚本，本脚本从16k输入起测，步长16k，最大输入96k；并发从4并发起，步长为4，
最大长度1000，但是约束了如果平均ttft超过60s则跳到下一轮输入开始测。
# 测试参考脚本
```shell
#!/bin/bash
set -euo pipefail

# ====================== 核心配置 ======================
INPUT_LEN_START=16384
INPUT_LEN_STEP=16384
INPUT_LEN_MAX=98304

CONCUR_START=4
CONCUR_STEP=4
CONCUR_MAX=1000

TTFT_LIMIT=60000  # TTFT超过这个值就熔断

MODEL_PATH="/workspace/model"
BASE_URL="http://localhost:8005"
SERVED_MODEL="kimi_k2.5"
OUTPUT_LEN=2048
SLEEP_INTERVAL=30

# 全局唯一结果文件
RESULT_TXT="./benchmark_all_results.txt"
# ======================================================

echo -e "\n========== 开始 vLLM 全自动压测 =========="
echo "📄 所有结果将保存到：$RESULT_TXT"
echo "⏱ 熔断阈值：Mean TTFT > ${TTFT_LIMIT}ms"

# 遍历输入长度
for input_len in $(seq $INPUT_LEN_START $INPUT_LEN_STEP $INPUT_LEN_MAX); do
    echo -e "\n=================================================="
    echo "📏 当前测试输入长度：$input_len tokens"
    echo "=================================================="

    # 熔断标记
    continue_bench=true

    # 遍历并发数
    for c in $(seq $CONCUR_START $CONCUR_STEP $CONCUR_MAX); do
        if [ "$continue_bench" = false ]; then
            break
        fi

        p=$((c * 4))
        echo -e "\n🚀 测试：输入长度=$input_len, 并发=$c, prompts=$p"

        # 执行 vllm bench，捕获全部输出
        output=$(vllm bench serve \
            --backend openai-chat \
            --model "$MODEL_PATH" \
            --base-url "$BASE_URL" \
            --endpoint /v1/chat/completions \
            --num-prompts $p \
            --trust-remote-code \
            --dataset-name random \
            --ignore-eos \
            --seed 100 \
            --served-model-name "$SERVED_MODEL" \
            --random-input-len $input_len \
            --random-output-len $OUTPUT_LEN \
            --max_concurrency $c 2>&1)

        # 屏幕打印输出
        echo "$output"

        # ====================== 写入全局 TXT ======================
        echo -e "\n\n========================================" >> "$RESULT_TXT"
        echo "测试时间：$(date '+%Y-%m-%d %H:%M:%S')" >> "$RESULT_TXT"
        echo "输入长度：$input_len tokens" >> "$RESULT_TXT"
        echo "并发数：$c" >> "$RESULT_TXT"
        echo "Prompt数：$p" >> "$RESULT_TXT"
        echo -e "========================================\n" >> "$RESULT_TXT"
        echo "$output" >> "$RESULT_TXT"

        # ====================== 【万能】提取 TTFT ======================
        # 支持：Mean TTFT (ms): 后面 任意个空格、tab，都能提取数字
        ttft_ms=$(echo "$output" | grep -i 'Mean TTFT (ms):' | awk -F ':' '{gsub(/^[ \t]+/,"",$2); print $2}' | tail -n1)

        # 判断是否拿到值
        if [ -z "$ttft_ms" ] || [ "$ttft_ms" = "0" ]; then
            echo "⚠️  未获取到 TTFT，跳过当前长度"
            continue_bench=false
            continue
        fi

        echo "✅ Mean TTFT：$ttft_ms ms"

        # 熔断判断
        if (( $(echo "$ttft_ms > $TTFT_LIMIT" | bc -l) )); then
            echo "❌ TTFT 超过 ${TTFT_LIMIT}ms，切换下一个输入长度！"
            continue_bench=false
        fi

        sleep $SLEEP_INTERVAL
    done
done

echo -e "\n🎉 所有测试完成！结果保存在：$RESULT_TXT"
```