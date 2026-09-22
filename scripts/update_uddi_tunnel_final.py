#!/usr/bin/env python3
"""
Point the NIOS-X-aaS access location at the real AWS tunnel endpoints.

The access location is created earlier (infoblox_vpn_configure_final.py) with
placeholder tunnel IPs, because the AWS side cannot be built until the Cloud
Service IPs exist. This script replaces those placeholders with the real ones.

It does so by DELETING and RECREATING the access location rather than updating
it in place. Updating in place brings IPsec up but leaves BGP unconfigured on
the Infoblox PoP: the session never leaves Active, no packets are emitted, and
AWS reports "IPSEC IS UP" with the tunnel DOWN and 0 accepted routes forever.
Recreating with the final values in the initial create establishes BGP in a
couple of minutes. See PTOPA-27769 (DpTunnelId churn on wanIP update leaves the
BGP source loopback without its address).

Tunnels are matched to AWS by inside CIDR (Infoblox cloud_cidr == AWS
TunnelInsideCidr), which is the only stable key shared by both sides.
"""

import os
import re
import sys
import json
import time
import uuid
import yaml
import boto3
import requests

AWS_REGION = os.environ.get("AWS_REGION", "eu-west-2")
CONFIG_FILE = "config_vpn.yaml"

# Deleted tunnel IDs sit in a 120s deferred pool. Recreating before it drains
# risks the controller allocating a fresh ID and leaving the BGP loopback unset.
DELETE_SETTLE_SECONDS = 180

POLL_ATTEMPTS = 12
POLL_INTERVAL = 10


def load_config(path=CONFIG_FILE):
    with open(path) as f:
        raw = f.read()
    interpolated = re.sub(
        r"\$\{(\w+)\}",
        lambda m: os.environ.get(m.group(1), f"<MISSING:{m.group(1)}>"),
        raw,
    )
    return yaml.safe_load(interpolated)


class InfobloxSession:
    def __init__(self):
        self.base_url = "https://csp.infoblox.com"
        self.email = os.getenv("INFOBLOX_EMAIL")
        self.password = os.getenv("INFOBLOX_PASSWORD")
        self.jwt = None
        self.session = requests.Session()

    def _headers(self):
        return {"Authorization": f"Bearer {self.jwt}", "Content-Type": "application/json"}

    def login(self):
        r = self.session.post(
            f"{self.base_url}/v2/session/users/sign_in",
            json={"email": self.email, "password": self.password},
        )
        r.raise_for_status()
        self.jwt = r.json()["jwt"]
        print("✅ Logged in")

    def switch_account(self):
        with open("sandbox_id.txt") as f:
            sandbox_id = f.read().strip()
        r = self.session.post(
            f"{self.base_url}/v2/session/account_switch",
            headers=self._headers(),
            json={"id": f"identity/accounts/{sandbox_id}"},
        )
        r.raise_for_status()
        self.jwt = r.json()["jwt"]
        print(f"✅ Switched to sandbox: {sandbox_id}")

    def get(self, endpoint):
        r = self.session.get(f"{self.base_url}{endpoint}", headers=self._headers())
        r.raise_for_status()
        return r.json()

    def configure(self, payload, tag):
        """POST to consolidated/configure, retrying while another op is in flight."""
        url = f"{self.base_url}/api/universalinfra/v1/consolidated/configure"
        for attempt in range(POLL_ATTEMPTS):
            r = self.session.post(url, headers=self._headers(), json=payload)
            if r.status_code not in (409, 429):
                break
            print(f"⏳ [{tag}] operation in progress, retry {attempt + 1}...")
            time.sleep(POLL_INTERVAL)

        if r.status_code >= 400:
            print(f"❌ [{tag}] failed: HTTP {r.status_code}\n{r.text}")
            r.raise_for_status()
        print(f"✅ [{tag}] accepted")
        return r.json() if r.text else {}


