import json
import os
import sys
import subprocess
import shutil
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import List, Tuple, Dict, Optional

GLOBAL_RANK_TABLE_PATH = '/user/global/config/global_rank_table.json'
WORKSPACE_SCRIPTS_PATH = '/workspace/scripts'
CHECK_ALREADY_DIR = '/workspace/scripts/checkalready/kimi/'
PROXY_SCRIPT = '/workspace/scripts/proxy.sh'
MOONCAKE_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mooncake.json')
MOONCAKE_MASTER_PORT = 50088

NODE_ROLES = {
    'PREFILL_MASTER': 'prefill_master',
    'PREFILL_SLAVE': 'prefill_slave',
    'DECODE_MASTER': 'decode_master',
    'DECODE_SLAVE': 'decode_slave'
}

SCRIPT_PATHS = {
    'prefill_master': '/workspace/scripts/prefill_master.sh',
    'prefill_slave': '/workspace/scripts/prefill_slave.sh',
    'decode_master': '/workspace/scripts/decode_master.sh',
    'decode_slave': '/workspace/scripts/decode_slave.sh'
}

FILE_PERMISSIONS = 0o755
MAX_RETRIES = 3
EXPECTED_NODE_COUNT = 4
CHECK_FILE_INTERVAL = 5
STARTUP_DELAY = 10
HTTP_SERVER_PORT = 8888

PREFILL_MASTER_INDEX = 0
PREFILL_SLAVE_INDEX = 1
DECODE_MASTER_INDEX = 2
DECODE_SLAVE_INDEX = 3

IS_MOONCAKE_MASTER_ALREADY = False

def update_mooncake_config(master_ip: str) -> bool:
    try:
        with open(MOONCAKE_CONFIG_PATH, 'r') as f:
            config = json.load(f)
        
        config['master_server_address'] = f"{master_ip}:{MOONCAKE_MASTER_PORT}"
        
        with open(MOONCAKE_CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=4)
        
        print(f"Updated mooncake.json master_server_address to {master_ip}:{MOONCAKE_MASTER_PORT}")
        return True
    except Exception as e:
        print(f"Failed to update mooncake.json: {e}")
        return False

class MooncakeMasterHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass
    
    def do_POST(self):
        global IS_MOONCAKE_MASTER_ALREADY
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            self.send_response(400)
            self.end_headers()
            return
        
        post_data = self.rfile.read(content_length)
        try:
            data = json.loads(post_data.decode('utf-8'))
            if isinstance(data, dict) and data.get('is_mooncake_master_already') == True:
                IS_MOONCAKE_MASTER_ALREADY = True
                print("Received mooncake master ready signal")
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"status": "ok"}')
            else:
                self.send_response(400)
                self.end_headers()
        except Exception as e:
            print(f"Failed to parse request: {e}")
            self.send_response(400)
            self.end_headers()

def start_http_server():
    server = HTTPServer(('0.0.0.0', HTTP_SERVER_PORT), MooncakeMasterHandler)
    server.serve_forever()

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
        print(e)
        return None

def get_local_ip() -> Optional[str]:
    local_ip = os.getenv('POD_IP')
    return local_ip

def run_script(node_role: str, env_vars: Optional[Dict[str, str]] = None) -> bool:
    env = os.environ.copy()
    if env_vars:
        env.update(env_vars)
    
    if node_role == NODE_ROLES['PREFILL_MASTER']:
        os.chmod(PROXY_SCRIPT, FILE_PERMISSIONS)
        result = subprocess.run([PROXY_SCRIPT, "&"], env=env, capture_output=False, text=True, shell=True)
        if result.returncode != 0:
            print('proxy execute failed')
            return False
    
    script_path = SCRIPT_PATHS.get(node_role)
    if not script_path:
        print(f'invalid node_role: {node_role}')
        return False
    
    os.chmod(script_path, FILE_PERMISSIONS)
    result = subprocess.run([script_path], env=env, capture_output=False, text=True)
    if result.returncode != 0:
        print('run script failed')
        return False
    return True

