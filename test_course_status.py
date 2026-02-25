#!/usr/bin/env python3
"""
測試課程狀態更新功能
"""

import sys
import os
from datetime import datetime, timedelta

# 添加當前目錄到 Python 路徑
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db, Course, check_course_status

def test_course_status_update():
    """測試課程狀態更新功能"""
    with app.app_context():
        print("=== 課程狀態更新測試 ===")
        
        # 創建一個測試課程
        now = datetime.now()
        test_course_name = f"測試課程 - {now.strftime('%H:%M:%S')}"
        
        # 創建一個應該已經開放的課程（開始時間是1分鐘前，結束時間是1小時後）
        test_course = Course(
            name=test_course_name,
            description="這是一個用於測試狀態更新的課程",
            status='尚未開放',
            registration_start_time=now - timedelta(minutes=1),  # 1分鐘前
            registration_end_time=now + timedelta(hours=1),      # 1小時後
            has_time_slots=False,
            duration_hours=1.0
        )
        
        db.session.add(test_course)
        db.session.commit()
        
        print(f"✅ 已創建測試課程: {test_course_name}")
        print(f"   開始時間: {test_course.registration_start_time}")
        print(f"   結束時間: {test_course.registration_end_time}")
        print(f"   初始狀態: {test_course.status}")
        
        # 執行狀態檢查
        print("\n正在執行狀態檢查...")
        check_course_status()
        
        # 重新查詢課程狀態
        db.session.refresh(test_course)
        print(f"✅ 狀態檢查完成")
        print(f"   更新後狀態: {test_course.status}")
        
        # 清理測試資料
        db.session.delete(test_course)
        db.session.commit()
        print(f"🗑️  已清理測試課程")
        
        # 驗證結果
        if test_course.status == '報名中':
            print("✅ 測試通過！課程狀態已正確更新為「報名中」")
            return True
        else:
            print(f"❌ 測試失敗！預期狀態為「報名中」，實際狀態為「{test_course.status}」")
            return False

def show_current_courses():
    """顯示當前所有課程的狀態"""
    with app.app_context():
        print("\n=== 當前課程狀態 ===")
        courses = Course.query.all()
        
        if not courses:
            print("沒有找到任何課程")
            return
        
        now = datetime.now()
        for course in courses:
            print(f"課程: {course.name}")
            print(f"  狀態: {course.status}")
            print(f"  開始時間: {course.registration_start_time}")
            print(f"  結束時間: {course.registration_end_time}")
            
            # 計算時間差
            if course.registration_start_time:
                start_diff = course.registration_start_time - now
                if start_diff.total_seconds() > 0:
                    print(f"  距離開放: {start_diff}")
                else:
                    print(f"  已過開放時間: {abs(start_diff)}")
            
            print()

def main():
    """主選單"""
    while True:
        print("\n" + "="*50)
        print("課程狀態測試工具")
        print("="*50)
        print("1. 執行狀態更新測試")
        print("2. 手動執行狀態檢查")
        print("3. 顯示當前課程狀態")
        print("4. 退出")
        print("="*50)
        
        choice = input("請選擇操作 (1-4): ").strip()
        
        if choice == '1':
            test_course_status_update()
        elif choice == '2':
            with app.app_context():
                print("正在執行手動狀態檢查...")
                check_course_status()
                print("✅ 狀態檢查完成")
        elif choice == '3':
            show_current_courses()
        elif choice == '4':
            print("再見！")
            break
        else:
            print("❌ 無效的選擇，請重新輸入")

if __name__ == '__main__':
    main()