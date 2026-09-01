# Giao Thức Bypass Xray VLESS-WS: Lợi Dụng Dải IP Anycast Dùng Chung (Proof of Concept)

Một dự án Proof of Concept (PoC) tự động bằng Python phục vụ cho mục đích giáo dục, trình diễn cách tận dụng **Xray-Core** và **Cloudflare Tunnel** (bao gồm cả `trycloudflare.com` tạm thời lẫn **Domain riêng/Named Tunnel**) để thiết lập một proxy VLESS-WebSocket an toàn. Kho lưu trữ này hoạt động như một môi trường thử nghiệm cục bộ nhằm xác thực khả năng vượt tường lửa kiểm tra gói tin sâu Layer 7 trên các mạng di động được miễn phí data (ví dụ: các gói cước TikTok) trước khi triển khai lên hạ tầng production thực tế.

Ý tưởng của dự án này được khơi nguồn từ đây: [Giải Mã Lỗ Hổng: Hành Trình Khám Phá Kỹ Thuật Tách Lớp Layer-7](IDEAS_vi.md)

---

## Kiến Trúc: Bản Thử Nghiệm (PoC) vs. Domain Riêng vs. Hạ Tầng Thực Tế (Production)

Việc hiểu rõ sự phát triển từ bộ suite thử nghiệm tạm thời đến việc tích hợp Tên miền riêng và các kiến trúc thương mại thực tế là vô cùng quan trọng:

### 1. Cloudflare Tunnel Tạm Thời (Thử Nghiệm Nhanh)
* **Hạ Tầng:** Sử dụng Cloudflare Tunnel tạm thời được tạo động thông qua lệnh `cloudflared tunnel --url`.
* **Hạn Chế:** Cloudflare cấp ngẫu nhiên một subdomain (dạng `*.trycloudflare.com`) sau mỗi lần thực thi script. Cơ chế này tiện lợi để xác thực logic mạng nhanh chóng nhưng không thích hợp để dùng cố định lâu dài.

### 2. Tên Miền Riêng Qua Cloudflare Named Tunnel (Đã hỗ trợ trong `main.py`)
* **Hạ Tầng:** Bằng cách điền `TUNNEL_TOKEN` và khai báo Tên miền riêng tại `WS_HOST` trong file `.env`, hệ thống sẽ tự động chuyển từ tunnel tạm thời sang Cloudflare Named Tunnel cố định.
* **Ưu Điểm:** Giúp bạn sở hữu một domain cố định (ví dụ: `v2ray.tenmien.com`) mà không cần IP công khai tại máy nhà/máy thử nghiệm, giữ nguyên cấu hình link VLESS không bị thay đổi mỗi khi khởi động lại script.

### 3. Hạ Tầng Thương Mại / Production Thực Tế
Để xây dựng một hệ thống ổn định, tốc độ cao và phục vụ nhiều người dùng:
* **Máy Chủ Ảo Riêng (VPS) Dedicated:** Thuê VPS Linux có IP Công khai cố định. Xray chạy native trực tiếp trên VPS, tiếp nhận các kết nối băng thông cao trên các cổng mạng tiêu chuẩn (80, 443) nhằm tối ưu độ trễ.
* **Cloudflare for SaaS (Custom Hostnames):** Đăng ký tên miền cố định trỏ qua Cloudflare Enterprise/SaaS (**Custom Hostnames** kết hợp **Fallback Origin** trỏ về IP VPS) để tách biệt vĩnh viễn IP cổng vào với máy chủ proxy thực sự.

---

## Nguyên Lý Vận Hành Kỹ Thuật

Cơ chế cốt lõi dựa trên việc nhà mạng whitelist theo dải IP/ASN, tách biệt hoàn toàn với việc SNI/Host thực tế có được kiểm tra hay không:


```

[ Thiết Bị Client ]
│
│ (1) Phân giải DNS domain api24-normal-alisg.tiktokv.com
│     -> ra một IP Cloudflare Anycast mà chính TikTok cũng đang dùng
▼
[ Tường Lửa / DPI Nhà Mạng ] ─── (Chỉ kiểm tra: IP/ASN đích có nằm trong dải
│                                  whitelist TikTok/Cloudflare không? -> có -> cho qua
│                                  miễn phí, KHÔNG kiểm tra SNI hay Host Header)
│
│ (2) Gói TLS ClientHello gửi tới IP đó — SNI = ten-mien-tunnel-cua-ban.com
│     (KHÔNG PHẢI api24-normal-alisg.tiktokv.com — xem main.py: trường `sni`
│     trong link vless được set bằng tunnel host, domain tiktok chỉ dùng để
│     phân giải ra IP đích)
▼
[ Edge Node Cloudflare ]
│
├─ Kết thúc kết nối TLS dựa trên SNI (tunnel host) vừa nêu trên.
├─ Đọc HTTP Host Header ẩn bên trong: [ten-mien-tunnel-cua-ban.com].
└─ Ánh xạ payload của host vào đường hầm tunnel đang hoạt động.
│
▼ (Chuyển tiếp lưu lượng xuống đường hầm máy cục bộ)
[ Tiến Trình Xray Cục Bộ ] ───> Giải mã payload VLESS -> Phân giải ra Internet công cộng

```

