# Xray VLESS-WS Bypass Protocol: Anycast IP-Range Piggybacking (Proof of Concept)

[Xem phiên bản Tiếng Việt](README_vi.md)

An automated, educational Python-based Proof of Concept (PoC) demonstrating how to leverage **Xray-Core** and **Cloudflare Tunnels** (both dynamic `trycloudflare.com` and custom domains) to establish a secure VLESS-WebSocket proxy. This repository serves as a localized staging environment to validate Layer 7 deep-packet inspection (DPI) bypasses over zero-rated carrier networks (e.g., TikTok bundles) before committing to production infrastructure.

The idea of this project came from here: [The Anatomy of a Loophole: A Tech-Enthusiast's Journey into Layer-7 Decoupling](IDEAS.md)

---

## Architecture: PoC vs. Custom Domain & Production

Understanding the progression from temporary testing environments to custom domains and commercial production infrastructure:

### 1. Ephemeral Cloudflare Tunnel (Quick Testing)
* **Infrastructure:** Utilizes temporary Cloudflare Tunnels generated dynamically via `cloudflared tunnel --url`.
* **Limitation:** Cloudflare dynamically assigns a random subdomain (e.g., `*.trycloudflare.com`) on every script execution. It is excellent for free, fast, zero-configuration network logic validation, but unsuitable for persistent environments.

### 2. Custom Domain via Cloudflare Named Tunnel (Supported in `main.py`)
* **Infrastructure:** By supplying a `TUNNEL_TOKEN` and specifying your custom domain in `WS_HOST` within `.env`, the script automatically switches from temporary URLs to a persistent Cloudflare Named Tunnel.
* **Advantage:** Gives you a fixed, custom domain (e.g., `v2ray.yourdomain.com`) without needing a public IP on your local/homelab setup, maintaining stable VLESS configuration links.

### 3. Commercial / Production Infrastructure
To build a resilient, high-speed, and multi-user commercial platform:
* **Dedicated Virtual Private Servers (VPS):** A Linux VPS (Ubuntu) equipped with a dedicated Public IP is leased. Xray runs natively, accepting direct high-throughput connections on standard network ports (e.g., 80, 443) with optimal peering latency.
* **Cloudflare for SaaS (Custom Hostnames):** Instead of ephemeral paths, a vanity domain is registered and linked to Cloudflare SaaS (**Custom Hostnames** combined with a **Fallback Origin** pointing to the VPS IP) to permanently separate entry gateway IPs from core proxy servers.

---

## Technical Operating Principle

The core mechanism relies on IP/ASN-level whitelisting at the carrier, decoupled from what is actually inspected (or not inspected) at the TLS/HTTP layer:


```

[ Client Device ]
│
│ (1) DNS lookup of api24-normal-alisg.tiktokv.com
│     -> resolves to a Cloudflare Anycast IP that TikTok itself uses
▼
[ Telco DPI / Firewall ] ─── (Only checks: is destination IP/ASN in the
│                              whitelisted TikTok/Cloudflare range? -> yes -> forwards,
│                              unmetered, WITHOUT inspecting SNI or Host header)
│
│ (2) TLS ClientHello sent to that IP — SNI = your-tunnel-domain.com
│     (NOT api24-normal-alisg.tiktokv.com — see main.py: `sni` in the vless
│     link is set to the tunnel host, the tiktok domain is only used to
│     resolve the destination IP)
▼
[ Cloudflare Edge Node ]
│
├─ terminates the TLS connection using the SNI (tunnel host) presented above.
├─ reads the inner HTTP Host Header: [your-tunnel-domain.com].
└─ maps the host payload to your authenticated active tunnel.
│
▼ (Forwards traffic down the local machine tunnel pipeline)
[ Local Xray Instance ] ───> Decrypts VLESS payload -> Resolves to Public Internet

```

1. **The DPI Bypass:** The client's V2ray app sets the `Address` field to a zero-rated carrier domain like `api24-normal-alisg.tiktokv.com`. This is only used to perform a **DNS lookup** so the client connects to whichever Cloudflare Anycast IP TikTok itself resolves to. The `SNI` sent in the actual TLS ClientHello is the Cloudflare tunnel host (e.g., `your-tunnel-domain.com`), **not** the TikTok domain.
2. **IP/ASN Whitelisting:** The Mobile Network Operator (MNO) whitelists traffic based on destination **IP address or ASN/prefix range** owned by Cloudflare, passing traffic unmetered regardless of the presented SNI or Host header.
3. **Anycast Realignment:** Because TikTok routes API nodes natively through Cloudflare Anycast, the carrier's coarse IP-range whitelist covers all Cloudflare tenants on that same range.
4. **Layer 7 Redirect:** The edge node terminates TLS using the presented SNI, inspects the `Host Header` (`host=your-tunnel-domain.com`), and routes traffic down to your active Xray server.

---

## Transport Comparison: WebSocket vs. xHTTP

The shift from **VLESS + WebSocket (WS)** to **VLESS + xHTTP** (particularly the `packet-up` mode) is a major turning point in the firewall-bypass community. Below is a detailed comparison of the two transports when paired with Cloudflare's CDN:

| Criteria | VLESS + WebSocket (WS) | VLESS + xHTTP (`packet-up`) |
| --- | --- | --- |
| **Protocol nature** | HTTP/1.1 Upgrade to WebSocket (TCP) | HTTP/2 or HTTP/3 stream (POST/upload stream) |
| **Data transfer mechanism** | Traditional full-duplex connection | Separate downstream & upstream flows (`packet-up`) |
| **Cloudflare CDN compatibility** | Good, but prone to throttling/CAPTCHA challenges | **Excellent** — mimics a standard large HTTP POST payload |
| **Latency / ping** | Higher (TCP handshake + head-of-line blocking) | **Lower** (multiplexing, 0-RTT/1-RTT optimizations) |
| **Bandwidth / speed** | Prone to congestion on large transfers | **Higher & more stable**, better utilizes CDN bandwidth |
| **Stealth** | Easier for modern DPI to fingerprint | **Harder to detect** — resembles ordinary file-upload/API traffic |

### Why xHTTP `packet-up` is a breakthrough over Cloudflare CDN

The term **`packet-up`** (packet upload) solves the biggest historical friction point between proxies and CDNs:

* **Defeating CDN heuristics:** Long-lived WebSocket connections through Cloudflare are easy for the edge to flag, throttle, or drop mid-session. `packet-up` instead packages upstream data as standard HTTP stream/chunked POST requests — to the CDN, this traffic looks indistinguishable from a user uploading a file or calling an API.
* **Independent up/down optimization:** Downstream and upstream data are handled as separate streams, letting Cloudflare prioritize and route each with less buffering and fewer dropped packets.
* **Leveraging HTTP/2 & HTTP/3:** WebSocket is bound to plain TCP. xHTTP instead rides HTTP/2 multiplexing or HTTP/3's QUIC (UDP) transport across Cloudflare's edge network, largely eliminating head-of-line blocking.

### Bottom line

* **VLESS + WS:** A proven, "legendary" workhorse for years — simple, easy to configure, and broadly compatible with clients.
* **VLESS + xHTTP (`packet-up`):** The new standard going forward. Behind Cloudflare's CDN, it typically delivers lower ping, higher throughput, and noticeably better connection resilience against DPI.

This project's `main.py` supports both transports via the `TRANSPORT` variable in `.env` — including running **both simultaneously** (`TRANSPORT=websocket,xhttp`), in which case the generated VLESS links are labeled `WS TLS`, `WS No TLS`, `XHTTP TLS`, and `XHTTP No TLS` so you can compare them side by side.

---

## Script Features

- **Dynamic Local Environment Orchestration:** Automated verification and generation of localized `.env` dependencies.
- **Support for Both Quick & Named Tunnels:** Automatically detects whether to launch a temporary `trycloudflare.com` tunnel or a persistent custom domain tunnel via `TUNNEL_TOKEN`.
- **WARP Outbound Integration:** Optional Cloudflare WARP egress routing via `wgcf-cli` (`ENABLE_WARP=true`) for privacy and bypassing strict target IP bans.
- **Auto-Architecture Binary Management:** Bundled standalone injectors (`download-xray.py`, `download-cloudflared.py`, `download-wgcf.py`) detect client platform kernels to pull current runtime binaries natively.
- **Asynchronous Engine Logging & Embedded Web UI Monitor:** Real-time log relay through an integrated background HTTP daemon (`logging_site.py`).
- **Webhook & JSON Export:** Auto-generates `frp_info.config` and `frp_info.json`, optionally dispatching payloads to a remote `WEBHOOK_URL`.

---

## Installation & Usage

```bash
# Clone the source code
git clone [https://github.com/vincentng295/xray_vless_ws_server](https://github.com/vincentng295/xray_vless_ws_server)

# Move into the project directory
cd xray_vless_ws_server

# Install the required Python dependencies
pip install -r requirements.txt

# Start the server
python main.py

```

---

## Configuration (`.env`)

```ini
PORT=127.0.0.1:8888,0.0.0.0:80
XRAY_UUID=5ccad305-e243-4bb2-abf0-1e37189ce4e8
FAKE_SNI=api24-normal-alisg.tiktokv.com
WS_PATH=/tiktok4g
WS_HOST=v2ray.yourdomain.com
TRANSPORT=WebSocket,xhttp
XHTTP_MODE=packet-up
TUNNEL_TOKEN=eyJhSWQiOiI...
ENABLE_WARP=false
WEBHOOK_URL=

```

### Parameter Description:

* **`PORT`**: Comma-separated list of inbound ports/interfaces for Xray.
* **`XRAY_UUID`**: UUID string used for VLESS client authentication.
* **`FAKE_SNI`**: Zero-rated domain used by clients for DNS/IP resolution (e.g., TikTok CDN domain).
* **`WS_PATH`**: WebSocket/xHTTP path endpoint.
* **`WS_HOST`**: Custom domain for your Named Tunnel, or `trycloudflare.com` for quick temporary tunnels.
* **`TRANSPORT`**: `websocket`, `xhttp`, or `websocket,xhttp` to run both at once. See [Transport Comparison](#transport-comparison-websocket-vs-xhttp) above. Dual mode transparently demuxes both transports over the same public port/path — no extra Cloudflare configuration needed.
* **`XHTTP_MODE`**: `packet-up` (recommended, most CDN-compatible), `stream-up`, or `stream-one`. Only used when `TRANSPORT` includes `xhttp`.
* **`TUNNEL_TOKEN`**: Cloudflare Tunnel Token for persistent custom domain setup. Leave blank to use free temporary `trycloudflare.com` URLs.
* **`ENABLE_WARP`**: Set to `true` to route Xray outbound through Cloudflare WARP (via `wgcf`).
* **`WEBHOOK_URL`**: Optional endpoint to receive connection payloads upon tunnel initialization.

---

## Acknowledgements

By reverse engineering commercial 4G bypass services, the structural mechanics of this framework were successfully verified.