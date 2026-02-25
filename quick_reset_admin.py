#!/usr/bin/env python3
"""
快速重設 admin 密碼的簡單腳本
"""

import sys
import os

# 添加當前目錄到 Python 路徑
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db, User

def quick_reset():
    """快速重設 admin 帳號為預設密碼"""
    with app.app_context():
        admin_user = User.query.filter_by(username='admin').first()
        
        if not admin_user:
            # 如果沒有 admin 帳號，建立一個
            print("建立新的 admin 帳號...")
            admin_user = User(username='admin', is_admin=True)
            db.session.add(admin_user)
        
        # 重設密碼為預設值
        admin_user.set_password('Futsu_Admin')
        admin_user.is_admin = True  # 確保管理者權限
        
        db.session.commit()
        
        print("✅ 完成！")
        print("帳號: admin")
        print("密碼: Futsu_Admin")
        print()
        print("請立即登入並更改密碼！")

if __name__ == '__main__':
    print("=== 快速重設管理者密碼 ===")
    print("這將重設 admin 帳號密碼為 'Futsu_Admin'")
    confirm = input("確定要繼續嗎？ (y/N): ").strip().lower()
    
    if confirm in ['y', 'yes']:
        quick_reset()
    else:
        print("操作已取消")