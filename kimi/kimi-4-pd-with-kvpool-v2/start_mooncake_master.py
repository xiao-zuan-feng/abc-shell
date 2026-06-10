import json
import os
import sys
import time
import subprocess
import threading
import requests
import fcntl
from typing import List, Optional

# mooncake_master启动需要libascend_hal.so, 从ma创建的纯cpu容器只有/usr/local/Ascend/cann-8.5.1/aarch64-linux/lib64/device/lib64下有
# 需要注意的是不同的镜像该路径可能不一样。
LD_LIBRARY_PATH = '/usr/local/Ascend/ascend-toolkit/latest/aarch64-linux/lib64:/usr/local/lib:/usr/local/Ascend/cann-8.5.1/aarch64-linux/lib64/device/lib64'

MOONCAKE_MASTER_CMD = "mooncake_master"
MOONCAKE_MASTER_PORT = 50088
METRICS_PORT = 9003
MOONCAKE_MASTER_ARGS = [
    "--port", str(MOONCAKE_MASTER_PORT),
    "--eviction_high_watermark_ratio", "0.9",
    "--eviction_ratio", "0.1",
    "--default_kv_lease_ttl", "11000"
]
HEALTH_CHECK_INTERVAL = 10
HEALTH_CHECK_MAX_FAILURES = 3
NOTIFY_RETRY_INTERVAL = 10
GLOBAL_RANK_TABLE_PATH = '/user/global/config/global_rank_table.json'
HTTP_SERVER_PORT = 8888

mooncake_master_process: Optional[subprocess.Popen] = None
health_check_fail_count = 0

def start_mooncake_master() -> Optional[subprocess.Popen]:
    global mooncake_master_process
    try:
        print(f"Starting mooncake_master with args: {MOONCAKE_MASTER_ARGS}")
        env = os.environ.copy()
        env['LD_LIBRARY_PATH'] = LD_LIBRARY_PATH + ':' + env.get('LD_LIBRARY_PATH', '')
        process = subprocess.Popen([MOONCAKE_MASTER_CMD] + MOONCAKE_MASTER_ARGS, env=env)
        mooncake_master_process = process
        print(f"mooncake_master started with PID: {process.pid}")
        return process
    except Exception as e:
        print(f"Failed to start mooncake_master: {e}")
        return None

def check_health() -> bool:
    global mooncake_master_process
    
    if mooncake_master_process is None or mooncake_master_process.poll() is not None:
        print("mooncake_master process is not running")
        return False
    
    try:
        health_url = f"http://localhost:{METRICS_PORT}/health"
        response = requests.get(health_url, timeout=5)
        return response.status_code == 200
    except Exception as e:
        print(f"Health check failed: {e}")
        return False

def restart_mooncake_master():
    global mooncake_master_process, health_check_fail_count
    
    if mooncake_master_process and mooncake_master_process.poll() is None:
        print("Terminating existing mooncake_master process...")
        mooncake_master_process.terminate()
        try:
            mooncake_master_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            mooncake_master_process.kill()
    
    print("Restarting mooncake_master...")
    health_check_fail_count = 0
    start_mooncake_master()

def health_check_loop():
    global health_check_fail_count
    
    time.sleep(5)
    
    while True:
        if check_health():
            health_check_fail_count = 0
            print("Health check passed")
        else:
            health_check_fail_count += 1
            print(f"Health check failed (count: {health_check_fail_count})")
            
            if health_check_fail_count >= HEALTH_CHECK_MAX_FAILURES:
                print(f"Health check failed {HEALTH_CHECK_MAX_FAILURES} times, restarting...")
                restart_mooncake_master()
        
        time.sleep(HEALTH_CHECK_INTERVAL)

if __name__ == "__main__":
    process = start_mooncake_master()
    if not process:
        print("Failed to start mooncake_master, exiting")
        sys.exit(1)
    
    try:
        health_check_loop()
    except KeyboardInterrupt:
        print("Received interrupt signal, shutting down...")
    finally:
        if mooncake_master_process and mooncake_master_process.poll() is None:
            mooncake_master_process.terminate()
            mooncake_master_process.wait()
        sys.exit(0)