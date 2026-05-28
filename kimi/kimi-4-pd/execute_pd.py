import json
import os
import sys
import subprocess
import shutil
import time

def get_ip_list():
    try:
        global_rank_table_path = '/user/global/config/global_rank_table.json'
        with open(global_rank_table_path, 'r') as file:
            buf = file.read()
        rank_table = json.loads(buf)
        ip_list = []
        for server_group in rank_table['server_group_list']:
            server_ip = server_group['server_list'][0]['server_ip']
            ip_list.append(server_ip)
        return ip_list
    except Exception as e:
        print(e)

def get_local_ip():
    local_ip = os.getenv('POD_IP')
    return local_ip

def run_script(node_role, env_vars=None):
    env = os.environ.copy()
    if env_vars:
        env.update(env_vars)
    if node_role == 'prefill_master':
        proxy_path = "/workspace/scripts/proxy.sh"
        os.chmod(proxy_path, 0o755)
        result = subprocess.run([proxy_path, "&"], env=env, capture_output=False, text=True, shell=True)
        if result.returncode != 0:
            print('proxy execute failed')
            return False
        script_path = "/workspace/scripts/prefill_master.sh"
    elif node_role == 'prefill_slave':
        script_path = "/workspace/scripts/prefill_slave.sh"
    elif node_role == 'decode_master':
        script_path = "/workspace/scripts/decode_master.sh"
    else:
        script_path = "/workspace/scripts/decode_slave.sh"
    os.chmod(script_path, 0o755)
    result = subprocess.run([script_path], env=env, capture_output=False, text=True)
    if result.returncode != 0:
        print('run script failed')
        return False
    return True

def check_file_coount():
    target_dir = "/workspace/scripts/checkalready/kimi/"
    ip_list = get_ip_list()
    if len(ip_list) == 0:
        return False, ""
    master_ip = ip_list[0]
    timestamp = int(time.time() * 1000)
    file_name = f"{master_ip}-{timestamp}.txt"
    file_path = os.path.join(target_dir, file_name)
    try:
        os.makedirs(target_dir, exist_ok=True)
    except Exception as e:
        print(f"mkdir for {target_dir} failed")
        return False, file_path

    max_retries = 3
    retry_count = 0
    create_success = False
    while not create_success and retry_count < max_retries:
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                pass
            if os.path.exists(file_path) and os.path.isfile(file_path):
                print(f"create {file_path} succeed")
                create_success = True
            else:
                retry_count += 1
        except Exception as e:
            retry_count += 1
    if not create_success:
        print(f"create {file_path} failed")
        return False, file_path

    while True:
        try:
            file_list = [f for f in os.listdir(target_dir)
                         if os.path.isfile(os.path.join(target_dir, f))
                         and f.startswith(f"{master_ip}-")]
            file_count = len(file_list)
            print(f"current file count: {file_count}")
            if file_count == 4:
                print("current file count is already")
                break
            time.sleep(5)
        except Exception as e:
            print(f"check file count failed: {e}")
            time.sleep(5)
    return True, file_path

def force_remove_dir(target_path):
    if not os.path.exists(target_path):
        return
    try:
        if os.path.isfile(target_path):
            os.unlink(target_path)
    except Exception as e:
        print(f"remove dir: {target_path} failed")

if __name__ == "__main__":
    check_file_count_result, file_path = check_file_coount()
    if not check_file_count_result:
        force_remove_dir(file_path)
        sys.exit(1)
    ip_list = get_ip_list()
    if len(ip_list) != 4:
        print("get ip_list failed, exit")
        force_remove_dir(file_path)
        sys.exit(1)
    local_ip = get_local_ip()
    if not local_ip:
        print("can not get local_ip, exit")
        force_remove_dir(file_path)
        sys.exit(1)

    prefill_master_ip = ip_list[0]
    decode_master_ip = ip_list[2]
    if local_ip == ip_list[0]:
        master_ip = prefill_master_ip
        node_role = 'prefill_master'
    elif local_ip == ip_list[1]:
        master_ip = prefill_master_ip
        node_role = 'prefill_slave'
    elif local_ip == ip_list[2]:
        master_ip = decode_master_ip
        node_role = 'decode_master'
    elif local_ip == ip_list[3]:
        master_ip = decode_master_ip
        node_role = 'decode_slave'
    else:
        print("local ip not in rank_table.json, exit")
        force_remove_dir(file_path)
        sys.exit(1)

    env_vars = {
        'local_ip': local_ip,
        'master_ip': master_ip,
        'node_role': node_role,
        'prefill_master_ip': prefill_master_ip,
        'decode_master_ip': decode_master_ip
    }
    time.sleep(10)
    force_remove_dir(file_path)
    result = run_script(node_role, env_vars)
    if not result:
        sys.exit(1)