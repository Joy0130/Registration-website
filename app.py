import os
import uuid
from datetime import datetime, timedelta 
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, send_from_directory, abort
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from apscheduler.schedulers.background import BackgroundScheduler

# --- App 組態設定 ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'a_default_secret_key'  # 可從環境變數取得，若無則使用預設值 (開發時可用)
#app.config['SECRET_KEY'] = 'a_very_secret_key_that_should_be_changed' # 測試用
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///../instance/database.db' # SQLite 資料庫路徑
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
    description = db.Column(db.Text, nullable=False)
    speaker_info = db.Column(db.String(200))
    has_time_slots = db.Column(db.Boolean, default=False, nullable=False)
    status = db.Column(db.String(20), default='尚未開放')
    registration_start_time = db.Column(db.DateTime, nullable=False)
    registration_end_time = db.Column(db.DateTime, nullable=False)
    allow_user_to_choose_time = db.Column(db.Boolean, default=False, nullable=False)
    duration_hours = db.Column(db.Float, nullable=True, default=1) # 新增：上課時數欄位
    # --- 將自選時間範圍拆分為日期和時間---
    user_choice_start_date = db.Column(db.Date, nullable=True)
    user_choice_end_date = db.Column(db.Date, nullable=True)
    user_choice_start_time_of_day = db.Column(db.Time, nullable=True)
    user_choice_end_time_of_day = db.Column(db.Time, nullable=True)

    __table_args__ = {'extend_existing': True}

    # --- 關聯 (Relationships) ---
    files = db.relationship('CourseFile', backref='course', lazy=True, cascade="all, delete-orphan")
    # A TimeSlot has many Registrations. When a TimeSlot is deleted, all its registrations are also deleted.
    # When a registration is deleted and it's the last one for a TimeSlot, the TimeSlot becomes an orphan and is deleted.
    time_slots = db.relationship('TimeSlot', backref='course', lazy=True, cascade="all, delete-orphan")

# 報名紀錄 table
class Registration(db.Model):
    __tablename__ = 'registration'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    time_slot_id = db.Column(db.Integer, db.ForeignKey('time_slot.id'), nullable=False)
    registration_time = db.Column(db.DateTime, default=datetime.utcnow) # 儲存的是 UTC 時間
    __table_args__ = {'extend_existing': True}

    # --- 關聯 (Relationships) ---
    user = db.relationship('User', backref=db.backref('registrations', lazy=True))
    time_slot = db.relationship('TimeSlot', backref=db.backref('registrations', lazy='dynamic', cascade="all, delete-orphan", single_parent=True))

    # --- ▼▼▼ 新增的輔助函式 ▼▼▼ ---
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
    capacity = db.Column(db.Integer, nullable=False, default=999)
    booked_count = db.Column(db.Integer, default=0)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    __table_args__ = {'extend_existing': True}


# --- 使用者載入函式 (Flask-Login) ---
@login_manager.user_loader
def load_user(user_id): # 透過 user_id 載入使用者
    return User.query.get(int(user_id)) # 從資料庫取得使用者資料

