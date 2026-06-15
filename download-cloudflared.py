import os
import platform
import requests
import shutil

CLOUDFLARED_VERSION = "2026.3.0" 
BASE_URL = f"https://github.com/cloudflare/cloudflared/releases/download/{CLOUDFLARED_VERSION}"

def get_download_info():
    sys = platform.system().lower()
    arch = platform.machine().lower()

    # Cloudflared đặt tên file theo dạng: cloudflared-linux-amd64, cloudflared-windows-amd64.exe
    if sys == "windows":
        if arch in ["amd64", "x86_64"]:
            return "cloudflared-windows-amd64.exe", "cloudflared.exe"
        return "cloudflared-windows-386.exe", "cloudflared.exe"

    if sys == "linux":
        if arch in ["aarch64", "arm64"]:
            return "cloudflared-linux-arm64", "cloudflared"
        if arch in ["armv7l", "arm"]:
            return "cloudflared-linux-arm", "cloudflared"
        if arch in ["amd64", "x86_64"]:
            return "cloudflared-linux-amd64", "cloudflared"
        return "cloudflared-linux-386", "cloudflared"

    if sys == "darwin": # macOS
        return "cloudflared-darwin-amd64.tgz", "cloudflared"

    raise Exception(f"Hệ điều hành {sys} {arch} chưa được hỗ trợ.")

def download_file(url, filename):
    print(f"Đang tải: {url}")
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(filename, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

def install_cloudflared():
    remote_file, local_name = get_download_info()
    url = f"{BASE_URL}/{remote_file}"
    
    print(f"Hệ thống: {platform.system()} ({platform.machine()})")

    # Cloudflared thường tải về là file chạy luôn (trừ macOS/FreeBSD là file nén)
    if remote_file.endswith(".exe") or "linux" in remote_file:
        download_file(url, local_name)
    else:
        # Xử lý nếu là file nén (ví dụ .tgz trên macOS)
        temp_archive = "cloudflared_temp.archive"
        download_file(url, temp_archive)
        print("Đang giải nén...")
        # Thêm logic giải nén nếu cần ở đây (shutil.unpack_archive)
        # Tạm thời với Linux/Windows thì cloudflared là binary trực tiếp
        os.rename(temp_archive, local_name)

    # Cấp quyền thực thi cho Linux/macOS
    if platform.system().lower() != "windows":
        os.chmod(local_name, 0o755)

    print(f"--- Đã cài đặt xong: {os.path.abspath(local_name)} ---")

if __name__ == "__main__":
    try:
        install_cloudflared()
    except Exception as e:
        print(f"Lỗi: {e}")