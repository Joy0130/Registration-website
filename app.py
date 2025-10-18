import os
import uuid
import io
from datetime import datetime, timedelta, time
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, send_from_directory, abort, send_file
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from apscheduler.schedulers.background import BackgroundScheduler
from openpyxl.styles import Font
import openpyxl
# --- App 組態設定 ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'a_default_secret_key'  # 可從環境變數取得，若無則使用預設值 (開發時可用)
#app.config['SECRET_KEY'] = 'a_very_secret_key_that_should_be_changed' # 測試用
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db' #符合Railway寫法

#app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////data/database.db'

# app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///../instance/database.db' # SQLite 資料庫路徑
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False # 關閉不必要的追蹤功能以節省資源
app.config['UPLOAD_FOLDER'] = 'uploads' # 上傳檔案的資料夾
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True) # 確保上傳資料夾存在

db = SQLAlchemy(app)
login_manager = LoginManager(app) # App 初始化登入管理
login_manager.login_view = 'login' # 如果使用者未登入就嘗試訪問受保護頁面，會被導向到登入頁
login_manager.login_message = "請先登入。"

# --- 使用者 table (Models) ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True) # 使用者ID 唯一值
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False) # 儲存雜湊後的密碼
    is_admin = db.Column(db.Boolean, default=False) # 是否為管理者
    __table_args__ = {'extend_existing': True} # 避免重複定義表格錯誤
    # 密碼相關方法
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    # 檢查密碼是否正確
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# --- 課程與報名相關table Models ---
class Course(db.Model):
    __tablename__ = 'course' # 建議明確指定表名
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False) # 課程描述
    speaker_info = db.Column(db.String(200)) # 講者資訊
    has_time_slots = db.Column(db.Boolean, default=False, nullable=False) # 是否有梯次
    status = db.Column(db.String(20), default='尚未開放') # 課程狀態：尚未開放、報名中、報名截止
    registration_start_time = db.Column(db.DateTime, nullable=False) # 報名開始時間
    registration_end_time = db.Column(db.DateTime, nullable=False) # 報名截止時間
    allow_user_to_choose_time = db.Column(db.Boolean, default=False, nullable=False) # 是否允許使用者自選時間
    duration_hours = db.Column(db.Float, nullable=True, default=1) # 新增：上課時數欄位
    user_choice_start_date = db.Column(db.Date, nullable=True) # 自選時間的可選起始日
    user_choice_end_date = db.Column(db.Date, nullable=True) # 自選時間的可選結束日
    user_choice_start_time_of_day = db.Column(db.Time, nullable=True) # 自選時間的每日可選起始時間
    user_choice_end_time_of_day = db.Column(db.Time, nullable=True) # 自選時間的每日可選結束時間

    __table_args__ = {'extend_existing': True} # 避免重複定義表格錯誤

    # --- 關聯 (Relationships) ---
    files = db.relationship('CourseFile', backref='course', lazy=True, cascade="all, delete-orphan") # 課程有多個檔案，刪除課程時也刪除相關檔案
    time_slots = db.relationship('TimeSlot', backref='course', lazy=True, cascade="all, delete-orphan") # 課程有多個梯次，刪除課程時也刪除相關梯次

# 報名紀錄 table
class Registration(db.Model):
    __tablename__ = 'registration'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    time_slot_id = db.Column(db.Integer, db.ForeignKey('time_slot.id'), nullable=False) # 報名的梯次
    registration_time = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = {'extend_existing': True}

    # --- 關聯 (Relationships) ---
    user = db.relationship('User', backref=db.backref('registrations', lazy=True))
    time_slot = db.relationship('TimeSlot', backref=db.backref('registrations', lazy='dynamic', cascade="all, delete-orphan", single_parent=True)) # 一個梯次有多個報名紀錄

    # --- 輔助函式 ---
    def local_registration_time(self):
        """將儲存的 UTC 時間轉換為台灣本地時間 (UTC+8)"""
        return self.registration_time + timedelta(hours=8)
    
# 課程檔案 table
class CourseFile(db.Model):
    __tablename__ = 'course_file' # 明確指定表名，避免與其他表名衝突
    id = db.Column(db.Integer, primary_key=True) # 檔案ID 唯一值
    file_path = db.Column(db.String(300), nullable=False) # 儲存 UUID 檔名
    display_filename = db.Column(db.String(300), nullable=False) # 儲存原始檔名 (顯示用)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False) # 課程ID 外鍵，參考 Course 表
    __table_args__ = {'extend_existing': True} # 避免重複定義表格錯誤

# 課程梯次 table 起迄日
class TimeSlot(db.Model):
    __tablename__ = 'time_slot'
    id = db.Column(db.Integer, primary_key=True)
    # 將 slot_time 拆分為開始與結束時間
    slot_start_time = db.Column(db.DateTime, nullable=False)
    slot_end_time = db.Column(db.DateTime, nullable=False)
    capacity = db.Column(db.Integer, nullable=False, default=999) # 梯次名額
    booked_count = db.Column(db.Integer, default=0) # 已報名人數
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False) # 課程ID 外鍵，參考 Course 表
    __table_args__ = {'extend_existing': True} # 避免重複定義表格錯誤



# --- 使用者載入函式 (Flask-Login) ---
@login_manager.user_loader
def load_user(user_id): # 透過 user_id 載入使用者
    return User.query.get(int(user_id)) # 從資料庫取得使用者資料

