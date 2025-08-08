import boto3

OUTPUT_FILE = "aws_tunnels.txt"

def extract_tunnel_ips():
    ec2 = boto3.client("ec2", region_name="eu-central-1")
    vpn_connections = ec2.describe_vpn_connections()["VpnConnections"]

    # Collect VPN data with name for sorting
    vpn_data = []
    for vpn in vpn_connections:
        vpn_id = vpn["VpnConnectionId"]
        name = next(
            (tag["Value"] for tag in vpn.get("Tags", []) if tag["Key"] == "Name"),
            vpn_id  # fallback to ID
        )
        tunnels = vpn.get("Options", {}).get("TunnelOptions", [])
        vpn_data.append((name, vpn_id, tunnels))

    # Sort by VPN name
    vpn_data.sort(key=lambda x: x[0].lower())  # Case-insensitive

    with open(OUTPUT_FILE, "w") as f:
        for name, vpn_id, tunnels in vpn_data:
            for idx, tunnel in enumerate(tunnels, start=1):
                outside_ip = tunnel.get("OutsideIpAddress")
                if outside_ip:
                    line = f"{vpn_id}, Tunnel {idx}, {outside_ip}\n"
                    f.write(line)
                    print(f"✅ {line.strip()}")

    print(f"\n📄 Tunnel IPs saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    extract_tunnel_ips()
