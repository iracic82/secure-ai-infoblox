import os
import re
import yaml
import requests
import time

def load_config_with_env(file_path):
    with open(file_path, "r") as f:
        raw_yaml = f.read()
    def replace_env(match):
        env_var = match.group(1)
        return os.environ.get(env_var, f"<MISSING:{env_var}>")
    interpolated = re.sub(r'\$\{(\w+)\}', replace_env, raw_yaml)
    return yaml.safe_load(interpolated)

class InfobloxVPNCleaner:
    def __init__(self, config_file):
        self.config = load_config_with_env(config_file)
        self.base_url = self.config["base_url"]
        self.email = self.config["email"]
        self.password = self.config["password"]
        self.sandbox_id_file = self.config["sandbox_id_file"]
        self.jwt = None
        self.headers = {}

    def authenticate(self):
        url = f"{self.base_url}/v2/session/users/sign_in"
        payload = {"email": self.email, "password": self.password}
        r = requests.post(url, json=payload)
        r.raise_for_status()
        self.jwt = r.json()["jwt"]
        self.headers = {
            "Authorization": f"Bearer {self.jwt}",
            "Content-Type": "application/json"
        }
        print("✅ Authenticated.")

    def switch_account(self):
        with open(self.sandbox_id_file, "r") as f:
            sandbox_id = f.read().strip()
        url = f"{self.base_url}/v2/session/account_switch"
        payload = {"id": f"identity/accounts/{sandbox_id}"}
        r = requests.post(url, headers=self.headers, json=payload)
        r.raise_for_status()
        self.jwt = r.json()["jwt"]
        self.headers["Authorization"] = f"Bearer {self.jwt}"
        print(f"🔁 Switched to sandbox account {sandbox_id}")
        time.sleep(2)

    def get_service_id_by_name(self, target_name):
        url = f"{self.base_url}/api/universalinfra/v1/universalservices"
        r = requests.get(url, headers=self.headers)
        r.raise_for_status()
        services = r.json().get("results", [])

        print(f"📦 Retrieved {len(services)} services:")
        for svc in services:
            svc_id = svc.get("id")
            svc_name = svc.get("name")
            print(f"  - 🔹 ID: {svc_id}, Name: {svc_name}")
            if svc_name == target_name:
                print(f"🧩 Match found for '{target_name}'")
                return svc_id

        print(f"❌ No exact match for service name '{target_name}'")
        return None

    def delete_service(self, full_id):
        # Normalize ID if it's a full path like "infra/universal_service/XYZ"
        service_uuid = full_id.split("/")[-1]
        url = f"{self.base_url}/api/universalinfra/v1/universalservices/{service_uuid}"
        r = requests.delete(url, headers=self.headers)
        if r.status_code == 200:
            print(f"🗑️ Successfully deleted service with ID: {service_uuid}")
        else:
            print(f"❌ Deletion failed. Status {r.status_code}:\n{r.text}")
            r.raise_for_status()

if __name__ == "__main__":
    vpn_name = "Instrqt-SaaS"

    client = InfobloxVPNCleaner("config_vpn.yaml")
    client.authenticate()
    client.switch_account()
    service_id = client.get_service_id_by_name(vpn_name)
    if service_id:
        client.delete_service(service_id)
