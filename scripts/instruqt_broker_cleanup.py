#!/usr/bin/env python3
"""
Instruqt Sandbox Cleanup via Broker API

This script marks a sandbox for deletion when a student stops their lab.
The broker's background cleanup job will delete it from CSP within ~5 minutes.

Usage in Instruqt:
1. Set environment variables (same as allocation):
   - BROKER_API_URL
   - BROKER_API_TOKEN
   - INSTRUQT_PARTICIPANT_ID

2. Run this script in your Instruqt track stop/cleanup lifecycle hook
"""

import os
import sys
import requests

# ----------------------------------
# Configuration
# ----------------------------------
BROKER_API_URL = os.environ.get(
    "BROKER_API_URL",
    "https://api-sandbox-broker.highvelocitynetworking.com/v1"
)
BROKER_API_TOKEN = os.environ.get("BROKER_API_TOKEN")
INSTRUQT_SANDBOX_ID = os.environ.get("INSTRUQT_PARTICIPANT_ID")

# Input file (from allocation script)
SANDBOX_ID_FILE = "sandbox_id.txt"

# ----------------------------------
# Validation
# ----------------------------------
if not BROKER_API_TOKEN:
    print("❌ BROKER_API_TOKEN environment variable not set", flush=True)
    sys.exit(1)

if not INSTRUQT_SANDBOX_ID:
    print("❌ INSTRUQT_PARTICIPANT_ID not found", flush=True)
    sys.exit(1)

# Read sandbox_id from file
try:
    with open(SANDBOX_ID_FILE, "r") as f:
        sandbox_id = f.read().strip()
except FileNotFoundError:
    print(f"⚠️ {SANDBOX_ID_FILE} not found, nothing to clean up", flush=True)
    sys.exit(0)  # Not an error - might not have been allocated

if not sandbox_id:
    print("⚠️ Sandbox ID file is empty, nothing to clean up", flush=True)
    sys.exit(0)

print(f"🧹 Marking sandbox {sandbox_id} for deletion...", flush=True)

# ----------------------------------
# Mark Sandbox for Deletion
# ----------------------------------
delete_url = f"{BROKER_API_URL}/sandboxes/{sandbox_id}/mark-for-deletion"
headers = {
    "Authorization": f"Bearer {BROKER_API_TOKEN}",
    "X-Instruqt-Sandbox-ID": INSTRUQT_SANDBOX_ID,
}

try:
    resp = requests.post(
        delete_url,
        headers=headers,
        timeout=(5, 15),
    )

    if resp.status_code == 200:
        result = resp.json()
        print(f"✅ Sandbox marked for deletion", flush=True)
        print(f"   Status: {result.get('status')}", flush=True)
        print(f"   Cleanup: Background job will delete from CSP within ~5 minutes", flush=True)

    elif resp.status_code == 404:
        print(f"⚠️ Sandbox {sandbox_id} not found (may have already been cleaned up)", flush=True)

    elif resp.status_code == 403:
        error = resp.json()
        print(f"❌ Authorization error: {error.get('detail', {}).get('message', 'Unknown error')}", flush=True)
        sys.exit(1)

    else:
        print(f"❌ Failed to mark sandbox for deletion: HTTP {resp.status_code}", flush=True)
        print(f"   Response: {resp.text}", flush=True)
        sys.exit(1)

except Exception as e:
    print(f"❌ Error marking sandbox for deletion: {e}", flush=True)
    sys.exit(1)

print("="*60, flush=True)
print("✅ Cleanup request successful", flush=True)
print("="*60, flush=True)