# --- 定時任務 (自動更新課程狀態) ---
def check_course_status():
    with app.app_context():
        print(" [Scheduler] 正在檢查課程狀態...")
        now = datetime.now()

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

    # --- ▼▼▼ 新增：取得已被預約的自選時段 ▼▼▼ ---
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
    if course.allow_user_to_choose_time and course.user_choice_start_date and course.user_choice_start_time_of_day:
        user_choice_start_datetime = datetime.combine(course.user_choice_start_date, course.user_choice_start_time_of_day)
    if course.allow_user_to_choose_time and course.user_choice_end_date and course.user_choice_end_time_of_day:
        user_choice_end_datetime = datetime.combine(course.user_choice_end_date, course.user_choice_end_time_of_day)
            
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
    """
    顯示所有使用者的報名紀錄，並支援多條件篩選。
    """
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
    
    # 取得所有課程列表，用於填充下拉選單
    all_courses = Course.query.order_by(Course.name).all()
    
    # 執行最終查詢並排序
    all_regs = query.order_by(Registration.id.desc()).all()
    
    # 將 request 和 all_courses 物件傳給模板
    return render_template(
        'admin_all_registrations.html', 
        registrations=all_regs, 
        all_courses=all_courses, 
        request=request
    )

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
    
    courses = query.order_by(Course.id.desc()).all()
    courses_data = []
    
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

        # --- ▼▼▼ 新增：判斷課程是否已額滿 ▼▼▼ ---
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
            'class_time_summary': class_time_summary, # <--- 確保這個鍵名存在
            'registration_start_time': c.registration_start_time.strftime('%Y-%m-%d %H:%M'),
            'registration_end_time': c.registration_end_time.strftime('%Y-%m-%d %H:%M'),
            'is_full': is_full, # <--- 新增的欄位
            'is_registered': is_registered,
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
    # 1. 找出這位使用者所有的報名紀錄
    registrations = Registration.query.filter_by(user_id=current_user.id).order_by(Registration.registration_time.desc()).all()
    
    my_registrations_data = []
    # 2. 遍歷每一筆報名紀錄
    for reg in registrations:
        try:
            # 3. 進行防錯檢查，確保關聯的資料都存在
            if not reg.time_slot or not reg.time_slot.course:
                continue  # 如果是無效的報名，直接跳到下一筆

            course = reg.time_slot.course
            slot = reg.time_slot
            
            # 4. 格式化該次報名的梯次時間
            start_str = slot.slot_start_time.strftime('%Y-%m-%d %H:%M')
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
            _validate_registration(course, current_user) # 統一驗證

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

            _validate_registration(course, current_user) # 統一驗證

            user_time = datetime.strptime(user_selected_time_str, '%Y-%m-%dT%H:%M')

            # --- ▼▼▼ 新增：檢查該時段是否已被預約 ▼▼▼ ---
            existing_slot = TimeSlot.query.filter_by(
                course_id=course.id, 
                slot_start_time=user_time
            ).first()
            if existing_slot:
                return jsonify({'success': False, 'message': '您選擇的時段已被其他使用者預約，請選擇其他時間。'}), 400

            # --- ▼▼▼ 修正：分別驗證日期和時間範圍 ▼▼▼ ---
            user_selected_date = user_time.date()
            user_selected_time_of_day = user_time.time()

            is_date_valid = course.user_choice_start_date <= user_selected_date <= course.user_choice_end_date
            is_time_valid = course.user_choice_start_time_of_day <= user_selected_time_of_day <= course.user_choice_end_time_of_day
            
            if not (is_date_valid and is_time_valid):
                return jsonify({'success': False, 'message': '您選擇的時間不在允許的範圍內'}), 400


            # 為這次報名動態創建一個專屬的 TimeSlot，結束時間根據課程時數計算
            new_slot = TimeSlot(
                course_id=course.id,
                slot_start_time=user_time,
                slot_end_time=user_time + timedelta(hours=course.duration_hours),
                capacity=1, # 這個梯次專屬於此使用者
                booked_count=1 # 直接設為已滿
            )
            db.session.add(new_slot)
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

def _validate_registration(course, user):
    """報名前的統一驗證輔助函式"""
    if course.status != '報名中' or datetime.now() >= course.registration_end_time:
        if course.status == '報名中':
            course.status = '報名截止'
            db.session.commit()
        raise ValueError('此課程報名已截止。')

    existing_reg = Registration.query.join(TimeSlot).filter(
        Registration.user_id == user.id,
        TimeSlot.course_id == course.id
    ).first()
    if existing_reg:
        raise ValueError('您已經報名過此課程。')

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
    if datetime.utcnow() > (slot.slot_start_time - timedelta(days=2)):
        return jsonify({'success': False, 'message': '已超過取消期限，無法取消報名'}), 400

    # 3. 執行取消邏輯
    try:
        # ▼▼▼ 這裡是主要的修改處 ▼▼▼
        # 先刪除報名紀錄本身
        db.session.delete(reg)

        # 接著判斷梯次類型並處理
        if slot.capacity == 1:
            # 如果是自選的單人梯次，則連同梯次一併刪除
            db.session.delete(slot)
        elif slot.booked_count > 0:
            # 如果是固定梯次，則將已報名人數減 1
            slot.booked_count -= 1
        # --- ▲▲▲ 修改結束 ▲▲▲ ---

        db.session.commit()
        return jsonify({'success': True, 'message': '已成功取消報名。'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'處理取消時發生錯誤: {e}'}), 500
# @app.route('/api/courses/<int:course_id>/register', methods=['POST'])
# @login_required
# def register_course(course_id):
#     course = Course.query.get_or_404(course_id)

#     # 增加即時的截止時間檢查
#     if datetime.now() >= course.registration_end_time:
#         # 如果時間已過，更新資料酷狀態
#         if course.status == '報名中':
#             course.status = '報名截止'
#             db.session.commit() # 提交狀態更新
#         return jsonify({'success': False, 'message': '此課程報名時間已截止。'}), 400
#     # 檢查課程是否開放報名
#     if course.status != '報名中':
#         return jsonify({'success': False, 'message': '此課程目前無法報名。'}), 400
#     # 檢查是否已經報名過
#     existing_reg = Registration.query.filter_by(user_id=current_user.id, course_id=course_id).first()
#     # 如果已經報名過，回傳錯誤訊息
#     if existing_reg:
#         return jsonify({'success': False, 'message': '您已經報名過此課程。'}), 400
#     # 建立新的報名紀錄
#     new_reg = Registration(user_id=current_user.id, course_id=course_id)
#     db.session.add(new_reg)
#     db.session.commit()
#     return jsonify({'success': True, 'message': '報名成功！'})


