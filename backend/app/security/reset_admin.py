"""Set a new password for the admin account (the one from ADMIN_EMAIL), creating it if missing.

    docker compose exec backend python -m app.security.reset_admin            # random password, printed once
    docker compose exec backend python -m app.security.reset_admin 'my-pass'  # your own password (12+ characters)
"""

from __future__ import annotations

import asyncio
import secrets
import sys

from sqlalchemy import select

from app.core.config import get_settings
from app.core.time import utcnow
from app.database.session import session_scope
from app.models import User
from app.security.auth import hash_password


async def reset(password: str) -> str:
    email = get_settings().admin_email
    async with session_scope() as session:
        user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            user = User(email=email, display_name="World Admin", role="admin", created_at=utcnow(), password_hash="")
            session.add(user)
        user.password_hash = hash_password(password)
        user.role = "admin"
        await session.commit()
    return email


def main() -> None:
    password = sys.argv[1] if len(sys.argv) > 1 else secrets.token_urlsafe(15)
    if len(password) < 12:
        sys.exit("the password must be at least 12 characters")
    email = asyncio.run(reset(password))
    print(f"admin login: {email}\npassword:    {password}")


if __name__ == "__main__":
    main()