# --- 定時任務 (自動更新課程狀態) ---
def check_course_status():
    with app.app_context():
        print(" [Scheduler] 正在檢查課程狀態...")
        now = datetime.now() # 伺服器已是 GMT+8，改回使用本地時間

        # 檢查任務一：檢查哪些課程應該從「尚未開放」變為「報名中」
        courses_to_open = Course.query.filter(Course.status == '尚未開放', Course.registration_start_time <= now).all()
        for course in courses_to_open:
            # 額外檢查：確保開始時間已到，但結束時間還沒到
            if now < course.registration_end_time:
                course.status = '報名中'
                print(f" [Scheduler] 課程 '{course.name}' 已自動開放報名。")
            else:
                # 處理一種特殊情況：管理員設定的開始時間和結束時間都已經是過去式
                course.status = '報名截止'
                print(f" [Scheduler] 課程 '{course.name}' 已過截止日期，直接設為報名截止。")

        # 檢查任務二：檢查哪些課程應該從「報名中」變為「報名截止」
        courses_to_close = Course.query.filter(Course.status == '報名中', Course.registration_end_time <= now).all()
        for course in courses_to_close:
            course.status = '報名截止'
            print(f" [Scheduler] 課程 '{course.name}' 已自動截止報名。")

        db.session.commit()

scheduler = BackgroundScheduler(daemon=True) # 在背景中檢查課程狀態
scheduler.add_job(check_course_status, 'interval', minutes=1) # 每分鐘檢查課成狀態
scheduler.start()

# --- 輔助函式 (檢查管理者權限) ---
from functools import wraps
def admin_required(f):
    @wraps(f)
    # 檢查使用者是否為管理者
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

#  我的課程頁面
@app.route('/my_courses')
@login_required
def my_courses():
    return render_template('my_courses.html')

# 課程詳情頁面
# ---- START: 請用這段完整的程式碼取代舊的 course_detail 函式 ----
@app.route('/course/<int:course_id>')
def course_detail(course_id):
    course = db.session.get(Course, course_id)
    if not course:
        abort(404)
    
    available_slots = []
    if course.has_time_slots:
        # 找出還有名額的梯次
        available_slots = TimeSlot.query.filter(
            TimeSlot.course_id == course.id, 
            TimeSlot.booked_count < TimeSlot.capacity
        ).order_by(TimeSlot.slot_start_time).all() 

    is_registered = False
    if current_user.is_authenticated:
        # 檢查使用者是否已報名此課程的任何一個梯次
        user_reg = Registration.query.join(TimeSlot).filter(
            Registration.user_id == current_user.id,
            TimeSlot.course_id == course.id
        ).first()
        is_registered = user_reg is not None

    # --- 取得已被預約的自選時段 ---
    booked_slots_display = []
    booked_slots_iso = []
    if course.allow_user_to_choose_time:
        # 動態生成的梯次 capacity 為 1，代表已被預約
        booked_slots_query = TimeSlot.query.filter_by(
            course_id=course.id, capacity=1
        ).order_by(TimeSlot.slot_start_time).all()
        booked_slots_display = booked_slots_query
        # 為了讓 JS 能比對，我們需要 ISO 格式的字串列表
        booked_slots_iso = [slot.slot_start_time.isoformat() for slot in booked_slots_query]

    # 為了讓前端能正確設定 min/max，我們需要組合完整的 datetime
    user_choice_start_datetime = None
    user_choice_end_datetime = None
    # 只有在允許自選時間且相關欄位都有值時才組合
    if course.allow_user_to_choose_time and course.user_choice_start_date and course.user_choice_start_time_of_day:
        user_choice_start_datetime = datetime.combine(course.user_choice_start_date, course.user_choice_start_time_of_day)
    # 同理處理結束日期與時間
    if course.allow_user_to_choose_time and course.user_choice_end_date and course.user_choice_end_time_of_day:
        user_choice_end_datetime = datetime.combine(course.user_choice_end_date, course.user_choice_end_time_of_day)
    # 將資料傳給模板        
    return render_template(
        'course_detail.html', 
        course=course, 
        is_registered=is_registered, 
        available_slots=available_slots,
        user_choice_start_datetime=user_choice_start_datetime,
        user_choice_end_datetime=user_choice_end_datetime,
        booked_user_choice_slots=booked_slots_display,
        booked_slots_iso=booked_slots_iso
    )
# ---- END ----