class AccessLocationRebuilder:
    def __init__(self, session):
        self.session = session
        self.psk = self._psk_from_config()

    @staticmethod
    def _psk_from_config():
        """Reuse the PSK the access location was originally built with.

        It must stay in step with PRE_SHARED_KEY in create_aws_vpn.py, otherwise
        IKE fails.
        """
        creds = load_config()["vpn_payload"]["credentials"]["create"]
        return creds[0]["value"]

    @staticmethod
    def aws_tunnels_by_inside_cidr():
        ec2 = boto3.client("ec2", region_name=AWS_REGION)
        mapping = {}
        for vpn in ec2.describe_vpn_connections()["VpnConnections"]:
            if vpn.get("State") == "deleted":
                continue
            for opt in vpn.get("Options", {}).get("TunnelOptions", []):
                cidr, ip = opt.get("TunnelInsideCidr"), opt.get("OutsideIpAddress")
                if cidr and ip:
                    mapping[cidr] = ip
        return mapping

    def _capabilities(self, usvc_id):
        """Preserve the DNS and Security capabilities across the rebuild."""
        dns_profile, dfp_profile = "", None
        try:
            usvc = self.session.get(f"/api/universalinfra/v1/universal_services/{usvc_id}")
            caps = usvc.get("capabilities") or usvc.get("results", {}).get("capabilities") or []
            for cap in caps:
                if cap.get("type") == "dfp" and cap.get("profile_id"):
                    dfp_profile = cap["profile_id"]
                if cap.get("type") == "dns":
                    dns_profile = cap.get("profile_id") or ""
        except requests.HTTPError:
            pass

        if not dfp_profile:
            policies = self.session.get(
                "/api/atcfw/v1/security_policies?_fields=id,name,is_default"
            ).get("results", [])
            default = next((p for p in policies if p.get("is_default")), policies[0])
            dfp_profile = str(default["id"])

        return [
            {"type": "dns", "profile_id": dns_profile},
            {"type": "dfp", "profile_id": dfp_profile},
        ]

    @staticmethod
    def _tunnel_spec(access_loc, cidr_to_ip):
        """Describe each tunnel with the real AWS outside IP it should point at."""
        spec = []
        for tunnel in access_loc["tunnel_configs"]:
            physical = tunnel["physical_tunnels"][0]
            bgp = physical["bgp_configs"][0]
            cloud_cidr = bgp["cloud_cidr"]

            access_ip = cidr_to_ip.get(cloud_cidr)
            if access_ip:
                print(f"🛰️ {tunnel['name']} ({cloud_cidr}) -> {access_ip}")
            else:
                access_ip = physical["access_ip"]
                print(f"⚠️ {tunnel['name']}: no AWS tunnel with inside CIDR {cloud_cidr}, "
                      f"keeping {access_ip}")

            spec.append({
                "name": tunnel["name"],
                "path": physical["path"],
                "access_ip": access_ip,
                "neighbour_ip": bgp["neighbour_ips"][0],
                "asn": bgp["asn"],
                "hop_limit": bgp["hop_limit"],
            })
        return spec

    def _build_create(self, endpoint, access_loc, spec, usvc):
        credentials, tunnel_configs = [], []
        for index, tunnel in enumerate(spec, start=1):
            ref = f"ref_cred_{index}"
            credentials.append({
                "id": ref,
                "type": "psk",
                "name": f"{tunnel['name'].lower()}-{uuid.uuid4().hex[:6]}",
                "value": self.psk,
                "cred_data": {},
            })
            tunnel_configs.append({
                "name": tunnel["name"],
                "physical_tunnels": [{
                    "path": tunnel["path"],
                    "credential_id": ref,
                    "index": 0,
                    "access_ip": tunnel["access_ip"],
                    "bgp_configs": [{
                        "asn": str(tunnel["asn"]),
                        "hop_limit": tunnel["hop_limit"],
                        "neighbour_ips": [tunnel["neighbour_ip"]],
                    }],
                }],
            })

        return {
            "universal_service": usvc,
            "access_locations": {
                "create": [{
                    "endpoint_id": endpoint["id"].split("/")[-1],
                    "routing_type": "dynamic",
                    "type": "Cloud VPN",
                    "name": access_loc["name"],
                    "cloud_type": access_loc["cloud_type"],
                    "cloud_region": access_loc["cloud_region"],
                    "lan_subnets": [],
                    "tunnel_configs": tunnel_configs,
                }],
                "update": [],
                "delete": [],
            },
            "endpoints": {"create": [], "update": [], "delete": []},
            "credentials": {"create": credentials, "update": []},
            "locations": {"create": [], "update": []},
        }

    def run(self):
        endpoint = self.session.get("/api/universalinfra/v1/endpoints/")["result"]
        access_locations = self.session.get("/api/universalinfra/v1/accesslocations")["results"]
        if not access_locations:
            sys.exit("❌ No access location found. Run infoblox_vpn_configure_final.py first.")
        access_loc = access_locations[0]

        cnames_before = endpoint["cnames"]
        print(f"📡 Cloud Service IPs: {cnames_before}")

        spec = self._tunnel_spec(access_loc, self.aws_tunnels_by_inside_cidr())
        usvc = {
            "operation": "UPDATE",
            "id": endpoint["universal_service_id"],
            "name": "Instrqt-SaaS",
            "description": "",
            "capabilities": self._capabilities(endpoint["universal_service_id"]),
            "tags": {},
        }

        self.session.configure({
            "universal_service": usvc,
            "access_locations": {
                "create": [],
                "update": [],
                "delete": [access_loc["id"].split("/")[-1]],
            },
            "endpoints": {"create": [], "update": [], "delete": []},
            "credentials": {"create": [], "update": []},
            "locations": {"create": [], "update": []},
        }, "delete")

        print(f"⏳ Waiting {DELETE_SETTLE_SECONDS}s for the tunnel ID pool to drain...")
        time.sleep(DELETE_SETTLE_SECONDS)

        self.session.configure(
            self._build_create(endpoint, access_loc, spec, usvc), "create"
        )

        cnames_after = self.session.get("/api/universalinfra/v1/endpoints/")["result"]["cnames"]
        if cnames_after != cnames_before:
            print(f"❌ Cloud Service IPs changed to {cnames_after} — the AWS customer "
                  f"gateways now point at the wrong addresses and must be rebuilt.")
            sys.exit(1)

        self._report()

    def _report(self):
        print("⏳ Waiting for tunnels to connect...")
        for _ in range(POLL_ATTEMPTS):
            time.sleep(POLL_INTERVAL)
            results = self.session.get("/api/universalinfra/v1/accesslocations")["results"]
            statuses = {
                t["name"]: t["physical_tunnels"][0].get("status")
                for t in results[0]["tunnel_configs"]
            }
            print(f"   {json.dumps(statuses)}")
            if all(s == "Connected" for s in statuses.values()):
                break

        print("\n🚀 Access location rebuilt with the real tunnel IPs.")
        print("   BGP can take a few more minutes to establish. Confirm with:")
        print("   aws ec2 describe-vpn-connections --region eu-west-2 | jq -r "
              "'.VpnConnections[].VgwTelemetry[] | \"\\(.OutsideIpAddress) \\(.Status) "
              "routes=\\(.AcceptedRouteCount) \\(.StatusMessage)\"'")


if __name__ == "__main__":
    session = InfobloxSession()
    session.login()
    session.switch_account()
    AccessLocationRebuilder(session).run()