def check_file_count() -> Tuple[bool, str]:
    ip_list = get_ip_list()
    if not ip_list or len(ip_list) == 0:
        return False, ""
    
    master_ip = ip_list[PREFILL_MASTER_INDEX]
    timestamp = int(time.time() * 1000)
    file_name = f"{master_ip}-{timestamp}.txt"
    file_path = os.path.join(CHECK_ALREADY_DIR, file_name)
    
    try:
        os.makedirs(CHECK_ALREADY_DIR, exist_ok=True)
    except Exception as e:
        print(f"mkdir for {CHECK_ALREADY_DIR} failed")
        return False, file_path

    create_success = False
    for retry_count in range(MAX_RETRIES):
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                pass
            if os.path.exists(file_path) and os.path.isfile(file_path):
                print(f"create {file_path} succeed")
                create_success = True
                break
        except Exception as e:
            print(f"create file attempt {retry_count + 1} failed: {e}")
    
    if not create_success:
        print(f"create {file_path} failed after {MAX_RETRIES} retries")
        return False, file_path

    while True:
        try:
            file_list = [f for f in os.listdir(CHECK_ALREADY_DIR)
                        if os.path.isfile(os.path.join(CHECK_ALREADY_DIR, f))
                        and f.startswith(f"{master_ip}-")]
            file_count = len(file_list)
            print(f"current file count: {file_count}")
            if file_count == EXPECTED_NODE_COUNT:
                print("current file count is already")
                break
            time.sleep(CHECK_FILE_INTERVAL)
        except Exception as e:
            print(f"check file count failed: {e}")
            time.sleep(CHECK_FILE_INTERVAL)
    
    return True, file_path

def force_remove_file(target_path: str) -> None:
    if not os.path.exists(target_path):
        return
    try:
        if os.path.isfile(target_path):
            os.unlink(target_path)
    except Exception as e:
        print(f"remove file: {target_path} failed: {e}")

def determine_node_role(local_ip: str, ip_list: List[str]) -> Tuple[Optional[str], Optional[str]]:
    if local_ip == ip_list[PREFILL_MASTER_INDEX]:
        return ip_list[PREFILL_MASTER_INDEX], NODE_ROLES['PREFILL_MASTER']
    elif local_ip == ip_list[PREFILL_SLAVE_INDEX]:
        return ip_list[PREFILL_MASTER_INDEX], NODE_ROLES['PREFILL_SLAVE']
    elif local_ip == ip_list[DECODE_MASTER_INDEX]:
        return ip_list[DECODE_MASTER_INDEX], NODE_ROLES['DECODE_MASTER']
    elif local_ip == ip_list[DECODE_SLAVE_INDEX]:
        return ip_list[DECODE_MASTER_INDEX], NODE_ROLES['DECODE_SLAVE']
    return None, None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python execute_pd.py <mooncake_master_ip>")
        sys.exit(1)
    
    mooncake_master_ip = sys.argv[1]
    if not update_mooncake_config(mooncake_master_ip):
        print("Failed to update mooncake config, exit")
        sys.exit(1)
    
    # http_server_thread = threading.Thread(target=start_http_server, daemon=True)
    # http_server_thread.start()
    # print(f"HTTP server started on port {HTTP_SERVER_PORT}")
    
    check_file_count_result, file_path = check_file_count()
    if not check_file_count_result:
        force_remove_file(file_path)
        sys.exit(1)
    
    ip_list = get_ip_list()
    if not ip_list or len(ip_list) != EXPECTED_NODE_COUNT:
        print("get ip_list failed, exit")
        force_remove_file(file_path)
        sys.exit(1)
    
    local_ip = get_local_ip()
    if not local_ip:
        print("can not get local_ip, exit")
        force_remove_file(file_path)
        sys.exit(1)

    master_ip, node_role = determine_node_role(local_ip, ip_list)
    if not master_ip or not node_role:
        print("local ip not in rank_table.json, exit")
        force_remove_file(file_path)
        sys.exit(1)

    env_vars = {
        'local_ip': local_ip,
        'master_ip': master_ip,
        'node_role': node_role,
        'prefill_master_ip': ip_list[PREFILL_MASTER_INDEX],
        'decode_master_ip': ip_list[DECODE_MASTER_INDEX]
    }
    
    time.sleep(STARTUP_DELAY)
    force_remove_file(file_path)
    result = run_script(node_role, env_vars)
    if not result:
        sys.exit(1)