from app import create_app
from models import User
from werkzeug.security import check_password_hash

app = create_app()

with app.app_context():
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        print("ERROR: Admin user not found in DB!")
    else:
        print(f"Admin found. Hash: {admin.password_hash}")
        is_valid = check_password_hash(admin.password_hash, 'admin123')
        print(f"Checking 'admin123': {is_valid}")
