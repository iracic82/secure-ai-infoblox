#!/usr/bin/env python3

import os
import boto3
import sys
import re
from datetime import datetime, timezone

# ---------------------------
# Setup logging
# ---------------------------
log_file = "dns_log_gm_cleanup.txt"
source_log_file = "dns_log_gm.txt"
timestamp = datetime.now(timezone.utc).isoformat()
log_lines = [f"\n--- GM DNS Record Deletion Log [{timestamp}] ---\n"]

def log(message):
    print(message)
    log_lines.append(message + "\n")

# ---------------------------
# AWS credentials
# ---------------------------
aws_access_key_id = os.getenv("DEMO_AWS_ACCESS_KEY_ID")
aws_secret_access_key = os.getenv("DEMO_AWS_SECRET_ACCESS_KEY")
region = os.getenv("DEMO_AWS_REGION", "us-east-1")
hosted_zone_id = os.getenv("DEMO_HOSTED_ZONE_ID")

if not aws_access_key_id or not aws_secret_access_key or not hosted_zone_id:
    log("❌ ERROR: AWS credentials or Hosted Zone ID missing")
    sys.exit(1)

# ---------------------------
# Extract FQDN and IP from dns_log_gm.txt
# ---------------------------
if not os.path.exists(source_log_file):
    log(f"❌ ERROR: Log file '{source_log_file}' not found.")
    sys.exit(1)

fqdn, ip = None, None
with open(source_log_file, "r") as f:
    for line in f:
        match = re.search(r"✅  A record created: (.+?) -> ([\d.]+)", line)
        if match:
            fqdn = match.group(1).strip()
            ip = match.group(2).strip()
            break

if not fqdn or not ip:
    log("❌ ERROR: No 'A record created' line found in log.")
    sys.exit(1)

# ---------------------------
# Boto3 session
# ---------------------------
session = boto3.Session(
    aws_access_key_id=aws_access_key_id,
    aws_secret_access_key=aws_secret_access_key,
    region_name=region
)
route53 = session.client("route53")

# ---------------------------
# Delete A record
# ---------------------------
log(f"🧹 Deleting A record: {fqdn} -> {ip}")
try:
    route53.change_resource_record_sets(
        HostedZoneId=hosted_zone_id,
        ChangeBatch={
            "Comment": f"Delete GM A record {fqdn}",
            "Changes": [
                {
                    "Action": "DELETE",
                    "ResourceRecordSet": {
                        "Name": fqdn,
                        "Type": "A",
                        "TTL": 300,
                        "ResourceRecords": [{"Value": ip}]
                    }
                }
            ]
        }
    )
    log(f"✅ Successfully deleted: {fqdn}")
except route53.exceptions.InvalidChangeBatch as e:
    log(f"⚠️  Record {fqdn} may not exist or is already deleted: {e}")
except Exception as e:
    log(f"❌ ERROR during deletion: {e}")
    sys.exit(1)

# ---------------------------
# Write cleanup log
# ---------------------------
with open(log_file, "a") as f:
    f.writelines(log_lines)

log(f"📄 Cleanup log written to {log_file}")
