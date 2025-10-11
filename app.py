import os
import uuid
import io
from datetime import datetime, timedelta, time
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, send_from_directory, abort, send_file
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from apscheduler.schedulers.background import BackgroundScheduler
from openpyxl.styles import Font
import openpyxl
from functools import wraps
from zoneinfo import ZoneInfo # <-- 引入時區模組
from types import SimpleNamespace # <-- 引入 SimpleNamespace

# --- Firebase Admin SDK 初始化 ---
import firebase_admin
from firebase_admin import credentials, firestore, storage
# 移除了不必要的 Transaction import


# 確保這個檔案路徑是正確的，且檔案已加入 .gitignore
# 建議使用相對路徑，例如 './serviceAccountKey.json'
cred = credentials.Certificate("/Users/joy/Documents/Registration website/serviceAccountKey.json")
firebase_admin.initialize_app(cred, {
    # 請務必將 'YOUR_PROJECT_ID' 替換成你的 Firebase 專案 ID
    'storageBucket': 'bank-robot-45a15.appspot.com' 
})

db = firestore.client() # 使用 firestore 存取資料庫
bucket = storage.bucket() # 使用 storage 存取檔案儲存桶

# --- App 組態設定 ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'a_default_secret_key'
app.config['UPLOAD_FOLDER'] = 'uploads' # 檔案上傳的本地暫存資料夾
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- 時區設定 ---
TAIWAN_TZ = ZoneInfo("Asia/Taipei")

# --- 時間格式化輔助函式 ---
def to_taiwan_time_str(dt_utc, fmt='%Y-%m-%d %H:%M:%S'):
    """將 Firestore 回傳的 UTC datetime 物件轉換為台灣時間的字串"""
    if not dt_utc:
        return ""
    # Firestore SDK 回傳的是帶有 UTC 時區的 datetime 物件
    return dt_utc.astimezone(TAIWAN_TZ).strftime(fmt)

# --- Flask-Login 初始化 ---
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = "請先登入。"

# --- 新的 User Class (不再是 SQLAlchemy Model) ---
class User(UserMixin):
    def __init__(self, user_id, username, password_hash, is_admin=False):
        self.id = user_id
        self.username = username
        self.password_hash = password_hash
        self.is_admin = is_admin

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @staticmethod
    def from_doc(doc):
        if doc.exists:
            data = doc.to_dict()
            return User(
                user_id=doc.id,
                username=data.get('username'),
                password_hash=data.get('password_hash'),
                is_admin=data.get('is_admin', False)
            )
        return None

# --- 重寫 user_loader 來從 Firestore 載入使用者 ---
@login_manager.user_loader
def load_user(user_id):
    user_doc = db.collection('users').document(user_id).get()
    return User.from_doc(user_doc)

# --- 定時任務 (自動更新課程狀態) ---
def check_course_status():
    with app.app_context():
        print(" [Scheduler] 正在檢查課程狀態...")
        now = datetime.now(TAIWAN_TZ) # <-- 使用台灣時區的當前時間
        batch = db.batch()

        # 任務一：從「尚未開放」變為「報名中」
        courses_to_open_query = db.collection('courses').where(filter=firestore.FieldFilter('status', '==', '尚未開放')).stream()
        for course_doc in courses_to_open_query:
            course = course_doc.to_dict()
            if course.get('registration_start_time') and course.get('registration_start_time') <= now:
                if now < course.get('registration_end_time'):
                    batch.update(course_doc.reference, {'status': '報名中'})
                    print(f" [Scheduler] 課程 '{course.get('name')}' 已自動開放報名。")
                else:
                    batch.update(course_doc.reference, {'status': '報名截止'})
                    print(f" [Scheduler] 課程 '{course.get('name')}' 已過截止日期，直接設為報名截止。")

        # 任務二：從「報名中」變為「報名截止」
        courses_to_close_query = db.collection('courses').where(filter=firestore.FieldFilter('status', '==', '報名中')).stream()
        for course_doc in courses_to_close_query:
            course = course_doc.to_dict()
            if course.get('registration_end_time') and course.get('registration_end_time') <= now:
                batch.update(course_doc.reference, {'status': '報名截止'})
                print(f" [Scheduler] 課程 '{course.get('name')}' 已自動截止報名。")
        
        batch.commit()

scheduler = BackgroundScheduler(daemon=True, timezone=TAIWAN_TZ)
scheduler.add_job(check_course_status, 'interval', minutes=1)
scheduler.start()

