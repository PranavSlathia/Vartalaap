#!/usr/bin/env python3
"""Migrate business configuration from YAML to database.

This script reads the existing YAML config files and creates corresponding
Business records in the database. It also sets up phone number mappings.

Usage:
    python scripts/migrate_yaml_to_db.py

    # With specific phone number
    python scripts/migrate_yaml_to_db.py --phone +911234567890

    # Dry run (no changes)
    python scripts/migrate_yaml_to_db.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.models import Business, BusinessPhoneNumber, BusinessStatus, BusinessType
from src.db.session import get_sync_engine
from sqlmodel import Session


def load_yaml_config(config_path: Path) -> dict:
    """Load and parse YAML config file."""
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path) as f:
        return yaml.safe_load(f)


def create_business_from_yaml(config: dict, business_id: str) -> Business:
    """Create Business model from YAML config dict."""
    business_config = config.get("business", {})
    reservation_rules = config.get("reservation_rules", {})

    # Map business type
    type_str = business_config.get("type", "restaurant")
    try:
        business_type = BusinessType(type_str)
    except ValueError:
        business_type = BusinessType.other

    # Serialize JSON fields
    operating_hours_json = None
    if "operating_hours" in business_config:
        operating_hours_json = json.dumps(business_config["operating_hours"])

    reservation_rules_json = None
    if reservation_rules:
        reservation_rules_json = json.dumps(reservation_rules)

    # Create default greeting
    name = business_config.get("name", "Restaurant")
    greeting = (
        f"Namaste! {name} mein aapka swagat hai. "
        "Yeh call service improvement ke liye transcribe ho sakti hai. "
        "Main aapki kaise madad kar sakti hoon?"
    )

    return Business(
        id=business_id,
        name=name,
        type=business_type,
        timezone=business_config.get("timezone", "Asia/Kolkata"),
        status=BusinessStatus.active,
        operating_hours_json=operating_hours_json,
        reservation_rules_json=reservation_rules_json,
        greeting_text=greeting,
        menu_summary=None,  # To be filled in via admin UI
        admin_password_hash=None,  # Uses global admin for MVP
    )


def migrate_business(
    session: Session,
    config_path: Path,
    phone_numbers: list[str] | None = None,
    dry_run: bool = False,
) -> Business | None:
    """Migrate a single business from YAML to database.

    Args:
        session: Database session
        config_path: Path to YAML config file
        phone_numbers: Optional list of phone numbers to associate
        dry_run: If True, don't commit changes

    Returns:
        Created Business object, or None if dry run
    """
    # Extract business_id from filename
    business_id = config_path.stem  # e.g., "himalayan_kitchen"

    print(f"\n{'='*60}")
    print(f"Migrating: {business_id}")
    print(f"Config: {config_path}")
    print(f"{'='*60}")

    # Load YAML config
    config = load_yaml_config(config_path)

    # Create Business model
    business = create_business_from_yaml(config, business_id)

    print(f"\nBusiness Details:")
    print(f"  ID: {business.id}")
    print(f"  Name: {business.name}")
    print(f"  Type: {business.type.value}")
    print(f"  Timezone: {business.timezone}")
    print(f"  Status: {business.status.value}")

    if business.operating_hours_json:
        hours = json.loads(business.operating_hours_json)
        print(f"\nOperating Hours:")
        for day, time_range in hours.items():
            print(f"  {day}: {time_range}")

    if business.reservation_rules_json:
        rules = json.loads(business.reservation_rules_json)
        print(f"\nReservation Rules:")
        for key, value in rules.items():
            print(f"  {key}: {value}")

    print(f"\nGreeting Text:")
    print(f"  {business.greeting_text}")

    if dry_run:
        print("\n[DRY RUN] No changes made to database")
        return None

    # Check if business already exists
    existing = session.get(Business, business_id)
    if existing:
        print(f"\n[WARNING] Business '{business_id}' already exists")
        update = input("Update existing record? (y/n): ").lower().strip()
        if update != "y":
            print("Skipping...")
            return existing

        # Update existing
        existing.name = business.name
        existing.type = business.type
        existing.timezone = business.timezone
        existing.operating_hours_json = business.operating_hours_json
        existing.reservation_rules_json = business.reservation_rules_json
        if not existing.greeting_text:
            existing.greeting_text = business.greeting_text
        session.add(existing)
        business = existing
        print("Updated existing business record")
    else:
        session.add(business)
        print("Created new business record")

    # Add phone number mappings
    if phone_numbers:
        print(f"\nPhone Number Mappings:")
        for i, phone in enumerate(phone_numbers):
            # Check if mapping already exists
            existing_mapping = session.get(BusinessPhoneNumber, phone)
            if existing_mapping:
                print(f"  {phone} - already mapped to {existing_mapping.business_id}")
                continue

            mapping = BusinessPhoneNumber(
                phone_number=phone,
                business_id=business_id,
                is_primary=(i == 0),
            )
            session.add(mapping)
            print(f"  {phone} - mapped (primary: {i == 0})")

    session.commit()
    print("\nChanges committed to database")

    return business


def migrate_all_businesses(
    session: Session,
    config_dir: Path,
    dry_run: bool = False,
) -> list[Business]:
    """Migrate all YAML configs in a directory.

    Args:
        session: Database session
        config_dir: Directory containing YAML config files
        dry_run: If True, don't commit changes

    Returns:
        List of created/updated Business objects
    """
    businesses = []

    yaml_files = list(config_dir.glob("*.yaml")) + list(config_dir.glob("*.yml"))

    if not yaml_files:
        print(f"No YAML files found in {config_dir}")
        return businesses

    print(f"Found {len(yaml_files)} config file(s)")

    for config_path in yaml_files:
        try:
            business = migrate_business(session, config_path, dry_run=dry_run)
            if business:
                businesses.append(business)
        except Exception as e:
            print(f"\n[ERROR] Failed to migrate {config_path}: {e}")

    return businesses


def main():
    parser = argparse.ArgumentParser(
        description="Migrate business YAML configs to database"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/business"),
        help="Path to config directory or single YAML file",
    )
    parser.add_argument(
        "--phone",
        action="append",
        help="Phone number(s) to associate with the business (E.164 format)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without making changes",
    )

    args = parser.parse_args()

    # Get database session
    engine = get_sync_engine()
    with Session(engine) as session:
        if args.config.is_file():
            # Single file
            migrate_business(
                session,
                args.config,
                phone_numbers=args.phone,
                dry_run=args.dry_run,
            )
        elif args.config.is_dir():
            # Directory of configs
            if args.phone:
                print("[WARNING] --phone is ignored when migrating a directory")
            migrate_all_businesses(session, args.config, dry_run=args.dry_run)
        else:
            print(f"Config path not found: {args.config}")
            sys.exit(1)

    print("\nMigration complete!")


if __name__ == "__main__":
    main()
