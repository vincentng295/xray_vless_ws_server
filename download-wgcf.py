import os
import platform
import sys
import shutil
import requests

WGCF_VERSION = "v0.3.6"
BASE_URL = f"https://github.com/vincentng295/wgcf-cli/releases/download/{WGCF_VERSION}"

def get_os_name():
    sys_type = platform.system().lower()
    arch = platform.machine().lower()

    if sys_type == "windows":
        if arch in ["x86_64", "amd64"]:
            return "windows-64.exe", "wgcf-cli.exe"
        if arch in ["aarch64", "arm64"]:
            return "windows-arm64-v8a.exe", "wgcf-cli.exe"
        return "windows-32.exe", "wgcf-cli.exe"

    if sys_type == "linux":
        if arch in ["aarch64", "arm64"]:
            return "linux-arm64-v8a", "wgcf-cli"
        if arch in ["armv7l", "arm"]:
            return "linux-arm32-v7a", "wgcf-cli"
        if arch in ["x86_64", "amd64"]:
            return "linux-64", "wgcf-cli"

    if sys_type == "darwin": 
        if arch in ["aarch64", "arm64"]:
            return "macos-arm64-v8a", "wgcf-cli"
        return "macos-64", "wgcf-cli"

    if sys_type == "android":
        if arch in ["aarch64", "arm64"]:
            return "android-arm64-v8a", "wgcf-cli"
        if arch in ["x86_64", "amd64"]:
            return "android-amd64", "wgcf-cli"
        
    raise Exception(f"OS {sys_type} {arch} not supported.")

def download_file(url, filename):
    print(f"Đang tải: {url}")
    r = requests.get(url, stream=True)
    r.raise_for_status()
    with open(filename, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)

def install_wgcf():
    archive_name, binary_name = get_os_name()
    url = f"{BASE_URL}/wgcf-cli-{archive_name}"

    dst = os.path.join(".", binary_name)

    download_file(url, dst)
   
    if platform.system().lower() in ["linux", "darwin"] or "ANDROID_DATA" in os.environ:
        os.chmod(dst, 0o755)

    print("Cài đặt thành công! File lưu tại:", os.path.abspath(dst))

if __name__ == "__main__":
    install_wgcf()