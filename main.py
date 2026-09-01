import os
import json
import re
import ipaddress
import socket
from urllib import request
from sys import prefix
from dotenv import load_dotenv
import threading
import subprocess
import platform
import uuid
import time
import datetime
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PrivateFormat,
    NoEncryption,
)
from cryptography.x509.oid import NameOID
from logging_site import RealtimeLogger
import requests
import importlib
import socket

xray_downloader = importlib.import_module("download-xray")
cloudflared_downloader = importlib.import_module("download-cloudflared")
wgcf_downloader = importlib.import_module("download-wgcf")

def main():
    # =========================================
    # CONFIG SERVER (Cloudflare Tunnel)
    # =========================================
    default_configs = {
        "PORT": "127.0.0.1:8888",
        "PASSWORD": "123",
        "XRAY_UUID": str(uuid.uuid4()),
        "FAKE_SNI": "api24-normal-alisg.tiktokv.com,vnpt.theworkpc.com",
        "WS_PATH": "/tiktok4g",
        "WS_HOST": "trycloudflare.com",
        "TRANSPORT": "websocket,xhttp",
        "XHTTP_MODE": "packet-up",
        "ENABLE_WARP": "false",
        "WEBHOOK_URL": "",
        "DEBUG_MODE": "false",
        "TUNNEL_TOKEN": "",
        "TLS_PORT": "",
        "TLS_KEY": "",
        "TLS_PEM": ""
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

    INTRANET_RANGES = [
        # IPv4
        "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8",
        "169.254.0.0/16", "172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24",
        "192.88.99.0/24", "192.168.0.0/16", "198.51.100.0/24", "203.0.113.0/24",
        "224.0.0.0/4", "240.0.0.0/4", "255.0.0.0/4", "255.255.255.0/24",
        "255.255.255.255/32",
        # IPv6
        "::/128", "::1/128", "::ffff:0:0/96", "100::/64", "64:ff9b::/96",
        "2001::/32", "2001:10::/28", "2001:20::/28", "2001:db8::/32",
        "2002::/16", "fc00::/7", "fe80::/10", "ff00::/8"
    ]
    PRIVATE_NETWORKS = [ipaddress.ip_network(net, strict=False) for net in INTRANET_RANGES]

    def get_all_ips():
        hostname = socket.gethostname()
        addr_info = socket.getaddrinfo(hostname, None)
        ip_addresses = set()
        for info in addr_info:
            ip = info[4][0]
            ip_addresses.add(ip)
        return ip_addresses

    def get_all_public_ips():
        all_ips = get_all_ips()
        public_ips = set()
        
        for ip_str in all_ips:
            try:
                ip_obj = ipaddress.ip_address(ip_str)
                is_intranet = any(ip_obj in net for net in PRIVATE_NETWORKS)
                if not is_intranet:
                    public_ips.add(ip_str)
            except ValueError:
                continue   
        return public_ips if public_ips else None

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
    TUNNEL_TOKEN = get_os_env("TUNNEL_TOKEN").strip()
    ENABLE_WARP = get_os_env("ENABLE_WARP").lower() == "true"
    PASSWORD = get_os_env("PASSWORD")
    DEBUG_MODE = get_os_env("DEBUG_MODE").lower() == "true"

    # TLS_PORT: optional direct VLESS+TLS listener (security=tls), independent
    # of the Cloudflare-facing ws/xhttp inbound(s). Same "ip:port" format as PORT.
    TLS_PORT_ENV = get_os_env("TLS_PORT").strip()
    TLS_KEY = get_os_env("TLS_KEY").strip()
    TLS_PEM = get_os_env("TLS_PEM").strip()

    # TRANSPORT: "websocket", "xhttp", or "websocket,xhttp" to run both at once.
    _transport_raw = get_os_env("TRANSPORT").strip().lower()
    _seen = set()
    TRANSPORTS = []
    for t in _transport_raw.split(","):
        t = t.strip()
        if t in ("websocket", "xhttp") and t not in _seen:
            TRANSPORTS.append(t)
            _seen.add(t)
    if not TRANSPORTS:
        print(f"[!] Unknown TRANSPORT '{_transport_raw}', falling back to 'websocket'.")
        TRANSPORTS = ["websocket"]

    DUAL_TRANSPORT = len(TRANSPORTS) > 1
    # Kept for any code/log paths that only care about a single-transport label.
    TRANSPORT = "+".join(TRANSPORTS)

    # XHTTP_MODE: only relevant when TRANSPORT=xhttp.
    # "packet-up" is the most CDN-compatible mode and is recommended when
    # routing traffic through Cloudflare (matches how the worker/tunnel forwards plain HTTP).
    XHTTP_MODE = get_os_env("XHTTP_MODE").strip().lower()
    if XHTTP_MODE not in ("packet-up", "stream-up", "stream-one"):
        print(f"[!] Unknown XHTTP_MODE '{XHTTP_MODE}', falling back to 'packet-up'.")
        XHTTP_MODE = "packet-up"

    # Parse multi-port configuration
    # Supported formats: "8888" (defaults to 0.0.0.0), "127.0.0.1:8888",
    # "0.0.0.0:443,0.0.0.0:80", and bracketed IPv6 like "[::1]:8888" or "[::]:443"
    # (the brackets are stripped -> listen_ip becomes the bare "::1" / "::",
    # which is what Xray's JSON "listen" field and Python's socket module expect).
    def parse_addr_port(item):
        item = item.strip()
        if item.startswith("["):
            end = item.index("]")
            ip = item[1:end]
            rest = item[end + 1:]
            if not rest.startswith(":"):
                raise ValueError(f"Invalid address:port '{item}' (missing port after ']')")
            port = int(rest[1:])
            return ip or "::", port
        if ":" in item:
            parts = item.split(":")
            listen_ip = ":".join(parts[:-1])
            port_num = int(parts[-1])
            return listen_ip, port_num
        return "0.0.0.0", int(item)

    inbound_ports = []
    for p_item in PORT_ENV.split(","):
        if not p_item.strip():
            continue
        inbound_ports.append(parse_addr_port(p_item))

    # Parse TLS_PORT (same format as PORT, brackets supported for IPv6). Empty disables it.
    tls_listen = None
    if TLS_PORT_ENV:
        tls_listen = parse_addr_port(TLS_PORT_ENV)

    def generate_self_signed_cert(domain):
        os.makedirs("tls", exist_ok=True)
        key_path = os.path.join("tls", "private.key")
        pem_path = os.path.join("tls", "fullchain.pem")
        if os.path.exists(key_path) and os.path.exists(pem_path):
            print(f"[*] Found existing self-signed cert at {key_path} / {pem_path}, reusing.")
            return key_path, pem_path
        print(f"[*] TLS_KEY/TLS_PEM not set, generating self-signed certificate for '{domain}'...")
        try:
            private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, domain),
            ])

            now = datetime.datetime.now(datetime.timezone.utc)
            cert = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(issuer)
                .public_key(private_key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(now - datetime.timedelta(days=1))
                .not_valid_after(now + datetime.timedelta(days=3650))
                .add_extension(
                    x509.SubjectAlternativeName([x509.DNSName(domain)]),
                    critical=False,
                )
                .sign(private_key, hashes.SHA256())
            )

            with open(key_path, "wb") as f:
                f.write(
                    private_key.private_bytes(
                        encoding=Encoding.PEM,
                        format=PrivateFormat.TraditionalOpenSSL,
                        encryption_algorithm=NoEncryption(),
                    )
                )
            with open(pem_path, "wb") as f:
                f.write(cert.public_bytes(Encoding.PEM))

            print(f"[+] Generated self-signed cert: {key_path}, {pem_path}")
        except Exception as e:
            print(f"[!] Failed to generate self-signed cert: {e}")
        return key_path, pem_path

    tls_key_path = None
    tls_pem_path = None
    if tls_listen:
        if TLS_KEY and TLS_PEM:
            tls_key_path, tls_pem_path = TLS_KEY, TLS_PEM
        else:
            tls_key_path, tls_pem_path = generate_self_signed_cert(WS_HOST)

    # Cloudflare tunnel will point to the first port in the list
    CLOUDFLARE_TARGET_IP = inbound_ports[0][0]
    CLOUDFLARE_TARGET_PORT = inbound_ports[0][1]
    # If listening on all interfaces, force cloudflared to connect via localhost
    if CLOUDFLARE_TARGET_IP == "0.0.0.0":
        CLOUDFLARE_TARGET_IP = "127.0.0.1"
    elif CLOUDFLARE_TARGET_IP in ("::", "::0"):
        CLOUDFLARE_TARGET_IP = "::1"
    # http:// URLs need brackets around a literal IPv6 host
    CLOUDFLARE_TARGET_HOST = (
        f"[{CLOUDFLARE_TARGET_IP}]" if ":" in CLOUDFLARE_TARGET_IP else CLOUDFLARE_TARGET_IP
    )

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
    def build_stream_settings(transport):
        if transport == "xhttp":
            return {
                "network": "xhttp",
                "security": "none",
                "xhttpSettings": {
                    "path": WS_PATH,
                    "mode": XHTTP_MODE
                }
            }
        return {
            "network": "ws",
            "security": "none",
            "wsSettings": {
                "path": WS_PATH,
                "headers": {}
            }
        }

    # For dual-transport mode, each real inbound port cannot bind two
    # different networks (ws vs xhttp) at once, so each transport gets its
    # own internal-only port on 127.0.0.1, and a lightweight TCP demux
    # listens on the original public-facing port. The demux peeks at the
    # start of each connection: requests with "Upgrade: websocket" go to
    # the ws inbound, everything else (plain HTTP used by xhttp) goes to
    # the xhttp inbound. This keeps a single external port/path for both
    # transports, so cloudflared/the Worker need no awareness of this split.
    WS_INTERNAL_OFFSET = 20000
    XHTTP_INTERNAL_OFFSET = 30000

    def internal_port_for(base_port, transport):
        offset = WS_INTERNAL_OFFSET if transport == "websocket" else XHTTP_INTERNAL_OFFSET
        return base_port + offset

    def peek_is_websocket(conn, timeout=3.0):
        conn.settimeout(timeout)
        try:
            data = conn.recv(8192, socket.MSG_PEEK)
        except Exception:
            data = b""
        finally:
            conn.settimeout(None)
        if not data:
            return False
        header_blob = data.decode("latin-1", errors="ignore").lower()
        return "upgrade: websocket" in header_blob

    def pipe_bytes(src, dst):
        try:
            while True:
                chunk = src.recv(65536)
                if not chunk:
                    break
                dst.sendall(chunk)
        except Exception:
            pass
        finally:
            try: src.shutdown(socket.SHUT_RD)
            except: pass
            try: dst.shutdown(socket.SHUT_WR)
            except: pass

    def handle_demux_conn(client_conn, ws_port, xhttp_port):
        is_ws = peek_is_websocket(client_conn)
        backend_port = ws_port if is_ws else xhttp_port
        try:
            backend_conn = socket.create_connection(("127.0.0.1", backend_port), timeout=5)
        except Exception:
            try: client_conn.close()
            except: pass
            return
        threading.Thread(target=pipe_bytes, args=(client_conn, backend_conn), daemon=True).start()
        threading.Thread(target=pipe_bytes, args=(backend_conn, client_conn), daemon=True).start()

    def start_demux_server(listen_ip, listen_port, ws_port, xhttp_port):
        is_v6 = ":" in listen_ip
        family = socket.AF_INET6 if is_v6 else socket.AF_INET
        srv = socket.socket(family, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        bind_ip = listen_ip
        if not is_v6 and listen_ip == "0.0.0.0":
            bind_ip = ""
        srv.bind((bind_ip, listen_port))
        srv.listen(128)

        def accept_loop():
            while True:
                try:
                    conn, _addr = srv.accept()
                except Exception:
                    break
                threading.Thread(target=handle_demux_conn, args=(conn, ws_port, xhttp_port), daemon=True).start()

        threading.Thread(target=accept_loop, daemon=True).start()
        print(f"[*] Dual-transport demux listening on {listen_ip}:{listen_port} -> ws:{ws_port} / xhttp:{xhttp_port}")
        return srv

    def write_configs():
        inbounds = []
        demux_servers = []

        for ip, port in inbound_ports:
            if DUAL_TRANSPORT:
                ws_port = internal_port_for(port, "websocket")
                xhttp_port = internal_port_for(port, "xhttp")

                inbounds.append({
                    "port": ws_port,
                    "listen": "127.0.0.1",
                    "protocol": "vless",
                    "sniffing": {
                        "enabled": True,
                        "destOverride": ["http", "tls"]
                    },
                    "settings": {
                        "clients": [{"id": UUID, "level": 0}],
                        "decryption": "none"
                    },
                    "streamSettings": build_stream_settings("websocket")
                })
                inbounds.append({
                    "port": xhttp_port,
                    "listen": "127.0.0.1",
                    "protocol": "vless",
                    "sniffing": {
                        "enabled": True,
                        "destOverride": ["http", "tls"]
                    },
                    "settings": {
                        "clients": [{"id": UUID, "level": 0}],
                        "decryption": "none"
                    },
                    "streamSettings": build_stream_settings("xhttp")
                })

                # The demux itself owns the original public-facing port;
                # started after Xray is up (see below), so just record intent here.
                demux_servers.append((ip, port, ws_port, xhttp_port))
            else:
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
                    "streamSettings": build_stream_settings(TRANSPORTS[0])
                })

        if tls_listen:
            tls_ip, tls_port_num = tls_listen
            tls_stream = build_stream_settings(TRANSPORTS[0])
            tls_stream["security"] = "tls"
            tls_stream["tlsSettings"] = {
                "certificates": [
                    {
                        "certificateFile": tls_pem_path,
                        "keyFile": tls_key_path
                    }
                ]
            }
            inbounds.append({
                "port": tls_port_num,
                "listen": tls_ip,
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
                "streamSettings": tls_stream
            })

        xray_config = {
            "log": {
                "loglevel": "debug"
            },
            "inbounds": inbounds,
            "outbounds": [
                {
                    "protocol": "freedom",
                    "settings": {
                        "domainStrategy": "UseIPv4"
                    }
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

        return demux_servers

    demux_servers = write_configs()

    print(f"All IPs: {get_all_ips()}") if DEBUG_MODE else None

    if get_all_public_ips() is None:
        print("[!] No Public IP was found on this host. Cloudflared Tunnel is needed if you want host to be connected from outside!")

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

    if DUAL_TRANSPORT:
        time.sleep(1)  # give xray a moment to bind its internal ports
        for ip, port, ws_port, xhttp_port in demux_servers:
            try:
                start_demux_server(ip, port, ws_port, xhttp_port)
            except Exception as e:
                print(f"[!] Failed to start dual-transport demux on {ip}:{port}: {e}")

    def write_cloudflared_config():
        config_yml_content = (
            f"tunnel: {TUNNEL_TOKEN}\n\n"
            "ingress:\n"
            f"  - hostname: {WS_HOST}\n"
            f"    service: http://{CLOUDFLARE_TARGET_HOST}:{CLOUDFLARE_TARGET_PORT}\n"
            "  - service: http_status:404\n"
        )
        with open("config.yml", "w", encoding="utf-8") as f:
            f.write(config_yml_content)

    def launch_cloudflared():
        if TUNNEL_TOKEN:
            write_cloudflared_config()
            print(f"[*] Launching Cloudflare Tunnel (named tunnel via config.yml)...")
            return subprocess.Popen(
                [CLF_BIN, "tunnel", "--config", "config.yml", "run"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
        print(f"[*] Launching Cloudflare Tunnel pointing to http://{CLOUDFLARE_TARGET_HOST}:{CLOUDFLARE_TARGET_PORT}...")
        return subprocess.Popen(
            [CLF_BIN, "tunnel", "--protocol", "http2", "--url", f"http://{CLOUDFLARE_TARGET_HOST}:{CLOUDFLARE_TARGET_PORT}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace'
        )

    RUN_CLOUDFLARED = (WS_HOST == "trycloudflare.com") or bool(TUNNEL_TOKEN)

    if RUN_CLOUDFLARED:
        clp = launch_cloudflared()
    else:
        print(f"[*] Skipping Cloudflare Tunnel: WS_HOST='{WS_HOST}' is a custom domain and TUNNEL_TOKEN is empty. Assuming the tunnel/reverse-proxy is managed externally.")
        clp = None

    cloudflare_url = None
    
    try:
        logger = RealtimeLogger(host="127.0.0.1", port=9999, password=PASSWORD)
        logger_url = logger.start()
        print(f"[*] Logger Web UI is running at: {logger_url}")
    except Exception:
        logger = None

    def logger_push(message, source):
        if logger:
            logger.push_log(f"[{source}] {message}", source)
            print(f"[{source}] {message}") if DEBUG_MODE else None

    def monitor_xray(pipe):
        try:
            with pipe:
                for line in iter(pipe.readline, ''):
                    # Suppress or catch common permission denied / bind errors quietly for Termux environment
                    if "Permission denied" in line or "EACCES" in line or "address already in use" in line:
                        # Log silently to Web UI instead of crashing the main process stdout aggressively
                        if logger:
                            logger_push(f"[SILENT BIND WARNING] {line.strip()}", "XRAY")
                        continue
                    
                    if logger:
                        logger_push(line.strip(), "XRAY")
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

                    if TUNNEL_TOKEN:
                        # Named tunnel via token: the hostname is whatever was
                        # configured on the Cloudflare dashboard / config.yml
                        # (WS_HOST), not something printed to stdout. Instead,
                        # watch for a "connection registered" log line to know
                        # the tunnel is actually up, then print links once.
                        if cloudflare_url is None and re.search(r'[Rr]egistered tunnel connection', clean_line):
                            print("\n" + "="*70)
                            print(" CONNECTED TO CLOUDFLARE TUNNEL")
                            print("="*70)
                            print("="*70 + "\n")
                            cloudflare_url = WS_HOST
                            print_vless_links(cloudflare_url, UUID, FAKE_SNI, WS_PATH)
                        continue

                    match = re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', clean_line)
                    if match:
                        new_url = match.group(0).replace("https://", "")
                        print("\n" + "="*70)
                        print(" CONNECTED TO CLOUDFLARE TUNNEL")
                        print("="*70)
                        print("="*70 + "\n")
                        if new_url != cloudflare_url:
                            if cloudflare_url:
                                print(f"[*] Detected new tunnel domain: {new_url} (was: {cloudflare_url})")
                            cloudflare_url = new_url
                            print_vless_links(cloudflare_url, UUID, FAKE_SNI, WS_PATH)
        except Exception as e:
            #print(e)
            pass

    threading.Thread(target=monitor_xray, args=(xp.stdout,), daemon=True).start()
    if clp is not None:
        threading.Thread(target=monitor_cloudflare, args=(clp.stdout,), daemon=True).start()

    def print_vless_links(tunnel_host, uuid_str, fake_sni, ws_path):
        import urllib.parse
        encoded_path = urllib.parse.quote(ws_path, safe='')

        tunnel_host_info = tunnel_host
        if WS_HOST and WS_HOST != "trycloudflare.com": 
            tunnel_host_info = WS_HOST
        
        if TRANSPORT == "xhttp":
            net_type = "xhttp"
            mode_param = f"&mode={XHTTP_MODE}"
            alpn_param_tls = "&alpn=h3%2Ch2"
        else:
            net_type = "ws"
            mode_param = ""
            alpn_param_tls = ""

        payloads = []
        sni_list = fake_sni.split(",");

        for idx, sni_entry in enumerate(sni_list):
            sni_entry = sni_entry.strip()
            if "#" in sni_entry:
                sni, remark = sni_entry.split("#", 1)
                sni = sni.strip()
                remark = remark.strip() or f"Tunnel {idx+1}"
            else:
                sni = sni_entry
                remark = f"Tunnel {idx+1}"

            encoded_remark = urllib.parse.quote(remark, safe='')

            if DUAL_TRANSPORT:
                payloads.extend([
                    f"vless://{uuid_str}@{sni}:443?type=ws&encryption=none&security=tls&path={encoded_path}&host={tunnel_host_info}&sni={tunnel_host_info}#{encoded_remark}%20WS%20TLS",
                    f"vless://{uuid_str}@{sni}:80?type=ws&encryption=none&security=&path={encoded_path}&host={tunnel_host_info}#{encoded_remark}%20WS%20No%20TLS",
                    f"vless://{uuid_str}@{sni}:443?type=xhttp&encryption=none&security=tls&path={encoded_path}&host={tunnel_host_info}&sni={tunnel_host_info}&mode={XHTTP_MODE}&alpn=h3%2Ch2#{encoded_remark}%20XHTTP%20TLS",
                    f"vless://{uuid_str}@{sni}:80?type=xhttp&encryption=none&security=&path={encoded_path}&host={tunnel_host_info}&mode={XHTTP_MODE}#{encoded_remark}%20XHTTP%20No%20TLS",
                ])
            else:
                payloads.extend([
                    f"vless://{uuid_str}@{sni}:443?type={net_type}&encryption=none&security=tls&path={encoded_path}&host={tunnel_host_info}&sni={tunnel_host_info}{mode_param}{alpn_param_tls}#{encoded_remark}%20TLS",
                    f"vless://{uuid_str}@{sni}:80?type={net_type}&encryption=none&security=&path={encoded_path}&host={tunnel_host_info}{mode_param}#{encoded_remark}%20NO%20TLS"
                ])

        with open("frp_info.config", "w", encoding='utf-8') as f:
            for payload in payloads:
                f.write(payload);
                f.write("\n") if payloads.index(payload) < len(payloads)-1 else None
                print(payload) if DEBUG_MODE else None
            print("Written to frp_info.config")
        
        frp_info = {
            "payloads": payloads,
            "ip": get_public_url(),
            "wshost": tunnel_host, 
            "wspath": ws_path,
            "transport": TRANSPORTS if DUAL_TRANSPORT else TRANSPORT,
            "xhttp_mode": XHTTP_MODE if "xhttp" in TRANSPORTS else None,
            "start_time": START_TIME,
        }

        send_webhook(frp_info)
        with open("frp_info.json", "w", encoding='utf-8') as f:
            json.dump(frp_info, f, indent=4)
            print("Written to frp_info.json")

    if clp is None:
        cloudflare_url = WS_HOST
        print_vless_links(cloudflare_url, UUID, FAKE_SNI, WS_PATH)

    try:
        while True:
            # Termux workaround: We don't crash if Xray returns a code but cloudflared is still happily running on the local port 8888.
            # However, if both stop or core configuration is broken, we terminate.
            if xp.poll() is not None and (clp is None or clp.poll() is not None):
                print(f"\n[!] WARNING: Both processes have stopped.")
                break

            # If only cloudflared died (e.g. quick tunnel dropped/restarted), relaunch it.
            # This will get a brand new trycloudflare.com domain, which monitor_cloudflare
            # picks up and re-broadcasts via print_vless_links() + webhook automatically.
            if clp is not None and clp.poll() is not None and xp.poll() is None:
                print("[!] Cloudflare Tunnel process stopped unexpectedly. Restarting...")
                clp = launch_cloudflared()
                threading.Thread(target=monitor_cloudflare, args=(clp.stdout,), daemon=True).start()

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