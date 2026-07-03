# Xray VLESS-WS Bypass Protocol: Anycast Routing & SNI Spoofing (Proof of Concept)

[Xem phiên bản Tiếng Việt](README_vi.MD)

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

Based on the network architecture analysis, the carrier's DPI firewall must enforce the following heuristic rules to completely mitigate this Layer-7 Decoupling exploit:

1. Strict Application-Layer Verification: The DPI gateway must evolve beyond evaluating merely the outer perimeter of a packet (such as the transport-layer Address or SNI). The firewall heuristics must be updated to inspect the inner application-layer data payload.
2. Cross-Field Header Validation: Carriers must implement strict packet verification down to the application layer to validate that the external, transport-layer SNI explicitly matches the internal HTTP Host mapping embedded within the Layer 7 headers. Any structural discrepancy (e.g., an outer packet flagged as a whitelisted TikTok domain while the inner host header maps to an unauthorized multi-tenant CDN or ephemeral tunnel) must trigger an immediate drop rule at the telco gateway.

---

## CDN Provider Interoperability

While this specific Proof of Concept utilizes Cloudflare infrastructure (`cloudflared` and Cloudflare Anycast IPs) for local ease of deployment, the underlying core mechanism - **Layer 7 Decoupling** - is provider-agnostic. 

The structural technique successfully extends to any multi-tenant Content Delivery Network (CDN) or Edge computing platform operating under similar routing architectures, including:
* **Amazon CloudFront (AWS):** By pairing a zero-rated SNI resolving to AWS infrastructure (e.g., legacy TikTok endpoints) with an inner HTTP Host Header or custom origin distribution mapped to an AWS CloudFront configuration.
* **Akamai / Fastly / Gcore:** As long as the Mobile Network Operator (MNO) routes the whitelisted perimeter traffic to the respective provider's edge nodes, the edge infrastructure can process and forward encapsulated payloads down to separate targeted backends.

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
PORT=127.0.0.1:8888,0.0.0.0:443,0.0.0.0:80
XRAY_UUID=5ccad305-e243-4bb2-abf0-1e37189ce4e8
FAKE_SNI=api24-normal-alisg.tiktokv.com
WS_PATH=/tiktok4g
WS_HOST=trycloudflare.com
WEBHOOK_URL=

```

> **Important SNI Note:** Older configurations relied on `link.e.tiktok.com`. However, current routing records indicate `link.e.tiktok.com` resolves through **Amazon CloudFront (AWS)**. Because Cloudflare's tunneling mechanism cannot resolve or manipulate incoming host fields landing on rival AWS node layers, **`api24-normal-alisg.tiktokv.com`** is required for this Cloudflare-centric PoC to guarantee successful edge delivery.

---

## Acknowledgements

By reverse engineering commercial 4G bypass services like `betltone.com`, `phuonglien4g.com`, and similar community providers, the structural mechanics of this framework were successfully verified.
