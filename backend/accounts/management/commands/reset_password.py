import getpass

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from accounts.models import User
from accounts.views import validate_password


class Command(BaseCommand):
    help = "Reset any user's password by username"

    def add_arguments(self, parser):
        parser.add_argument("username", type=str, help="Username to reset")

    def handle(self, *args, **options):
        username = options["username"]

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f'User "{username}" does not exist')

        self.stdout.write(f"Resetting password for: {user.username}")

        while True:
            password = getpass.getpass("Enter new password: ")
            password_confirm = getpass.getpass("Confirm password: ")

            if password != password_confirm:
                self.stdout.write(self.style.ERROR("Passwords do not match. Try again."))
                continue

            is_valid, message = validate_password(password)
            if not is_valid:
                self.stdout.write(self.style.ERROR(f"Invalid password: {message}"))
                continue

            break

        user.password = make_password(password)
        user.save()

        self.stdout.write(
            self.style.SUCCESS(f'Successfully reset password for "{username}"')
        )
