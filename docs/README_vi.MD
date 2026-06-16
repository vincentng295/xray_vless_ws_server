# Giao Thức Bypass Xray VLESS-WS: Định Tuyến Anycast & Giả Mạo SNI (Proof of Concept)

Một dự án Proof of Concept (PoC) tự động bằng Python phục vụ cho mục đích giáo dục, trình diễn cách tận dụng **Xray-Core** và các **Cloudflare Tunnel** tạm thời (`trycloudflare.com`) để thiết lập một proxy VLESS-WebSocket an toàn. Kho lưu trữ này hoạt động như một môi trường thử nghiệm cục bộ nhằm xác thực khả năng vượt tường lửa kiểm tra gói tin sâu Layer 7 trên các mạng di động được miễn phí data (ví dụ: các gói cước TikTok) trước khi triển khai lên hạ tầng production thực tế.

Ý tưởng của dự án này được khơi nguồn từ đây: [Giải Mã Lỗ Hổng: Hành Trình Khám Phá Kỹ Thuật Tách Lớp Layer-7](IDEAS_vi.MD)

---

## Kiến Trúc: Bản Thử Nghiệm (PoC) vs. Hạ Tầng Thực Tế (Production)

Việc hiểu rõ sự khác biệt giữa bộ suite thử nghiệm tạm thời này và các kiến trúc thương mại thực tế (như **betltone.com** hay **phuonglien4g.com**) là vô cùng quan trọng:

### 1. Bản Thử Nghiệm Này (Môi Trường Thử Nghiệm)
* **Hạ Tầng:** Sử dụng một Cloudflare Tunnel tạm thời được tạo động thông qua lệnh `cloudflared tunnel --url`.
* **Hạn Chế:** Cloudflare sẽ cấp ngẫu nhiên một subdomain (e.g., `*.trycloudflare.com`) sau mỗi lần thực thi script. Cơ chế này rất tuyệt để xác thực logic mạng nhanh chóng, miễn phí và không cần cấu hình phức tạp, nhưng **không phù hợp cho môi trường production lâu dài** do tên miền không cố định, giới hạn tần suất gọi API (rate limiting), và suy giảm hiệu năng khi có nhiều người dùng cùng lúc.

### 2. Hạ Tầng Thương Mại / Production Thực Tế
Để xây dựng một hệ thống ổn định, tốc độ cao và có thể chia sẻ cho nhiều người giống như các nhà cung cấp thương mại lớn, bạn cần nâng cấp các thành phần sau:
* **Máy Chủ Ảo Riêng (VPS) Dedicated:** Thuê một VPS Linux (Ubuntu) có IP Công khai cố định. Xray sẽ chạy native trực tiếp trên VPS, tiếp nhận các kết nối băng thông cao trên các cổng mạng tiêu chuẩn (ví dụ: 80, 443) nhằm tối ưu độ trễ (peering latency).
* **Cloudflare for SaaS (Custom Hostnames):** Thay vì sử dụng các đường dẫn tạm thời, một tên miền giá rẻ (ví dụ: `.com`, `.xyz`) sẽ được đăng ký và trỏ về Cloudflare. Bằng cách sử dụng tính năng Enterprise/SaaS của Cloudflare (**Custom Hostnames** kết hợp với một **Fallback Origin** trỏ về IP của VPS), quản trị viên có thể tách biệt vĩnh viễn các lớp mạng. Điều này cho phép bất kỳ IP Cloudflare hoặc SNI nào nằm trong danh sách trắng đều có thể đóng vai trò là cổng vào (entry gateway), trong khi vẫn điều hướng các gói tin ngầm một cách an toàn về phía VPS cốt lõi.

---

## Nguyên Lý Vận Hành Kỹ Thuật

Cơ chế cốt lõi dựa trên việc tách biệt lớp vận chuyển bên ngoài (outer transport layer) khỏi ngữ cảnh định tuyến bên trong (inner routing context):


