import sys
import requests
import socket
import logging
import json
import os

logging.basicConfig(
    format='%(asctime)s [%(levelname)s][%(filename)s:%(lineno)d] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=logging.INFO,
    filename='/workspace/scripts/health_check_probe.log',
    filemode='a'
)

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

if __name__ == "__main__":
    local_ip = get_local_ip()
    ip_list = get_ip_list()
    hostname = socket.gethostname()

    if local_ip != ip_list[0]:
        logging.debug(f"node {hostname} is not head, do not need probe")
        sys.exit(0)

    api_url = f"http://{local_ip}:8005/v1/chat/completions"
    headers = {
        'Content-Type': 'application/json',
    }
    request_data = {
        "model": "kimi_k2.5",
        "messages": [{"role": "user", "content": "hello"}],
        "stream": False,
        "max_tokens": 5,
        "temperature": 0.6
    }

    try:
        response = requests.post(
            api_url,
            json=request_data,
            headers=headers,
            stream=False,
            timeout=1200
        )
    except Exception as e:
        logging.error(f"requests.post failed, Exception: {e}")
        sys.exit(1)

    if response.status_code != 200:
        logging.error(f"response error, status_code: {response.status_code}, text: {response.text}")
        sys.exit(1)

    try:
        response_info = json.loads(response.text)
        if len(response_info['choices'][0]['message']['reasoning']) == 0:
            logging.error("response reasoning len is 0")
            sys.exit(1)
    except Exception as e:
        logging.error(f"json parse failed, text: {response.text}, Exception: {e}")
        sys.exit(1)

    logging.info(f"health check success, response: {response.text}")