import json
import os
import sys
import time
import subprocess
import threading
import requests
import fcntl
from typing import List, Optional

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
LOCK_FILE_PATH = '/workspace/scripts/checkalready/kimi/mooncake_master.lock'
LOCK_FILE_DIR = '/workspace/scripts/checkalready/kimi/'

mooncake_master_process: Optional[subprocess.Popen] = None
health_check_fail_count = 0
has_notified = False
lock_file = None

def acquire_lock() -> bool:
    global lock_file
    try:
        os.makedirs(LOCK_FILE_DIR, exist_ok=True)
        lock_file = open(LOCK_FILE_PATH, 'w')
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except (IOError, OSError):
        if lock_file:
            lock_file.close()
            lock_file = None
        return False

def release_lock():
    global lock_file
    if lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()
            lock_file = None
        except Exception:
            pass

def get_ip_list() -> Optional[List[str]]:
    try:
        with open(GLOBAL_RANK_TABLE_PATH, 'r') as file:
            buf = file.read()
        rank_table = json.loads(buf)
        ip_list = []
        for server_group in rank_table['server_group_list']:
            server_info = server_group['server_list'][0]
            if 'device' in server_info:
                server_ip = server_info['server_ip']
                ip_list.append(server_ip)
        return ip_list
    except Exception as e:
        print(f"get_ip_list failed: {e}")
        return None

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

def send_notification(ip: str) -> bool:
    try:
        url = f"http://{ip}:{HTTP_SERVER_PORT}"
        payload = {"is_mooncake_master_already": True}
        headers = {"Content-Type": "application/json"}
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"Failed to notify {ip}: {e}")
        return False

def notify_node_loop(ip: str):
    while True:
        if send_notification(ip):
            print(f"Successfully notified {ip}")
            break
        print(f"Failed to notify {ip}, retrying in {NOTIFY_RETRY_INTERVAL}s...")
        time.sleep(NOTIFY_RETRY_INTERVAL)

def notify_nodes_async(ip_list: List[str]):
    for ip in ip_list:
        thread = threading.Thread(target=notify_node_loop, args=(ip,), daemon=True)
        thread.start()

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
    global health_check_fail_count, has_notified
    
    time.sleep(5)
    
    while True:
        if check_health():
            health_check_fail_count = 0
            print("Health check passed")
            
            if not has_notified:
                has_notified = True
                ip_list = get_ip_list()
                if ip_list:
                    print(f"Notifying nodes: {ip_list}")
                    notify_nodes_async(ip_list)
                else:
                    print("Failed to get ip_list for notification")
        else:
            health_check_fail_count += 1
            print(f"Health check failed (count: {health_check_fail_count})")
            
            if health_check_fail_count >= HEALTH_CHECK_MAX_FAILURES:
                print(f"Health check failed {HEALTH_CHECK_MAX_FAILURES} times, restarting...")
                restart_mooncake_master()
        
        time.sleep(HEALTH_CHECK_INTERVAL)

if __name__ == "__main__":
    if not acquire_lock():
        print("Another instance is already running, exiting")
        sys.exit(0)
    
    print("Lock acquired, starting mooncake_master...")
    
    process = start_mooncake_master()
    if not process:
        print("Failed to start mooncake_master, exiting")
        release_lock()
        sys.exit(1)
    
    try:
        health_check_loop()
    except KeyboardInterrupt:
        print("Received interrupt signal, shutting down...")
    finally:
        if mooncake_master_process and mooncake_master_process.poll() is None:
            mooncake_master_process.terminate()
            mooncake_master_process.wait()
        release_lock()
        sys.exit(0)