```

[ Thiết Bị Client ]
│
│ (SNI Vỏ Bọc Ngoài: api24-normal-alisg.tiktokv.com)
▼
[ Tường Lửa DPI Nhà Mạng ] ─── (Quét SNI -> Xác thực Gói TikTok -> Cho qua miễn phí)
│
│ (Hạ cánh xuống Edge Node Cloudflare Global Anycast)
▼
[ Edge Node Cloudflare ]
│
├─ Bóc tách lớp payload TLS bên ngoài.
├─ Đọc HTTP Host Header ẩn bên trong: [your-random.trycloudflare.com].
└─ Ánh xạ payload của host vào đường hầm (tunnel) tạm thời đang hoạt động.
│
▼ (Chuyển tiếp lưu lượng xuống đường hầm máy cục bộ)
[ Tiến Trình Xray Cục Bộ ] ───> Giải mã payload VLESS -> Phân giải ra Internet công cộng

```

1. **Bắt Tay Vượt DPI (DPI Bypass Handshake):** Ứng dụng V2ray phía client thiết lập trường `Address` và `SNI` một cách tường minh thành một tên miền được nhà mạng miễn phí (zero-rated), chẳng hạn như `api24-normal-alisg.tiktokv.com`. Hệ thống **Kiểm tra gói tin sâu (DPI)** của nhà mạng di động gắn cờ đây là hành vi ứng dụng hợp lệ, không tính phí và cho phép đi qua tự do.
2. **Căn Chỉnh Định Tuyến Anycast:** Vì các node API của TikTok vốn định tuyến native qua **Hạ tầng Toàn cầu Cloudflare Anycast**, nhà mạng sẽ chuyển giao gói tin một cách an toàn đến một edge node Cloudflare gần nhất.
3. **Điều Hướng Lớp Layer 7 (Layer 7 Redirect):** Edge node mở khung vận chuyển bên ngoài, kiểm tra trường `Host Header` ẩn bên trong (`host=xxxx.trycloudflare.com`), và chuyển tiếp kết nối proxy xuống môi trường đang thực thi của bạn.

---

## Các Tính Năng Của Script

- **Điều Phối Môi Trường Cục Bộ Tự Động:** Tự động xác thực và khởi tạo các phụ thuộc tệp `.env` cục bộ.
- **Quản Lý Binary Theo Kiến Trúc Tự Động:** Các script injector độc lập đi kèm (`download-xray.py`, `download-cloudflared.py`) tự động nhận diện kernel nền tảng của client để tải về các file thực thi chuẩn xác nhất.
- **Ghi Log Công Cụ Bất Đồng Bộ:** Giám sát đa luồng đồng thời theo thời gian thực luồng log trạng thái của cả hai file thực thi proxy.
- **Tích Hợp Giao Diện Giám Sát Web (Web UI Monitor):** Truyền tiếp log theo thời gian thực thông qua một background HTTP daemon được tích hợp sẵn (`logging_site.py`).
- **Tương Thích GitHub Actions:** Hỗ trợ các script daemon tùy chọn cho phép các môi trường chạy headless cục bộ duy trì trạng thái hoạt động trên các runner phát triển upstream.

---

## Cấu Hình Tệp Môi Trường (`.env`)

```ini
PORT=8888
XRAY_UUID=your-custom-vless-uuid
FAKE_SNI=api24-normal-alisg.tiktokv.com
WS_PATH=/tiktok4g

```

> **Lưu ý Quan Trọng Về SNI:** Các cấu hình cũ thường dựa vào `link.e.tiktok.com`. Tuy nhiên, các bản ghi định tuyến hiện tại chỉ ra rằng `link.e.tiktok.com` được phân giải qua **Amazon CloudFront (AWS)**. Vì cơ chế tunnel của Cloudflare không thể phân giải hoặc can thiệp vào các trường host được gửi đến các tầng node đối thủ của AWS, **`api24-normal-alisg.tiktokv.com`** là bắt buộc đối với bản PoC tập trung vào Cloudflare này để đảm bảo truyền tải dữ liệu thành công tại edge.

---

## Lời Cảm Ơn

Bằng cách dịch ngược (reverse engineering) các dịch vụ bypass 4G thương mại như `betltone.com`, `phuonglien4g.com` và các nhà cung cấp tương tự trong cộng đồng, cơ chế cấu trúc của framework này đã được xác thực thành công.
