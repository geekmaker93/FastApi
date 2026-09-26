import argparse

from sqlalchemy import func

from app.database import SessionLocal, engine
from app.models.db_models import User, ensure_user_schema


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Grant admin access to one existing, verified FarmSense user."
    )
    parser.add_argument("email", help="Email address of the verified account to promote")
    email = parser.parse_args().email.strip().lower()
    if not email:
        parser.error("email cannot be blank")

    ensure_user_schema(engine)
    db = SessionLocal()
    try:
        user = db.query(User).filter(func.lower(User.email) == email).one_or_none()
        if user is None:
            parser.error("No existing user has that email; sign up and verify the account first")
        if not user.is_verified:
            parser.error("The account must be verified before it can be promoted")

        if not user.is_admin:
            user.is_admin = True
            db.commit()

        print(f"Admin access enabled for user id {user.id}.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()