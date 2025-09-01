import os
import json
import requests

class InfobloxSession:
    def __init__(self):
        self.base_url = "https://csp.infoblox.com"
        self.email = os.getenv("INFOBLOX_EMAIL")
        self.password = os.getenv("INFOBLOX_PASSWORD")
        self.jwt = None
        self.session = requests.Session()
        self.headers = {"Content-Type": "application/json"}

    def _auth_headers(self):
        return {
            "Authorization": f"Bearer {self.jwt}",
            "Content-Type": "application/json"
        }

    def _read_file(self, filename):
        with open(filename, "r") as f:
            return f.read().strip()

    def _save_to_file(self, filename, content):
        with open(filename, "w") as f:
            f.write(content)

    def login(self):
        url = f"{self.base_url}/v2/session/users/sign_in"
        payload = {"email": self.email, "password": self.password}
        response = self.session.post(url, headers=self.headers, json=payload)
        response.raise_for_status()
        self.jwt = response.json().get("jwt")
        print("✅ Logged in")

    def switch_account(self):
        sandbox_id = self._read_file("sandbox_id.txt")
        url = f"{self.base_url}/v2/session/account_switch"
        payload = {"id": f"identity/accounts/{sandbox_id}"}
        response = self.session.post(url, headers=self._auth_headers(), json=payload)
        response.raise_for_status()
        self.jwt = response.json().get("jwt")
        print(f"✅ Switched to sandbox: {sandbox_id}")

    def get(self, endpoint, params=None):
        url = f"{self.base_url}{endpoint}"
        response = self.session.get(url, headers=self._auth_headers(), params=params or {})
        response.raise_for_status()
        return response.json()

    def post(self, endpoint, payload):
        url = f"{self.base_url}{endpoint}"
        response = self.session.post(url, headers=self._auth_headers(), json=payload)
        if response.status_code != 200:
            print(f"❌ Failed POST to {url}")
            print(f"Status Code: {response.status_code}")
            print(f"Response Text:\n{response.text}")
            print(f"Payload Sent:\n{json.dumps(payload, indent=2)}")
        response.raise_for_status()
        return response.json()

    # ---------- Helpers to fetch policy/capabilities ----------
    def get_default_security_policy_id(self):
        """
        Returns the default DFP/security policy id.
        """
        data = self.get("/api/atcfw/v1/security_policies", params={"_fields": "id,name,is_default"})
        for it in data.get("results", []):
            if it.get("is_default") is True:
                return str(it["id"])
        # Fallback: first item if no explicit default
        items = data.get("results", [])
        if items:
            return str(items[0]["id"])
        raise RuntimeError("No security policies found in tenant.")

    def get_universal_service(self, usvc_id):
        """
        Returns the universal service object including capabilities, if available.
        """
        return self.get(f"/api/universalinfra/v1/universal_services/{usvc_id}")

