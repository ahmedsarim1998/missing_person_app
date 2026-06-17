"""
Admin password-reset / recovery utility.

Usage (from the backend folder):
    python reset_admin.py                      # reset 'admin' to a random password (printed once)
    python reset_admin.py --password "S3cret!" # reset to a specific password
    python reset_admin.py --username admin --password "S3cret!"

The new password is read from --password or the ADMIN_RESET_PASSWORD env var;
if neither is given a strong random password is generated and printed once.
"""

import argparse
import os
import secrets

from app import create_app
from extensions import db
from models import User
from werkzeug.security import generate_password_hash


def main():
    parser = argparse.ArgumentParser(description="Reset / create the admin account")
    parser.add_argument('--username', default=os.environ.get('ADMIN_USERNAME', 'admin'))
    parser.add_argument('--password', default=os.environ.get('ADMIN_RESET_PASSWORD'))
    parser.add_argument('--email', default=os.environ.get('ADMIN_EMAIL', 'admin@locaite.com'))
    args = parser.parse_args()

    password = args.password or secrets.token_urlsafe(12)
    generated = not args.password
    if len(password) < 8:
        parser.error("Password must be at least 8 characters.")

    app = create_app()
    with app.app_context():
        admin = User.query.filter_by(username=args.username).first()
        if admin:
            admin.password_hash = generate_password_hash(password)
            admin.role = 'admin'
            print(f"Reset password for '{args.username}'.")
        else:
            admin = User(
                username=args.username, email=args.email,
                first_name='System', last_name='Admin', middle_name='',
                password_hash=generate_password_hash(password), role='admin',
            )
            db.session.add(admin)
            print(f"Created admin '{args.username}'.")
        db.session.commit()

    if generated:
        print(f"Generated password (store it securely): {password}")
    print("Done.")


if __name__ == '__main__':
    main()
