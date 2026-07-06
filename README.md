# 報名網站 (Registration-website)

短述

這是一個以 Flask 建置的課程報名系統（中文介面），功能包含課程管理、固定梯次 / 使用者自選時段報名、報名紀錄匯出（Excel）、電子郵件重設密碼、管理者後台等。

專案重點

- 使用 Flask 框架構建 Web 應用
- ORM：Flask-SQLAlchemy
- 使用者登入：Flask-Login
- 郵件：Flask-Mail（支援寄送重設密碼）
- 匯出 Excel：openpyxl
- 背景排程：APScheduler（自動檢查並更新課程狀態）
- 支援固定梯次與「使用者自選時間」兩種報名模式

專案目錄（重要檔案）

- app.py — 主應用程式與所有 route、models、業務邏輯
- requirements.txt — Python 相依套件
- init_db.py — 初始化資料（如需）
- templates/ — Jinja2 模板
- static/ — 靜態資源（CSS/JS/圖片）
- uploads/ — 上傳檔案儲存位置
- Procfile —（若部署於 Heroku / 類似平台）

系統需求

- Python 3.10+（建議）
- pip

安裝與本機執行（開發環境）

1. 取得原始碼

   git clone https://github.com/Joy0130/Registration-website.git
   cd Registration-website

2. 建議建立虛擬環境並啟用

   python -m venv .venv
   # macOS / Linux
   source .venv/bin/activate
   # Windows (PowerShell)
   .\.venv\Scripts\Activate.ps1

3. 安裝相依套件

   pip install -r requirements.txt

4. 設定環境變數（範例）

在開發時可建立一個 `.env` 檔案（專案內已有使用 python-dotenv）或直接在系統環境變數中設定：

- SECRET_KEY — Flask 的 secret key
- MAIL_SERVER — SMTP 伺服器 (預設 smtp.gmail.com)
- MAIL_PORT — SMTP 連線埠 (預設 587)
- MAIL_USE_TLS — 是否使用 TLS (true/false)
- MAIL_USERNAME — 寄件郵箱帳號
- MAIL_PASSWORD — 寄件郵箱密碼或 app password
- MAIL_DEFAULT_SENDER — 郵件預設寄件人（可不設定，則會用 MAIL_USERNAME）
- PORT —（選用）要對外監聽的埠號（預設 5003）

範例 .env：

SECRET_KEY=your_secret_key_here
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=you@example.com
MAIL_PASSWORD=yourpassword
MAIL_DEFAULT_SENDER=you@example.com

5. 初始化資料庫（程式開頭會在 app.run 時自動建立資料表）

若想手動初始化或重建資料庫，可執行：

   python init_db.py

(或直接執行 `python app.py`，程式中會在啟動時呼叫 db.create_all()，並建立預設 admin 帳號)

6. 啟動開發伺服器

   python app.py

之後開啟瀏覽器： http://127.0.0.1:5003/

預設管理員帳號

依 app.py 的設定，啟動時若沒有 admin 帳號會建立一個預設管理員：

- 帳號：admin
- 密碼：admin123
- email: misfutsu@gmail.com

（請務必在公開環境變更預設密碼）

主要功能與 API 一覽

- 前台頁面
  - / — 首頁
  - /course/<id> — 課程詳情
  - /my_courses — 我報名的課程（需登入）
  - /login, /register, /logout, /forgot_password, /change_password

- 後台（需管理者權限）
  - /admin — 管理後台
  - /admin/course/new, /admin/course/edit/<id>
  - /admin/all_registrations — 顯示所有報名紀錄
  - /admin/export_registrations — 匯出篩選後報名紀錄為 Excel

- 主要 API
  - GET /api/courses — 取得課程 JSON 列表（支援搜尋與狀態篩選）
  - GET /api/my_courses — 取得目前使用者的報名（需登入）
  - POST /api/register — 報名（time_slot_id 或 course_id + user_selected_time）
  - POST /api/check_course_status — 手動觸發課程狀態檢查
  - POST /api/admin/courses — 新增課程（管理者）
  - POST /api/admin/courses/<id> — 更新課程（管理者）
  - DELETE /api/admin/courses/<id> — 刪除課程（管理者）
  - 其餘檔案上傳、刪除與報名取消等 API 請參考 app.py

注意事項與已知實作細節

- 專案以 SQLite（instance/database.db）作為預設資料庫，資料檔放在 instance/ 目錄。
- 報名時間檢查在後端會使用伺服器時間（程式碼以本地時間處理，註解標明為 GMT+8），若部署在不同時區請特別留意時間邏輯。
- 使用者自選時間模式會建立 capacity=1 的 TimeSlot 作為該次預約的紀錄，並且系統會檢查與午休時間(12:00~13:30)的衝突。
- 匯出 Excel 使用 openpyxl，並嘗試自動調整欄寬與中文字寬度的處理。
- 郵件功能依賴正確的 SMTP 設定；若寄送失敗，系統會回滾密碼變更。

部署建議

- 使用 gunicorn 或其他 WSGI server（requirements.txt 已包含 gunicorn）在 production 運行：

  gunicorn -w 4 "app:app" -b 0.0.0.0:$PORT

- 若使用 Heroku，可利用現成的 Procfile 啟動（Procfile 已在專案中）。
- 在 production 環境務必：
  - 使用安全的 SECRET_KEY
  - 設定真實且安全的郵件憑證
  - 把資料庫換成更可靠的 DB（Postgres 等）以支援多實例與穩定性

測試

專案中有 test_course_status.py，建議安裝 pytest 並撰寫更多單元測試來覆蓋課程狀態更新、報名邏輯與時間衝突檢查。

貢獻

歡迎提出 Pull Request、回報 Issue，或直接在 Issues 中討論功能需求與 Bug。提交 PR 時請提供可重現的步驟與相關測試。

授權

請在此處放上授權資訊（例如 MIT、Apache-2.0），若你沒有指定，我可以幫你加一個範例 LICENSE 檔案。

聯絡

若有問題可以在 GitHub Repo 提 issue，或聯絡專案擁有者。
