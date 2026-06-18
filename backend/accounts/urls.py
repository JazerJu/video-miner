from django.urls import path
from . import views

urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", views.user_login, name="login"),
    path("logout/", views.user_logout, name="logout"),
    path("profile/", views.user_profile, name="profile"),
    path("check-root/", views.check_root_exists, name="check_root_exists"),
    path("register-root/", views.register_root, name="register_root"),
    path("create-user/", views.create_user, name="create_user"),
    path("list-users/", views.list_users, name="list_users"),
    path("update-user/<int:user_id>/", views.update_user, name="update_user"),
    path(
        "user-hidden-categories/",
        views.user_hidden_categories,
        name="user_hidden_categories",
    ),
    path("tokens/create", views.create_api_token, name="create_api_token"),
    path("tokens/list", views.list_api_tokens, name="list_api_tokens"),
    path("tokens/revoke", views.revoke_api_token, name="revoke_api_token"),
]
