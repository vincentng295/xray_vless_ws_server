import os
import platform
import sys
import shutil
import requests
import zstandard as zstd
import tarfile

WGCF_VERSION = "v0.3.6"
BASE_URL = f"https://github.com/ArchiveNetwork/wgcf-cli/releases/download/{WGCF_VERSION}"

def get_os_name():
    sys_type = platform.system().lower()
    arch = platform.machine().lower()

   
    is_android = "android" in sys.platform or "ANDROID_DATA" in os.environ

    if is_android:
        if arch in ["aarch64", "arm64"]:
            return "android-arm64-v8a.tar.zstd", "wgcf-cli"

    if sys_type == "windows":
        if arch in ["x86_64", "amd64"]:
            return "windows-64.tar.zstd", "wgcf-cli.exe"
        if arch in ["aarch64", "arm64"]:
            return "windows-arm64-v8a.tar.zstd", "wgcf-cli.exe"
        return "windows-32.tar.zstd", "wgcf-cli.exe"

    if sys_type == "linux":
        if arch in ["aarch64", "arm64"]:
            return "linux-arm64-v8a.tar.zstd", "wgcf-cli"
        if arch in ["armv7l", "arm"]:
            return "linux-arm32-v7a.tar.zstd", "wgcf-cli"
        return "linux-64.tar.zstd", "wgcf-cli"

    if sys_type == "darwin": 
        if arch in ["aarch64", "arm64"]:
            return "macos-arm64-v8a.tar.zstd", "wgcf-cli"
        return "macos-64.tar.zstd", "wgcf-cli"

    raise Exception(f"Hệ điều hành hoặc kiến trúc không được hỗ trợ: {sys_type} ({arch})")

def download_file(url, filename):
    print(f"Đang tải: {url}")
    r = requests.get(url, stream=True)
    r.raise_for_status()
    with open(filename, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)

def extract_tar_zstd(archive_path, extract_dir):
   
    dctx = zstd.ZstdDecompressor()
    tar_path = archive_path.replace(".zstd", "")
    
    with open(archive_path, 'rb') as ifh, open(tar_path, 'wb') as ofh:
        dctx.copy_stream(ifh, ofh)
        
    with tarfile.open(tar_path, "r:") as tar:
        tar.extractall(path=extract_dir)
        
    os.remove(tar_path)

def install_wgcf():
    archive_name, binary_name = get_os_name()
    url = f"{BASE_URL}/wgcf-cli-{archive_name}"
    archive_path = "wgcf-cli.tar.zstd"
    extract_dir = "wgcf_bin"

   
    download_file(url, archive_path)

   
    if os.path.exists(extract_dir):
        shutil.rmtree(extract_dir)

   
    print("Đang giải nén...")
    try:
        extract_tar_zstd(archive_path, extract_dir)
    finally:
        if os.path.exists(archive_path):
            os.remove(archive_path)

   
    src = os.path.join(extract_dir, binary_name)
    dst = os.path.join(".", binary_name)

    if os.path.exists(dst):
        os.remove(dst)

    shutil.move(src, dst)
    shutil.rmtree(extract_dir)

   
    if platform.system().lower() in ["linux", "darwin"] or "ANDROID_DATA" in os.environ:
        os.chmod(dst, 0o755)

    print("Cài đặt thành công! File lưu tại:", os.path.abspath(dst))

if __name__ == "__main__":
    install_wgcf()