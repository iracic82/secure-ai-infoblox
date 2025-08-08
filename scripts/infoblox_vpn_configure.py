import os
import re
import yaml
import time
import requests


def load_config_with_env(file_path):
    with open(file_path, "r") as f:
        raw_yaml = f.read()

    def replace_env(match):
        env_var = match.group(1)
        return os.environ.get(env_var, f"<MISSING:{env_var}>")

    interpolated = re.sub(r'\$\{(\w+)\}', replace_env, raw_yaml)
    return yaml.safe_load(interpolated)


def post_with_conflict_retry(url, headers, json_payload,
                             max_attempts=12, base_sleep=5, max_sleep=60):
    """
    Retries on 409 'operation in progress' or 429 rate-limit with exponential backoff.
    """
    attempt = 1
    while True:
        r = requests.post(url, headers=headers, json=json_payload)
        if r.status_code not in (409, 429):
            return r  # success or another error

        # Try Retry-After header, else backoff formula
        retry_after = r.headers.get("Retry-After")
        if retry_after:
            try:
                sleep_s = int(retry_after)
            except ValueError:
                sleep_s = base_sleep
        else:
            sleep_s = min(max_sleep, base_sleep * (2 ** (attempt - 1)))

        # Log and wait
        print(f"⏳ Op in progress (HTTP {r.status_code}). Retry {attempt}/{max_attempts} in {sleep_s}s...")
        time.sleep(sleep_s)

        attempt += 1
        if attempt > max_attempts:
            return r


class InfobloxVPNDeployer:
    def __init__(self, config_file):
        self.config = load_config_with_env(config_file)
        self.base_url = self.config["base_url"].rstrip("/")
        self.email = self.config["email"]
        self.password = self.config["password"]
        self.sandbox_id_file = self.config["sandbox_id_file"]
        self.jwt = None
        self.headers = {"Content-Type": "application/json"}

    def authenticate(self):
        url = f"{self.base_url}/v2/session/users/sign_in"
        payload = {"email": self.email, "password": self.password}
        r = requests.post(url, json=payload)
        r.raise_for_status()
        self.jwt = r.json()["jwt"]
        self.headers["Authorization"] = f"Bearer {self.jwt}"
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
        time.sleep(3)

    def get_security_policy_id(self, policy_name=None):
        url = f"{self.base_url}/api/atcfw/v1/security_policies"
        params = {"_fields": "id,name,is_default"}
        r = requests.get(url, headers=self.headers, params=params)
        r.raise_for_status()
        items = r.json().get("results", [])
        if policy_name:
            for it in items:
                if it.get("name") == policy_name:
                    return str(it["id"])
        for it in items:
            if it.get("is_default") is True:
                return str(it["id"])
        raise RuntimeError("No matching security policy found.")

    @staticmethod
    def _extract_usvc_id(resp_json):
        usvc = resp_json.get("universal_service")
        if isinstance(usvc, dict) and "id" in usvc:
            return usvc["id"]
        res = resp_json.get("results", {})
        if isinstance(res, dict):
            usvc2 = res.get("universal_service")
            if isinstance(usvc2, dict) and "id" in usvc2:
                return usvc2["id"]
        return None

    def deploy_vpn(self):
        url_cfg = f"{self.base_url}/api/universalinfra/v1/consolidated/configure"
        create_payload = self.config["vpn_payload"]

        # --- CREATE ---
        r = requests.post(url_cfg, headers=self.headers, json=create_payload)
        try:
            r.raise_for_status()
        except requests.exceptions.HTTPError:
            print("❌ Deployment failed (CREATE)")
            print(f"Status: {r.status_code}\nBody: {r.text}")
            raise

        create_resp = r.json() if r.text else {}
        usvc_id = self._extract_usvc_id(create_resp)
        if not usvc_id:
            print("ℹ️ Full response (for debugging):")
            print(r.text)
            raise RuntimeError("CREATE succeeded but universal_service.id not found in response")

        print(f"✅ Created universal service: {usvc_id}")

        # --- UPDATE (add Security) ---
        sec_cfg = self.config.get("security", {})
        if sec_cfg.get("enable", False):
            policy_id = self.get_security_policy_id(sec_cfg.get("policy_name"))
            print(f"🔐 Using security policy id: {policy_id}")

            update_payload = {
                "universal_service": {
                    "operation": "UPDATE",
                    "id": usvc_id,
                    "name": create_payload["universal_service"]["name"],
                    "description": "",
                    "capabilities": [
                        {"type": "dfp", "profile_id": policy_id},
                        {"type": "dns", "profile_id": ""}  # keep DNS
                    ],
                    "tags": create_payload["universal_service"].get("tags", {})
                },
                "access_locations": {"create": [], "update": [], "delete": []},
                "endpoints": {"create": [], "update": [], "delete": []},
                "credentials": {"create": [], "update": []},
                "locations": {"create": [], "update": []}
            }

            print("⏳ Waiting for CREATE op to finish before adding security...")
            r2 = post_with_conflict_retry(url_cfg, self.headers, update_payload)

            try:
                r2.raise_for_status()
            except requests.exceptions.HTTPError:
                print("❌ Update failed (add security/dfp) after retries")
                print(f"Status: {r2.status_code}\nBody: {r2.text}")
                raise

            print("✅ Security (dfp) added; DNS retained.")
        else:
            print("➡️ Security disabled in config; keeping DNS-only service.")

    def run(self):
        self.authenticate()
        self.switch_account()
        self.deploy_vpn()


if __name__ == "__main__":
    InfobloxVPNDeployer("config_vpn.yaml").run()
