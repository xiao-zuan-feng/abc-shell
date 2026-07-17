#!/usr/bin/env python3
"""
extract_all_benchmarks.py - 从 vLLM bench serve 日志中提取多条测试记录的性能指标

用法：
    python extract_all_benchmarks.py test.log
    python extract_all_benchmarks.py test.log >> daily_report.csv
    cat test.log | python extract_all_benchmarks.py
"""

import re
import sys
import csv
from io import StringIO

# 字段顺序（CSV 列名）
FIELD_NAMES = [
    'input_len', 'output_len', 'concurrency',
    'Mean_TTFT_ms', 'Mean_TPOT_ms', 'Output_Throughput_tok_s'
]

def parse_records(text):
    """
    解析文本，返回字典列表，每个字典代表一条测试记录。
    识别逻辑：
      - 每遇到 "Testing:" 行开始一个新记录，记录 input_len 和 concurrency
      - 随后遇到 "Sampling input_len from ... output_len from [" 行，记录 output_len
      - 遇到 "Serving Benchmark Result" 后，在随后的行中提取 TTFT、TPOT、Output throughput
      - 遇到下一个 "Testing:" 或文件结束则完成当前记录
    """
    records = []
    current = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]

        # 检测新测试的开始
        m_test = re.search(r'Testing:\s*input_len=(\d+),\s*concurrency=(\d+)', line)
        if m_test:
            # 如果当前有未完成的记录，先保存（可能因缺少字段而被丢弃）
            if current and all(k in current for k in FIELD_NAMES[:3]):
                # 但此时可能还没有 TTFT 等字段，所以暂不保存，等待后面的结果
                pass
            # 重置当前记录
            current = {
                'input_len': int(m_test.group(1)),
                'concurrency': int(m_test.group(2))
            }
            i += 1
            continue

        # 如果已经有 input_len，尝试捕获 output_len
        if 'input_len' in current and 'output_len' not in current:
            m_out = re.search(r'Sampling input_len from \[\d+, \d+\] and output_len from \[(\d+), \d+\]', line)
            if m_out:
                current['output_len'] = int(m_out.group(1))
                i += 1
                continue

        # 检测 Serving Benchmark Result 区域
        if 'Serving Benchmark Result' in line:
            # 从下一行开始，扫描直到遇到空行或下一个 Testing: 或文件结束
            j = i + 1
            while j < len(lines) and not lines[j].startswith('Testing:'):
                sub_line = lines[j].strip()
                # 提取 Mean TTFT
                m_ttft = re.search(r'Mean TTFT \(ms\):\s+([\d.]+)', sub_line)
                if m_ttft:
                    current['Mean_TTFT_ms'] = float(m_ttft.group(1))
                # 提取 Mean TPOT
                m_tpot = re.search(r'Mean TPOT \(ms\):\s+([\d.]+)', sub_line)
                if m_tpot:
                    current['Mean_TPOT_ms'] = float(m_tpot.group(1))
                # 提取 Output token throughput
                m_out_tp = re.search(r'Output token throughput \(tok/s\):\s+([\d.]+)', sub_line)
                if m_out_tp:
                    current['Output_Throughput_tok_s'] = float(m_out_tp.group(1))
                j += 1
            # 检查当前记录是否完整
            required = ['input_len', 'output_len', 'concurrency',
                        'Mean_TTFT_ms', 'Mean_TPOT_ms', 'Output_Throughput_tok_s']
            if all(k in current for k in required):
                records.append(dict(current))
            else:
                missing = [k for k in required if k not in current]
                print(f"[警告] 跳过不完整记录 (缺失: {missing})", file=sys.stderr)
            # 重置当前记录，准备下一个
            current = {}
            i = j  # 跳到下一个 Testing: 或末尾
            continue

        i += 1

    # 处理最后一条可能的记录（如果文件不以 Testing: 结束）
    if current and all(k in current for k in ['input_len', 'concurrency']):
        # 这种情况很少见，一般不会有 TTFT 等字段，忽略
        pass

    return records


def main():
    # 读取输入（文件或 stdin）
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r') as f:
            content = f.read()
    else:
        content = sys.stdin.read()

    records = parse_records(content)

    if not records:
        print("未找到任何完整的测试记录。", file=sys.stderr)
        sys.exit(1)

    # 输出 CSV 到 stdout
    writer = csv.DictWriter(sys.stdout, fieldnames=FIELD_NAMES, extrasaction='ignore')
    writer.writeheader()
    for rec in records:
        writer.writerow(rec)


if __name__ == '__main__':
    main()