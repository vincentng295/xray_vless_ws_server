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
import importlib

xray_downloader = importlib.import_module("download-xray")
cloudflared_downloader = importlib.import_module("download-cloudflared")
wgcf_downloader = importlib.import_module("download-wgcf")

def main():
    # =========================================
    # CONFIG SERVER (Cloudflare Tunnel)
    # =========================================
    default_configs = {
        "PORT": "127.0.0.1:8888",
        "XRAY_UUID": str(uuid.uuid4()),
        "FAKE_SNI": "api24-normal-alisg.tiktokv.com,api24-normal-useast1a.tiktokv.com",
        "WS_PATH": "/tiktok4g",
        "WS_HOST": "trycloudflare.com",
        "ENABLE_WARP": "false",
        "WEBHOOK_URL": ""
    }
    START_TIME = int(time.time())

    def get_os_env(name):
        return os.getenv(name, default_configs.get(name))

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
        # Support multiple ports format. 
        # Default: localhost:8888

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

    # Read raw PORT string from .env
    PORT_ENV = get_os_env("PORT")
    UUID = get_os_env("XRAY_UUID")
    FAKE_SNI = get_os_env("FAKE_SNI")
    WS_PATH = get_os_env("WS_PATH")
    WS_HOST = get_os_env("WS_HOST")
    WEBHOOK_URL = get_os_env("WEBHOOK_URL")
    ENABLE_WARP = get_os_env("ENABLE_WARP").lower() == "true"

    # Parse multi-port configuration
    # Supported formats: "8888" (defaults to 0.0.0.0), "127.0.0.1:8888", "0.0.0.0:443,0.0.0.0:80"
    inbound_ports = []
    for p_item in PORT_ENV.split(","):
        p_item = p_item.strip()
        if ":" in p_item:
            parts = p_item.split(":")
            listen_ip = ":".join(parts[:-1])
            port_num = int(parts[-1])
            inbound_ports.append((listen_ip, port_num))
        else:
            inbound_ports.append(("0.0.0.0", int(p_item)))

    # Cloudflare tunnel will point to the first port in the list
    CLOUDFLARE_TARGET_IP = inbound_ports[0][0]
    CLOUDFLARE_TARGET_PORT = inbound_ports[0][1]
    # If listening on all interfaces, force cloudflared to connect via localhost
    if CLOUDFLARE_TARGET_IP == "0.0.0.0":
        CLOUDFLARE_TARGET_IP = "127.0.0.1"

    def send_webhook(data):
        if not WEBHOOK_URL: 
            return
        def task():
            try:
                response = requests.post(
                    WEBHOOK_URL, 
                    json=data,
                    timeout=10
                )
                if response.status_code == 200:
                    print("[+] Webhook sent successfully!")
                else:
                    print(f"[-] Webhook failed with status: {response.status_code}")
            except Exception as e:
                print(f"[!] Error sending webhook: {e}")
        thread = threading.Thread(target=task)
        thread.daemon = True
        thread.start()

    if not WS_PATH.startswith("/"):
        WS_PATH = "/" + WS_PATH

    XRAY_BIN = "./xray.exe" if platform.system().lower() == "windows" else "./xray"
    CLF_BIN = "./cloudflared.exe" if platform.system().lower() == "windows" else "./cloudflared"
    WGCF_BIN = "./wgcf-cli.exe" if platform.system().lower() == "windows" else "./wgcf-cli"

    if not os.path.exists(XRAY_BIN):
        print(f"[ERROR] Unable to find xray path: {XRAY_BIN}")
        xray_downloader.install_xray()
    if not os.path.exists(CLF_BIN):
        print(f"[ERROR] Unable to find Cloudflared path: {CLF_BIN}")
        cloudflared_downloader.install_cloudflared()

    wgcf_outbound = None

    if ENABLE_WARP:
        if not os.path.exists(WGCF_BIN):
            print(f"[ERROR] Unable to find WGCF path: {WGCF_BIN}")
            wgcf_downloader.install_wgcf()
        
        if not os.path.exists("wgcf.xray.json"):
            print("[*] Generating WARP account...")
            # Dont print output of wgcf-cli to avoid leaking sensitive info, but ensure it runs successfully
            subprocess.run([WGCF_BIN, "register"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run([WGCF_BIN, "generate", "--xray"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        """
        this is content of wgcf.xray.json generated by wgcf-cli, which is used to configure WARP as an outbound in Xray.
        {
            "protocol": "wireguard",
            "settings": {
                ...
            },
            "tag": "wireguard"
        }
        """
        with open("wgcf.xray.json", "r") as f:
            wgcf_outbound = json.load(f)

    # =========================================
    # VLESS-WS CONFIG GENERATOR
    # =========================================
    def write_configs():
        inbounds = []
        for ip, port in inbound_ports:
            inbounds.append({
                "port": port,
                "listen": ip,
                "protocol": "vless",
                "sniffing": {
                    "enabled": True,
                    "destOverride": ["http", "tls"]
                },
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
            })

        xray_config = {
            "log": {
                "loglevel": "warning"
            },
            "inbounds": inbounds,
            "outbounds": [
                {
                    "protocol": "freedom",
                    "settings": {}
                }
            ]
        }

        # Change outbound to WARP if enabled
        if ENABLE_WARP and wgcf_outbound:
            xray_config["outbounds"].insert(0, wgcf_outbound)

        if os.path.exists("config.json"):
            try: os.remove("config.json")
            except: pass
            
        with open("config.json", "w", encoding="utf-8") as f: 
            json.dump(xray_config, f, indent=2)

    write_configs()

    print(f"[*] Launching XRAY with multi-port inbounds...")
    # Using 'run' with extra environment or fallback handling is ideal, 
    # but natively Xray logs the error to stderr and continues if other ports work.
    xp = subprocess.Popen(
        [XRAY_BIN, "run", "-c", "config.json"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        errors='replace'
    )

    print(f"[*] Launching Cloudflare Tunnel pointing to http://{CLOUDFLARE_TARGET_IP}:{CLOUDFLARE_TARGET_PORT}...")
    clp = subprocess.Popen(
        [CLF_BIN, "tunnel", "--url", f"http://{CLOUDFLARE_TARGET_IP}:{CLOUDFLARE_TARGET_PORT}"],
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
                    # Suppress or catch common permission denied / bind errors quietly for Termux environment
                    if "Permission denied" in line or "EACCES" in line or "address already in use" in line:
                        # Log silently to Web UI instead of crashing the main process stdout aggressively
                        if logger:
                            logger.push_log(f"[SILENT BIND WARNING] {line.strip()}", "XRAY")
                        continue
                    
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
        except Exception as e:
            #print(e)
            pass

    threading.Thread(target=monitor_xray, args=(xp.stdout,), daemon=True).start()
    threading.Thread(target=monitor_cloudflare, args=(clp.stdout,), daemon=True).start()

    def print_vless_links(tunnel_host, uuid_str, fake_sni, ws_path):
        import urllib.parse
        encoded_path = urllib.parse.quote(ws_path, safe='')

        tunnel_host_info = tunnel_host
        if WS_HOST and WS_HOST != "trycloudflare.com": 
            tunnel_host_info = WS_HOST
        
        payloads = []
        sni_list = fake_sni.split(",");

        for sni in sni_list:
            payloads.extend([
                f"vless://{uuid_str}@{sni}:443?type=ws&encryption=none&security=tls&path={encoded_path}&host={tunnel_host_info}&sni={tunnel_host_info}#Tunnel%20{sni_list.index(sni)+1}%20TLS",
                f"vless://{uuid_str}@{sni}:80?type=ws&encryption=none&security=&path={encoded_path}&host={tunnel_host_info}#Tunnel%20{sni_list.index(sni)+1}%20NO%20TLS"
            ])

        print("\n" + "="*70)
        print(" CONNECTED TO CLOUDFLARE TUNNEL")
        print("="*70)
        print("="*70 + "\n")

        with open("frp_info.config", "w", encoding='utf-8') as f:
            for payload in payloads:
                f.write(payload);
                f.write("\n") if payloads.index(payload) < len(payloads)-1 else None
            print("Written to frp_info.config")
        
        frp_info = {
            "payloads": payloads,
            "ip": get_public_url(),
            "wshost": tunnel_host, 
            "wspath": ws_path,
            "start_time": START_TIME,
        }

        send_webhook(frp_info)
        with open("frp_info.json", "w", encoding='utf-8') as f:
            json.dump(frp_info, f, indent=4)
            print("Written to frp_info.json")

    try:
        while True:
            # Termux workaround: We don't crash if Xray returns a code but cloudflared is still happily running on the local port 8888.
            # However, if both stop or core configuration is broken, we terminate.
            if xp.poll() is not None and clp.poll() is not None:
                print(f"\n[!] WARNING: Both processes have stopped.")
                break
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n[*] Stopping services...")
    finally:
        try: xp.terminate()
        except: pass
        try: clp.terminate()
        except: pass

if __name__ == "__main__":
    main()