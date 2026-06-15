from multiprocessing.dummy import Process
import os
import json
import requests
import threading
import time
from main import main
from github_utils import upload_file

def export_secrets_to_env():
    # Lấy nội dung từ biến môi trường ENV_CONFIG (GitHub sẽ nạp từ Secrets vào đây)
    env_config = os.getenv("ENV_CONFIG")
    env_path = ".env"

    if env_config:
        print("[*] Đang phát hiện cấu hình từ GitHub Secrets...")
        try:
            # Ghi đè hoặc tạo mới file .env
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(env_config.strip())
            print("[+] Đã chuyển đổi ENV_CONFIG sang file .env thành công.")
        except Exception as e:
            print(f"[!] Lỗi khi ghi file .env: {e}")
    else:
        print("[!] Không tìm thấy ENV_CONFIG. Bỏ qua bước tạo file .env (Chế độ Local).")

def bridge_workflows(token, bridge_inputs = True):
    repo = os.getenv("GITHUB_REPOSITORY")          # owner/repo
    ref = os.getenv("GITHUB_REF")                  # refs/heads/main
    run_id = os.getenv("GITHUB_RUN_ID")            # current run ID
    event_path = os.getenv("GITHUB_EVENT_PATH")    # path to event.json
    api_base = f"https://api.github.com/repos/{repo}"
    # Step 1: Get current workflow_id using run_id
    run_url = f"{api_base}/actions/runs/{run_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    run_response = requests.get(run_url, headers=headers)
    if run_response.status_code != 200:
        raise Exception(f"Failed to fetch run: {run_response.status_code} - {run_response.text}")
    workflow_id = run_response.json().get("workflow_id")
    if not workflow_id:
        raise Exception("Could not find workflow_id from run.")
    # Step 2: Extract original inputs if available
    inputs = {}
    if bridge_inputs:
        if event_path and os.path.exists(event_path):
            with open(event_path, "r") as f:
                event_data = json.load(f)
                inputs = event_data.get("inputs", {})
    # Step 3: Trigger the workflow again
    dispatch_url = f"{api_base}/actions/workflows/{workflow_id}/dispatches"
    payload = {
        "ref": ref.split("/")[-1],
        "inputs": inputs
    }
    dispatch_response = requests.post(dispatch_url, headers=headers, json=payload)
    if dispatch_response.status_code == 204 or dispatch_response.status_code == 200: # could be 204 No Content or 200 OK
        print(f"Triggered workflow {workflow_id} on branch {payload['ref']}")
    else:
        raise Exception(f"Failed to trigger workflow: {dispatch_response.status_code}")

def run_bridge():
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "") 
    bridge_workflows(GITHUB_TOKEN, True)


def watch_and_upload_proxy_info():
    files_to_watch = ["frp_info.config", "frp_info.json"]
    token = os.getenv("GITHUB_TOKEN", "")
    repo = os.getenv("GITHUB_REPOSITORY", "") 
    if not token or not repo:
        print("Missing GITHUB_TOKEN or GITHUB_REPOSITORY")
        return
    file_states = {
        filepath: {"last_mtime": None, "last_uploaded_time": 0}
        for filepath in files_to_watch
    }
    print(f"Starting to watch files: {', '.join(files_to_watch)} (uploading to 'config')...")
    while True:
        for filepath in files_to_watch:
            try:
                if os.path.exists(filepath):
                    mtime = os.path.getmtime(filepath)
                    state = file_states[filepath]
                    if state["last_mtime"] is None or mtime != state["last_mtime"]:
                        now = time.time()
                        if now - state["last_uploaded_time"] > 3:
                            print(f"[{filepath}] File changed or created!")
                            for attempt in range(3):
                                try:
                                    upload_file(token, repo, filepath, "config")
                                    state["last_uploaded_time"] = now
                                    print(f"[{filepath}] Uploaded successfully to 'config'.")
                                    break
                                except Exception as e:
                                    print(f"[{filepath}] Upload retry {attempt + 1}/3 failed: {e}")
                                    time.sleep(2)
                        state["last_mtime"] = mtime
            except Exception as e:
                print(f"Error while processing {filepath}: {e}")
        time.sleep(2)

def run_threads():
    if os.getenv("BRIDGE_WORKFLOWS", "false").lower() == "true":
        # Run the bridge workflow after 5 hours and 30 minutes to continue the workflow before timeout
        thread_bridge = threading.Timer(5 * 60 * 60 + 30 * 60, run_bridge)
        thread_bridge.daemon = True
        thread_bridge.start()
    thread_upload = threading.Thread(target=watch_and_upload_proxy_info)
    thread_upload.daemon = True  # Set as daemon
    thread_upload.start()
    threading.Thread(target=lambda: (time.sleep(5 * 60 * 60 + 40 * 60), os._exit(0)), daemon=True).start()

if __name__ == "__main__":
    run_threads()
    export_secrets_to_env()
    main()