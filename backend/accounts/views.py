from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.hashers import make_password
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
import json
import re
import uuid
import os
from .models import User


def validate_email(email):
    if not email:
        return False, "Email is required"
    email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    if not re.match(email_regex, email):
        return False, "Invalid email format"
    return True, "Valid email"


@csrf_exempt
@require_http_methods(["POST"])
def register(request):
    """User registration endpoint"""
    try:
        data = json.loads(request.body)
        username = data.get("username")
        password = data.get("password")
        email = data.get("email", "")

        if not username or not password:
            return JsonResponse(
                {"error": "Username and password are required"}, status=400
            )

        if email:
            is_email_valid, email_message = validate_email(email)
            if not is_email_valid:
                return JsonResponse({"error": email_message}, status=400)
            if User.objects.filter(email=email).exists():
                return JsonResponse({"error": "Email already registered"}, status=400)

        if User.objects.filter(username=username).exists():
            return JsonResponse({"error": "Username already exists"}, status=400)

        user = User.objects.create(
            username=username,
            email=email,
            password=make_password(password),
            premium_authority=False,
            hidden_categories=[],
        )

        return JsonResponse(
            {
                "success": True,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "premium_authority": user.premium_authority,
                    "hidden_categories": user.hidden_categories,
                },
            }
        )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@require_http_methods(["GET"])
def check_root_exists(request):
    """Check if root user exists"""
    root_exists = User.objects.filter(is_root=True).exists()
    return JsonResponse(
        {
            "root_exists": root_exists,
            "message": "Use command: python manage.py reset_root_password"
            if root_exists
            else "Root user needs to be created",
        }
    )


def validate_password(password):
    """Validate password requirements: numbers, lowercase, uppercase"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"

    if not re.search(r"[0-9]", password):
        return False, "Password must contain at least one number"

    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"

    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"

    return True, "Valid password"


@csrf_exempt
@require_http_methods(["POST"])
def register_root(request):
    """Register root user - only works if no root exists"""
    try:
        if User.objects.filter(is_root=True).exists():
            return JsonResponse({"error": "Root user already exists"}, status=400)

        data = json.loads(request.body)
        username = data.get("username")
        password = data.get("password")
        email = data.get("email", "")

        if not username or not password:
            return JsonResponse(
                {"error": "Username and password are required"}, status=400
            )

        # Validate password requirements
        is_valid, message = validate_password(password)
        if not is_valid:
            return JsonResponse({"error": message}, status=400)

        if User.objects.filter(username=username).exists():
            return JsonResponse({"error": "Username already exists"}, status=400)

        user = User.objects.create(
            username=username,
            email=email,
            password=make_password(password),
            is_root=True,
            premium_authority=True,
            is_staff=True,
            is_superuser=True,
            hidden_categories=[],
        )

        return JsonResponse(
            {
                "success": True,
                "message": "Root user created successfully",
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "is_root": user.is_root,
                    "premium_authority": user.premium_authority,
                },
            }
        )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def create_user(request):
    """Create normal user - only for root users"""
    if not request.user.is_authenticated or not request.user.is_root:
        return JsonResponse({"error": "Only root users can create users"}, status=403)

    try:
        data = json.loads(request.body)
        username = data.get("username")
        password = data.get("password")
        email = data.get("email", "")
        premium_authority = data.get("premium_authority", False)
        hidden_categories = data.get("hidden_categories", [])

        if not username or not password:
            return JsonResponse(
                {"error": "Username and password are required"}, status=400
            )

        if User.objects.filter(username=username).exists():
            return JsonResponse({"error": "Username already exists"}, status=400)

        user = User.objects.create(
            username=username,
            email=email,
            password=make_password(password),
            premium_authority=premium_authority,
            hidden_categories=hidden_categories,
            is_root=False,
        )

        return JsonResponse(
            {
                "success": True,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "premium_authority": user.premium_authority,
                    "hidden_categories": user.hidden_categories,
                },
            }
        )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@require_http_methods(["GET"])
def list_users(request):
    """List all users - only for root users"""
    if not request.user.is_authenticated or not request.user.is_root:
        return JsonResponse({"error": "Only root users can list users"}, status=403)

    users = User.objects.all().values(
        "id",
        "username",
        "email",
        "premium_authority",
        "hidden_categories",
        "is_root",
        "is_active",
        "created_at",
    )

    return JsonResponse({"success": True, "users": list(users)})


@csrf_exempt
@require_http_methods(["POST"])
def update_user(request, user_id):
    """Update user - only for root users"""
    if not request.user.is_authenticated or not request.user.is_root:
        return JsonResponse({"error": "Only root users can update users"}, status=403)

    try:
        user = User.objects.get(id=user_id)
        data = json.loads(request.body)

        # Don't allow modifying root status
        if "premium_authority" in data:
            user.premium_authority = data["premium_authority"]

        if "hidden_categories" in data:
            user.hidden_categories = data["hidden_categories"]

        if "email" in data:
            user.email = data["email"]

        if "is_active" in data:
            user.is_active = data["is_active"]

        user.save()

        return JsonResponse(
            {
                "success": True,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "premium_authority": user.premium_authority,
                    "hidden_categories": user.hidden_categories,
                    "is_active": user.is_active,
                },
            }
        )

    except User.DoesNotExist:
        return JsonResponse({"error": "User not found"}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def user_login(request):
    """User login endpoint"""
    try:
        data = json.loads(request.body)
        username = data.get("username")
        password = data.get("password")

        if not username or not password:
            return JsonResponse(
                {"error": "Username and password are required"}, status=400
            )

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return JsonResponse(
                {
                    "success": True,
                    "user": {
                        "id": user.id,
                        "username": user.username,
                        "email": user.email,
                        "premium_authority": user.premium_authority,
                        "hidden_categories": user.hidden_categories,
                        "is_root": user.is_root,
                        "is_active": user.is_active,
                    },
                }
            )
        else:
            return JsonResponse({"error": "Invalid credentials"}, status=401)

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@require_http_methods(["GET"])
def check_root_exists(request):
    """Check if root user exists"""
    root_exists = User.objects.filter(is_root=True).exists()
    return JsonResponse(
        {
            "root_exists": root_exists,
            "message": "Use command: python manage.py reset_root_password"
            if root_exists
            else "Root user needs to be created",
        }
    )


def validate_password(password):
    """Validate password requirements: numbers, lowercase, uppercase"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"

    if not re.search(r"[0-9]", password):
        return False, "Password must contain at least one number"

    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"

    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"

    return True, "Valid password"


