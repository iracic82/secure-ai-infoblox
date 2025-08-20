import os
import json
import requests
import time
import random

class InfobloxSession:
    def __init__(self):
        self.base_url = "https://csp.infoblox.com"
        self.email = os.getenv("INFOBLOX_EMAIL")
        self.password = os.getenv("INFOBLOX_PASSWORD")
        self.jwt = None
        self.session = requests.Session()
        self.headers = {"Content-Type": "application/json"}
        self.account_id = os.getenv("INSTRUQT_AWS_ACCOUNT_INFOBLOX_DEMO_ACCOUNT_ID")

    def login(self):
        payload = {"email": self.email, "password": self.password}
        response = self.session.post(
            f"{self.base_url}/v2/session/users/sign_in",
            headers=self.headers, json=payload
        )
        response.raise_for_status()
        self.jwt = response.json().get("jwt")
        self._save_to_file("jwt.txt", self.jwt)
        print("✅ Logged in and saved JWT to jwt.txt")

    def switch_account(self):
        sandbox_id = self._read_file("sandbox_id.txt")
        payload = {"id": f"identity/accounts/{sandbox_id}"}
        response = self.session.post(
            f"{self.base_url}/v2/session/account_switch",
            headers=self._auth_headers(), json=payload
        )
        response.raise_for_status()
        self.jwt = response.json().get("jwt")
        self._save_to_file("jwt.txt", self.jwt)
        print(f"✅ Switched to sandbox {sandbox_id} and updated JWT")

    def get_current_account(self):
        response = self.session.get(
            f"{self.base_url}/v2/current_account",
            headers=self._auth_headers()
        )
        response.raise_for_status()
        print("🔍 Current Account Info:")
        print(json.dumps(response.json(), indent=2))

    def create_aws_key(self):
        access_key_id = os.getenv("INSTRUQT_AWS_ACCOUNT_INFOBLOX_DEMO_AWS_ACCESS_KEY_ID")
        secret_access_key = os.getenv("INSTRUQT_AWS_ACCOUNT_INFOBLOX_DEMO_AWS_SECRET_ACCESS_KEY")

        if not access_key_id or not secret_access_key:
            raise RuntimeError("❌ AWS credentials not found in environment variables.")

        payload = {
            "name": "aws-creds-instruqt",
            "source_id": "aws",
            "active": True,
            "key_data": {
                "access_key_id": access_key_id,
                "secret_access_key": secret_access_key
            },
            "key_type": "id_and_secret"
        }

        response = self.session.post(
            f"{self.base_url}/api/iam/v2/keys",
            headers=self._auth_headers(),
            json=payload
        )

        if response.status_code == 409:
            print("⚠️ AWS key already exists, skipping creation.")
        else:
            response.raise_for_status()
            print("🔐 AWS key created successfully.")

    # --------- Hardened waiters with backoff + jitter + periodic session refresh ---------

    def fetch_cloud_credential_id(self, timeout=240, initial_interval=5, max_interval=20):
        """
        Poll /api/iam/v1/cloud_credential until an AWS credential is visible.
        - Treats 403/503 as propagation/transient.
        - Exponential backoff with jitter.
        - Refreshes session (login + account switch) every few attempts.
        """
        url = f"{self.base_url}/api/iam/v1/cloud_credential"
        print(f"⏳ Waiting (up to {timeout}s) for AWS Cloud Credential to appear...")
        start = time.monotonic()
        interval = initial_interval
        attempts = 0

        while True:
            elapsed = time.monotonic() - start
            if elapsed > timeout:
                raise RuntimeError(f"❌ Timed out after {timeout}s waiting for AWS Cloud Credential to appear.")

            try:
                r = self.session.get(url, headers=self._auth_headers())
                if r.status_code == 429:
                    ra = r.headers.get("Retry-After")
                    sleep_s = int(ra) if (ra and ra.isdigit()) else min(max_interval, max(5, interval))
                    print(f"⏸️  429 Too Many Requests. Sleeping {sleep_s}s (Retry-After).")
                    time.sleep(sleep_s)
                    continue

                if r.status_code in (403, 503):
                    print(f"🚦 {r.status_code} transient ({r.reason}); retrying...")
                else:
                    r.raise_for_status()
                    data = r.json()
                    creds = data.get("results", []) if isinstance(data, dict) else []
                    for cred in creds:
                        if cred.get("credential_type") == "Amazon Web Services":
                            credential_id = cred.get("id")
                            self._save_to_file("cloud_credential_id.txt", credential_id)
                            print(f"✅ AWS Cloud Credential ID found and saved: {credential_id}")
                            return credential_id

            except requests.RequestException as e:
                print(f"⚠️ Fetch error: {e}; continuing...")

            attempts += 1
            if attempts % 3 == 0:
                try:
                    print("🔄 Refreshing session (login + account switch)...")
                    self.login()
                    self.switch_account()
                except Exception as e:
                    print(f"⚠️ Session refresh failed: {e}")

            sleep_s = min(max_interval, interval) + random.uniform(0, 0.3 * interval)
            print(f"🕐 Still waiting... elapsed={int(elapsed)}s; next check in ~{sleep_s:.1f}s")
            time.sleep(sleep_s)
            interval = min(max_interval, max(initial_interval, interval * 1.7))

    def fetch_dns_view_id(self, timeout=240, initial_interval=5, max_interval=20):
        """
        Poll /api/ddi/v1/dns/view until at least one DNS View is visible.
        - Treats 403/503 as propagation/transient.
        - Exponential backoff with jitter.
        - Refreshes session (login + account switch) every few attempts.
        """
        url = f"{self.base_url}/api/ddi/v1/dns/view"
        print(f"⏳ Waiting (up to {timeout}s) for DNS View to become accessible...")
        start = time.monotonic()
        interval = initial_interval
        attempts = 0

        while True:
            elapsed = time.monotonic() - start
            if elapsed > timeout:
                raise RuntimeError("❌ Timed out waiting for DNS View to be available")

            try:
                r = self.session.get(url, headers=self._auth_headers())
                if r.status_code == 429:
                    ra = r.headers.get("Retry-After")
                    sleep_s = int(ra) if (ra and ra.isdigit()) else min(max_interval, max(5, interval))
                    print(f"⏸️  429 Too Many Requests. Sleeping {sleep_s}s (Retry-After).")
                    time.sleep(sleep_s)
                    continue

                if r.status_code in (403, 503):
                    print(f"🚦 {r.status_code} transient ({r.reason}); retrying...")
                else:
                    r.raise_for_status()
                    data = r.json()
                    views = data.get("results", []) if isinstance(data, dict) else []
                    if views:
                        dns_view_id = views[0].get("id")
                        self._save_to_file("dns_view_id.txt", dns_view_id)
                        print(f"✅ DNS View ID saved: {dns_view_id}")
                        return dns_view_id

            except requests.RequestException as e:
                print(f"⚠️ Fetch error: {e}; continuing...")

            attempts += 1
            if attempts % 3 == 0:
                try:
                    print("🔄 Refreshing session (login + account switch)...")
                    self.login()
                    self.switch_account()
                except Exception as e:
                    print(f"⚠️ Session refresh failed: {e}")

            sleep_s = min(max_interval, interval) + random.uniform(0, 0.3 * interval)
            print(f"🕐 Still waiting... elapsed={int(elapsed)}s; next check in ~{sleep_s:.1f}s")
            time.sleep(sleep_s)
            interval = min(max_interval, max(initial_interval, interval * 1.7))

    # ------------------ rest unchanged ------------------

    def inject_variables_into_payload(self, template_file, output_file, dns_view_id, cloud_credential_id, account_id):
        with open(template_file, "r") as f:
            payload = json.load(f)

        payload["destinations"][0]["config"]["dns"]["view_id"] = dns_view_id
        payload["source_configs"][0]["cloud_credential_id"] = cloud_credential_id
        payload["source_configs"][0]["restricted_to_accounts"] = [account_id]

        with open(output_file, "w") as f:
            json.dump(payload, f, indent=2)

        print(f"📦 Payload created in {output_file} with injected variables")

    def submit_discovery_job(self, payload_file):
        with open(payload_file, "r") as f:
            payload = json.load(f)

        url = f"{self.base_url}/api/cloud_discovery/v2/providers"
        response = self.session.post(url, headers=self._auth_headers(), json=payload)
        response.raise_for_status()
        print("🚀 Cloud Discovery Job submitted:")
        print(json.dumps(response.json(), indent=2))

    def _auth_headers(self):
        return {"Content-Type": "application/json", "Authorization": f"Bearer {self.jwt}"}

    def _save_to_file(self, filename, content):
        with open(filename, "w") as f:
            f.write(content.strip())

    def _read_file(self, filename):
        with open(filename, "r") as f:
            return f.read().strip()


if __name__ == "__main__":
    session = InfobloxSession()
    session.login()
    session.switch_account()
    session.get_current_account()
    session.create_aws_key()
    cloud_credential_id = session.fetch_cloud_credential_id()
    dns_view_id = session.fetch_dns_view_id()
    session.inject_variables_into_payload(
        "payload_template.json", "payload.json",
        dns_view_id=dns_view_id,
        cloud_credential_id=cloud_credential_id,
        account_id=session.account_id
    )
    session.submit_discovery_job("payload.json")
