from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom User model with additional fields for premium features and hidden categories"""

    premium_authority = models.BooleanField(
        default=False,
        help_text="Whether the user has premium access to advanced features",
    )

    is_root = models.BooleanField(
        default=False, help_text="Whether the user is a root user with admin privileges"
    )

    hidden_categories = models.JSONField(
        default=list,
        blank=True,
        help_text="List of category IDs that are hidden from this user (system-wide)",
    )

    usr_def_hidden_categories = models.JSONField(
        default=list,
        blank=True,
        help_text="List of category IDs that are hidden by user preference",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    password_reset_token = models.CharField(max_length=255, blank=True, null=True)
    password_reset_expires = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "auth_user"
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        return self.username

    def has_premium_access(self):
        """Check if user has premium authority"""
        return self.premium_authority

    def is_root_user(self):
        """Check if user is root user"""
        return self.is_root

    def hide_category(self, category_id):
        """Add a category to the user's hidden categories list"""
        if category_id not in self.hidden_categories:
            self.hidden_categories.append(category_id)
            self.save()

    def unhide_category(self, category_id):
        """Remove a category from the user's hidden categories list"""
        if category_id in self.hidden_categories:
            self.hidden_categories.remove(category_id)
            self.save()

    def is_category_hidden(self, category_id):
        """Check if a specific category is hidden for this user (either system-wide or user-defined)"""
        return category_id in self.get_combined_hidden_categories()

    def get_combined_hidden_categories(self):
        """Get combined list of hidden categories (system + user-defined)"""
        combined = list(self.hidden_categories) + list(self.usr_def_hidden_categories)
        return list(set(combined))  # Remove duplicates

    def hide_category_user(self, category_id):
        """Add a category to the user's defined hidden categories list"""
        if category_id not in self.usr_def_hidden_categories:
            self.usr_def_hidden_categories.append(category_id)
            self.save()

    def unhide_category_user(self, category_id):
        """Remove a category from the user's defined hidden categories list"""
        if category_id in self.usr_def_hidden_categories:
            self.usr_def_hidden_categories.remove(category_id)
            self.save()

    def is_category_user_hidden(self, category_id):
        """Check if a specific category is hidden by user preference (not system-wide)"""
        return category_id in self.usr_def_hidden_categories