@csrf_exempt
@require_http_methods(["POST"])
def register_root(request):
    """Register root user - only works if no root exists"""
    try:
        if User.objects.filter(is_root=True).exists():
            return JsonResponse({"error": "Root user already exists"}, status=400)

        data = json.loads(request.body)
        username = data.get("username")
        password = data.get("password")
        email = data.get("email", "")

        if not username or not password:
            return JsonResponse(
                {"error": "Username and password are required"}, status=400
            )

        # Validate password requirements
        is_valid, message = validate_password(password)
        if not is_valid:
            return JsonResponse({"error": message}, status=400)

        if User.objects.filter(username=username).exists():
            return JsonResponse({"error": "Username already exists"}, status=400)

        user = User.objects.create(
            username=username,
            email=email,
            password=make_password(password),
            is_root=True,
            premium_authority=True,
            is_staff=True,
            is_superuser=True,
            hidden_categories=[],
        )

        return JsonResponse(
            {
                "success": True,
                "message": "Root user created successfully",
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "is_root": user.is_root,
                    "premium_authority": user.premium_authority,
                },
            }
        )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def create_user(request):
    """Create normal user - only for root users"""
    if not request.user.is_authenticated or not request.user.is_root:
        return JsonResponse({"error": "Only root users can create users"}, status=403)

    try:
        data = json.loads(request.body)
        username = data.get("username")
        password = data.get("password")
        email = data.get("email", "")
        premium_authority = data.get("premium_authority", False)
        hidden_categories = data.get("hidden_categories", [])

        if not username or not password:
            return JsonResponse(
                {"error": "Username and password are required"}, status=400
            )

        if User.objects.filter(username=username).exists():
            return JsonResponse({"error": "Username already exists"}, status=400)

        user = User.objects.create(
            username=username,
            email=email,
            password=make_password(password),
            premium_authority=premium_authority,
            hidden_categories=hidden_categories,
            is_root=False,
        )

        return JsonResponse(
            {
                "success": True,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "premium_authority": user.premium_authority,
                    "hidden_categories": user.hidden_categories,
                },
            }
        )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@require_http_methods(["GET"])
