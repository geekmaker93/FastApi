import unittest
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.dependencies import get_current_user, get_db
from app.models.db_models import AnalyticsEvent, User
from app.routes.admin import router


class AdminApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        User.__table__.create(self.engine)
        AnalyticsEvent.__table__.create(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)

        with self.session_factory() as db:
            admin = User(
                name="Admin",
                email="admin@example.com",
                password="hashed",
                is_admin=True,
                is_verified=True,
            )
            member = User(
                name="Member",
                email="member@example.com",
                password="hashed",
                is_admin=False,
                is_verified=True,
            )
            db.add_all([admin, member])
            db.flush()
            self.member_id = member.id
            db.add(
                AnalyticsEvent(
                    user_id=member.id,
                    event_name="app_opened",
                    event_data={},
                    platform="android",
                )
            )
            db.commit()

        self.app = FastAPI()
        self.app.include_router(router)
        self.app.state.current_user = SimpleNamespace(is_admin=False)
        self.app.dependency_overrides[get_current_user] = lambda: self.app.state.current_user

        def override_db():
            with self.session_factory() as db:
                yield db

        self.app.dependency_overrides[get_db] = override_db
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.engine.dispose()

    def test_admin_routes_require_authentication_and_admin_role(self):
        self.app.dependency_overrides.pop(get_current_user)
        self.assertEqual(self.client.get("/admin/overview").status_code, 401)

        self.app.dependency_overrides[get_current_user] = lambda: self.app.state.current_user
        self.assertEqual(self.client.get("/admin/overview").status_code, 403)

    def test_admin_endpoints_return_aggregates_and_user_activity(self):
        self.app.state.current_user = SimpleNamespace(is_admin=True)

        overview = self.client.get("/admin/overview")
        self.assertEqual(overview.status_code, 200)
        self.assertEqual(
            overview.json(),
            {"total_users": 2, "total_events": 1, "active_users": 1},
        )

        users = self.client.get("/admin/users").json()
        member = next(user for user in users if user["id"] == self.member_id)
        self.assertEqual(member["email_masked"], "m***@example.com")
        self.assertEqual(member["event_count"], 1)
        self.assertNotIn("email", member)

        activity = self.client.get(f"/admin/users/{self.member_id}")
        self.assertEqual(activity.status_code, 200)
        self.assertEqual(activity.json()["user"]["email"], "member@example.com")
        self.assertEqual(activity.json()["events"][0]["event_name"], "app_opened")

        self.assertEqual(
            self.client.get("/admin/analytics/features").json(),
            [{"event_name": "app_opened", "usage": 1}],
        )
        self.assertEqual(len(self.client.get("/admin/analytics/events?limit=1").json()), 1)
        self.assertEqual(self.client.get("/admin/analytics/events?limit=501").status_code, 422)


if __name__ == "__main__":
    unittest.main()