1. **Cơ Chế Vượt DPI:** Ứng dụng V2ray phía client set trường `Address` thành domain zero-rated (ví dụ: `api24-normal-alisg.tiktokv.com`). Domain này **chỉ dùng để tra cứu DNS** lấy IP Cloudflare Anycast. Trường `SNI` trong TLS ClientHello được đặt thành domain tunnel (ví dụ: `ten-mien-tunnel-cua-ban.com`), **không phải** domain TikTok.
2. **Whitelist Theo IP/ASN:** Nhà mạng cho qua lưu lượng dựa trên dải IP/ASN của Cloudflare mà không chặn lọc kỹ SNI/Host thực tế.
3. **Trùng Dải Anycast:** Vì TikTok dùng chung hạ tầng Cloudflare Anycast, các tunnel chạy qua Cloudflare cũng được hưởng lợi từ chính sách miễn phí data này.
4. **Điều Hướng Lớp Layer 7:** Edge Node giải mã TLS, đọc `Host Header` và định tuyến dữ liệu chính xác về tiến trình Xray cục bộ.

---

## So Sánh Giao Thức: WebSocket vs xHTTP

Sự chuyển dịch từ **VLESS + WebSocket (WS)** sang **VLESS + xHTTP** (đặc biệt là biến thể `packet-up`) đang là bước ngoặt lớn trong cộng đồng bypass firewall. Dưới đây là bảng so sánh chi tiết giữa hai giao thức khi kết hợp với Cloudflare CDN:

| Tiêu chí | VLESS + WebSocket (WS) | VLESS + xHTTP (`packet-up`) |
| --- | --- | --- |
| **Bản chất giao thức** | HTTP/1.1 Upgrade sang WebSocket (TCP) | HTTP/2 hoặc HTTP/3 Stream (POST/Upload stream) |
| **Cơ chế truyền dữ liệu** | Tạo kết nối Full-Duplex truyền thống | Tách biệt luồng Downstream & Upstream (`packet-up`) |
| **Tương thích Cloudflare CDN** | Tốt, nhưng dễ bị bóp băng thông/bắt Capcha | **Cực tốt**, giả lập đúng chuẩn HTTP POST payload lớn |
| **Latency / Ping** | Cao hơn (dính TCP Handshake + Head-of-Line Blocking) | **Thấp hơn** (Tối ưu multiplexing, kết nối 0-RTT/1-RTT) |
| **Băng thông / Tốc độ** | Dễ bị nghẽn khi tải dữ liệu dung lượng lớn | **Cao & ổn định hơn**, khai thác tối đa băng thông CDN |
| **Khả năng che giấu (Stealth)** | Dễ bị nhận diện bởi DPI hiện đại | **Khó bị phát hiện**, hệt như traffic upload file/API call |

### Điểm đột phá của xHTTP `packet-up` với Cloudflare CDN

Thuật ngữ **`packet-up`** (Packet Upload) trong triển khai xHTTP giải quyết triệt để rào cản lớn nhất giữa proxy và CDN:

* **Đánh lừa cơ chế CDN:** Khi dùng WebSocket qua Cloudflare, kết nối kéo dài lâu dài (long-lived connection) rất dễ bị Cloudflare gắn cờ (flag), bóp băng thông (throttling), hoặc ngắt kết nối giữa chừng (timeout). Trong khi đó, `packet-up` đóng gói dữ liệu đẩy lên (Upstream) thành các luồng HTTP Stream/Chunked POST chuẩn chỉnh. Với CDN, traffic này trông không khác gì hành động người dùng đang upload file hoặc truyền dữ liệu qua API.
* **Tối ưu luồng Down/Up độc lập:** Dữ liệu nhận về (Downstream) và gửi đi (Upstream) được tách xử lý tối ưu. Cloudflare phân phối các HTTP stream này với ưu tiên cao, giảm thiểu tình trạng đệm (buffer) và rớt gói.
* **Tận dụng lợi thế HTTP/2 & HTTP/3:** WebSocket bắt buộc phải chạy trên TCP. Trong khi đó, xHTTP tận dụng triệt để Multiplexing của HTTP/2 hoặc giao thức QUIC (UDP) của HTTP/3 qua Cloudflare Edge Network, giúp triệt tiêu hiện tượng nghẽn luồng (Head-of-Line Blocking).

### Tổng kết

