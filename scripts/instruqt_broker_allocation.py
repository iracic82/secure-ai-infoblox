#!/usr/bin/env python3
"""
Instruqt Sandbox Allocation via Broker API

This script allocates a pre-created sandbox from the broker instead of
creating a new one directly in CSP.

Usage in Instruqt:
1. Set environment variables:
   - BROKER_API_URL (default: https://api-sandbox-broker.highvelocitynetworking.com/v1)
   - BROKER_API_TOKEN (required)
   - INSTRUQT_PARTICIPANT_ID (provided by Instruqt)
   - INSTRUQT_TRACK_SLUG (provided by Instruqt - lab identifier)

2. Run this script in your Instruqt track setup
3. Script will allocate a sandbox and save IDs to files
"""

import os
import sys
import time
import random
import requests

# ----------------------------------
# Configuration
# ----------------------------------
BROKER_API_URL = os.environ.get(
    "BROKER_API_URL",
    "https://api-sandbox-broker.highvelocitynetworking.com/v1"
)
BROKER_API_TOKEN = os.environ.get("BROKER_API_TOKEN")

# Instruqt provides these automatically
INSTRUQT_SANDBOX_ID = os.environ.get("INSTRUQT_PARTICIPANT_ID")
INSTRUQT_TRACK_ID = os.environ.get("INSTRUQT_TRACK_SLUG", "unknown-lab")

# Optional: Filter sandboxes by name prefix (e.g., "lab-adventure")
# Only allocate sandboxes whose names start with this prefix
SANDBOX_NAME_PREFIX = os.environ.get("SANDBOX_NAME_PREFIX")

# Output files
SANDBOX_ID_FILE = "sandbox_id.txt"
EXTERNAL_ID_FILE = "external_id.txt"
SANDBOX_NAME_FILE = "sandbox_name.txt"

# Startup jitter (avoid collision when multiple students start simultaneously)
time.sleep(random.uniform(1, 5))

# ----------------------------------
# Validation
# ----------------------------------
if not BROKER_API_TOKEN:
    print("❌ BROKER_API_TOKEN environment variable not set", flush=True)
    sys.exit(1)

if not INSTRUQT_SANDBOX_ID:
    print("❌ INSTRUQT_PARTICIPANT_ID not found (are you running in Instruqt?)", flush=True)
    sys.exit(1)

print(f"🎓 Student: {INSTRUQT_SANDBOX_ID}", flush=True)
print(f"📚 Lab: {INSTRUQT_TRACK_ID}", flush=True)
if SANDBOX_NAME_PREFIX:
    print(f"🔍 Filter: Only allocate sandboxes starting with '{SANDBOX_NAME_PREFIX}'", flush=True)

# ----------------------------------
# Allocate Sandbox from Broker
# ----------------------------------
allocate_url = f"{BROKER_API_URL}/allocate"
headers = {
    "Authorization": f"Bearer {BROKER_API_TOKEN}",
    "Content-Type": "application/json",
    "X-Instruqt-Sandbox-ID": INSTRUQT_SANDBOX_ID,
    "X-Instruqt-Track-ID": INSTRUQT_TRACK_ID,
}

# Add optional name prefix filter (server-side filtering)
if SANDBOX_NAME_PREFIX:
    headers["X-Sandbox-Name-Prefix"] = SANDBOX_NAME_PREFIX

max_retries = 5
retryable_statuses = {500, 502, 503, 504}

