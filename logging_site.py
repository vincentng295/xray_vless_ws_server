import json
import base64
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# --- GIAO DIỆN LOGGING ---
LOGGING_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <title>Hệ thống Log Realtime</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, sans-serif; background-color: #f0f2f5; margin: 0; padding: 20px; }
        .card { background: white; padding: 1.5rem; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.1); max-width: 950px; margin: auto; display: flex; flex-direction: column; max-height: 90vh; }
        h2 { border-bottom: 2px solid #eee; padding-bottom: 10px; display: flex; justify-content: space-between; align-items: center; }
        #log-container { background: #1e1e1e; color: #d4d4d4; padding: 15px; border-radius: 8px; overflow-y: auto; font-family: monospace; flex-grow: 1; height: 500px; }
        .log-entry { margin-bottom: 4px; border-bottom: 1px solid #2d2d2d; padding-bottom: 2px; }
        .timestamp { color: #888; margin-right: 8px; }
        .type-info { color: #007bff; font-weight: bold; }
        .type-error { color: #ff4757; font-weight: bold; }
        .type-success { color: #2ed573; font-weight: bold; }
        pre { margin: 5px 0; color: #f1fa8c; background: #282a36; padding: 8px; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="card">
        <h2>Log Realtime <small style="font-size: 12px; color: green;">● Online</small></h2>
        <div id="log-container">Đang chờ log...</div>
    </div>
    <script>
        const logContainer = document.getElementById("log-container");
        let lastLogId = 0;
        function formatLog(item) {
            let typeClass = "type-info";
            const type = (item.type || "INFO").toUpperCase();
            if (type.includes("ERROR")) typeClass = "type-error";
            if (type.includes("SUCCESS")) typeClass = "type-success";
            let msg = typeof item.text === "object" ? `<pre>${JSON.stringify(item.text, null, 2)}</pre>` : item.text;
            return `<div class="log-entry"><span class="timestamp">[${item.time}]</span><span class="${typeClass}">[${type}]</span> ${msg}</div>`;
        }
        async function fetchLogs() {
            try {
                const res = await fetch(`/logs?last_id=${lastLogId}`);
                const data = await res.json();
                if (data.new_logs.length > 0) {
                    if (logContainer.innerText.includes("Đang chờ")) logContainer.innerHTML = "";
                    logContainer.insertAdjacentHTML('beforeend', data.new_logs.map(formatLog).join(""));
                    lastLogId = data.last_id;
                    logContainer.scrollTop = logContainer.scrollHeight;
                }
            } catch (e) {}
        }
        setInterval(fetchLogs, 1000);
    </script>
</body>
</html>
"""

class RealtimeLogger:
    def __init__(self, port=8080, password="admin", max_logs=500):
        self.port = port
        self.password = password
        self.max_logs = max_logs
        self.logs = []
        self.log_sequence = 0
        self.server = None
        self.server_thread = None
        self._lock = threading.Lock()

    def set_password(self, password):
        self.password = password

    def set_port(self, port):
        if self.server:
            return False  # Không thể đổi port khi server đang chạy
        self.port = port
        return True

    def push_log(self, text, log_type="INFO"):
        with self._lock:
            self.log_sequence += 1
            item = {
                "id": self.log_sequence,
                "time": time.strftime("%H:%M:%S"),
                "type": log_type,
                "text": text
            }
            self.logs.append(item)
            if len(self.logs) > self.max_logs:
                self.logs.pop(0)

    def _create_handler(self):
        # Lưu reference của logger vào handler để nó truy cập được dữ liệu logs/password
        logger_ref = self

        class WebHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                return  # Tắt log mặc định của server vào console để đỡ rác

            def check_auth(self):
                if not logger_ref.password: return True
                auth = self.headers.get("Authorization")
                if not auth: return False
                try:
                    decoded = base64.b64decode(auth.split(" ")[1]).decode()
                    return decoded.split(":", 1)[1] == logger_ref.password
                except: return False

            def do_GET(self):
                if not self.check_auth():
                    self.send_response(401)
                    self.send_header("WWW-Authenticate", 'Basic realm="Login Required"')
                    self.end_headers()
                    self.wfile.write(b"Unauthorized")
                    return

                parsed = urlparse(self.path)
                if parsed.path == "/":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(LOGGING_HTML_TEMPLATE.encode())
                
                elif parsed.path == "/logs":
                    query = parse_qs(parsed.query)
                    last_id = int(query.get("last_id", [0])[0])
                    
                    with logger_ref._lock:
                        new_logs = [l for l in logger_ref.logs if l["id"] > last_id]
                        resp = {"new_logs": new_logs, "last_id": logger_ref.log_sequence}
                    
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(resp).encode())
        
        return WebHandler

    def start(self):
        """Khởi chạy server trong một thread riêng"""
        if self.server:
            return f"http://localhost:{self.port}"

        def run_server():
            self.server = ThreadingHTTPServer(("0.0.0.0", self.port), self._create_handler())
            self.server.serve_forever()

        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        return f"http://localhost:{self.port}"

    def stop(self):
        """Dừng server"""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
            return True
        return False

# --- VÍ DỤ SỬ DỤNG TRONG FILE KHÁC ---
if __name__ == "__main__":
    # 1. Khởi tạo
    logger = RealtimeLogger(port=9000, password="123")
    
    # 2. Start
    logger.start()
    
    # 3. Sử dụng
    try:
        while True:
            logger.push_log("Đang xử lý dữ liệu...", "INFO")
            time.sleep(2)
    except KeyboardInterrupt:
        logger.stop()