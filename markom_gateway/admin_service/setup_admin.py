#!/usr/bin/env python3
"""
MarKom Gateway — Admin Setup Script

Creates the initial admin user in the RBAC system.
Run this once after first deployment.

Usage:
    python -m markom_gateway.admin_service.setup_admin
    python -m markom_gateway.admin_service.setup_admin --user admin --role admin --api-key sk-your-key
"""

import argparse
import os
import sys

# Add parent dir to path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def main():
    parser = argparse.ArgumentParser(description="Setup MarKom Gateway admin user")
    parser.add_argument("--user", default="admin", help="External user ID (default: admin)")
    parser.add_argument("--email", default=None, help="Admin email")
    parser.add_argument("--name", default="Administrator", help="Display name")
    parser.add_argument("--role", default="admin", choices=["admin", "team_lead", "developer", "viewer"])
    parser.add_argument("--api-key", default=None, help="API key to associate with this user")
    parser.add_argument("--team-id", default=None, help="Team ID to assign role for")
    args = parser.parse_args()

    from markom_gateway.admin_service.markom_admin.rbac import RBACService, ROLE_PERMISSIONS

    print(f"Setting up user: {args.user}")
    print(f"  Role: {args.role}")
    if args.email:
        print(f"  Email: {args.email}")
    if args.team_id:
        print(f"  Team: {args.team_id}")
    if args.api_key:
        print(f"  API Key: {args.api_key[:8]}...")

    print(f"\nRole permissions ({args.role}):")
    for perm in sorted(ROLE_PERMISSIONS.get(args.role, set())):
        print(f"  - {perm}")

    success = RBACService.set_user_role(
        user_external_id=args.user,
        role=args.role,
        email=args.email,
        display_name=args.name,
        team_id=args.team_id,
        granted_by="system",
        api_key=args.api_key,
    )

    if success:
        print(f"\nUser '{args.user}' created/updated successfully with role '{args.role}'")
    else:
        print("\nFailed to create user. Check database connection and try again.")
        sys.exit(1)


if __name__ == "__main__":
    main()
