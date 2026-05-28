#!/usr/bin/env python3
"""
Bootstrap the first superadmin user for a fresh pilot deployment.

Run inside the backend container after `alembic upgrade head`:

    docker compose --env-file .env.production run --rm backend \\
        python scripts/create_pilot_admin.py \\
        --email admin@yourcompany.cz \\
        --full-name "Pilot Admin" \\
        --password "YourStr0ng!Pass"

Idempotent: exits cleanly if a superadmin already exists.
Also seeds the global work catalog (analysis profiles, pricing, work types)
on first run — safe to repeat.
"""
import argparse
import asyncio
import sys
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.security import enforce_password_strength
from app.db.bootstrap import _seed_global_work_catalog
from app.models.domain import Organization, User
from app.services.auth_service import hash_password


async def _create_superadmin(email: str, full_name: str, password: str) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        result = await session.execute(
            select(User).where(User.is_superadmin.is_(True)).limit(1)
        )
        existing = result.scalar_one_or_none()
        if existing:
            print(f"Superadmin already exists: {existing.email}")
            print("Use the admin API (/api/v1/admin/users) to add additional users.")
        else:
            org_id = "org_novu"
            org = await session.get(Organization, org_id)
            if org is None:
                org = Organization(
                    id=org_id,
                    name="NOVU Builder Platform",
                    ico="",
                    email=email,
                    default_currency="CZK",
                )
                session.add(org)
                print(f"Created organization: {org.name}  (id={org_id})")

            user_id = f"usr_{uuid.uuid4().hex[:12]}"
            user = User(
                id=user_id,
                organization_id=org_id,
                email=email,
                password_hash=hash_password(password),
                full_name=full_name,
                role="superadmin",
                is_active=True,
                is_superadmin=True,
            )
            session.add(user)
            await session.commit()
            print(f"Superadmin created: {email}  (id={user_id})")

    async with Session() as session:
        print("Seeding global work catalog (analysis profiles, pricing, work types)...")
        report = await _seed_global_work_catalog(session)
        print(f"Work catalog seeded: inserted={report.inserted} updated={report.updated} unchanged={report.unchanged}")

    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create first superadmin for pilot deployment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Password requirements: min 10 chars, "
            "upper + lower + digit + special character."
        ),
    )
    parser.add_argument("--email", required=True, help="Superadmin email address")
    parser.add_argument("--full-name", required=True, dest="full_name", help="Display name")
    parser.add_argument("--password", required=True, help="Initial password")
    args = parser.parse_args()

    try:
        enforce_password_strength(args.password)
    except ValueError as e:
        print(f"Password rejected: {e}", file=sys.stderr)
        sys.exit(1)

    asyncio.run(_create_superadmin(args.email, args.full_name, args.password))
    print("Done.")


if __name__ == "__main__":
    main()
