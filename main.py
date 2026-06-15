import os
import json
import re
import socket
from urllib import request
from sys import prefix
from dotenv import load_dotenv
import threading
import subprocess
import platform
import uuid
import time
from logging_site import RealtimeLogger
import requests

def main():
    # =========================================
    # CONFIG SERVER (Cloudflare Tunnel)
    # =========================================
    START_TIME = int(time.time())
    def get_public_url():
        # Get ip via ipify
        try:
            ip = requests.get("https://api.ipify.org").text
            return ip
        except Exception as e:
            print(f"[!] Failed to get public IP: {e}")
            return "0.0.0.0"

    def init_env_file():
        env_path = ".env"
        default_configs = {
            "PORT": "8888",
            "XRAY_UUID": str(uuid.uuid4()),
            "FAKE_SNI": "api24-normal-alisg.tiktokv.com",
            "WS_PATH": "/tiktok4g"
        }

        if not os.path.exists(env_path):
            print("[*] File .env does not exist. Using default configuration...")
            with open(env_path, "w", encoding="utf-8") as f:
                for key, value in default_configs.items():
                    f.write(f"{key}={value}\n")
            print("[+] Generated .env configuration.")
        else:
            print("[*] Found .env configuration.")

    init_env_file()
    load_dotenv()

    PORT = int(os.getenv("PORT", 8888))
    UUID = os.getenv("XRAY_UUID", str(uuid.uuid4()))
    FAKE_SNI = os.getenv("FAKE_SNI", "link.e.tiktok.com")
    WS_PATH = os.getenv("WS_PATH", "/tiktok4g")

    if not WS_PATH.startswith("/"):
        WS_PATH = "/" + WS_PATH

    XRAY_BIN = "./xray.exe" if platform.system().lower() == "windows" else "./xray"
    CLF_BIN = "./cloudflared.exe" if platform.system().lower() == "windows" else "./cloudflared"

    if not os.path.exists(XRAY_BIN):
        print(f"[ERROR] Unable to find xray path: {XRAY_BIN}")
        return
    if not os.path.exists(CLF_BIN):
        print(f"[ERROR] Unable to find Cloudflared path: {CLF_BIN}")
        return

    # =========================================
    # VLESS-WS
    # =========================================
    def write_configs():
        xray_config = {
            "log": {
                "loglevel": "warning"
            },
            "inbounds": [
                {
                    "port": PORT,
                    "listen": "0.0.0.0",
                    "protocol": "vless",
                    "settings": {
                        "clients": [
                            {
                                "id": UUID,
                                "level": 0
                            }
                        ],
                        "decryption": "none"
                    },
                    "streamSettings": {
                        "network": "ws",
                        "security": "none",
                        "wsSettings": {
                            "path": WS_PATH,
                            "headers": {}
                        }
                    }
                }
            ],
            "outbounds": [
                {
                    "protocol": "freedom",
                    "settings": {}
                }
            ]
        }
        if os.path.exists("config.json"):
            try: os.remove("config.json")
            except: pass
            
        with open("config.json", "w", encoding="utf-8") as f: 
            json.dump(xray_config, f, indent=2)

    write_configs()

    print(f"[*] Launching XRAY at {PORT}...")
    xp = subprocess.Popen(
        [XRAY_BIN, "run", "-c", "config.json"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        errors='replace'
    )

    print("[*] Launching Cloudflare Tunnel at (TryCloudflare)...")
    clp = subprocess.Popen(
        [CLF_BIN, "tunnel", "--url", f"http://127.0.0.1:{PORT}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        errors='replace'
    )

    cloudflare_url = None
    
    try:
        logger = RealtimeLogger(port=9999, password=None)
        logger_url = logger.start()
        print(f"[*] Logger Web UI is running at: {logger_url}")
    except Exception:
        logger = None

    def monitor_xray(pipe):
        try:
            with pipe:
                for line in iter(pipe.readline, ''):
                    # print(f"[XRAY CRITICAL LOG] -> {line.strip()}")
                    if logger:
                        logger.push_log(line.strip(), "XRAY")
        except Exception:
            pass

    def monitor_cloudflare(pipe):
        nonlocal cloudflare_url
        ansi_escape = re.compile(r'\x1b\[[0-9;]*[mK]')
        try:
            with pipe:
                for line in iter(pipe.readline, ''):
                    clean_line = ansi_escape.sub('', line)
                    print(f"[CLOUDFLARE LOG] {clean_line.strip()}")
                    
                    match = re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', clean_line)
                    if match and not cloudflare_url:
                        cloudflare_url = match.group(0).replace("https://", "")
                        print_vless_links(cloudflare_url, UUID, FAKE_SNI, WS_PATH)
        except Exception:
            pass

    threading.Thread(target=monitor_xray, args=(xp.stdout,), daemon=True).start()
    threading.Thread(target=monitor_cloudflare, args=(clp.stdout,), daemon=True).start()

    def print_vless_links(tunnel_host, uuid_str, fake_sni, ws_path):
        import urllib.parse
        encoded_path = urllib.parse.quote(ws_path, safe='')
        
        vless_tls = f"vless://{uuid_str}@{fake_sni}:443?type=ws&encryption=none&security=tls&path={encoded_path}&host={tunnel_host}&sni={tunnel_host}#Cloudflare%20TLS"
        vless_http = f"vless://{uuid_str}@{fake_sni}:80?type=ws&encryption=none&security=&path={encoded_path}&host={tunnel_host}#Cloudflare%20HTTP"

        print("\n" + "="*70)
        print(" CONNECTED TO CLOUDFLARE TUNNEL")
        print("="*70)
        # print(f"[+] Port 443 (TLS): \n    {vless_tls}\n")
        # print(f"[+] Port 80 (No TLS): \n    {vless_http}\n")
        print("="*70 + "\n")

        with open("frp_info.config", "w", encoding='utf-8') as f:
            f.write(vless_tls + "\n" + vless_http)
            print("Written to frp_info.config")
        
        frp_info = {
            "payloads": [vless_tls, vless_http],
            "ip": get_public_url(),
            "start_time": START_TIME,
        }

        with open("frp_info.json", "w", encoding='utf-8') as f:
            json.dump(frp_info, f, indent=4)
            print("Written to frp_info.json")

    try:
        while True:
            if xp.poll() is not None:
                print(f"\n[!] CẢNH BÁO: Tiến trình XRAY đã tự động dừng (Mã thoát: {xp.poll()}).")
                print("[!] Vui lòng đọc dòng [XRAY CRITICAL LOG] ở ngay phía trên để biết lý do chính xác.")
                break
            if clp.poll() is not None:
                print(f"\n[!] CẢNH BÁO: Tiến trình CLOUDFLARED đã tự động dừng (Mã thoát: {clp.poll()}).")
                break
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n[*] Đang dừng các dịch vụ...")
    finally:
        try: xp.terminate()
        except: pass
        try: clp.terminate()
        except: pass

if __name__ == "__main__":
    main()