def list_users(request):
    """List all users - only for root users"""
    if not request.user.is_authenticated or not request.user.is_root:
        return JsonResponse({"error": "Only root users can list users"}, status=403)

    users = User.objects.all().values(
        "id",
        "username",
        "email",
        "premium_authority",
        "hidden_categories",
        "is_root",
        "is_active",
        "created_at",
    )

    return JsonResponse({"success": True, "users": list(users)})


@csrf_exempt
@require_http_methods(["POST"])
def update_user(request, user_id):
    """Update user - only for root users"""
    if not request.user.is_authenticated or not request.user.is_root:
        return JsonResponse({"error": "Only root users can update users"}, status=403)

    try:
        user = User.objects.get(id=user_id)
        data = json.loads(request.body)

        # Don't allow modifying root status
        if "premium_authority" in data:
            user.premium_authority = data["premium_authority"]

        if "hidden_categories" in data:
            user.hidden_categories = data["hidden_categories"]

        if "email" in data:
            user.email = data["email"]

        if "is_active" in data:
            user.is_active = data["is_active"]

        user.save()

        return JsonResponse(
            {
                "success": True,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "premium_authority": user.premium_authority,
                    "hidden_categories": user.hidden_categories,
                    "is_active": user.is_active,
                },
            }
        )

    except User.DoesNotExist:
        return JsonResponse({"error": "User not found"}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def user_logout(request):
    """User logout endpoint"""
    logout(request)
    return JsonResponse({"success": True, "message": "Logged out successfully"})


@require_http_methods(["GET"])
def user_profile(request):
    """Get current user profile"""
    if request.user.is_authenticated:
        return JsonResponse(
            {
                "success": True,
                "user": {
                    "id": request.user.id,
                    "username": request.user.username,
                    "email": request.user.email,
                    "premium_authority": request.user.premium_authority,
                    "hidden_categories": request.user.hidden_categories,
                    "is_root": request.user.is_root,
                    "is_active": request.user.is_active,
                },
            }
        )
    else:
        return JsonResponse({"error": "Not authenticated"}, status=401)


@require_http_methods(["GET"])
def check_root_exists(request):
    """Check if root user exists"""
    root_exists = User.objects.filter(is_root=True).exists()
    return JsonResponse(
        {
            "root_exists": root_exists,
            "message": "Use command: python manage.py reset_root_password"
            if root_exists
            else "Root user needs to be created",
        }
    )


def validate_password(password):
    """Validate password requirements: numbers, lowercase, uppercase"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"

    if not re.search(r"[0-9]", password):
        return False, "Password must contain at least one number"

    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"

    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"

    return True, "Valid password"


@csrf_exempt
@require_http_methods(["POST"])
def register_root(request):
    """Register root user - only works if no root exists"""
    try:
        if User.objects.filter(is_root=True).exists():
            return JsonResponse({"error": "Root user already exists"}, status=400)

        data = json.loads(request.body)
        username = data.get("username")
        password = data.get("password")
        email = data.get("email", "")

        if not username or not password:
            return JsonResponse(
                {"error": "Username and password are required"}, status=400
            )

        # Validate password requirements
        is_valid, message = validate_password(password)
        if not is_valid:
            return JsonResponse({"error": message}, status=400)

        if User.objects.filter(username=username).exists():
            return JsonResponse({"error": "Username already exists"}, status=400)

        user = User.objects.create(
            username=username,
            email=email,
            password=make_password(password),
            is_root=True,
            premium_authority=True,
            is_staff=True,
            is_superuser=True,
            hidden_categories=[],
        )

        return JsonResponse(
            {
                "success": True,
                "message": "Root user created successfully",
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "is_root": user.is_root,
                    "premium_authority": user.premium_authority,
                },
            }
        )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def create_user(request):
    """Create normal user - only for root users"""
    if not request.user.is_authenticated or not request.user.is_root:
        return JsonResponse({"error": "Only root users can create users"}, status=403)

    try:
        data = json.loads(request.body)
        username = data.get("username")
        password = data.get("password")
        email = data.get("email", "")
        premium_authority = data.get("premium_authority", False)
        hidden_categories = data.get("hidden_categories", [])

        if not username or not password:
            return JsonResponse(
                {"error": "Username and password are required"}, status=400
            )

        if User.objects.filter(username=username).exists():
            return JsonResponse({"error": "Username already exists"}, status=400)

        user = User.objects.create(
            username=username,
            email=email,
            password=make_password(password),
            premium_authority=premium_authority,
            hidden_categories=hidden_categories,
            is_root=False,
        )

        return JsonResponse(
            {
                "success": True,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "premium_authority": user.premium_authority,
                    "hidden_categories": user.hidden_categories,
                },
            }
        )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@require_http_methods(["GET"])
def list_users(request):
    """List all users - only for root users"""
    if not request.user.is_authenticated or not request.user.is_root:
        return JsonResponse({"error": "Only root users can list users"}, status=403)

    users = User.objects.all().values(
        "id",
        "username",
        "email",
        "premium_authority",
        "hidden_categories",
        "is_root",
        "is_active",
        "created_at",
    )

    return JsonResponse({"success": True, "users": list(users)})


@csrf_exempt
@require_http_methods(["POST"])
def update_user(request, user_id):
    """Update user - only for root users"""
    if not request.user.is_authenticated or not request.user.is_root:
        return JsonResponse({"error": "Only root users can update users"}, status=403)

    try:
        user = User.objects.get(id=user_id)
        data = json.loads(request.body)

        # Don't allow modifying root status
        if "premium_authority" in data:
            user.premium_authority = data["premium_authority"]

        if "hidden_categories" in data:
            user.hidden_categories = data["hidden_categories"]

        if "email" in data:
            user.email = data["email"]

        if "is_active" in data:
            user.is_active = data["is_active"]

        user.save()

        return JsonResponse(
            {
                "success": True,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "premium_authority": user.premium_authority,
                    "hidden_categories": user.hidden_categories,
                    "is_active": user.is_active,
                },
            }
        )

    except User.DoesNotExist:
        return JsonResponse({"error": "User not found"}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


import uuid
from django.core.mail import send_mail
from django.utils import timezone
from datetime import timedelta


@csrf_exempt
@require_http_methods(["POST"])
def request_password_reset(request):
    """Request password reset email"""
    try:
        data = json.loads(request.body)
        email = data.get("email", "").strip().lower()

        if not email:
            return JsonResponse({"error": "Email is required"}, status=400)

        # Check if user exists with this email
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Don't reveal whether email exists
            return JsonResponse(
                {
                    "success": True,
                    "message": "If an account exists with this email, a password reset link will be sent.",
                }
            )

        # Generate reset token
        reset_token = str(uuid.uuid4())
        user.password_reset_token = reset_token
        user.password_reset_expires = timezone.now() + timedelta(
            seconds=getattr(settings, "PASSWORD_RESET_TIMEOUT", 3600)
        )
        user.save(update_fields=["password_reset_token", "password_reset_expires"])

        # Build reset URL
        # Try to auto-detect backend URL from request, fallback to env var or default
        host = request.get_host()
        scheme = "https" if request.is_secure() else "http"
        frontend_url = os.getenv("FRONTEND_URL", f"{scheme}://{host}")
        reset_url = f"{frontend_url}/reset-password?token={reset_token}&email={email}"

        # Send email (console backend in development)
        try:
            send_mail(
                subject="VidGo Password Reset",
                message=f"Click the following link to reset your password: {reset_url}\n\nThis link will expire in 1 hour.",
                from_email=getattr(
                    settings, "DEFAULT_FROM_EMAIL", "noreply@vidgo.local"
                ),
                recipient_list=[email],
                fail_silently=False,
            )
        except Exception as e:
            # In development, just log the URL
            print(f"Password reset URL: {reset_url}")
            print(f"Email send error: {str(e)}")

        return JsonResponse(
            {
                "success": True,
                "message": "If an account exists with this email, a password reset link will be sent.",
            }
        )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def reset_password(request):
    """Reset password with token"""
    try:
        data = json.loads(request.body)
        email = data.get("email", "").strip().lower()
        token = data.get("token", "").strip()
        new_password = data.get("new_password")

        if not email or not token or not new_password:
            return JsonResponse(
                {"error": "Email, token, and new password are required"}, status=400
            )

        # Validate password
        is_valid, message = validate_password(new_password)
        if not is_valid:
            return JsonResponse({"error": message}, status=400)

        # Find user and verify token
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return JsonResponse({"error": "Invalid or expired reset token"}, status=400)

        # Check token validity
        if (
            user.password_reset_token != token
            or user.password_reset_expires is None
            or timezone.now() > user.password_reset_expires
        ):
            return JsonResponse({"error": "Invalid or expired reset token"}, status=400)

        # Update password
        user.password = make_password(new_password)
        user.password_reset_token = None
        user.password_reset_expires = None
        user.save()

        return JsonResponse(
            {
                "success": True,
                "message": "Password reset successfully. You can now login with your new password.",
            }
        )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def update_own_profile(request):
    """Update own profile (email)"""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    try:
        data = json.loads(request.body)
        user = request.user

        # Update email if provided
        if "email" in data:
            new_email = data["email"].strip().lower()
            if new_email:
                # Check if email is already used by another user
                if User.objects.exclude(id=user.id).filter(email=new_email).exists():
                    return JsonResponse(
                        {"error": "Email is already in use"}, status=400
                    )
                user.email = new_email

        user.save()

        return JsonResponse(
            {
                "success": True,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "premium_authority": user.premium_authority,
                    "is_root": user.is_root,
                    "is_active": user.is_active,
                },
            }
        )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def user_hidden_categories(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Not authenticated"}, status=401)

    try:
        if request.method == "GET":
            user = request.user
            combined_hidden_categories = user.get_combined_hidden_categories()
            return JsonResponse(
                {
                    "success": True,
                    "hidden_categories": user.hidden_categories or [],
                    "usr_def_hidden_categories": user.usr_def_hidden_categories or [],
                    "combined_hidden_categories": combined_hidden_categories,
                }
            )

        elif request.method == "POST":
            data = json.loads(request.body)
            user = request.user

            if "usr_def_hidden_categories" in data:
                user.usr_def_hidden_categories = data["usr_def_hidden_categories"]
                user.save(update_fields=["usr_def_hidden_categories"])

            return JsonResponse(
                {
                    "success": True,
                    "hidden_categories": user.hidden_categories or [],
                    "usr_def_hidden_categories": user.usr_def_hidden_categories or [],
                    "combined_hidden_categories": user.get_combined_hidden_categories(),
                }
            )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def create_api_token(request):
    """Create a new API token using username and password"""
    try:
        data = json.loads(request.body)
        username = data.get("username")
        password = data.get("password")

        if not username or not password:
            return JsonResponse(
                {"error": "Username and password are required"}, status=400
            )

        user = authenticate(request, username=username, password=password)
        if user is None:
            return JsonResponse({"error": "Invalid credentials"}, status=401)

        from rest_framework.authtoken.models import Token
        
        existing_token = Token.objects.filter(user=user).first()
        if existing_token:
            existing_token.delete()
        
        token = Token.objects.create(user=user)

        return JsonResponse({
            "success": True,
            "token": token.key,
            "username": user.username,
            "created_at": token.created.isoformat(),
        })

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@require_http_methods(["GET"])
def list_api_tokens(request):
    """List all API tokens for the authenticated user"""
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)

    try:
        from rest_framework.authtoken.models import Token
        tokens = Token.objects.filter(user=request.user).values(
            'id', 'key', 'created'
        )

        token_list = []
        for t in tokens:
            token_list.append({
                'id': t['id'],
                'key': t['key'][:8] + '...',
                'created_at': t['created'].isoformat() if t['created'] else None,
            })

        return JsonResponse({
            "success": True,
            "username": request.user.username,
            "tokens": token_list,
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def revoke_api_token(request):
    """Revoke an API token using username and password"""
    try:
        data = json.loads(request.body)
        username = data.get("username")
        password = data.get("password")
        token_id = data.get("token_id")

        if not username or not password:
            return JsonResponse(
                {"error": "Username and password are required"}, status=400
            )

        if not token_id:
            return JsonResponse({"error": "token_id is required"}, status=400)

        user = authenticate(request, username=username, password=password)
        if user is None:
            return JsonResponse({"error": "Invalid credentials"}, status=401)

        from rest_framework.authtoken.models import Token
        token = Token.objects.filter(id=token_id, user=user).first()

        if not token:
            return JsonResponse({"error": "Token not found"}, status=404)

        token.delete()

        return JsonResponse({
            "success": True,
            "message": "Token revoked successfully",
        })

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
