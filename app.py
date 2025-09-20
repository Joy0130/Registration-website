import os
import uuid
from datetime import datetime, timedelta 
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, send_from_directory
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
    __table_args__ = {'extend_existing': True}

    # --- 關聯 (Relationships) ---
    files = db.relationship('CourseFile', backref='course', lazy=True, cascade="all, delete-orphan")
    # 新增梯次關聯
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
    time_slot = db.relationship('TimeSlot', backref=db.backref('registrations', lazy=True, cascade="all, delete-orphan"))

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

scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(check_course_status, 'interval', minutes=1)
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
            
    return render_template(
        'course_detail.html', 
        course=course, 
        is_registered=is_registered, 
        available_slots=available_slots
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
        
        courses_data.append({
            'id': c.id,
            'name': c.name,
            'description': c.description,
            'speaker_info': c.speaker_info,
            'status': c.status,
            'class_time_summary': class_time_summary, # <--- 確保這個鍵名存在
            'registration_start_time': c.registration_start_time.strftime('%Y-%m-%d %H:%M'),
            'registration_end_time': c.registration_end_time.strftime('%Y-%m-%d %H:%M'),
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
    # 1. 找出這位使用者所有的報名紀錄，並排序
    registrations = Registration.query.filter_by(user_id=current_user.id).order_by(Registration.registration_time.desc()).all()
    
    # 2. 為每一筆報名紀錄組合回傳的資料
    my_registrations_data = []
    for reg in registrations:
        course = reg.time_slot.course
        slot = reg.time_slot
        
        # 格式化該次報名的梯次時間
        start_str = slot.slot_start_time.strftime('%Y-%m-%d %H:%M')
        if slot.slot_start_time.date() == slot.slot_end_time.date():
            end_str = slot.slot_end_time.strftime('%H:%M')
        else:
            end_str = slot.slot_end_time.strftime('%Y-%m-%d %H:%M')
        
        class_time = f"{start_str} ~ {end_str}"

        my_registrations_data.append({
            'course_id': course.id,
            'course_name': course.name,
            'class_time': class_time, # 包含使用者報名的具體上課時間
            'course_description': course.description,
            'speaker_info': course.speaker_info,
            'files': [
                {'id': f.id, 'url': url_for('download_file', file_id=f.id), 'name': f.display_filename} 
                for f in course.files
            ]
        })
    return jsonify(my_registrations_data)
# ---- END ----

# [POST] 報名課程

@app.route('/api/register', methods=['POST'])
@login_required
def register_for_slot():
    data = request.get_json()
    slot_id = data.get('time_slot_id')

    if not slot_id:
        return jsonify({'success': False, 'message': '未選擇上課梯次'}), 400

    slot = TimeSlot.query.get(slot_id)
    if not slot:
        return jsonify({'success': False, 'message': '找不到指定的梯次'}), 404

    # 檢查是否還有名額 (重要！)
    if slot.booked_count >= slot.capacity:
        return jsonify({'success': False, 'message': '此梯次名額已滿'}), 400

    # 檢查是否已報名過此課程的任何梯次
    existing_reg = Registration.query.join(TimeSlot).filter(
        Registration.user_id == current_user.id,
        TimeSlot.course_id == slot.course_id
    ).first()
    if existing_reg:
        return jsonify({'success': False, 'message': '您已報名過此課程的其他梯次'}), 400

    # 建立報名紀錄並更新已報名人數
    new_reg = Registration(user_id=current_user.id, time_slot_id=slot.id)
    slot.booked_count += 1
    db.session.add(new_reg)
    db.session.commit()

    return jsonify({'success': True, 'message': '報名成功！'})

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
            status=calculated_status,
            registration_start_time=start_time,
            registration_end_time=end_time,
            has_time_slots=('has_time_slots' in data)
        )

        # 呼叫輔助函式來處理梯次和檔案
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
        course.status = calculated_status
        course.registration_start_time = start_time
        course.registration_end_time = end_time
        course.has_time_slots = 'has_time_slots' in data

        # 清除舊梯次並呼叫輔助函式重建
        TimeSlot.query.filter_by(course_id=course.id).delete()
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
    if 'has_time_slots' in data:
        slot_start_times = data.getlist('slot_start_times')
        slot_end_times = data.getlist('slot_end_times')
        slot_capacities = data.getlist('slot_capacities')

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
    # 同時刪除相關的報名紀錄
    Registration.query.filter_by(course_id=course_id).delete()
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
    app.run(debug=True) # debug=True 會在程式碼變動時自動重啟
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
    app.run(debug=True) # debug=True 會在程式碼變動時自動重啟