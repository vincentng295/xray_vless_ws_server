# Xray VLESS-WS Bypass Protocol: Anycast Routing & SNI Spoofing (Proof of Concept)

An automated, educational Python-based Proof of Concept (PoC) demonstrating how to leverage **Xray-Core** and ephemeral **Cloudflare Tunnels (`trycloudflare.com`)** to establish a secure VLESS-WebSocket proxy. This repository serves as a localized staging environment to validate Layer 7 deep-packet inspection (DPI) bypasses over zero-rated carrier networks (e.g., TikTok bundles) before committing to production infrastructure.

The idea of this project came from here: [The Anatomy of a Loophole: A Tech-Enthusiast's Journey into Layer-7 Decoupling](IDEAS.MD)

---

## Architecture: PoC vs. Production Infrastructure

Understanding the difference between this temporary testing suite and commercial architectures (such as **betltone.com** or **phuonglien4g.com**) is crucial:

### 1. This Proof of Concept (Testing Environment)
* **Infrastructure:** Utilizes an ephemeral Cloudflare Tunnel generated dynamically via `cloudflared tunnel --url`.
* **Limitation:** Cloudflare dynamically assigns a random subdomain (e.g., `*.trycloudflare.com`) on every script execution. It is excellent for free, fast, zero-configuration network logic validation, but **unsuitable for persistent production environments** due to unstable domains, potential rate limiting, and performance degradation under high multi-user stress.

### 2. Commercial / Production Infrastructure
To build a resilient, high-speed, and shareable system similar to major commercial providers, you must upgrade the components:
* **Dedicated Virtual Private Servers (VPS):** A Linux VPS (Ubuntu) equipped with a dedicated Public IP is leased. Xray runs natively, accepting direct high-throughput connections on standard network ports (e.g., 80, 443) with optimal peering latency.
* **Cloudflare for SaaS (Custom Hostnames):** Instead of ephemeral paths, a cheap vanity domain (e.g., `.com`, `.xyz`) is registered and linked to Cloudflare. By utilizing Cloudflare’s Enterprise/SaaS feature (**Custom Hostnames** combined with a **Fallback Origin** pointing to the VPS IP), administrators can permanently split network layers. This allows any arbitrary Cloudflare IP or whitelisted SNI to act as the entry gateway while securely directing under-the-hood packets to the core VPS.

---

## Technical Operating Principle

The core mechanism relies on decoupling the outer transport layer from inner routing context:


```

[ Client Device ]
│
│ (Outer Wrapper SNI: api24-normal-alisg.tiktokv.com)
▼
[ Telco DPI Firewall ] ─── (Scans SNI -> Validates TikTok Bundle -> Forwards Free Pass)
│
│ (Arrives at Cloudflare Global Anycast Edge Node)
▼
[ Cloudflare Edge Node ]
│
├─ strips the outer TLS payload layer.
├─ reads the inner HTTP Host Header: [your-random.trycloudflare.com].
└─ maps the host payload to your authenticated active ephemeral tunnel.
│
▼ (Forwards traffic down the local machine tunnel pipeline)
[ Local Xray Instance ] ───> Decrypts VLESS payload -> Resolves to Public Internet

```

1. **The DPI Bypass Handshake:** The client's V2ray app sets the `Address` and `SNI` explicitly to a zero-rated carrier domain like `api24-normal-alisg.tiktokv.com`. The Mobile Network Operator's (MNO) **Deep Packet Inspection (DPI)** flags this as whitelisted, unmetered app behavior, granting free passage.
2. **Anycast Realignment:** Because TikTok routes API nodes natively through **Cloudflare Anycast Global Infrastructure**, the carrier safely hands the packet directly to a nearby Cloudflare edge node.
3. **The Layer 7 Redirect:** The edge node opens the outer transport frame, inspects the hidden `Host Header` (`host=xxxx.trycloudflare.com`), and passes the proxy connection down to your executing environment.

---

## Script Features

- **Dynamic Local Environment Orchestration:** Automated verification and generation of localized `.env` dependencies.
- **Auto-Architecture Binary Management:** Bundled standalone injectors (`download-xray.py`, `download-cloudflared.py`) detect client platform kernels to pull current runtime binaries natively.
- **Asynchronous Engine Logging:** Concurrent multi-threaded monitoring nodes tracking state logs for both proxy binaries.
- **Embedded Web UI Monitor:** Real-time log relay through an integrated background HTTP daemon (`logging_site.py`).
- **GitHub Actions Compatibility:** Optional daemon scripts allowing localized headless environments to stay active on upstream development runners.

---

## Configuration (`.env`)

```ini
PORT=8888
XRAY_UUID=your-custom-vless-uuid
FAKE_SNI=api24-normal-alisg.tiktokv.com
WS_PATH=/tiktok4g

```

> **Important SNI Note:** Older configurations relied on `link.e.tiktok.com`. However, current routing records indicate `link.e.tiktok.com` resolves through **Amazon CloudFront (AWS)**. Because Cloudflare's tunneling mechanism cannot resolve or manipulate incoming host fields landing on rival AWS node layers, **`api24-normal-alisg.tiktokv.com`** is required for this Cloudflare-centric PoC to guarantee successful edge delivery.

---

## Acknowledgements

By reverse engineering commercial 4G bypass services like `betltone.com`, `phuonglien4g.com`, and similar community providers, the structural mechanics of this framework were successfully verified.

Through analyzing their production-grade reverse proxies, Wireshark payloads, and advanced multi-tenant Cloudflare SaaS configurations (Custom Hostnames / Fallback Origins), we decoded the exact decoupling mechanics of Address and Host packet manipulation. Their active network implementations provided the empirical technical blueprints necessary to translate complex corporate CDN edge configurations into this simplified, educational staging utility.