# --- 輔助函式 (檢查管理者權限) ---
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('您沒有權限。', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# --- 前台使用者頁面路由 ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/my_courses')
@login_required
def my_courses():
    return render_template('my_courses.html')

@app.route('/course/<string:course_id>')
def course_detail(course_id):
    course_doc = db.collection('courses').document(course_id).get()
    if not course_doc.exists:
        abort(404)
    
    course = course_doc.to_dict()
    course['id'] = course_doc.id

    # 取得可用時段
    available_slots = []
    booked_slots_iso = []
    if course.get('has_time_slots'):
        slots_ref = db.collection('courses').document(course_id).collection('time_slots')
        slots_query = slots_ref.order_by('slot_start_time').stream()
        for slot_doc in slots_query:
            slot = slot_doc.to_dict()
            slot['id'] = slot_doc.id
            # 過濾已滿時段
            if slot.get('booked_count', 0) < slot.get('capacity', 999):
                # 確保 slot_start_time 可序列化
                if 'slot_start_time' in slot and isinstance(slot['slot_start_time'], datetime):
                    slot['slot_start_time_iso'] = slot['slot_start_time'].isoformat()
                    booked_slots_iso.append(slot['slot_start_time_iso'])
                available_slots.append(slot)

    # 檢查使用者是否已報名
    is_registered = False
    if current_user.is_authenticated:
        reg_query = db.collection('registrations')\
                      .where('user_id', '==', current_user.id)\
                      .where('course_id', '==', course_id)\
                      .limit(1).stream()
        is_registered = any(reg_query)

    # --- START: 【新增】取得「使用者自選時間」中已被預約的時段 ---
    booked_user_choice_slots = []
    if course.get('allow_user_to_choose_time'):
        # 查詢所有由使用者自選且已預約的梯次
        booked_slots_query = db.collection('courses').document(course_id)\
                                 .collection('time_slots')\
                                 .where(filter=firestore.FieldFilter('is_user_choice', '==', True))\
                                 .order_by('slot_start_time')\
                                 .stream()
        for slot_doc in booked_slots_query:
            # --- START: 【修正】將讀取的時間轉換為台灣時區 ---
            slot_data = slot_doc.to_dict()
            if slot_data.get('slot_start_time'):
                slot_data['slot_start_time'] = slot_data['slot_start_time'].astimezone(TAIWAN_TZ)
            if slot_data.get('slot_end_time'):
                slot_data['slot_end_time'] = slot_data['slot_end_time'].astimezone(TAIWAN_TZ)
            booked_user_choice_slots.append(slot_data)
            # --- END ---
    # --- END ---

    # --- START: 【新增】處理「使用者自選時間」的範圍計算 ---
    user_choice_start_datetime = None
    user_choice_end_datetime = None
    if course.get('allow_user_to_choose_time'):
        start_date = course.get('user_choice_start_date')
        end_date = course.get('user_choice_end_date')
        start_time_str = course.get('user_choice_start_time_of_day')
        end_time_str = course.get('user_choice_end_time_of_day')

        # 確保所有必要欄位都存在
        if all([start_date, end_date, start_time_str, end_time_str]):
            try:
                # 將時間字串 'HH:MM' 轉換為 time 物件
                start_time_obj = datetime.strptime(start_time_str, '%H:%M').time()
                end_time_obj = datetime.strptime(end_time_str, '%H:%M').time()

                # 組合日期與時間，並設定為台灣時區
                user_choice_start_datetime = datetime.combine(start_date, start_time_obj).replace(tzinfo=TAIWAN_TZ)
                user_choice_end_datetime = datetime.combine(end_date, end_time_obj).replace(tzinfo=TAIWAN_TZ)
            except (ValueError, TypeError) as e:
                print(f"處理自選時間範圍時發生錯誤: {e}")
                # 如果出錯，保持為 None，前端將不會顯示
    # --- END ---

    # 回傳模板，確保 booked_slots_iso 永遠有值
    return render_template(
        'course_detail.html',
        course=course,
        is_registered=is_registered,
        available_slots=available_slots,
        booked_slots_iso=booked_slots_iso,
        user_choice_start_datetime=user_choice_start_datetime, # 新增
        user_choice_end_datetime=user_choice_end_datetime,   # 新增
        booked_user_choice_slots=booked_user_choice_slots    # 新增
    )


# --- 使用者認證相關路由 ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        users_ref = db.collection('users').where(filter=firestore.FieldFilter('username', '==', username)).limit(1).stream()
        user_doc = next(users_ref, None)
        
        if user_doc:
            user = User.from_doc(user_doc)
            if user and user.check_password(password):
                login_user(user, remember=True)
                flash('登入成功！', 'success')
                next_page = request.args.get('next')
                return redirect(next_page or url_for('index'))
        
        flash('登入失敗，請檢查您的帳號或密碼。', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['POST'])
def register():
    # ... (此函式無需修改) ...
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    username = request.form['username']
    password = request.form['password']
    users_ref = db.collection('users').where(filter=firestore.FieldFilter('username', '==', username)).limit(1).stream()
    if any(users_ref):
        flash('這個帳號已經被註冊了。', 'warning')
        return redirect(url_for('login'))
    password_hash = generate_password_hash(password)
    new_user_data = {'username': username, 'password_hash': password_hash, 'is_admin': False}
    db.collection('users').add(new_user_data)
    flash('註冊成功，請登入！', 'success')
    return redirect(url_for('login'))


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('您已成功登出。', 'info')
    return redirect(url_for('index'))

@app.route('/download_file')
@login_required
def download_file():
    # ... (此函式無需修改) ...
    storage_path = request.args.get('path')
    if not storage_path:
        abort(400, '缺少檔案路徑')
    try:
        blob = bucket.blob(storage_path)
        if not blob.exists():
            abort(404, '找不到指定的檔案')
        signed_url = blob.generate_signed_url(expiration=timedelta(minutes=15), method='GET')
        return redirect(signed_url)
    except Exception as e:
        print(f"產生簽署 URL 時發生錯誤: {e}")
        abort(500, '無法產生下載連結')


# --- API 路由 (供前端 JavaScript 呼叫) ---

@app.route('/api/courses', methods=['GET'])
def get_courses():
    try:
        courses_ref = db.collection('courses')
        docs = courses_ref.stream()
        courses_data = []

        for doc in docs:
            course = doc.to_dict()
            course['id'] = doc.id
            
            # --- START: 【修正】改為在迴圈內進行複合查詢 ---
            is_registered = False
            if current_user.is_authenticated:
                # 這個查詢需要一個複合索引 (user_id, course_id)，如果不存在，執行時會在終端機提供建立連結
                reg_query = db.collection('registrations').where(filter=firestore.FieldFilter('user_id', '==', current_user.id)).where(filter=firestore.FieldFilter('course_id', '==', doc.id)).limit(1).stream()
                is_registered = any(reg_query)
            course['is_registered'] = is_registered
            # --- END: 【修正】 ---

            class_time_summary = "尚未設定"
            if course.get('has_time_slots') and not course.get('allow_user_to_choose_time'):
                slots_ref = db.collection('courses').document(doc.id).collection('time_slots').stream()
                slots = [s.to_dict() for s in slots_ref]
                if slots:
                    all_start_times = [s['slot_start_time'] for s in slots if 'slot_start_time' in s]
                    all_end_times = [s['slot_end_time'] for s in slots if 'slot_end_time' in s]
                    if all_start_times and all_end_times:
                        earliest_start_time = min(all_start_times)
                        latest_end_time = max(all_end_times)
                        start_str = to_taiwan_time_str(earliest_start_time, '%Y-%m-%d %H:%M')
                        if earliest_start_time.date() == latest_end_time.date():
                            end_str = to_taiwan_time_str(latest_end_time, '%H:%M')
                        else:
                            end_str = to_taiwan_time_str(latest_end_time, '%Y-%m-%d %H:%M')
                        class_time_summary = f"{start_str} ~ {end_str}"
            elif course.get('allow_user_to_choose_time'):
                 class_time_summary = "自行選擇"
            course['class_time_summary'] = class_time_summary
            if 'files' in course and course['files']:
                for file_data in course['files']:
                    file_data['url'] = url_for('download_file', path=file_data.get('storage_path'))
            course['registration_start_time'] = to_taiwan_time_str(course.get('registration_start_time'), fmt='%Y-%m-%d %H:%M')
            course['registration_end_time'] = to_taiwan_time_str(course.get('registration_end_time'), fmt='%Y-%m-%d %H:%M')
            courses_data.append(course)
        
        return jsonify(courses_data)
    except Exception as e:
        print(f"Error getting courses: {e}")
        return jsonify({"error": "An error occurred"}), 500

# --- START: 新增並實作「我報名的課程」API ---
@app.route('/api/my_courses', methods=['GET'])
@login_required
def get_my_courses():
    try:
        status_filter = request.args.get('status')
        my_registrations_data = []
        now = datetime.now(TAIWAN_TZ)

        regs_query = db.collection('registrations').where(filter=firestore.FieldFilter('user_id', '==', current_user.id)).stream()

        for reg_doc in regs_query:
            reg = reg_doc.to_dict()
            course_id = reg.get('course_id')
            slot_id = reg.get('time_slot_id')

            if not course_id or not slot_id:
                continue

            course_doc = db.collection('courses').document(course_id).get()
            slot_doc = db.collection('courses').document(course_id).collection('time_slots').document(slot_id).get()

            if not course_doc.exists or not slot_doc.exists:
                continue
            
            course = course_doc.to_dict()
            slot = slot_doc.to_dict()
            
            slot_start_time = slot.get('slot_start_time')
            slot_end_time = slot.get('slot_end_time')

            if not slot_start_time or not slot_end_time:
                continue
            
            registration_status = "狀態未知"
            if now < slot_start_time:
                registration_status = "課程即將開始"
            elif slot_start_time <= now < slot_end_time:
                registration_status = "課程進行中"
            else:
                registration_status = "課程已結束"

            # 伺服器端篩選
            if status_filter and status_filter != 'all' and status_filter != registration_status:
                continue

            my_registrations_data.append({
                'registration_id': reg_doc.id,
                'course_id': course_id,
                'course_name': course.get('name'),
                'class_time': f"{to_taiwan_time_str(slot_start_time, '%Y-%m-%d %H:%M')} ~ {to_taiwan_time_str(slot_end_time, '%H:%M')}",
                'course_description': course.get('description'),
                'speaker_info': course.get('speaker_info'),
                'slot_start_time': slot_start_time.isoformat(),
                'status': registration_status,
                'files': course.get('files', [])
            })
        
        # 伺服器端排序
        def sort_key(reg):
            slot_start = datetime.fromisoformat(reg['slot_start_time'])
            if reg['status'] == '課程進行中':
                return (0, slot_start)
            elif reg['status'] == '課程即將開始':
                return (1, slot_start)
            else: # 課程已結束
                return (2, -slot_start.timestamp())

        sorted_registrations = sorted(my_registrations_data, key=sort_key)
        
        return jsonify(sorted_registrations)
    except Exception as e:
        print(f"取得我的課程時發生錯誤: {e}")
        return jsonify({"error": "無法取得您的課程列表"}), 500
# --- END ---

@firestore.transactional
def register_in_transaction(transaction, course_ref, slot_ref, user_id):
    slot_snapshot = slot_ref.get(transaction=transaction)
    if not slot_snapshot.exists:
        raise Exception("找不到指定的梯次。")
    
    slot_data = slot_snapshot.to_dict()
    booked_count = slot_data.get('booked_count', 0)
    capacity = slot_data.get('capacity', 0)
    
    if booked_count >= capacity:
        raise Exception("此梯次名額已滿。")
        
    transaction.update(slot_ref, {'booked_count': firestore.Increment(1)})
    
    reg_ref = db.collection('registrations').document()
    transaction.set(reg_ref, {
        'user_id': user_id,
        'course_id': course_ref.id,
        'time_slot_id': slot_ref.id,
        'registration_time': firestore.SERVER_TIMESTAMP
    })

@app.route('/api/register', methods=['POST'])
@login_required
def register_for_slot():
    try:
        data = request.get_json()
        course_id = data.get('course_id')
        if not course_id:
            return jsonify({'success': False, 'message': '缺少課程 ID'}), 400

        course_ref = db.collection('courses').document(course_id)
        course_doc = course_ref.get()
        if not course_doc.exists or course_doc.to_dict().get('status') != '報名中':
            return jsonify({'success': False, 'message': '此課程目前未開放報名'}), 400

        existing_reg_query = db.collection('registrations').where(filter=firestore.FieldFilter('user_id', '==', current_user.id)).where(filter=firestore.FieldFilter('course_id', '==', course_id)).limit(1).stream()
        if any(existing_reg_query):
            return jsonify({'success': False, 'message': '您已經報名過此課程'}), 400

        # --- START: 【修正】區分兩種報名模式 ---
        slot_id = data.get('time_slot_id')
        user_selected_time_str = data.get('user_selected_time')

        if user_selected_time_str:
            # 模式一：使用者自選時間
            course_data = course_doc.to_dict()
            duration_hours = course_data.get('duration_hours', 1) # 預設為 1 小時
            start_time = datetime.fromisoformat(user_selected_time_str).replace(tzinfo=TAIWAN_TZ)
            end_time = start_time + timedelta(hours=duration_hours)

            # 為這個自選時間建立一個新的 time_slot 文件
            slot_ref = course_ref.collection('time_slots').document()
            slot_ref.set({
                'slot_start_time': start_time,
                'slot_end_time': end_time,
                'capacity': 1, # 自選時間的梯次容量永遠是 1
                'booked_count': 0,
                'is_user_choice': True # 標記為使用者自選
            })
        elif slot_id:
            # 模式二：固定梯次
            slot_ref = course_ref.collection('time_slots').document(slot_id)
        else:
            return jsonify({'success': False, 'message': '報名資訊不完整，缺少梯次或自選時間'}), 400
        # --- END: 【修正】 ---

        transaction = db.transaction()
        register_in_transaction(transaction, course_ref, slot_ref, current_user.id)
        
        return jsonify({'success': True, 'message': '報名成功！'})
    except Exception as e:
        print(f"報名時發生錯誤: {e}")
        return jsonify({'success': False, 'message': f'{e}'}), 500

@firestore.transactional
def cancel_in_transaction(transaction, reg_ref, slot_ref, is_user_choice_slot=False):
    """在交易中處理取消報名"""
    # --- START: 【修正】徹底重構以遵循「先讀後寫」原則 ---
    # 1. 先執行所有可能的讀取操作
    slot_snapshot = None
    if not is_user_choice_slot:
        # 只有固定梯次才需要讀取 slot 資料來更新人數
        slot_snapshot = slot_ref.get(transaction=transaction)

    # 2. 再執行所有寫入操作
    transaction.delete(reg_ref) # 寫入：刪除報名紀錄

    if is_user_choice_slot:
        transaction.delete(slot_ref) # 寫入：刪除自選的梯次
    elif slot_snapshot and slot_snapshot.exists:
        # 寫入：更新固定梯次的人數
        transaction.update(slot_ref, {'booked_count': firestore.Increment(-1)})
    # --- END: 【修正】 ---

@app.route('/api/registrations/<string:registration_id>/cancel', methods=['POST'])
@login_required
def cancel_registration(registration_id):
    try:
        reg_ref = db.collection('registrations').document(registration_id)
        reg_doc = reg_ref.get()

        if not reg_doc.exists or reg_doc.to_dict().get('user_id') != current_user.id:
            return jsonify({'success': False, 'message': '找不到您的報名紀錄或無權限操作。'}), 404

        reg_data = reg_doc.to_dict()
        course_id = reg_data.get('course_id')
        slot_id = reg_data.get('time_slot_id')
        slot_ref = db.collection('courses').document(course_id).collection('time_slots').document(slot_id)
        slot_doc = slot_ref.get()
        
        if not slot_doc.exists:
             reg_ref.delete()
             return jsonify({'success': True, 'message': '已成功取消報名(課程梯次不存在)。'})
        
        slot_data = slot_doc.to_dict()
        slot_start_time = slot_data.get('slot_start_time')
        if datetime.now(TAIWAN_TZ) > (slot_start_time - timedelta(days=1)):
             return jsonify({'success': False, 'message': '已超過取消期限 (課程開始前24小時)，無法取消報名。'}), 400

        # --- START: 【修正】判斷是否為使用者自選的梯次 ---
        is_user_choice = slot_data.get('is_user_choice', False)
        transaction = db.transaction()
        cancel_in_transaction(transaction, reg_ref, slot_ref, is_user_choice_slot=is_user_choice)
        # --- END ---

        return jsonify({'success': True, 'message': "已成功取消報名。"})

    except Exception as e:
        print(f"取消報名時發生錯誤: {e}")
        return jsonify({'success': False, 'message': f'處理取消時發生錯誤: {e}'}), 500
# --- END ---


# --- 後台管理路由與 API ---
@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    return render_template('admin_dashboard.html')

@app.route('/admin/course/new')
@login_required
@admin_required
def new_course():
    return render_template('admin_course_form.html', course=None)

@app.route('/admin/course/edit/<string:course_id>')
@login_required
@admin_required
def edit_course(course_id):
    course_doc = db.collection('courses').document(course_id).get()
    if course_doc.exists:
        course = course_doc.to_dict()
        course['id'] = course_doc.id
        return render_template('admin_course_form.html', course=course)
    else:
        flash('找不到指定的課程', 'warning')
        return redirect(url_for('admin_dashboard'))

# --- START: 【修正】重構 all_registrations 以符合樣板 ---
@app.route('/admin/all_registrations')
@login_required
@admin_required
def all_registrations():
    try:
        # --- START: 【修正】實作篩選邏輯 ---
        query = db.collection('registrations')

        # 取得篩選參數
        filter_username = request.args.get('username')
        filter_course_id = request.args.get('course_id')
        filter_registration_date = request.args.get('registration_date')
        filter_slot_date = request.args.get('slot_date') # 較複雜，稍後處理

        # 1. 依使用者名稱篩選
        if filter_username:
            # 先找到符合名稱的使用者 ID
            users_query = db.collection('users').where(filter=firestore.FieldFilter('username', '>=', filter_username)).where(filter=firestore.FieldFilter('username', '<=', filter_username + '\uf8ff')).stream()
            user_ids = [user.id for user in users_query]
            if not user_ids: # 如果找不到任何使用者，直接回傳空結果
                return render_template('admin_all_registrations.html', registrations=[], all_courses=[], request=request)
            # Firestore 'in' 查詢最多支援 30 個值
            query = query.where(filter=firestore.FieldFilter('user_id', 'in', user_ids[:30]))

        # 2. 依課程 ID 篩選
        if filter_course_id:
            query = query.where(filter=firestore.FieldFilter('course_id', '==', filter_course_id))

        # 3. 依報名日期篩選
        if filter_registration_date:
            try:
                start_date = datetime.strptime(filter_registration_date, '%Y-%m-%d').replace(tzinfo=TAIWAN_TZ)
                end_date = start_date + timedelta(days=1)
                query = query.where(filter=firestore.FieldFilter('registration_time', '>=', start_date)).where(filter=firestore.FieldFilter('registration_time', '<', end_date))
            except ValueError:
                flash('報名日期格式不正確', 'warning')

        # 執行最終查詢，並預設排序
        # 注意：如果上面有用到不等式篩選(如日期)
        if filter_registration_date:
             regs_ref = query.order_by('registration_time', direction=firestore.Query.DESCENDING).stream()
        else:
             regs_ref = query.order_by('registration_time', direction=firestore.Query.DESCENDING).stream()
        # --- END: 【修正】 ---

        all_regs_structured = []

        for reg_doc in regs_ref: # 現在 regs_ref 是篩選後的結果
            reg_data = reg_doc.to_dict()

            user_doc = db.collection('users').document(reg_data.get('user_id')).get()
            course_doc = db.collection('courses').document(reg_data.get('course_id')).get()
            slot_doc = db.collection('courses').document(reg_data.get('course_id')).collection('time_slots').document(reg_data.get('time_slot_id')).get()

            # 建立巢狀物件以符合 Jinja2 樣板的存取方式
            user_obj = SimpleNamespace(username=user_doc.to_dict().get('username', 'N/A') if user_doc.exists else 'N/A')
            course_obj = SimpleNamespace(name=course_doc.to_dict().get('name', 'N/A') if course_doc.exists else 'N/A')
            
            slot_start_time_utc = slot_doc.to_dict().get('slot_start_time') if slot_doc.exists else None
            slot_end_time_utc = slot_doc.to_dict().get('slot_end_time') if slot_doc.exists else None
            
            slot_obj = SimpleNamespace(
                course=course_obj,
                # Pre-convert to Taiwan time datetime objects
                slot_start_time=slot_start_time_utc.astimezone(TAIWAN_TZ) if slot_start_time_utc else None,
                slot_end_time=slot_end_time_utc.astimezone(TAIWAN_TZ) if slot_end_time_utc else None
            )

            registration_time_utc = reg_data.get('registration_time')

            # 建立最終的 registration 物件
            structured_reg = SimpleNamespace(
                id=reg_doc.id,
                user=user_obj,
                time_slot=slot_obj,
                registration_time=registration_time_utc,
                # --- 【修正】直接轉換為台灣時區的 datetime 物件 ---
                local_registration_time=registration_time_utc.astimezone(TAIWAN_TZ) if registration_time_utc else None
            )

            # --- START: 【修正】後端進行「上課時間」日期的篩選 ---
            should_add = True
            if filter_slot_date:
                try:
                    slot_filter_date = datetime.strptime(filter_slot_date, '%Y-%m-%d').date()
                    if not (structured_reg.time_slot and structured_reg.time_slot.slot_start_time and structured_reg.time_slot.slot_start_time.date() == slot_filter_date):
                        should_add = False
                except ValueError:
                    flash('上課日期格式不正確', 'warning')
                    should_add = False # 日期格式錯，不加入
            
            if should_add:
                all_regs_structured.append(structured_reg)
            # --- END: 【修正】 ---


        all_courses_docs = db.collection('courses').order_by('name').stream()
        all_courses = [{'id': doc.id, **doc.to_dict()} for doc in all_courses_docs]

        return render_template(
            'admin_all_registrations.html', 
            registrations=all_regs_structured,
            all_courses=all_courses,
            request=request
        )
    except Exception as e:
        print(f"載入報名紀錄時發生錯誤: {e}")
        flash(f'載入報名紀錄時發生錯誤: {e}', 'danger')
        return render_template('admin_all_registrations.html', registrations=[], all_courses=[])
# --- END ---


# --- START: 【修正】匯出 Excel 路由 ---
@app.route('/admin/export_registrations')
@login_required
@admin_required
def export_registrations_to_excel():
    try:
        # 這裡先實作匯出所有紀錄，之後可再加入篩選邏輯
        registrations_ref = db.collection('registrations').order_by('registration_time').stream()

        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "報名紀錄"

        header_font = Font(name='Calibri', size=16, bold=True)
        headers = ["報名 ID", "使用者名稱", "報名課程", "上課時間", "報名時間"]
        sheet.append(headers)
        for cell in sheet[1]:
            cell.font = header_font

        for reg_doc in registrations_ref:
            reg = reg_doc.to_dict()
            user_doc = db.collection('users').document(reg['user_id']).get()
            course_doc = db.collection('courses').document(reg['course_id']).get()
            slot_doc = db.collection('courses').document(reg['course_id']).collection('time_slots').document(reg['time_slot_id']).get()

            username = user_doc.to_dict().get('username', 'N/A') if user_doc.exists else 'N/A'
            course_name = course_doc.to_dict().get('name', 'N/A') if course_doc.exists else 'N/A'
            
            slot_time_str = "N/A"
            if slot_doc.exists:
                slot = slot_doc.to_dict()
                slot_time_str = f"{to_taiwan_time_str(slot.get('slot_start_time'), '%Y-%m-%d %H:%M')} ~ {to_taiwan_time_str(slot.get('slot_end_time'), '%H:%M')}"
            
            row = [
                reg_doc.id, 
                username, 
                course_name, 
                slot_time_str, 
                to_taiwan_time_str(reg.get('registration_time'))
            ]
            sheet.append(row)

        output = io.BytesIO()
        workbook.save(output)
        output.seek(0)

        return send_file(output, as_attachment=True, download_name='registrations.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    except Exception as e:
        flash(f"匯出 Excel 時發生錯誤: {e}", "danger")
        return redirect(url_for('all_registrations'))
# --- END ---

def _handle_file_uploads_storage(files, course_id):
    uploaded_files_metadata = []
    for file in files:
        if file and file.filename != '':
            original_filename = secure_filename(file.filename)
            _, ext = os.path.splitext(original_filename)
            unique_filename = f"{uuid.uuid4().hex}{ext}"
            storage_path = f"course_files/{course_id}/{unique_filename}"
            blob = bucket.blob(storage_path)
            blob.upload_from_file(file)
            uploaded_files_metadata.append({"display_name": original_filename, "storage_path": storage_path, "upload_time": datetime.utcnow()})
    return uploaded_files_metadata

def _handle_time_slots_firestore(data, course_ref):
    slot_start_times = data.getlist('slot_start_times')
    slot_end_times = data.getlist('slot_end_times')
    slot_capacities = data.getlist('slot_capacities')

    if not slot_start_times:
        raise ValueError("固定梯次模式下，請至少設定一個上課時間梯次。")

    batch = db.batch()

    for start_str, end_str, capacity_str in zip(slot_start_times, slot_end_times, slot_capacities):
        if not all([start_str, end_str, capacity_str]):
            continue

        try:
            capacity = int(capacity_str)
            if capacity <= 0:
                raise ValueError("人數上限必須大於 0。")

            # 將表單時間字串轉為 datetime（預設為台灣時間）
            start_time = datetime.strptime(start_str, "%Y-%m-%dT%H:%M").replace(tzinfo=TAIWAN_TZ)
            end_time = datetime.strptime(end_str, "%Y-%m-%dT%H:%M").replace(tzinfo=TAIWAN_TZ)

            # 新增到 Firestore 子集合
            slot_ref = course_ref.collection('time_slots').document()
            batch.set(slot_ref, {
                'slot_start_time': start_time,
                'slot_end_time': end_time,
                'capacity': capacity,
                'booked_count': 0
            })
        except Exception as e:
            raise ValueError(f"建立梯次時發生錯誤：{e}")

    batch.commit()


@app.route('/api/admin/courses', methods=['POST'])
@login_required
@admin_required
def create_course():
    try:
        data = request.form
        uploaded_files = request.files.getlist('files')
        
        # --- START: 【修正】即時判斷課程初始狀態 ---
        start_time_naive = datetime.strptime(data['registration_start_time'], '%Y-%m-%dT%H:%M')
        end_time_naive = datetime.strptime(data['registration_end_time'], '%Y-%m-%dT%H:%M')
        start_time_aware = start_time_naive.replace(tzinfo=TAIWAN_TZ)
        end_time_aware = end_time_naive.replace(tzinfo=TAIWAN_TZ)
        now = datetime.now(TAIWAN_TZ)

        initial_status = "尚未開放"
        if start_time_aware <= now < end_time_aware:
            initial_status = "報名中"
        elif now >= end_time_aware:
            initial_status = "報名截止"
        # --- END: 【修正】 ---

        allow_user_choice = 'allow_user_to_choose_time' in data
        course_data = {
            "name": data['name'], "description": data['description'], "speaker_info": data.get('speaker_info'),
            "status": initial_status, # 使用計算出的初始狀態
            "registration_start_time": start_time_aware, "registration_end_time": end_time_aware,
            "files": [],
            "allow_user_to_choose_time": allow_user_choice,
            "has_time_slots": not allow_user_choice,
            "user_choice_start_date": datetime.combine(
                datetime.strptime(data['user_choice_start_date'], '%Y-%m-%d').date(),
                time.min
            ).replace(tzinfo=TAIWAN_TZ) if allow_user_choice and data.get('user_choice_start_date') else None,
            "user_choice_end_date": datetime.combine(
                datetime.strptime(data['user_choice_end_date'], '%Y-%m-%d').date(),
                time.min
            ).replace(tzinfo=TAIWAN_TZ) if allow_user_choice and data.get('user_choice_end_date') else None,
            "user_choice_start_time_of_day": data.get('user_choice_start_time_of_day') if allow_user_choice and data.get('user_choice_start_time_of_day') else None,
            "user_choice_end_time_of_day": data.get('user_choice_end_time_of_day') if allow_user_choice and data.get('user_choice_end_time_of_day') else None,
        }
        course_ref = db.collection('courses').document()
        course_id = course_ref.id
        if uploaded_files:
            files_metadata = _handle_file_uploads_storage(uploaded_files, course_id)
            course_data['files'] = files_metadata
        course_ref.set(course_data)
        if not allow_user_choice:
            _handle_time_slots_firestore(data, course_ref)
        flash('課程新增成功！', 'success')
        return redirect(url_for('admin_dashboard'))
    except Exception as e:
        flash(f'新增課程時發生錯誤: {e}', 'danger')
        # --- START: 【修正】錯誤時重新渲染並保留資料 ---
        form_data = request.form.to_dict()
        # 將時間字串轉換回 datetime 物件，以便樣板能正確渲染
        if form_data.get('registration_start_time'):
            form_data['registration_start_time'] = datetime.strptime(form_data['registration_start_time'], '%Y-%m-%dT%H:%M')
        if form_data.get('registration_end_time'):
            form_data['registration_end_time'] = datetime.strptime(form_data['registration_end_time'], '%Y-%m-%dT%H:%M')
        # date 和 time 欄位維持字串即可，因為 input type="date/time" 接受字串 value
            
        time_slots = []
        slot_starts = request.form.getlist('slot_start_times')
        slot_ends = request.form.getlist('slot_end_times')
        slot_caps = request.form.getlist('slot_capacities')
        for i in range(len(slot_starts)):
            time_slots.append({
                "slot_start_time": slot_starts[i],
                "slot_end_time": slot_ends[i],
                "capacity": slot_caps[i]
            })
        form_data['time_slots'] = time_slots
        course_from_form = SimpleNamespace(**form_data)
        return render_template('admin_course_form.html', course=course_from_form), 400
        # --- END: 【修正】 ---

@app.route('/api/admin/courses/<string:course_id>', methods=['POST'])
@login_required
@admin_required
def update_course(course_id):
    course_ref = db.collection('courses').document(course_id)
    try:
        data = request.form
        uploaded_files = request.files.getlist('files')
        start_time_naive = datetime.strptime(data['registration_start_time'], '%Y-%m-%dT%H:%M')
        end_time_naive = datetime.strptime(data['registration_end_time'], '%Y-%m-%dT%H:%M')
        allow_user_choice = 'allow_user_to_choose_time' in data
        update_data = {
            "name": data['name'], "description": data['description'], "speaker_info": data.get('speaker_info'),
            "registration_start_time": start_time_naive.replace(tzinfo=TAIWAN_TZ), "registration_end_time": end_time_naive.replace(tzinfo=TAIWAN_TZ),
            "allow_user_to_choose_time": allow_user_choice, "has_time_slots": not allow_user_choice,
            "user_choice_start_date": datetime.strptime(data['user_choice_start_date'], '%Y-%m-%d').date() if allow_user_choice and data.get('user_choice_start_date') else None,
            "user_choice_end_date": datetime.strptime(data['user_choice_end_date'], '%Y-%m-%d').date() if allow_user_choice and data.get('user_choice_end_date') else None,
            "user_choice_start_time_of_day": data.get('user_choice_start_time_of_day') if allow_user_choice and data.get('user_choice_start_time_of_day') else None,
            "user_choice_end_time_of_day": data.get('user_choice_end_time_of_day') if allow_user_choice and data.get('user_choice_end_time_of_day') else None,
        }
        if uploaded_files:
            files_metadata = _handle_file_uploads_storage(uploaded_files, course_id)
            update_data['files'] = firestore.ArrayUnion(files_metadata)
        course_ref.update(update_data)
        old_slots_ref = course_ref.collection('time_slots')
        delete_collection(old_slots_ref, 50)
        if not allow_user_choice:
            _handle_time_slots_firestore(data, course_ref)
        flash('課程更新成功！', 'success')
        return redirect(url_for('admin_dashboard'))
    except Exception as e:
        flash(f'更新課程時發生錯誤: {e}', 'danger')
        # --- START: 【修正】錯誤時重新渲染並保留資料 ---
        course_data_from_db = course_ref.get().to_dict()
        form_data = request.form.to_dict()
        course_data_from_db.update(form_data)
        
        # 將時間字串轉換回 datetime 物件
        if course_data_from_db.get('registration_start_time') and isinstance(course_data_from_db['registration_start_time'], str):
            course_data_from_db['registration_start_time'] = datetime.strptime(course_data_from_db['registration_start_time'], '%Y-%m-%dT%H:%M')
        if course_data_from_db.get('registration_end_time') and isinstance(course_data_from_db['registration_end_time'], str):
            course_data_from_db['registration_end_time'] = datetime.strptime(course_data_from_db['registration_end_time'], '%Y-%m-%dT%H:%M')
        # ... 對其他時間欄位做同樣的處理 ...
            
        time_slots = []
        slot_starts = request.form.getlist('slot_start_times')
        slot_ends = request.form.getlist('slot_end_times')
        slot_caps = request.form.getlist('slot_capacities')
        for i in range(len(slot_starts)):
            time_slots.append({
                "slot_start_time": slot_starts[i],
                "slot_end_time": slot_ends[i],
                "capacity": slot_caps[i]
            })
        course_data_from_db['time_slots'] = time_slots
        course_from_form = SimpleNamespace(**course_data_from_db)
        course_from_form.id = course_id
        return render_template('admin_course_form.html', course=course_from_form), 400
        # --- END: 【修正】 ---

def delete_collection(coll_ref, batch_size):
    docs = coll_ref.limit(batch_size).stream()
    deleted = 0
    for doc in docs:
        print(f"正在刪除文件: {doc.id}")
        doc.reference.delete()
        deleted += 1
    if deleted >= batch_size:
        return delete_collection(coll_ref, batch_size)

@app.route('/api/admin/courses/<string:course_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_course(course_id):
    try:
        course_ref = db.collection('courses').document(course_id)
        course_doc = course_ref.get()
        if not course_doc.exists:
            return jsonify({'success': False, 'message': '找不到要刪除的課程'}), 404
        course_data = course_doc.to_dict()
        if 'files' in course_data and course_data['files']:
            for file_info in course_data['files']:
                if 'storage_path' in file_info:
                    blob = bucket.blob(file_info['storage_path'])
                    if blob.exists():
                        blob.delete()
                        print(f"已刪除 Storage 檔案: {file_info['storage_path']}")
        slots_ref = course_ref.collection('time_slots')
        delete_collection(slots_ref, 50)
        regs_query = db.collection('registrations').where(filter=firestore.FieldFilter('course_id', '==', course_id)).stream()
        batch = db.batch()
        for reg_doc in regs_query:
            batch.delete(reg_doc.reference)
        batch.commit()
        print(f"已刪除與課程 {course_id} 相關的報名紀錄")
        course_ref.delete()
        print(f"已刪除課程文件: {course_id}")
        return jsonify({'success': True, 'message': '課程已成功刪除'})
    except Exception as e:
        print(f"刪除課程時發生錯誤: {e}")
        return jsonify({'success': False, 'message': f'刪除課程時發生伺服器錯誤: {e}'}), 500

@app.route('/api/admin/courses/<string:course_id>/registrations', methods=['GET'])
@login_required
@admin_required
def get_registrations(course_id):
    try:
        regs_query = db.collection('registrations').where(filter=firestore.FieldFilter('course_id', '==', course_id)).order_by('registration_time').stream()
        users_data = []
        for reg_doc in regs_query:
            reg = reg_doc.to_dict()
            user_doc = db.collection('users').document(reg['user_id']).get()
            username = user_doc.to_dict().get('username') if user_doc.exists else '未知用戶'
            slot_time_display = "自選時間或資料錯誤"
            if reg.get('time_slot_id'):
                slot_doc = db.collection('courses').document(course_id).collection('time_slots').document(reg['time_slot_id']).get()
                if slot_doc.exists:
                    slot = slot_doc.to_dict()
                    start_str = to_taiwan_time_str(slot.get('slot_start_time'), '%Y-%m-%d %H:%M')
                    end_str = to_taiwan_time_str(slot.get('slot_end_time'), '%H:%M')
                    slot_time_display = f"{start_str} ~ {end_str}"
            users_data.append({'username': username, 'registration_time': to_taiwan_time_str(reg.get('registration_time'), '%Y-%m-%d %H:%M'), 'slot_time': slot_time_display})
        return jsonify(users_data)
    except Exception as e:
        print(f"獲取報名列表時發生錯誤: {e}")
        return jsonify({'error': f'伺服器錯誤: {e}'}), 500

@app.route('/api/admin/courses/<string:course_id>/files/delete', methods=['POST'])
@login_required
@admin_required
def delete_course_file(course_id):
    try:
        data = request.get_json()
        storage_path_to_delete = data.get('storage_path')
        file_to_remove = data.get('file_object')
        if not storage_path_to_delete or not file_to_remove:
            return jsonify({'success': False, 'message': '請求資訊不完整'}), 400
        blob = bucket.blob(storage_path_to_delete)
        if blob.exists():
            blob.delete()
        course_ref = db.collection('courses').document(course_id)
        course_ref.update({'files': firestore.ArrayRemove([file_to_remove])})
        return jsonify({'success': True, 'message': '檔案已刪除'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'刪除檔案時發生錯誤: {e}'}), 500


# --- START: 【修正】補全 admin_cancel_registration 路由 ---
@app.route('/api/admin/registrations/<string:registration_id>/cancel', methods=['POST'])
@login_required
@admin_required
def admin_cancel_registration(registration_id):
    try:
        reg_ref = db.collection('registrations').document(registration_id)
        reg_doc = reg_ref.get()

        if not reg_doc.exists:
            flash('找不到指定的報名紀錄。', 'danger')
            return redirect(url_for('all_registrations', **request.args))

        reg_data = reg_doc.to_dict()
        course_id = reg_data.get('course_id')
        slot_id = reg_data.get('time_slot_id')

        if course_id and slot_id:
            # --- START: 【修正】在交易前判斷梯次類型 ---
            slot_ref = db.collection('courses').document(course_id).collection('time_slots').document(slot_id)
            slot_doc = slot_ref.get()
            is_user_choice = False
            if slot_doc.exists:
                is_user_choice = slot_doc.to_dict().get('is_user_choice', False)
            
            transaction = db.transaction()
            cancel_in_transaction(transaction, reg_ref, slot_ref, is_user_choice_slot=is_user_choice)
            # --- END: 【修正】 ---
        else:
            reg_ref.delete()
        
        flash('已成功取消該筆報名。', 'success')
    except Exception as e:
        print(f"管理員取消報名時發生錯誤: {e}")
        flash(f'處理取消時發生錯誤: {e}', 'danger')
    
    return redirect(url_for('all_registrations', **request.args))
# --- END ---


# --- 主程式進入點 & 初始化 ---
if __name__ == '__main__':
    # 檢查是否已有 admin 使用者，若無則建立一個
    admin_query = db.collection('users').where(filter=firestore.FieldFilter('username', '==', 'admin')).limit(1).stream()
    if not any(admin_query):
        print("建立預設管理者帳號...")
        password_hash = generate_password_hash('Futsu_Admin')
        admin_data = {
            'username': 'admin',
            'is_admin': True,
            'password_hash': password_hash
        }
        db.collection('users').add(admin_data)
        print("管理者帳號: admin, 密碼: Futsu_Admin")

    print("[Startup] 正在執行首次課程狀態檢查...")
    check_course_status()
    print("[Startup] 首次檢查完成。")



    app.run(debug=True, host='0.0.0.0', port=5003)