# --- 使用者認證相關路由 ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST': # 處理登入表單提交
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            flash('登入成功！', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('登入失敗，請檢查您的帳號或密碼。', 'danger')
    return render_template('login.html')

# 註冊頁面
@app.route('/register', methods=['POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    username = request.form['username']
    password = request.form['password']
    
    if User.query.filter_by(username=username).first():
        flash('這個帳號已經被註冊了。', 'warning')
        return redirect(url_for('login'))

    new_user = User(username=username)
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()
    flash('註冊成功，請登入！', 'success')
    return redirect(url_for('login'))

# 登出路由
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('您已成功登出。', 'info')
    return redirect(url_for('index'))

# --- 後台管理頁面路由 ---
@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    return render_template('admin_dashboard.html')

# 新增與編輯課程頁面
@app.route('/admin/course/new')
@login_required
@admin_required
def new_course():
    return render_template('admin_course_form.html', course=None)

# 編輯課程頁面
@app.route('/admin/course/edit/<int:course_id>')
@login_required
@admin_required
def edit_course(course_id):
    course = Course.query.get_or_404(course_id)
    return render_template('admin_course_form.html', course=course)

# 顯示所有報名紀錄的頁面ß
@app.route('/admin/all_registrations')
@login_required
@admin_required
def all_registrations():
    """顯示所有使用者的報名紀錄，並支援多條件篩選。"""
    # 基礎查詢，預先 JOIN 需要用到的 Table
    query = Registration.query.join(TimeSlot).join(User)

    # 1. 根據「報名 ID」篩選
    reg_id_str = request.args.get('registration_id')
    if reg_id_str:
        try:
            query = query.filter(Registration.id == int(reg_id_str))
        except ValueError:
            flash('報名 ID 必須是數字', 'warning')

    # 2. 根據「使用者名稱」篩選 (模糊查詢，不分大小寫)
    username = request.args.get('username')
    if username:
        query = query.filter(User.username.ilike(f"%{username}%"))

    # 3. 根據「報名課程」篩選
    course_id_str = request.args.get('course_id')
    if course_id_str:
        try:
            query = query.filter(TimeSlot.course_id == int(course_id_str))
        except ValueError:
            flash('課程 ID 格式不正確', 'warning')

    # 4. 根據「梯次上課日期」篩選
    slot_date_str = request.args.get('slot_date')
    if slot_date_str:
        try:
            slot_date = datetime.strptime(slot_date_str, '%Y-%m-%d').date()
            query = query.filter(func.date(TimeSlot.slot_start_time) == slot_date)
        except ValueError:
            flash('梯次日期格式不正確', 'warning')

    # 5. 根據「報名日期 (台灣時間)」篩選
    reg_date_str = request.args.get('registration_date')
    if reg_date_str:
        try:
            reg_date = datetime.strptime(reg_date_str, '%Y-%m-%d').date()
            start_of_day_cst = datetime.combine(reg_date, datetime.min.time())
            end_of_day_cst = datetime.combine(reg_date, datetime.max.time())
            start_of_day_utc = start_of_day_cst - timedelta(hours=8)
            end_of_day_utc = end_of_day_cst - timedelta(hours=8)
            query = query.filter(Registration.registration_time.between(start_of_day_utc, end_of_day_utc))
        except ValueError:
            flash('報名日期格式不正確', 'warning')
    
    # 取得所有有報名紀錄的課程列表，用於填充下拉選單
    all_courses = db.session.query(Course).join(TimeSlot).join(Registration).distinct(Course.id).order_by(Course.name).all()
    
    # 執行最終查詢並排序
    all_regs = query.order_by(Registration.id.desc()).all()
    
    # Debug: Print the course names to console
    print("Debug: all_courses names:", [course.name for course in all_courses])
    
    # 將 request 和 all_courses 物件傳給模板
    return render_template(
        'admin_all_registrations.html', 
        registrations=all_regs, 
        all_courses=all_courses, 
        request=request
    )

# ---- START: 新增的匯出 Excel 路由 ----
@app.route('/admin/export_registrations')
@login_required
@admin_required
def export_registrations_to_excel():
    """根據篩選條件，將報名紀錄匯出為 Excel 檔案。"""
    # --- 這段查詢邏輯與 all_registrations 函式完全相同 ---
    query = Registration.query.join(TimeSlot).join(User) # 預先 JOIN 需要用到的 Table

    reg_id_str = request.args.get('registration_id') # 根據「報名 ID」篩選
    if reg_id_str:
        try:
            query = query.filter(Registration.id == int(reg_id_str)) # 嘗試轉換為整數
        except ValueError: pass

    username = request.args.get('username') # 根據「使用者名稱」篩選 (模糊查詢，不分大小寫)
    if username:
        query = query.filter(User.username.ilike(f"%{username}%"))

    course_id_str = request.args.get('course_id') # 根據「報名課程」篩選
    if course_id_str:
        try:
            query = query.filter(TimeSlot.course_id == int(course_id_str))
        except ValueError: pass

    slot_date_str = request.args.get('slot_date') # 根據「梯次上課日期」篩選
    if slot_date_str:
        try:
            slot_date = datetime.strptime(slot_date_str, '%Y-%m-%d').date()
            query = query.filter(func.date(TimeSlot.slot_start_time) == slot_date)
        except ValueError: pass

    reg_date_str = request.args.get('registration_date') # 根據「報名日期」篩選
    if reg_date_str:
        try:
            reg_date = datetime.strptime(reg_date_str, '%Y-%m-%d').date()
            start_of_day_cst = datetime.combine(reg_date, datetime.min.time())
            end_of_day_cst = datetime.combine(reg_date, datetime.max.time())
            start_of_day_utc = start_of_day_cst - timedelta(hours=8)
            end_of_day_utc = end_of_day_cst - timedelta(hours=8)
            query = query.filter(Registration.registration_time.between(start_of_day_utc, end_of_day_utc))
        except ValueError: pass

    registrations = query.order_by(Registration.id.desc()).all() # 執行最終查詢並排序

    # --- 使用 openpyxl 建立 Excel 檔案 ---
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "報名紀錄"

    # --- 定義匯出excel中的字體和表頭樣式 ---
    # 定義一般儲存格的字體樣式
    default_font = Font(name='Calibri', size=14)
    # 定義表頭的字體樣式 (粗體)
    header_font = Font(name='Calibri', size=16, bold=True)

    # 寫入表頭
    headers = ["報名 ID", "使用者名稱", "報名課程", "上課時間", "報名時間"]
    sheet.append(headers)
    # 將表頭設定為粗體
    for cell in sheet[1]:
        cell.font = header_font

    # 寫入資料
    for reg in registrations:
        slot_time_str = f"{reg.time_slot.slot_start_time.strftime('%Y-%m-%d %H:%M')} ~ {reg.time_slot.slot_end_time.strftime('%H:%M')}"
        row = [reg.id, reg.user.username, reg.time_slot.course.name, slot_time_str, reg.local_registration_time().strftime('%Y-%m-%d %H:%M:%S')]
        sheet.append(row)

    # --- 調整欄寬與套用字體 ---
    # 遍歷所有儲存格，套用預設字體
    for row in sheet.iter_rows(min_row=2): # 從第二行開始，因為表頭已設定
        for cell in row:
            cell.font = default_font

    # 根據內容自動調整欄寬
    for column_cells in sheet.columns:
        max_length = 0
        column_letter = column_cells[0].column_letter # 獲取欄位字母 (e.g., 'A')
        for cell in column_cells:
            # 考慮中文字元寬度約為英數字元的兩倍
            cell_length = sum(2 if '\u4e00' <= char <= '\u9fff' else 1 for char in str(cell.value))
            if cell_length > max_length:
                max_length = cell_length
        adjusted_width = max_length + 6 # 增加一點額外寬度
        sheet.column_dimensions[column_letter].width = adjusted_width

    # 將檔案儲存到記憶體中
    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)

    return send_file(output, as_attachment=True, download_name='registrations.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
# --- END 使用 openpyxl 建立 Excel 檔案 ---

# @app.route('/uploads/<filename>')
# def uploaded_file(filename):
#    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# 下載檔案路由
@app.route('/download/<int:file_id>')
@login_required
def download_file(file_id):
    course_file = db.session.get(CourseFile, file_id)
    if not course_file:
        flash('找不到指定的檔案', 'warning')
        
    # 在提供下載時才使用 secure_filename
    safe_display_name = secure_filename(course_file.display_filename)

    return send_from_directory(
        app.config['UPLOAD_FOLDER'], 
        course_file.file_path, 
        as_attachment=True, 
        download_name=safe_display_name # 使用淨化後的檔名
    )
# ---- END ----

# --- API 路由 (供前端 JavaScript 呼叫) ---

# [GET] 取得課程列表 (支援搜尋與篩選)
@app.route('/api/courses', methods=['GET'])
def get_courses():
    query = Course.query
    search = request.args.get('search')
    status = request.args.get('status')

    if search:
        query = query.filter(Course.name.contains(search))
    if status and status != 'all':
        query = query.filter_by(status=status)
    
    courses = query.all()

    # --- 計算每門課程的排序用時間戳 ---
    now = datetime.now() # 伺服器已是 GMT+8，改回使用本地時間
    for c in courses:
        c.sort_timestamp = datetime.max # 預設一個很大的時間，讓沒有時間的課程排在最後
        if c.time_slots:
            # 過濾掉已經過去的梯次，只考慮未來的最早梯次
            future_slots = [s.slot_start_time for s in c.time_slots if s.slot_start_time > now]
            if future_slots:
                c.sort_timestamp = min(future_slots)
        elif c.allow_user_to_choose_time and c.user_choice_start_date:
            # 如果是自選時間，使用可選的開始日期作為排序依據
            # 為了能和其他 datetime 物件比較，我們組合一個 datetime
            c.sort_timestamp = datetime.combine(c.user_choice_start_date, datetime.min.time())

    # 1. '報名中' 的課程優先
    # 2. 其他課程依照 sort_timestamp (最早開始時間) 由近到遠排序
    courses.sort(key=lambda c: (c.status != '報名中', c.sort_timestamp))

    courses_data = []
    # 遍歷每一門課程，組合成前端需要的 JSON 格式
    for c in courses:
        is_registered = False
        if current_user.is_authenticated:
            user_reg = Registration.query.join(TimeSlot).filter(
                Registration.user_id == current_user.id,
                TimeSlot.course_id == c.id
            ).first()
            is_registered = user_reg is not None
        
        class_time_summary = "尚未設定"
        if c.time_slots:
            earliest_start_time = min(slot.slot_start_time for slot in c.time_slots)
            latest_end_time = max(slot.slot_end_time for slot in c.time_slots)
            start_str = earliest_start_time.strftime('%Y-%m-%d %H:%M')
            if earliest_start_time.date() == latest_end_time.date():
                end_str = latest_end_time.strftime('%H:%M')
            else:
                end_str = latest_end_time.strftime('%Y-%m-%d %H:%M')
            class_time_summary = f"{start_str} ~ {end_str}"

        # --- 判斷課程是否已額滿 ---
        is_full = False
        # 只有在有固定梯次且非自選時間的模式下，才需要判斷是否額滿
        if c.has_time_slots and not c.allow_user_to_choose_time:
            # 查詢是否還存在任何一個有剩餘名額的梯次
            available_slot_exists = db.session.query(TimeSlot.query.filter(
                TimeSlot.course_id == c.id,
                TimeSlot.booked_count < TimeSlot.capacity
            ).exists()).scalar()
            is_full = not available_slot_exists
        
        courses_data.append({
            'id': c.id,
            'name': c.name,
            'description': c.description,
            'speaker_info': c.speaker_info,
            'status': c.status,
            'class_time_summary': class_time_summary, # 課程時間摘要
            'registration_start_time': c.registration_start_time.strftime('%Y-%m-%d %H:%M'),
            'registration_end_time': c.registration_end_time.strftime('%Y-%m-%d %H:%M'),
            'is_full': is_full, # <--- 新增的欄位
            'is_registered': is_registered, # 使用者是否已報名
            # 課程檔案列表
            'files': [
                {'id': f.id, 'url': url_for('download_file', file_id=f.id), 'name': f.display_filename} 
                for f in c.files
            ]
        })

    return jsonify(courses_data)
# ---- END ----

# [GET] 取得我報名的課程
@app.route('/api/my_courses', methods=['GET'])
@login_required
def get_my_courses():
    """
    取得目前使用者報名的課程列表。
    支援透過 query string `status` 進行篩選：
    - '課程即將開始'
    - '課程進行中'
    - '課程已結束'
    """
    status_filter = request.args.get('status')
    # --- 修正：使用本地時間 (now) 來進行比較，以匹配資料庫中儲存的本地時間 ---
    now = datetime.now() # 伺服器已是 GMT+8，改回使用本地時間

    # 1. 建立基礎查詢，找出這位使用者所有的報名紀錄
    query = Registration.query.filter_by(user_id=current_user.id).join(TimeSlot)

    # 2. 根據傳入的 status 參數，增加時間過濾條件
    if status_filter == '課程即將開始':
        query = query.filter(TimeSlot.slot_start_time > now)
    elif status_filter == '課程進行中':
        query = query.filter(TimeSlot.slot_start_time <= now, TimeSlot.slot_end_time > now)
    elif status_filter == '課程已結束':
        query = query.filter(TimeSlot.slot_end_time <= now)

    # 3. 執行查詢與排序
    if status_filter and status_filter != 'all':
        # 如果是篩選特定狀態，則統一由舊到新排序
        registrations = query.order_by(TimeSlot.slot_start_time.asc()).all()
    else:
        # 如果是顯示「全部」，則套用自訂排序邏輯
        all_regs = query.all()
        
        def sort_key(reg):
            slot = reg.time_slot
            
            if slot.slot_start_time <= now < slot.slot_end_time:
                # 1. 進行中的課程，優先級最高
                return (0, slot.slot_start_time)
            elif now < slot.slot_start_time:
                # 2. 即將開始的課程，次高，按開始時間升序
                return (1, slot.slot_start_time)
            else:
                # 3. 已結束的課程，最低，按開始時間降序 (最近結束的排在前面)
                return (2, -slot.slot_start_time.timestamp())
        registrations = sorted(all_regs, key=sort_key)
    
    my_registrations_data = []
    for reg in registrations:
        try:
            # 進行防錯檢查，確保關聯的資料都存在
            if not reg.time_slot or not reg.time_slot.course:
                continue  # 如果是無效的報名，直接跳到下一筆

            course = reg.time_slot.course
            slot = reg.time_slot
            
            # 4. 格式化該次報名的梯次時間
            # 判斷課程狀態
            if now < slot.slot_start_time:
                registration_status = "課程即將開始"
            elif slot.slot_start_time <= now < slot.slot_end_time:
                registration_status = "課程進行中"
            else:
                registration_status = "課程已結束"

            # 格式化該次報名的梯次時間
            start_str = slot.slot_start_time.strftime('%Y-%m-%d %H:%M') # 格式化開始時間
            if slot.slot_start_time.date() == slot.slot_end_time.date():
                end_str = slot.slot_end_time.strftime('%H:%M')
            else:
                end_str = slot.slot_end_time.strftime('%Y-%m-%d %H:%M')
            
            class_time = f"{start_str} ~ {end_str}"

            # 5. 組合回傳給前端的 JSON 資料
            my_registrations_data.append({
                'registration_id': reg.id,
                'course_id': course.id,
                'course_name': course.name,
                'class_time': class_time,
                'course_description': course.description,
                'speaker_info': course.speaker_info,
                'slot_start_time': slot.slot_start_time.isoformat(),
                'status': registration_status, # 新增：課程狀態
                'files': [
                    {'id': f.id, 'url': url_for('download_file', file_id=f.id), 'name': f.display_filename} 
                    for f in course.files
                ]
            })
        except Exception as e:
            # 如果處理某筆紀錄時發生任何未知錯誤，就在後台印出錯誤訊息，然後繼續處理下一筆
            print(f"處理報名紀錄 ID {reg.id} 時發生錯誤: {e}")
            continue

    return jsonify(my_registrations_data)
# ---- END ----

# [POST] 報名課程

@app.route('/api/register', methods=['POST'])
@login_required
def register_for_slot():
    """
    處理課程報名，支援兩種模式：
    1. 固定梯次報名 (傳入 time_slot_id)
    2. 使用者自選時間報名 (傳入 course_id 和 user_selected_time)
    """
    data = request.get_json()
    slot_id = data.get('time_slot_id')
    course_id = data.get('course_id')
    user_selected_time_str = data.get('user_selected_time')

    try:
        if slot_id:
            # --- 模式一：固定梯次報名 ---
            slot = TimeSlot.query.get(slot_id)
            if not slot:
                return jsonify({'success': False, 'message': '找不到指定的梯次'}), 404
            
            course = slot.course
            # ▼▼▼ 修改：接收驗證函式的回傳值 ▼▼▼
            validation_error = _validate_registration(course, current_user)
            if validation_error:
                return jsonify({'success': False, 'message': validation_error}), 400

            # 檢查時間衝突
            conflicting_course_name = _check_time_conflict(current_user, slot.slot_start_time, slot.slot_end_time)
            if conflicting_course_name:
                error_message = f"報名失敗：此時段與您已報名的課程「{conflicting_course_name}」時間重疊。"
                return jsonify({'success': False, 'message': error_message}), 400

            if slot.booked_count >= slot.capacity:
                return jsonify({'success': False, 'message': '此梯次名額已滿'}), 400

            # 更新已報名人數
            slot.booked_count += 1
            target_slot_id = slot.id

        elif course_id and user_selected_time_str:
            # --- 模式二：使用者自選時間報名 ---
            course = db.session.get(Course, course_id)
            if not course or not course.allow_user_to_choose_time:
                return jsonify({'success': False, 'message': '此課程不支援自選時間或不存在'}), 404

            # 接收驗證函式的回傳值
            validation_error = _validate_registration(course, current_user)
            if validation_error:
                return jsonify({'success': False, 'message': validation_error}), 400

            user_time = datetime.strptime(user_selected_time_str, '%Y-%m-%dT%H:%M')
            user_end_time = user_time + timedelta(hours=course.duration_hours)

            # --- 新增：檢查是否與午休時間 (12:00-13:30) 重疊 ---
            # "不包含12點" 和 "不包含1點半" 意味著任何與 (12:00, 13:30) 這個開區間重疊的預約都是無效的
            lunch_break_start = datetime.combine(user_time.date(), time(12, 0))
            lunch_break_end = datetime.combine(user_time.date(), time(13, 30))

            # 檢查重疊條件：(課程開始時間 < 午休結束時間) AND (課程結束時間 > 午休開始時間)
            if user_time < lunch_break_end and user_end_time > lunch_break_start:
                error_message = "報名失敗：預約時段不可與中午休息時間 (12:00 ~ 13:30) 重疊。"
                return jsonify({'success': False, 'message': error_message}), 400

            # 檢查時間衝突，並傳入 course.id 以啟用 1.5 小時緩衝檢查
            conflicting_course_name = _check_time_conflict(current_user, user_time, user_end_time, course_id_for_self_choice=course.id)
            if conflicting_course_name:
                error_message = f"報名失敗：您選擇的時段與其他人的預約時段過於接近（需間隔1.5小時），或與您已報名的其他課程時間重疊。"
                return jsonify({'success': False, 'message': error_message}), 400

            # --- 檢查該時段是否與此課程的其他預約時間重疊 ---
            # 條件: (新時段的開始 < 已預約時段的結束) AND (新時段的結束 > 已預約時段的開始)
            conflicting_slot = TimeSlot.query.filter(
                TimeSlot.course_id == course.id,
                TimeSlot.slot_start_time < user_end_time,
                TimeSlot.slot_end_time > user_time
            ).first()
            if conflicting_slot:
                return jsonify({'success': False, 'message': '您選擇的時段與其他人的預約時間重疊，請選擇其他時間。'}), 400

            # --- 分別驗證日期和時間範圍 ---
            user_selected_date = user_time.date()
            user_selected_time_of_day = user_time.time()
            is_date_valid = course.user_choice_start_date <= user_selected_date <= course.user_choice_end_date
            is_time_valid = course.user_choice_start_time_of_day <= user_selected_time_of_day <= course.user_choice_end_time_of_day
            # 確保兩者都有效
            if not (is_date_valid and is_time_valid):
                return jsonify({'success': False, 'message': '您選擇的時間不在允許的範圍內(中午休息時間不能選擇)'}), 400

            # 為這次報名動態創建一個專屬的 TimeSlot，結束時間根據課程時數計算
            new_slot = TimeSlot(
                course_id=course.id,
                slot_start_time=user_time,
                slot_end_time=user_end_time, # 根據課程時數計算結束時間
                capacity=1, # 這個梯次專屬於此使用者
                booked_count=1 # 直接設為已滿
            )
            db.session.add(new_slot) # 新增到 session
            db.session.flush() # 立即執行插入以獲取 new_slot.id
            target_slot_id = new_slot.id

        else:
            return jsonify({'success': False, 'message': '報名資訊不完整'}), 400

        # 建立報名紀錄
        new_reg = Registration(user_id=current_user.id, time_slot_id=target_slot_id)
        db.session.add(new_reg)
        db.session.commit()

        return jsonify({'success': True, 'message': '報名成功！'})

    except (ValueError, TypeError) as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'報名失敗: {e}'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'伺服器發生未知錯誤: {e}'}), 500

def _check_time_conflict(user, new_slot_start, new_slot_end, course_id_for_self_choice=None):
    """
    檢查新的時間區段是否與使用者已報名的課程時間重疊。
    對於自選時間的課程，還會檢查與該課程其他已預約時段的衝突。

    :param user: 目前登入的使用者物件
    :param new_slot_start: 新報名課程的開始時間 (datetime object)
    :param new_slot_end: 新報名課程的結束時間 (datetime object)
    :param course_id_for_self_choice: 如果是自選時間模式，傳入課程 ID 以檢查同課程的其他預約
    :return: 如果有衝突，返回衝突的課程名稱；否則返回 None。
    """
    # 定義課程之間的緩衝時間為 1.5 小時
    buffer = timedelta(hours=1.5)

    # 步驟 1: 檢查與使用者自己已報名的 *所有* 課程是否有時間衝突
    # 查詢使用者所有已報名的紀錄
    all_user_registrations = Registration.query.filter_by(user_id=user.id).join(TimeSlot).all()

    for reg in all_user_registrations:
        existing_start = reg.time_slot.slot_start_time
        existing_end = reg.time_slot.slot_end_time
        # 檢查時間重疊，不考慮緩衝
        if new_slot_start < existing_end and new_slot_end > existing_start:
            return reg.time_slot.course.name # 發現衝突，返回衝突的課程名稱

    # 步驟 2: 如果是自選時間模式，檢查與該課程 *其他* 已被預約的時段是否有緩衝衝突
    if course_id_for_self_choice:
        # 找出該課程所有已被預約的時段 (capacity=1 代表是自選時段)
        booked_slots = TimeSlot.query.filter_by(course_id=course_id_for_self_choice, capacity=1).all()
        for slot in booked_slots:
            # 檢查時間重疊，並考慮緩衝時間
            # 條件：(新時段的開始) < (已預約時段的結束 + 緩衝) AND (新時段的結束 + 緩衝) > (已預約時段的開始)
            if new_slot_start < (slot.slot_end_time + buffer) and (new_slot_end + buffer) > slot.slot_start_time:
                return slot.course.name # 發現衝突
            
    return None # 沒有任何衝突

def _validate_registration(course, user):
    """報名前的統一驗證輔助函式"""
    # 檢查課程是否仍在報名期間
    if course.status != '報名中' or datetime.now() >= course.registration_end_time: # 伺服器已是 GMT+8，改回使用本地時間
        if course.status == '報名中':
            course.status = '報名截止'
            db.session.commit()
        return '此課程報名已截止。'

    # 檢查是否已經報名過此課程的任何梯次
    existing_reg = Registration.query.join(TimeSlot).filter(
        Registration.user_id == user.id,
        TimeSlot.course_id == course.id
    ).first()
    if existing_reg:
        return '您已經報名過此課程。'
    return None # 如果所有驗證都通過，返回 None

# [DELETE] 使用者取消報名
@app.route('/api/registrations/<int:registration_id>/cancel', methods=['POST'])
@login_required
def cancel_registration(registration_id):
    # 1. 找到報名紀錄，並確保是目前登入的使用者所擁有的
    reg = Registration.query.filter_by(id=registration_id, user_id=current_user.id).first()
    if not reg:
        return jsonify({'success': False, 'message': '找不到您的報名紀錄或無權限操作。'}), 404

    slot = reg.time_slot
    # 2. 檢查是否在可取消的期限內 (課程開始前 2 天)
    if datetime.utc() > (slot.slot_start_time - timedelta(days=2)):
        return jsonify({'success': False, 'message': '已超過取消期限，無法取消報名'}), 400

    # 3. 執行取消邏輯
    try:

        # 先刪除報名紀錄本身
        db.session.delete(reg)

        # 接著判斷梯次類型並處理
        if slot.capacity == 1:
            # 如果是自選的單人梯次，則連同梯次一併刪除
            db.session.delete(slot)
        elif slot.booked_count > 0:
            # 如果是固定梯次，則將已報名人數減 1
            slot.booked_count -= 1

        db.session.commit()
        return jsonify({'success': True, 'message': '已成功取消報名。'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'處理取消時發生錯誤: {e}'}), 500


# --- 以下為後台管理 API ---

# [POST] 新增課程
@app.route('/api/admin/courses', methods=['POST'])
@login_required
@admin_required
def create_course():
    data = request.form
    uploaded_files = request.files.getlist('files')
    # 解析並驗證時間格式
    try:
        start_time = datetime.strptime(data['registration_start_time'], '%Y-%m-%dT%H:%M')
        end_time = datetime.strptime(data['registration_end_time'], '%Y-%m-%dT%H:%M')

        # --- 處理自選時間的邏輯 ---
        allow_user_choice = 'allow_user_to_choose_time' in data
        user_choice_start_date = datetime.strptime(data['user_choice_start_date'], '%Y-%m-%d').date() if allow_user_choice and data.get('user_choice_start_date') else None
        user_choice_end_date = datetime.strptime(data['user_choice_end_date'], '%Y-%m-%d').date() if allow_user_choice and data.get('user_choice_end_date') else None
        user_choice_start_time_of_day = datetime.strptime(data['user_choice_start_time_of_day'], '%H:%M').time() if allow_user_choice and data.get('user_choice_start_time_of_day') else None
        user_choice_end_time_of_day = datetime.strptime(data['user_choice_end_time_of_day'], '%H:%M').time() if allow_user_choice and data.get('user_choice_end_time_of_day') else None
            
        new_course = Course(
            name=data['name'],
            description=data['description'],
            speaker_info=data['speaker_info'],
            duration_hours=float(data.get('duration_hours', 1)),
            status='尚未開放', # 統一由排程任務更新狀態
            registration_start_time=start_time,
            registration_end_time=end_time,
            has_time_slots=not allow_user_choice,
            allow_user_to_choose_time=allow_user_choice,
            user_choice_start_date=user_choice_start_date,
            user_choice_end_date=user_choice_end_date,
            user_choice_start_time_of_day=user_choice_start_time_of_day,
            user_choice_end_time_of_day=user_choice_end_time_of_day
        )

        # 呼叫輔助函式來處理梯次和檔案
        if not allow_user_choice:
            _handle_time_slots(data, new_course)

        _handle_file_uploads(uploaded_files, new_course)
        
        db.session.add(new_course)
        db.session.commit()
        
        flash('課程新增成功！', 'success')
        return redirect(url_for('admin_dashboard'))

    except ValueError as e:
        flash(str(e), 'danger')
        return redirect(url_for('new_course'))

# [POST] 更新課程
@app.route('/api/admin/courses/<int:course_id>', methods=['POST'])
@login_required
@admin_required
def update_course(course_id):
    course = Course.query.get_or_404(course_id)
    data = request.form
    uploaded_files = request.files.getlist('files')

    try:
        start_time = datetime.strptime(data['registration_start_time'], '%Y-%m-%dT%H:%M')
        end_time = datetime.strptime(data['registration_end_time'], '%Y-%m-%dT%H:%M')

        # --- 處理自選時間的邏輯 ---
        allow_user_choice = 'allow_user_to_choose_time' in data
        user_choice_start_date = datetime.strptime(data['user_choice_start_date'], '%Y-%m-%d').date() if allow_user_choice and data.get('user_choice_start_date') else None
        user_choice_end_date = datetime.strptime(data['user_choice_end_date'], '%Y-%m-%d').date() if allow_user_choice and data.get('user_choice_end_date') else None
        user_choice_start_time_of_day = datetime.strptime(data['user_choice_start_time_of_day'], '%H:%M').time() if allow_user_choice and data.get('user_choice_start_time_of_day') else None
        user_choice_end_time_of_day = datetime.strptime(data['user_choice_end_time_of_day'], '%H:%M').time() if allow_user_choice and data.get('user_choice_end_time_of_day') else None

        # 更新課程基本資料
        course.name = data['name']
        course.description = data['description']
        course.speaker_info = data['speaker_info']
        course.duration_hours = float(data.get('duration_hours', 1))
        course.status = '尚未開放' # 統一由排程任務更新狀態
        course.registration_start_time = start_time
        course.registration_end_time = end_time
        course.has_time_slots = not allow_user_choice
        course.allow_user_to_choose_time = allow_user_choice
        course.user_choice_start_date = user_choice_start_date
        course.user_choice_end_date = user_choice_end_date
        course.user_choice_start_time_of_day = user_choice_start_time_of_day
        course.user_choice_end_time_of_day = user_choice_end_time_of_day

        # 清除舊梯次並呼叫輔助函式重建
        TimeSlot.query.filter_by(course_id=course.id).delete()
        # 只有在未啟用自選時間時，才處理固定梯次
        if not allow_user_choice:
            _handle_time_slots(data, course)

        # 呼叫輔助函式處理新上傳的檔案
        _handle_file_uploads(uploaded_files, course)

        db.session.commit()
        
        flash('課程更新成功！', 'success')
        return redirect(url_for('admin_dashboard'))

    except ValueError as e:
        flash(str(e), 'danger')
        return redirect(url_for('edit_course', course_id=course.id))

# ---- START: 新增的輔助函式 ----
def _handle_time_slots(data, course_object):
    """輔助函式：處理課程梯次的建立"""
    # 只有在 'allow_user_to_choose_time' 未勾選時，這些欄位才可能存在且需要處理
    slot_start_times = data.getlist('slot_start_times') 
    slot_end_times = data.getlist('slot_end_times') 
    slot_capacities = data.getlist('slot_capacities') 

    # 如果沒有提交任何梯次資料，且是固定梯次模式，則報錯
    if not slot_start_times:
        raise ValueError("請至少設定一個上課時間梯次。")

    for start_str, end_str, capacity_str in zip(slot_start_times, slot_end_times, slot_capacities):
        if not start_str or not end_str or not capacity_str:
            continue
        
        try:
            capacity = int(capacity_str)
            if capacity <= 0:
                raise ValueError("人數上限必須是正整數")
            
            start_time = datetime.strptime(start_str, '%Y-%m-%dT%H:%M')
            end_time = datetime.strptime(end_str, '%Y-%m-%dT%H:%M')

            # 驗證：結束時間必須晚於開始時間
            if end_time <= start_time:
                raise ValueError("結束時間必須晚於開始時間")

            new_slot = TimeSlot(
                slot_start_time=start_time,
                slot_end_time=end_time,
                capacity=capacity
            )
            course_object.time_slots.append(new_slot)
        except (ValueError, TypeError) as e:
            raise ValueError(f"梯次資料格式錯誤: '{start_str}' -> '{end_str}' ({e})")

# 輔助函式：處理檔案上傳
def _handle_file_uploads(files, course_object):
    for file in files:
        if file and file.filename != '':
            original_filename = file.filename
            
            # (舊的錯誤程式碼已被移除)
            # safe_display_name = secure_filename(original_filename) 

            _, ext = os.path.splitext(original_filename)
            stored_filename = f"{uuid.uuid4().hex}{ext}"
            
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], stored_filename))
            
            new_file = CourseFile(
                file_path=stored_filename,
                display_filename=original_filename, 
                course=course_object
            )
            db.session.add(new_file)

