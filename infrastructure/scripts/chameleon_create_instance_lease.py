#!/usr/bin/env python3
"""
Chameleon KVM@TACC: create a Blazar instance lease, then print shell exports for Terraform.

Mirrors the MLOps-on-Chameleon lab flow (lease -> note reservation id -> TF_VAR_* -> terraform),
without requiring Jupyter: run this file from a terminal or from the companion notebook.

Prerequisites (same as the lab OpenStack cells):
  - python-openstackclient + Chameleon python-blazarclient in this Python environment:
      pip install python-openstackclient \
        'git+https://github.com/ChameleonCloud/python-blazarclient.git@chameleoncloud/xena'
  - ~/.config/openstack/clouds.yaml (application credential). Example:
      export OS_CLOUD=openstack

Reservation shape:
  Course examples often use resource_type=flavor:instance,flavor_id=<nova flavor id>.
  The Chameleon python-blazarclient shipped for OSC only parses virtual:instance with
  vcpus, memory_mb, disk_gb (see blazarclient leases.py). This script builds that line
  from `openstack flavor show -f json`, equivalent capacity to the lab's m1.* lease.

Usage:
  python3 infrastructure/scripts/chameleon_create_instance_lease.py --keypair <horizon-keypair-name> [LEASE_NAME] [FLAVOR] [HOURS]

Examples:
  python3 infrastructure/scripts/chameleon_create_instance_lease.py --keypair id_rsa_chameleon
  python3 infrastructure/scripts/chameleon_create_instance_lease.py --keypair id_rsa_chameleon proj17-lease-1 m1.xxlarge 72
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone


def _run_openstack(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["openstack", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def _require_openstack_reservation() -> None:
    r = _run_openstack(["reservation", "lease", "list"])
    if r.returncode != 0:
        sys.stderr.write(
            "Error: 'openstack reservation' failed. Install Chameleon Blazar client, e.g.:\n"
            "  pip install 'git+https://github.com/ChameleonCloud/python-blazarclient.git@chameleoncloud/xena'\n"
        )
        if r.stderr:
            sys.stderr.write(r.stderr)
        sys.exit(1)


def _flavor_record(name: str) -> dict:
    r = _run_openstack(["flavor", "show", name, "-f", "json"])
    if r.returncode != 0:
        sys.stderr.write(r.stderr or r.stdout or "openstack flavor show failed\n")
        sys.exit(1)
    return json.loads(r.stdout)


def _lease_window_utc(hours: float) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    start = now + timedelta(seconds=30)
    end = now + timedelta(hours=hours)
    fmt = "%Y-%m-%d %H:%M"
    return start.strftime(fmt), end.strftime(fmt)


def _virtual_instance_reservation(flavor_name: str) -> str:
    f = _flavor_record(flavor_name)
    vcpus = f.get("vcpus")
    ram = f.get("ram")
    disk = f.get("disk")
    if vcpus is None or ram is None:
        sys.stderr.write(
            f"Error: could not read vcpus/ram from flavor {flavor_name!r} (openstack flavor show -f json)\n"
        )
        sys.exit(1)
    if disk is None or int(disk) <= 0:
        sys.stderr.write(
            f"Error: flavor {flavor_name!r} has disk={disk!r}; need non-zero root disk for virtual:instance.\n"
        )
        sys.exit(1)
    return (
        f"resource_type=virtual:instance,vcpus={int(vcpus)},"
        f"memory_mb={int(ram)},disk_gb={int(disk)},amount=1"
    )


def _create_lease(name: str, start: str, end: str, reservation: str) -> None:
    sys.stderr.write(
        f"Creating lease {name!r} ({start} UTC -> {end} UTC)\n  {reservation}\n"
    )
    r = _run_openstack(
        [
            "reservation",
            "lease",
            "create",
            "--start-date",
            start,
            "--end-date",
            end,
            "--reservation",
            reservation,
            name,
        ]
    )
    if r.returncode != 0:
        sys.stderr.write(r.stderr or r.stdout or "openstack reservation lease create failed\n")
        sys.exit(r.returncode)


def _wait_lease_active(name: str, timeout_sec: int = 600, poll_sec: int = 5) -> None:
    deadline = time.monotonic() + timeout_sec
    last_shown = None
    final_status = None
    while time.monotonic() < deadline:
        r = _run_openstack(["reservation", "lease", "show", name, "-f", "value", "-c", "status"])
        status = (r.stdout or "").strip() or "UNKNOWN"
        final_status = status
        if status != last_shown:
            sys.stderr.write(f"  status: {status}\n")
            last_shown = status
        low = status.lower()
        if low == "error":
            sys.stderr.write("Lease entered ERROR. Check Horizon -> Reservations -> Leases.\n")
            _run_openstack(["reservation", "lease", "show", name])
            sys.exit(1)
        if low == "active":
            return
        time.sleep(poll_sec)
    sys.stderr.write(
        f"Timeout waiting for ACTIVE (last status: {final_status}). Try:\n"
        f"  openstack reservation lease show {name}\n"
    )
    sys.exit(1)


def _reservation_flavor_id(lease_name: str) -> str:
    r = _run_openstack(["reservation", "lease", "show", lease_name, "-f", "json"])
    if r.returncode != 0:
        sys.stderr.write(r.stderr or r.stdout or "lease show failed\n")
        sys.exit(1)
    data = json.loads(r.stdout)
    reservations = data.get("reservations") or []
    if not reservations:
        sys.stderr.write("Lease JSON has no reservations.\n")
        sys.stderr.write(r.stdout)
        sys.exit(1)
    first = reservations[0]
    fid = first.get("flavor_id") or first.get("id")
    if not fid:
        sys.stderr.write("Could not read flavor_id/id from first reservation.\n")
        sys.stderr.write(r.stdout)
        sys.exit(1)
    return str(fid)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Create a Chameleon Blazar instance lease and print TF_VAR exports for Terraform.",
    )
    default_lease = f"mlops-lease-{os.getenv('USER', 'user')}-{datetime.now(timezone.utc):%Y%m%d%H%M%S}"
    parser.add_argument(
        "--keypair",
        required=True,
        metavar="NAME",
        help="OpenStack Horizon key pair name (printed as TF_VAR_keypair_name; lab: TF_VAR_key).",
    )
    parser.add_argument(
        "--prefix",
        default="proj17",
        help="Printed as TF_VAR_prefix (lab: TF_VAR_suffix). Default: %(default)s.",
    )
    parser.add_argument("lease_name", nargs="?", default=default_lease)
    parser.add_argument("flavor", nargs="?", default="m1.xxlarge")
    parser.add_argument("hours", nargs="?", type=float, default=48.0)
    args = parser.parse_args(argv)

    _require_openstack_reservation()
    start, end = _lease_window_utc(args.hours)
    reservation = _virtual_instance_reservation(args.flavor)
    _create_lease(args.lease_name, start, end, reservation)
    _wait_lease_active(args.lease_name)
    flavor_uuid = _reservation_flavor_id(args.lease_name)

    # Match this repo's variable name (reservation_id). Course PDF often says TF_VAR_reservation.
    print()
    print(f"# Lease name (Horizon / CLI only): {args.lease_name}")
    print("# Paste into your shell, then: cd infrastructure/terraform && terraform plan && terraform apply")
    print()
    print(f'export TF_VAR_reservation_id="{flavor_uuid}"')
    print(f'export TF_VAR_prefix="{args.prefix}"')
    print(f'export TF_VAR_keypair_name="{args.keypair}"')
    print()
    print("# Course lab naming (GourmetGram tf used reservation + suffix + key):")
    print(f'#   export TF_VAR_reservation="{flavor_uuid}"   # use TF_VAR_reservation_id in this repo')
    print(f'#   export TF_VAR_suffix="{args.prefix}"        # use TF_VAR_prefix in this repo')
    print(f'#   export TF_VAR_key="{args.keypair}"          # use TF_VAR_keypair_name in this repo')
    print()
    print("Verify Nova reservation flavor:")
    print(f"  openstack flavor list | grep {flavor_uuid}")
    print()
    print("Terraform (from repo root):")
    print("  cd infrastructure/terraform && terraform init && terraform plan && terraform apply")


if __name__ == "__main__":
    main()
