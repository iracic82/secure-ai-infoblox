import os
import re
import yaml
import time
import uuid
import requests
from copy import deepcopy


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
    attempt = 1
    while True:
        r = requests.post(url, headers=headers, json=json_payload)
        if r.status_code not in (409, 429):
            return r
        retry_after = r.headers.get("Retry-After")
        if retry_after:
            try:
                sleep_s = int(retry_after)
            except ValueError:
                sleep_s = base_sleep
        else:
            sleep_s = min(max_sleep, base_sleep * (2 ** (attempt - 1)))
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

    # ---------- Session ----------
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

    # ---------- Lookups ----------
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

    # ---- Robust credential discovery ----
    def try_get(self, path, params=None):
        url = f"{self.base_url}{path}"
        r = requests.get(url, headers=self.headers, params=params or {})
        if r.status_code >= 400:
            return None
        return r.json()

    def list_credentials(self):
        """
        Return {name: {id, ...}} if discoverable, else None.
        """
        candidates = [
            ("/api/universalinfra/v1/credentials", None),
            ("/api/universalinfra/v1/credential", None),
            ("/api/universalinfra/v1/universal_services?include=credentials", None),
            ("/api/atcinfra/v1/credentials", None),
        ]
        for path, params in candidates:
            data = self.try_get(path, params)
            if not data:
                continue
            results = []
            if isinstance(data, dict):
                if isinstance(data.get("results"), list):
                    results = data["results"]
                elif isinstance(data.get("items"), list):
                    results = data["items"]
                elif "name" in data or "id" in data:
                    results = [data]
            out = {}
            for c in results:
                nm = c.get("name"); cid = c.get("id")
                if nm and cid:
                    out[nm] = c
            if out:
                return out
        return None  # listing unavailable

    # ---------- Payload helpers ----------
    @staticmethod
    def _iter_objs(section: dict):
        """Yield objects under section.create and section.update."""
        if not isinstance(section, dict):
            return
        for key in ("create", "update"):
            for obj in section.get(key, []) or []:
                if isinstance(obj, dict):
                    yield obj

    @staticmethod
    def _normalize_cred_ref_in_obj(obj: dict, mode: str, resolver: dict):
        """
        Normalize 'credential'/'credentials' refs in a single object.
        mode: 'by_id' or 'by_name'
        resolver: {name -> id} when mode == 'by_id'
        """
        if not isinstance(obj, dict):
            return
        for key in ("credential", "credentials"):
            cref = obj.get(key)
            if isinstance(cref, dict):
                if mode == "by_id":
                    nm = cref.get("name")
                    if nm and nm in resolver:
                        cref["id"] = resolver[nm]
                        cref.pop("name", None)
                else:  # by_name
                    if "name" in cref:
                        cref.pop("id", None)

    def _normalize_section_credential_refs(self, payload: dict, mode: str, name_to_id: dict):
        # endpoints
        endpoints = payload.get("endpoints", {})
        for obj in self._iter_objs(endpoints):
            self._normalize_cred_ref_in_obj(obj, mode, name_to_id)
        payload["endpoints"] = endpoints

        # access_locations
        acc = payload.get("access_locations", {})
        for obj in self._iter_objs(acc):
            self._normalize_cred_ref_in_obj(obj, mode, name_to_id)
        payload["access_locations"] = acc

    def _resolve_or_create_credentials_in_payload(self, payload: dict):
        """
        Smart handling:
          - If we can list credentials:
              * reuse existing by name (drop from create)
              * normalize endpoint/access_location refs to id
          - If we cannot list:
              * KEEP credentials.create (so first call can create them)
              * normalize refs to rely on 'name' (strip 'id' if present)
        Returns (modified_payload, mode)
        """
        p = deepcopy(payload)
        creds_section = p.get("credentials", {})
        create_list = creds_section.get("create", []) or []
        update_list = creds_section.get("update", []) or []

        existing_by_name = self.list_credentials()

        if existing_by_name is None:
            # Listing unavailable → keep creates; rely on names in refs.
            self._normalize_section_credential_refs(p, mode="by_name", name_to_id={})
            print("🛈 Credential listing not available (501/404). Using name-bind mode (credential creates allowed).")
            return p, "by_name"

        # Listing available → build name->id map and drop duplicate creates
        name_to_id = {}
        remaining_creates = []
        for c in create_list:
            if not isinstance(c, dict):
                remaining_creates.append(c)
                continue
            nm = c.get("name")
            if nm and nm in existing_by_name:
                cid = existing_by_name[nm]["id"]
                name_to_id[nm] = cid
                print(f"♻️  Reusing existing credential '{nm}' (id={cid})")
            else:
                remaining_creates.append(c)
        p.setdefault("credentials", {})["create"] = remaining_creates

        normalized_updates = []
        for c in update_list:
            if not isinstance(c, dict):
                normalized_updates.append(c)
                continue
            nm = c.get("name")
            if nm and nm in existing_by_name:
                cid = existing_by_name[nm]["id"]
                c["id"] = cid
                c.pop("name", None)
                name_to_id[nm] = cid
                print(f"🛠️  Normalized credential UPDATE to id for '{nm}' (id={cid})")
            normalized_updates.append(c)
        p["credentials"]["update"] = normalized_updates

        # Normalize all sections to id-based refs
        self._normalize_section_credential_refs(p, mode="by_id", name_to_id=name_to_id)
        return p, "by_id"

    # ---- Uniquify (for name-bind mode and duplicate-name retries) ----
    @staticmethod
    def uniquify_credential_names(payload: dict):
        """
        Append a unique suffix to any credential names in .credentials.create
        and update endpoint/access_location refs accordingly.
        """
        p = deepcopy(payload)
        if "credentials" not in p:
            return p
        creds = p["credentials"].get("create", []) or []
        if not creds:
            return p

        suffix_map = {}
        for c in creds:
            if isinstance(c, dict) and "name" in c:
                old = c["name"]
                new = f"{old}-{uuid.uuid4().hex[:6]}"
                c["name"] = new
                suffix_map[old] = new

        # rewrite refs to new names
        for section_key in ("endpoints", "access_locations"):
            sect = p.get(section_key, {})
            for typ in ("create", "update"):
                for obj in sect.get(typ, []) or []:
                    for refkey in ("credential", "credentials"):
                        cref = obj.get(refkey)
                        if isinstance(cref, dict) and "name" in cref:
                            nm = cref["name"]
                            if nm in suffix_map:
                                cref["name"] = suffix_map[nm]
        return p

    # ---------- Response helpers ----------
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

    # ---------- Deploy ----------
    def deploy_vpn(self):
        url_cfg = f"{self.base_url}/api/universalinfra/v1/consolidated/configure"
        original_payload = self.config["vpn_payload"]

        # Resolve (reuse via id) or prepare name-bind mode
        create_payload, mode = self._resolve_or_create_credentials_in_payload(original_payload)

        # If we’re in name-bind mode, pre-uniquify to avoid duplicate-name collisions
        if mode == "by_name":
            create_payload = self.uniquify_credential_names(create_payload)

        # --- CREATE ---
        r = requests.post(url_cfg, headers=self.headers, json=create_payload)

        # If backend still says duplicate-name, uniquify and retry once (keeps creates)
        if r.status_code == 400 and "duplicate key name" in r.text.lower():
            print("⚠️  Duplicate-name on CREATE. Retrying once with uniquified credential names...")
            retry_payload = self.uniquify_credential_names(create_payload)
            r = requests.post(url_cfg, headers=self.headers, json=retry_payload)

        try:
            r.raise_for_status()
        except requests.exceptions.HTTPError:
            print("❌ Deployment failed (CREATE)")
            print(f"Status: {r.status_code}\nBody: {r.text}")
            if "failed to get credential" in r.text.lower():
                print("💡 Hint: A referenced credential name doesn’t exist in this account and could not be created. "
                      "Ensure your vpn_payload.credentials.create contains that name, or adjust the reference.")
            raise

        create_resp = r.json() if r.text else {}
        usvc_id = self._extract_usvc_id(create_resp)
        if not usvc_id:
            print("ℹ️ Full response (for debugging):")
            print(r.text)
            raise RuntimeError("CREATE succeeded but universal_service.id not found in response")

        print(f"✅ Created/updated universal service: {usvc_id} (credential mode: {mode})")

        # --- UPDATE (add Security) ---
        sec_cfg = self.config.get("security", {})
        if sec_cfg.get("enable", False):
            policy_id = self.get_security_policy_id(sec_cfg.get("policy_name"))
            print(f"🔐 Using security policy id: {policy_id}")

            usvc_name = original_payload["universal_service"]["name"]
            usvc_tags = original_payload["universal_service"].get("tags", {})

            update_payload = {
                "universal_service": {
                    "operation": "UPDATE",
                    "id": usvc_id,
                    "name": usvc_name,
                    "description": "",
                    "capabilities": [
                        {"type": "dfp", "profile_id": policy_id},
                        {"type": "dns", "profile_id": ""}  # keep DNS
                    ],
                    "tags": usvc_tags
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

    # ---------- Orchestrate ----------
    def run(self):
        self.authenticate()
        self.switch_account()
        self.deploy_vpn()


if __name__ == "__main__":
    InfobloxVPNDeployer("config_vpn.yaml").run()
