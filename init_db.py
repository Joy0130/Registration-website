#!/usr/bin/env python
"""
Database initialization script
Creates database with updated schema including email and needs_password_change fields
"""
import os
import sys

# Add the project directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from app import app, db, User

def init_db():
    """Initialize the database with the updated schema"""
    with app.app_context():
        print("Creating database tables...")
        db.create_all()
        print("Database tables created successfully!")
        
        # Check if admin user exists, if not create one
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            print("Creating default admin user...")
            admin = User(
                username='admin', 
                email='admin@example.com',
                is_admin=True,
                needs_password_change=False
            )
            admin.set_password('admin123')  # Default password
            db.session.add(admin)
            db.session.commit()
            print("Admin user created with username: admin, password: admin123")
        else:
            print("Admin user already exists")

if __name__ == '__main__':
    init_db()