* **VLESS + WS:** Đã hoàn thành xuất sắc vai trò "huyền thoại" trong nhiều năm nhờ tính đơn giản, dễ cấu hình và độ tương thích thiết bị rộng.
* **VLESS + xHTTP (`packet-up`):** Là chuẩn mực mới cho hiện tại và tương lai. Nếu bạn qua CDN Cloudflare, xHTTP không chỉ mang lại Ping thấp hơn, tốc độ cao hơn mà còn tăng đáng kể độ bền của kết nối trước các hệ thống DPI.

Script `main.py` trong dự án này hỗ trợ cả hai giao thức thông qua biến `TRANSPORT` trong `.env` — bao gồm cả khả năng **chạy song song cả hai** (`TRANSPORT=websocket,xhttp`). Khi đó, các link VLESS sinh ra sẽ được gắn nhãn `WS TLS`, `WS No TLS`, `XHTTP TLS`, `XHTTP No TLS` để bạn tiện so sánh trực tiếp.

---

## Các Tính Năng Của Script

- **Điều Phối Môi Trường Tự Động:** Tự động tạo và kiểm tra file `.env`.
- **Hỗ Trợ Cả Tunnel Tạm Thời & Domain Riêng:** Tự động nhận diện `TUNNEL_TOKEN` để khởi tạo Cloudflare Tunnel ngẫu nhiên (`trycloudflare.com`) hoặc Tunnel cố định với Tên miền riêng.
- **Tích Hợp WARP Outbound:** Hỗ trợ định tuyến đầu ra Xray qua Cloudflare WARP (bằng `wgcf`) khi bật `ENABLE_WARP=true`.
- **Quản Lý Binary Tự Động:** Tự động tải Xray, Cloudflared, WGCF phù hợp với hệ điều hành (Windows/Linux/Termux).
- **Ghi Log Bất Đồng Bộ & Web UI Monitor:** Tích hợp sẵn giao diện theo dõi log qua HTTP local server (`logging_site.py`).
- **Xuất Cấu Hình & Webhook:** Tự động xuất link ra file `frp_info.config`, `frp_info.json` và gửi thông báo qua `WEBHOOK_URL` (nếu cấu hình).

---

## Cài Đặt & Sử Dụng

```bash
# Tải source code về máy
git clone [https://github.com/vincentng295/xray_vless_ws_server](https://github.com/vincentng295/xray_vless_ws_server)

# Di chuyển vào thư mục project
cd xray_vless_ws_server

# Cài đặt thư viện Python
pip install -r requirements.txt

# Bật server
python main.py

```

---

## Cấu Hình Tệp Môi Trường (`.env`)

```ini
PORT=127.0.0.1:8888,0.0.0.0:80
XRAY_UUID=5ccad305-e243-4bb2-abf0-1e37189ce4e8
FAKE_SNI=api24-normal-alisg.tiktokv.com
WS_PATH=/tiktok4g
WS_HOST=v2ray.tenmien.com
TRANSPORT=websocket,xhttp
XHTTP_MODE=packet-up
TUNNEL_TOKEN=eyJhSWQiOiI...
ENABLE_WARP=false
WEBHOOK_URL=

```

### Giải Thích Các Biến Cấu Hình:

* **`PORT`**: Các cổng/giao diện mạng cho Xray lắng nghe.
* **`XRAY_UUID`**: Mã UUID xác thực người dùng VLESS.
* **`FAKE_SNI`**: Tên miền miễn phí data dùng để phân giải IP kết nối.
* **`WS_PATH`**: Đường dẫn WebSocket/xHTTP path.
* **`WS_HOST`**: Tên miền riêng cấu hình trên Cloudflare Tunnel, hoặc để `trycloudflare.com` nếu dùng tunnel tạm thời.
* **`TRANSPORT`**: `websocket`, `xhttp`, hoặc `websocket,xhttp` để chạy song song cả hai. Xem thêm mục [So Sánh Giao Thức](#so-sánh-giao-thức-websocket-vs-xhttp) ở trên. Ở chế độ song song, cả hai giao thức được tự động phân luồng (demux) trên cùng một port/path công khai — không cần cấu hình thêm gì phía Cloudflare.
* **`XHTTP_MODE`**: `packet-up` (khuyên dùng, tương thích CDN tốt nhất), `stream-up`, hoặc `stream-one`. Chỉ có tác dụng khi `TRANSPORT` có chứa `xhttp`.
* **`TUNNEL_TOKEN`**: Token của Cloudflare Tunnel nếu bạn muốn dùng Domain riêng cố định. Để trống nếu muốn dùng tunnel miễn phí ngẫu nhiên.
* **`ENABLE_WARP`**: Đặt `true` để bật WARP làm outbound cho Xray (qua `wgcf`).
* **`WEBHOOK_URL`**: Đường dẫn webhook tùy chọn để nhận thông tin cấu hình link sau khi khởi tạo thành công.

---

## Lời Cảm Ơn

Bằng cách dịch ngược các dịch vụ bypass 4G thương mại trong cộng đồng, cơ chế cấu trúc của framework này đã được xác thực thành công.
