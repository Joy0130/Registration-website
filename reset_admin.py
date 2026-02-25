#!/usr/bin/env python3
"""
管理者密碼重設工具
用於重設或建立新的管理者帳號
"""

import sys
import os

# 添加當前目錄到 Python 路徑
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db, User

def reset_admin_password():
    """重設管理者密碼"""
    with app.app_context():
        print("=== 管理者密碼重設工具 ===")
        
        # 尋找現有的管理者帳號
        admin_user = User.query.filter_by(username='admin').first()
        
        if admin_user:
            print("找到現有的 admin 帳號，正在重設密碼...")
            new_password = input("請輸入新密碼（按 Enter 使用預設密碼 'Futsu_Admin'）: ").strip()
            if not new_password:
                new_password = 'Futsu_Admin'
            
            admin_user.set_password(new_password)
            admin_user.is_admin = True  # 確保管理者權限
            db.session.commit()
            
            print(f"✅ admin 帳號密碼已重設為: {new_password}")
        else:
            print("未找到 admin 帳號，正在建立新的管理者帳號...")
            new_password = input("請輸入新密碼（按 Enter 使用預設密碼 'Futsu_Admin'）: ").strip()
            if not new_password:
                new_password = 'Futsu_Admin'
            
            admin_user = User(username='admin', is_admin=True)
            admin_user.set_password(new_password)
            db.session.add(admin_user)
            db.session.commit()
            
            print(f"✅ 新的 admin 帳號已建立，密碼為: {new_password}")

def create_additional_admin():
    """建立額外的管理者帳號"""
    with app.app_context():
        print("=== 建立額外管理者帳號 ===")
        
        username = input("請輸入新管理者帳號名稱: ").strip()
        if not username:
            print("❌ 帳號名稱不能為空")
            return
        
        # 檢查帳號是否已存在
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            print(f"❌ 帳號 '{username}' 已存在")
            return
        
        password = input("請輸入密碼: ").strip()
        if not password:
            print("❌ 密碼不能為空")
            return
        
        # 建立新的管理者帳號
        new_admin = User(username=username, is_admin=True)
        new_admin.set_password(password)
        db.session.add(new_admin)
        db.session.commit()
        
        print(f"✅ 新的管理者帳號已建立: {username}")

def list_admin_accounts():
    """列出所有管理者帳號"""
    with app.app_context():
        print("=== 管理者帳號列表 ===")
        admins = User.query.filter_by(is_admin=True).all()
        
        if not admins:
            print("未找到任何管理者帳號")
            return
        
        for admin in admins:
            print(f"- {admin.username} (ID: {admin.id})")

def main():
    """主選單"""
    while True:
        print("\n" + "="*50)
        print("管理者帳號管理工具")
        print("="*50)
        print("1. 重設 admin 帳號密碼")
        print("2. 建立額外管理者帳號")
        print("3. 列出所有管理者帳號")
        print("4. 退出")
        print("="*50)
        
        choice = input("請選擇操作 (1-4): ").strip()
        
        if choice == '1':
            reset_admin_password()
        elif choice == '2':
            create_additional_admin()
        elif choice == '3':
            list_admin_accounts()
        elif choice == '4':
            print("再見！")
            break
        else:
            print("❌ 無效的選擇，請重新輸入")

if __name__ == '__main__':
    main()