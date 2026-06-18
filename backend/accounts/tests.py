# pyright: reportAttributeAccessIssue=false, reportImplicitRelativeImport=false, reportUninitializedInstanceVariable=false

import json

from django.test import TestCase
from rest_framework.authtoken.models import Token

from accounts.models import User


class JsonRequestMixin:
    def post_json(self, path, payload=None):
        return self.client.post(
            path,
            data=json.dumps(payload or {}),
            content_type="application/json",
        )


class RegisterTests(JsonRequestMixin, TestCase):
    path = "/api/auth/register/"

    def test_first_user_becomes_root(self):
        response = self.post_json(
            self.path,
            {"username": "root", "password": "Root12345", "email": "root@example.com"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["user"]["username"], "root")
        self.assertTrue(data["user"]["is_root"])
        self.assertTrue(data["user"]["premium_authority"])
        self.assertEqual(data["user"]["hidden_categories"], [])

        user = User.objects.get(username="root")
        self.assertTrue(user.is_root)
        self.assertTrue(user.premium_authority)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_register_normal_user(self):
        User.objects.create_user(
            username="root",
            password="Root12345",
            is_root=True,
            premium_authority=True,
        )

        response = self.post_json(
            self.path,
            {"username": "user", "password": "User12345", "email": "user@example.com"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["user"]["username"], "user")
        self.assertFalse(data["user"]["is_root"])
        self.assertFalse(data["user"]["premium_authority"])

        user = User.objects.get(username="user")
        self.assertFalse(user.is_root)
        self.assertFalse(user.premium_authority)

    def test_register_missing_fields(self):
        response = self.post_json(self.path, {"username": "user"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "Username and password are required"})

    def test_register_duplicate_username(self):
        User.objects.create_user(username="user", password="User12345")

        response = self.post_json(self.path, {"username": "user", "password": "Other12345"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "Username already exists"})


class LoginTests(JsonRequestMixin, TestCase):
    path = "/api/auth/login/"

    def setUp(self):
        self.user = User.objects.create_user(
            username="user",
            password="User12345",
            email="user@example.com",
            premium_authority=True,
            hidden_categories=[1, 2],
        )

    def test_login_success(self):
        response = self.post_json(self.path, {"username": "user", "password": "User12345"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["user"]["id"], self.user.id)
        self.assertEqual(data["user"]["username"], "user")
        self.assertEqual(data["user"]["email"], "user@example.com")
        self.assertTrue(data["user"]["premium_authority"])
        self.assertEqual(data["user"]["hidden_categories"], [1, 2])
        self.assertFalse(data["user"]["is_root"])
        self.assertTrue(data["user"]["is_active"])

    def test_login_invalid_credentials(self):
        response = self.post_json(self.path, {"username": "user", "password": "Wrong12345"})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"error": "Invalid credentials"})

    def test_login_missing_fields(self):
        response = self.post_json(self.path, {"username": "user"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "Username and password are required"})


class LogoutTests(TestCase):
    def test_logout_success(self):
        User.objects.create_user(username="user", password="User12345")
        self.client.login(username="user", password="User12345")

        response = self.client.post("/api/auth/logout/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"success": True, "message": "Logged out successfully"},
        )


class ProfileTests(TestCase):
    path = "/api/auth/profile/"

    def setUp(self):
        self.user = User.objects.create_user(
            username="user",
            password="User12345",
            email="user@example.com",
            premium_authority=True,
            hidden_categories=[3],
        )

    def test_profile_authenticated(self):
        self.client.login(username="user", password="User12345")

        response = self.client.get(self.path)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["user"]["id"], self.user.id)
        self.assertEqual(data["user"]["username"], "user")
        self.assertEqual(data["user"]["email"], "user@example.com")
        self.assertTrue(data["user"]["premium_authority"])
        self.assertEqual(data["user"]["hidden_categories"], [3])
        self.assertFalse(data["user"]["is_root"])
        self.assertTrue(data["user"]["is_active"])

    def test_profile_unauthenticated(self):
        response = self.client.get(self.path)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"error": "Not authenticated"})


class CheckRootTests(TestCase):
    path = "/api/auth/check-root/"

    def test_no_root_exists(self):
        response = self.client.get(self.path)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["root_exists"])
        self.assertEqual(data["message"], "Root user needs to be created")

    def test_root_exists(self):
        User.objects.create_user(username="root", password="Root12345", is_root=True)

        response = self.client.get(self.path)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["root_exists"])
        self.assertEqual(data["message"], "Use command: python manage.py reset_root_password")