# [DELETE] 刪除課程
@app.route('/api/admin/courses/<int:course_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_course(course_id): # 刪除課程 函式
    course = Course.query.get_or_404(course_id)
    db.session.delete(course)
    db.session.commit()
    return jsonify({'success': True, 'message': '課程已刪除'})

# [GET] 取得單一課程的報名者列表
@app.route('/api/admin/courses/<int:course_id>/registrations', methods=['GET'])
@login_required
@admin_required
def get_registrations(course_id):# 取得單一課程的報名者列表 函式
    registrations = Registration.query.join(TimeSlot).filter(TimeSlot.course_id == course_id).order_by(TimeSlot.slot_start_time, Registration.registration_time).all()
    
    users_data = []
    for reg in registrations:
        # 格式化梯次的起迄時間
        slot_start = reg.time_slot.slot_start_time
        slot_end = reg.time_slot.slot_end_time
        
        # 檢查是否為同一天
        if slot_start.date() == slot_end.date():
            slot_display = f"{slot_start.strftime('%Y-%m-%d %H:%M')} ~ {slot_end.strftime('%H:%M')}"
        else:
            slot_display = f"{slot_start.strftime('%Y-%m-%d %H:%M')} ~ {slot_end.strftime('%Y-%m-%d %H:%M')}"

        users_data.append({
            'username': reg.user.username,
            'registration_time': reg.local_registration_time().strftime('%Y-%m-%d %H:%M'),
            'slot_time': slot_display # <-- 確保這個鍵名是 slot_time
        })
        
    return jsonify(users_data)

# [DELETE] 刪除指定的課程檔案
@app.route('/api/admin/files/<int:file_id>', methods=['DELETE'])
@login_required
@admin_required
# 刪除指定的課程檔案 函式
def delete_course_file(file_id):
    
    #API: 刪除指定的課程檔案
    # 1. 從資料庫中找到檔案紀錄
    file_to_delete = CourseFile.query.get_or_404(file_id)
    
    # 2. 取得檔案在伺服器上的實際路徑
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file_to_delete.file_path)
    
    try:
        # 3. 從資料庫刪除紀錄
        db.session.delete(file_to_delete)
        
        # 4. 從伺服器刪除實體檔案
        if os.path.exists(file_path):
            os.remove(file_path)
            
        # 5. 提交變更
        db.session.commit()
        
        return jsonify({'success': True, 'message': '檔案已成功刪除'})
    # 6. 錯誤處理
    except Exception as e:
        db.session.rollback()
        print(f"刪除檔案時發生錯誤: {e}")
        return jsonify({'success': False, 'message': '刪除檔案時發生錯誤'}), 500