class TunnelUpdater:
    def __init__(self, session: InfobloxSession):
        self.session = session
        self.tunnel_file = "aws_tunnels.txt"

    def get_first_tunnel_ip(self):
        with open(self.tunnel_file, "r") as f:
            return f.readline().strip().split(",")[-1].strip()

    def _resolve_capabilities(self, usvc_id):
        """
        Prefer reusing current capabilities. If DFP missing or no capabilities
        returned, fall back to default security policy for DFP and keep DNS as-is.
        """
        dfp_profile_id = None
        dns_profile_id = None

        try:
            usvc = self.session.get_universal_service(usvc_id)
            caps = usvc.get("capabilities") or usvc.get("results", {}).get("capabilities") or []
            for cap in caps:
                ctype = cap.get("type")
                pid = cap.get("profile_id", "")
                if ctype == "dfp" and pid:
                    dfp_profile_id = pid
                if ctype == "dns":
                    # DNS may legitimately be empty string if "keep DNS"
                    dns_profile_id = pid if pid is not None else ""
        except requests.HTTPError:
            # If we can't fetch, we'll fall back below
            pass

        if not dfp_profile_id:
            # Must not be empty — backend enforces this
            dfp_profile_id = self.session.get_default_security_policy_id()

        # If DNS profile id is None, set to empty string to keep existing behavior
        if dns_profile_id is None:
            dns_profile_id = ""

        return dns_profile_id, dfp_profile_id

    def build_access_location_update(self, endpoint, access_loc, tunnel_ip, dns_profile_id, dfp_profile_id):
        pri_tunnel = access_loc["tunnel_configs"][0]
        sec_tunnel = access_loc["tunnel_configs"][1]

        pri_physical = pri_tunnel["physical_tunnels"][0]
        sec_physical = sec_tunnel["physical_tunnels"][0]

        access_location_payload = {
            "endpoint_id": endpoint["id"].split("/")[-1],
            "id": access_loc["id"].split("/")[-1],
            "routing_type": "dynamic",
            "type": "Cloud VPN",
            "name": access_loc["name"],
            "cloud_type": access_loc["cloud_type"],
            "cloud_region": access_loc["cloud_region"],
            "lan_subnets": [],
            "tunnel_configs": [
                {
                    "id": pri_tunnel["id"],
                    "name": pri_tunnel["name"],
                    "physical_tunnels": [
                        {
                            "path": pri_physical["path"],
                            "credential_id": pri_physical["credential_id"],
                            "index": 0,
                            "access_ip": tunnel_ip,
                            "bgp_configs": [
                                {
                                    "id": pri_physical["bgp_configs"][0]["id"],
                                    "asn": 64512,
                                    "hop_limit": 2,
                                    "cloud_cidr": pri_physical["bgp_configs"][0]["cloud_cidr"]
                                }
                            ]
                        }
                    ]
                },
                {
                    "id": sec_tunnel["id"],
                    "name": sec_tunnel["name"],
                    "physical_tunnels": [
                        {
                            "path": sec_physical["path"],
                            "credential_id": sec_physical["credential_id"],
                            "index": 0,
                            "access_ip": sec_physical["access_ip"],
                            "bgp_configs": [
                                {
                                    "id": sec_physical["bgp_configs"][0]["id"],
                                    "asn": 64512,
                                    "hop_limit": 2,
                                    "cloud_cidr": sec_physical["bgp_configs"][0]["cloud_cidr"]
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        endpoint_payload = {
            "id": endpoint["id"].split("/")[-1],
            "name": endpoint["name"],
            "size": endpoint["size"],
            "service_location": endpoint["service_location"],
            "service_ip": endpoint["service_ip"],
            "neighbour_ips": endpoint["neighbour_ips"],
            "preferred_provider": endpoint["preferred_provider"],
            "tags": {},
            "routing_type": endpoint["routing_type"],
            "routing_config": endpoint["routing_config"]
        }

        # Build capabilities: keep DNS (empty id is fine in your flow), set DFP to a real id
        caps = []
        # DNS first (preserve behavior)
        caps.append({"type": "dns", "profile_id": dns_profile_id if dns_profile_id is not None else ""})
        # DFP must NOT be empty
        caps.append({"type": "dfp", "profile_id": dfp_profile_id})

        return {
            "universal_service": {
                "operation": "UPDATE",
                "id": endpoint["universal_service_id"],
                "name": "Instrqt-SaaS",
                "description": "",
                "capabilities": caps,
                "tags": {}
            },
            "access_locations": {
                "create": [],
                "update": [access_location_payload],
                "delete": []
            },
            "endpoints": {
                "create": [],
                "update": [endpoint_payload],
                "delete": []
            },
            "credentials": {"create": [], "update": []},
            "locations": {"create": [], "update": []}
        }

    def update_primary_tunnel_ip(self):
        tunnel_ip = self.get_first_tunnel_ip()
        print(f"🛰️ Using Tunnel 1 IP: {tunnel_ip}")

        # Pull current endpoint + access location
        endpoint_data = self.session.get("/api/universalinfra/v1/endpoints/")
        access_data = self.session.get("/api/universalinfra/v1/accesslocations")

        endpoint = endpoint_data["result"]
        access_loc = access_data["results"][0]

        # Resolve capability profile IDs
        dns_pid, dfp_pid = self._resolve_capabilities(endpoint["universal_service_id"])

        payload = self.build_access_location_update(endpoint, access_loc, tunnel_ip, dns_pid, dfp_pid)
        _ = self.session.post("/api/universalinfra/v1/consolidated/configure", payload)
        print("🚀 Successfully updated primary tunnel IP!")


# === ENTRY POINT ===
if __name__ == "__main__":
    session = InfobloxSession()
    session.login()
    session.switch_account()

    updater = TunnelUpdater(session)
    updater.update_primary_tunnel_ip()
