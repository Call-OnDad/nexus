#!/usr/bin/env python3
"""Grant the call-on-dad service account Viewer access on all 4 GA4 properties.

Bypasses the GA4 web UI (which rejects SA emails with "doesn't match a Google
Account") by going straight to the Analytics Admin API. The API has its own
validator that accepts SA principals.

Usage on Windows desktop:

  pip install google-analytics-admin google-auth-oauthlib
  python add_sa_to_ga4.py

A browser window will open. Sign in as mediaserver2407@gmail.com, allow access.
The script then adds the SA to all 4 properties.
"""
import os
import sys
import json

CLIENT_SECRET_PATH = r"C:\Users\anton\Desktop\Call-On\Documentation\client_secret_278559443060-tk6mm39ht5521mifdovbp3qfbqci9i4v.apps.googleusercontent.com.json"

SA_EMAIL = "command-central@call-on-dad.iam.gserviceaccount.com"

PROPERTIES = {
    "call-on.dad":   "514109553",
    "call-on.mom":   "538804272",
    "call-on.media": "538833050",
    "call-on.shop":  "538904485",
}

SCOPES = ["https://www.googleapis.com/auth/analytics.manage.users"]


def main():
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        # AccessBinding is in admin_v1alpha (v1beta only has data-access reports).
        from google.analytics.admin_v1alpha import AnalyticsAdminServiceClient
        from google.analytics.admin_v1alpha.types import AccessBinding
        from google.api_core.exceptions import AlreadyExists, PermissionDenied, GoogleAPICallError
    except ImportError as e:
        print(f"\nMissing dependency: {e}")
        print("Install with:")
        print('  pip install google-analytics-admin google-auth-oauthlib')
        sys.exit(1)

    if not os.path.exists(CLIENT_SECRET_PATH):
        print(f"Client secret JSON not found at {CLIENT_SECRET_PATH}")
        sys.exit(1)

    print(f"Loading client secret from {CLIENT_SECRET_PATH}")
    flow  = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_PATH, SCOPES)
    print("\nOpening browser for OAuth.  Sign in as mediaserver2407@gmail.com,")
    print("review the requested scope, click Allow.\n")
    creds = flow.run_local_server(port=0, prompt="consent")
    print("Got credentials.\n")

    client = AnalyticsAdminServiceClient(credentials=creds)

    for name, prop_id in PROPERTIES.items():
        parent = f"properties/{prop_id}"
        binding = AccessBinding(
            user=SA_EMAIL,
            roles=["predefinedRoles/viewer"],
        )
        try:
            result = client.create_access_binding(parent=parent, access_binding=binding)
            print(f"[OK]   {name:<14} ({prop_id})  -> {result.name}")
        except AlreadyExists:
            print(f"[SKIP] {name:<14} ({prop_id})  SA already has access")
        except PermissionDenied as e:
            print(f"[FAIL] {name:<14} ({prop_id})  PERMISSION_DENIED: {e}")
        except GoogleAPICallError as e:
            print(f"[FAIL] {name:<14} ({prop_id})  {type(e).__name__}: {e}")
        except Exception as e:
            print(f"[FAIL] {name:<14} ({prop_id})  {type(e).__name__}: {e}")

    print("\nDone.  Now hit /api/ga4/summary from NEXUS to verify.")


if __name__ == "__main__":
    main()
