import os
import platform
import zipfile
import requests
import shutil

XRAY_VERSION = "v26.3.27"

BASE_URL = f"https://github.com/XTLS/Xray-core/releases/download/{XRAY_VERSION}"

def get_os_name():
    sys = platform.system().lower()
    arch = platform.machine().lower()

    if sys == "windows":
        return "windows-64.zip", "xray.exe"

    if sys == "linux":
        # Hỗ trợ Android/Termux và các chip ARM
        if arch in ["aarch64", "arm64"]:
            return "linux-arm64-v8a.zip", "xray"
        if arch in ["armv7l", "arm"]:
            return "linux-arm32-v7a.zip", "xray"
        # Mặc định cho Linux PC
        return "linux-64.zip", "xray"

    raise Exception("Unsupported OS")

def download_file(url, filename):
    print(f"Downloading: {url}")

    r = requests.get(url, stream=True)

    r.raise_for_status()

    with open(filename, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)

def install_xray():
    archive_name, binary_name = get_os_name()

    url = f"{BASE_URL}/Xray-{archive_name}"

    zip_path = "xray.zip"

    download_file(url, zip_path)

    extract_dir = "xray_bin"

    if os.path.exists(extract_dir):
        shutil.rmtree(extract_dir)

    os.makedirs(extract_dir, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(extract_dir)

    os.remove(zip_path)

    # move binary ra root
    src = os.path.join(extract_dir, binary_name)

    dst = os.path.join(".", binary_name)

    shutil.move(src, dst)

    # chmod linux
    if platform.system().lower() == "linux":
        os.chmod(dst, 0o755)

    print("Xray installed at:", dst)

if __name__ == "__main__":
    install_xray()