# --- 以下為後台管理 API ---

# [POST] 新增課程
@app.route('/api/admin/courses', methods=['POST'])
@login_required
@admin_required
def create_course():
    data = request.form
    uploaded_files = request.files.getlist('files')
    
    try:
        start_time = datetime.strptime(data['registration_start_time'], '%Y-%m-%dT%H:%M')
        end_time = datetime.strptime(data['registration_end_time'], '%Y-%m-%dT%H:%M')
        now = datetime.now()

        # --- ▼▼▼ 新增：處理自選時間的邏輯 ▼▼▼ ---
        allow_user_choice = 'allow_user_to_choose_time' in data
        user_choice_start_date = datetime.strptime(data['user_choice_start_date'], '%Y-%m-%d').date() if allow_user_choice and data.get('user_choice_start_date') else None
        user_choice_end_date = datetime.strptime(data['user_choice_end_date'], '%Y-%m-%d').date() if allow_user_choice and data.get('user_choice_end_date') else None
        user_choice_start_time_of_day = datetime.strptime(data['user_choice_start_time_of_day'], '%H:%M').time() if allow_user_choice and data.get('user_choice_start_time_of_day') else None
        user_choice_end_time_of_day = datetime.strptime(data['user_choice_end_time_of_day'], '%H:%M').time() if allow_user_choice and data.get('user_choice_end_time_of_day') else None

        if now < start_time:
            calculated_status = '尚未開放'
        elif start_time <= now < end_time:
            calculated_status = '報名中'
        else:
            calculated_status = '報名截止'
            
        new_course = Course(
            name=data['name'],
            description=data['description'],
            speaker_info=data['speaker_info'],
            duration_hours=float(data.get('duration_hours', 1)),
            status=calculated_status,
            registration_start_time=start_time,
            registration_end_time=end_time,
            # --- ▼▼▼ 修改：根據新邏輯設定欄位值 ▼▼▼ ---
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
        now = datetime.now()

        # --- ▼▼▼ 新增：處理自選時間的邏輯 ▼▼▼ ---
        allow_user_choice = 'allow_user_to_choose_time' in data
        user_choice_start_date = datetime.strptime(data['user_choice_start_date'], '%Y-%m-%d').date() if allow_user_choice and data.get('user_choice_start_date') else None
        user_choice_end_date = datetime.strptime(data['user_choice_end_date'], '%Y-%m-%d').date() if allow_user_choice and data.get('user_choice_end_date') else None
        user_choice_start_time_of_day = datetime.strptime(data['user_choice_start_time_of_day'], '%H:%M').time() if allow_user_choice and data.get('user_choice_start_time_of_day') else None
        user_choice_end_time_of_day = datetime.strptime(data['user_choice_end_time_of_day'], '%H:%M').time() if allow_user_choice and data.get('user_choice_end_time_of_day') else None

        if now < start_time:
            calculated_status = '尚未開放'
        elif start_time <= now < end_time:
            calculated_status = '報名中'
        else:
            calculated_status = '報名截止'

        # 更新課程基本資料
        course.name = data['name']
        course.description = data['description']
        course.speaker_info = data['speaker_info']
        course.duration_hours = float(data.get('duration_hours', 1))
        course.status = calculated_status
        course.registration_start_time = start_time
        course.registration_end_time = end_time
        # --- ▼▼▼ 修改：根據新邏輯設定欄位值 ▼▼▼ ---
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

            # 新增驗證：結束時間必須晚於開始時間
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


def _handle_file_uploads(files, course_object):
    """輔助函式：處理檔案上傳"""
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
                # ▼▼▼ 這裡是主要的修改處：直接儲存原始檔名 ▼▼▼
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
if __name__ == '__main__':
    with app.app_context():
        db.create_all() # 建立所有資料表
        # 檢查是否已有 admin 使用者，若無則建立一個
        if not User.query.filter_by(username='admin').first():
            print("建立預設管理者帳號...")
            admin_user = User(username='admin', is_admin=True)
            admin_user.set_password('Futsu_Admin') # 預設密碼
            db.session.add(admin_user)
            db.session.commit()
            print("管理者帳號: admin, 密碼: Futsu_Admin")

        # 在啟動前手動執行一次狀態檢查
        print("[Startup] 正在執行首次課程狀態檢查...")
        check_course_status()
        print("[Startup] 首次檢查完成。")

    app.run(debug=True) # debug=True 會在程式碼變動時自動重啟