# [POST] 管理者取消報名
@app.route('/api/admin/registrations/<int:registration_id>/cancel', methods=['POST'])
@login_required
@admin_required
def admin_cancel_registration(registration_id):
    reg = db.session.get(Registration, registration_id)
    if not reg:
        flash('找不到指定的報名紀錄。', 'danger')
        return redirect(url_for('all_registrations', **request.args))

    try:
        slot = reg.time_slot
        
        # 先刪除報名紀錄
        db.session.delete(reg)
        
        # 判斷梯次類型並處理
        if slot.capacity == 1:
            # 自選的單人梯次，一併刪除
            db.session.delete(slot)
        elif slot.booked_count > 0:
            # 固定梯次，人數減 1
            slot.booked_count -= 1
        
        db.session.commit()
        flash('已成功取消該筆報名。', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'處理取消時發生錯誤: {e}', 'danger')
    
    return redirect(url_for('all_registrations', **request.args))


# --- 主程式進入點 & 初始化 ---
# --- 主程式進入點 & 初始化 ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            print("建立預設管理者帳號...")
            admin_user = User(username='admin', is_admin=True)
            admin_user.set_password('Futsu_Admin')
            db.session.add(admin_user)
            db.session.commit()
            print("管理者帳號: admin, 密碼: Futsu_Admin")

        print("[Startup] 正在執行首次課程狀態檢查...")
        check_course_status()
        print("[Startup] 首次檢查完成。")

    # 改成這樣，不要啟用 debug
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5003)))

# if __name__ == '__main__':
#     with app.app_context():
#         db.create_all() # 建立所有資料表
#         # 檢查是否已有 admin 使用者，若無則建立一個
#         if not User.query.filter_by(username='admin').first():
#             print("建立預設管理者帳號...")
#             admin_user = User(username='admin', is_admin=True)
#             admin_user.set_password('Futsu_Admin') # 預設密碼
#             db.session.add(admin_user)
#             db.session.commit()
#             print("管理者帳號: admin, 密碼: Futsu_Admin")

#         # 在啟動前手動執行一次狀態檢查
#         print("[Startup] 正在執行首次課程狀態檢查...")
#         check_course_status()
#         print("[Startup] 首次檢查完成。")

#     app.run(debug=True) # debug=True 會在程式碼變動時自動重啟