allocation_response = None
for attempt in range(max_retries):
    try:
        print(f"🔄 Allocation attempt {attempt + 1}/{max_retries}...", flush=True)

        resp = requests.post(
            allocate_url,
            headers=headers,
            timeout=(5, 30),  # connect=5s, read=30s
        )

        # Success (201 = new allocation, 200 = idempotent retry)
        if resp.status_code in (200, 201):
            allocation_response = resp.json()
            status_emoji = "✅" if resp.status_code == 201 else "🔄"
            print(f"{status_emoji} Sandbox allocated (HTTP {resp.status_code})", flush=True)
            break

        # Pool exhausted - no sandboxes available
        elif resp.status_code == 409:
            print("❌ Pool exhausted: No sandboxes available", flush=True)
            print("   Contact your instructor to provision more sandboxes", flush=True)
            sys.exit(1)

        # Rate limited by WAF
        elif resp.status_code == 403:
            print("⚠️ Rate limited by WAF, waiting before retry...", flush=True)
            time.sleep(10)  # Wait longer for WAF cooldown
            continue

        # Retryable server errors
        elif resp.status_code in retryable_statuses:
            print(f"⚠️ Server error {resp.status_code}, retrying...", flush=True)
            sleep_time = min(2 ** attempt + random.uniform(0, 1), 30)
            time.sleep(sleep_time)
            continue

        # Non-retryable error
        else:
            print(f"❌ Allocation failed with HTTP {resp.status_code}", flush=True)
            print(f"   Response: {resp.text}", flush=True)
            sys.exit(1)

    except requests.exceptions.Timeout:
        print(f"⚠️ Request timeout, retrying...", flush=True)
        sleep_time = min(2 ** attempt + random.uniform(0, 1), 30)
        time.sleep(sleep_time)

    except Exception as e:
        print(f"⚠️ Unexpected error: {e}", flush=True)
        sleep_time = min(2 ** attempt + random.uniform(0, 1), 30)
        time.sleep(sleep_time)

else:
    print("❌ Sandbox allocation failed after all retries", flush=True)
    sys.exit(1)

# ----------------------------------
# Extract IDs from Response
# ----------------------------------
# Response format:
# {
#   "sandbox_id": "2012224",
#   "name": "sandbox-1",
#   "external_id": "af06cbf7-b07c-4c4f-bfa4-bd7dd0e2d4c3",
#   "allocated_at": 1728054123,
#   "expires_at": 1728070323
# }

sandbox_id = allocation_response.get("sandbox_id")
external_id = allocation_response.get("external_id")
sandbox_name = allocation_response.get("name")
expires_at = allocation_response.get("expires_at")

if not sandbox_id or not external_id:
    print("❌ Invalid response: missing sandbox_id or external_id", flush=True)
    print(f"   Response: {allocation_response}", flush=True)
    sys.exit(1)

# Extract just the UUID from external_id (strip "identity/accounts/" prefix)
# Match old script behavior: external_id.split("/")[-1]
if external_id and "/" in external_id:
    external_id = external_id.split("/")[-1]

# ----------------------------------
# Save to Files
# ----------------------------------
with open(SANDBOX_ID_FILE, "w") as f:
    f.write(sandbox_id)
print(f"✅ Sandbox ID saved to {SANDBOX_ID_FILE}: {sandbox_id}", flush=True)

with open(EXTERNAL_ID_FILE, "w") as f:
    f.write(external_id)
print(f"✅ External ID saved to {EXTERNAL_ID_FILE}: {external_id}", flush=True)

with open(SANDBOX_NAME_FILE, "w") as f:
    f.write(sandbox_name)
print(f"✅ Sandbox name saved to {SANDBOX_NAME_FILE}: {sandbox_name}", flush=True)

# ----------------------------------
# Export as Environment Variables
# ----------------------------------
# Create a shell script that can be sourced to set environment variables
# Python can't modify parent shell's environment, so we generate a sourceable script
ENV_SCRIPT = "sandbox_env.sh"
with open(ENV_SCRIPT, "w") as f:
    f.write(f"#!/bin/bash\n")
    f.write(f"# Auto-generated by instruqt_broker_allocation.py\n")
    f.write(f"export STUDENT_TENANT={sandbox_name}\n")
    f.write(f"export CSP_ACCOUNT_ID={external_id}\n")
    f.write(f"export SANDBOX_ID={sandbox_id}\n")

print(f"\n💡 To use these variables in bash:", flush=True)
print(f"   source {ENV_SCRIPT}", flush=True)
print(f"\n   Or for Instruqt (persists across steps):", flush=True)
print(f"   set-var STUDENT_TENANT {sandbox_name}", flush=True)
print(f"   set-var CSP_ACCOUNT_ID {external_id}", flush=True)

# ----------------------------------
# Summary
# ----------------------------------
print("\n" + "="*60, flush=True)
print("🎉 Sandbox Allocation Complete!", flush=True)
print(f"   Name: {sandbox_name}", flush=True)
print(f"   Sandbox ID: {sandbox_id}", flush=True)
print(f"   External ID: {external_id} (use this to connect to CSP)", flush=True)
print(f"   Expires: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(expires_at))}", flush=True)
print("="*60, flush=True)