class RegisterRootTests(JsonRequestMixin, TestCase):
    path = "/api/auth/register-root/"

    def test_register_root_success(self):
        response = self.post_json(
            self.path,
            {"username": "root", "password": "Root12345", "email": "root@example.com"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["message"], "Root user created successfully")
        self.assertEqual(data["user"]["username"], "root")
        self.assertTrue(data["user"]["is_root"])
        self.assertTrue(data["user"]["premium_authority"])

        user = User.objects.get(username="root")
        self.assertTrue(user.is_root)
        self.assertTrue(user.premium_authority)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_root_already_exists(self):
        User.objects.create_user(username="root", password="Root12345", is_root=True)

        response = self.post_json(
            self.path,
            {"username": "other-root", "password": "Root12345"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "Root user already exists"})

    def test_weak_password_rejected(self):
        response = self.post_json(self.path, {"username": "root", "password": "short"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {"error": "Password must be at least 8 characters long"},
        )


class UserManagementTests(JsonRequestMixin, TestCase):
    def setUp(self):
        self.root = User.objects.create_user(
            username="root",
            password="Root12345",
            email="root@example.com",
            is_root=True,
            premium_authority=True,
        )
        self.user = User.objects.create_user(
            username="user",
            password="User12345",
            email="user@example.com",
        )

    def login_root(self):
        self.client.login(username="root", password="Root12345")

    def login_user(self):
        self.client.login(username="user", password="User12345")

    def test_create_user_as_root(self):
        self.login_root()

        response = self.post_json(
            "/api/auth/create-user/",
            {
                "username": "created",
                "password": "Created12345",
                "email": "created@example.com",
                "premium_authority": True,
                "hidden_categories": [1, 4],
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["user"]["username"], "created")
        self.assertTrue(data["user"]["premium_authority"])
        self.assertEqual(data["user"]["hidden_categories"], [1, 4])

        user = User.objects.get(username="created")
        self.assertFalse(user.is_root)
        self.assertTrue(user.premium_authority)

    def test_create_user_as_non_root_forbidden(self):
        self.login_user()

        response = self.post_json(
            "/api/auth/create-user/",
            {"username": "created", "password": "Created12345"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"error": "Only root users can create users"})
        self.assertFalse(User.objects.filter(username="created").exists())

    def test_list_users_as_root(self):
        self.login_root()

        response = self.client.get("/api/auth/list-users/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        usernames = {user["username"] for user in data["users"]}
        self.assertEqual(usernames, {"root", "user"})

    def test_list_users_as_non_root_forbidden(self):
        self.login_user()

        response = self.client.get("/api/auth/list-users/")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"error": "Only root users can list users"})

    def test_update_user_success(self):
        self.login_root()

        response = self.post_json(
            f"/api/auth/update-user/{self.user.id}/",
            {
                "premium_authority": True,
                "hidden_categories": [5, 6],
                "email": "updated@example.com",
                "is_active": False,
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["user"]["email"], "updated@example.com")
        self.assertTrue(data["user"]["premium_authority"])
        self.assertEqual(data["user"]["hidden_categories"], [5, 6])
        self.assertFalse(data["user"]["is_active"])

        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "updated@example.com")
        self.assertTrue(self.user.premium_authority)
        self.assertEqual(self.user.hidden_categories, [5, 6])
        self.assertFalse(self.user.is_active)

    def test_update_user_as_non_root_forbidden(self):
        self.login_user()

        response = self.post_json(
            f"/api/auth/update-user/{self.user.id}/",
            {"premium_authority": True},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"error": "Only root users can update users"})

    def test_update_nonexistent_user(self):
        self.login_root()

        response = self.post_json("/api/auth/update-user/999999/", {"premium_authority": True})

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "User not found"})


class TokenTests(JsonRequestMixin, TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="user", password="User12345")

    def test_create_token_success(self):
        response = self.post_json(
            "/api/auth/tokens/create",
            {"username": "user", "password": "User12345"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["username"], "user")
        self.assertIn("token", data)
        self.assertIn("created_at", data)
        self.assertTrue(Token.objects.filter(user=self.user, key=data["token"]).exists())

    def test_create_token_invalid(self):
        response = self.post_json(
            "/api/auth/tokens/create",
            {"username": "user", "password": "Wrong12345"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"error": "Invalid credentials"})
        self.assertFalse(Token.objects.filter(user=self.user).exists())

    def test_list_tokens_authenticated(self):
        token = Token.objects.create(user=self.user)

        response = self.client.get(
            "/api/auth/tokens/list",
            HTTP_AUTHORIZATION=f"Bearer {token.key}",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["username"], "user")
        self.assertEqual(len(data["tokens"]), 1)
        self.assertEqual(data["tokens"][0]["key"], token.key[:8] + "...")
        self.assertIn("created_at", data["tokens"][0])

    def test_revoke_token_success(self):
        Token.objects.create(user=self.user)

        response = self.post_json(
            "/api/auth/tokens/revoke",
            {"username": "user", "password": "User12345"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"success": True, "message": "Token revoked successfully"},
        )
        self.assertFalse(Token.objects.filter(user=self.user).exists())


class UserHiddenCategoriesTests(JsonRequestMixin, TestCase):
    path = "/api/auth/user-hidden-categories/"

    def setUp(self):
        self.user = User.objects.create_user(
            username="user",
            password="User12345",
            hidden_categories=[1, 2],
            usr_def_hidden_categories=[2, 3],
        )

    def test_get_user_hidden_categories_authenticated(self):
        self.client.login(username="user", password="User12345")

        response = self.client.get(self.path)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["hidden_categories"], [1, 2])
        self.assertEqual(data["usr_def_hidden_categories"], [2, 3])
        self.assertCountEqual(data["combined_hidden_categories"], [1, 2, 3])

    def test_post_user_hidden_categories_updates_user_preferences(self):
        self.client.login(username="user", password="User12345")

        response = self.post_json(self.path, {"usr_def_hidden_categories": [4, 5]})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["hidden_categories"], [1, 2])
        self.assertEqual(data["usr_def_hidden_categories"], [4, 5])
        self.assertCountEqual(data["combined_hidden_categories"], [1, 2, 4, 5])

        self.user.refresh_from_db()
        self.assertEqual(self.user.usr_def_hidden_categories, [4, 5])

    def test_user_hidden_categories_unauthenticated(self):
        response = self.client.get(self.path)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"error": "Not authenticated"})
