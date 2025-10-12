/**
 * 前端主應用程式腳本 (main.js)
 * 整合 Firebase Client SDK 以處理認證與 API 請求
 */

// --- START: ⚠️ 重要設定區 ⚠️ ---
// 1. 填入您的 Firebase 專案設定
// 您可以從 Firebase Console -> 專案設定 -> 一般 -> 您的應用程式 -> SDK 設定和設定 中找到
const firebaseConfig = {
    apiKey: "AIzaSyCSFoReny4VmiaCxiRqR0i-nv0pYyM9jxk",
    authDomain: "bank-robot-45a15.firebaseapp.com",
    projectId: "bank-robot-45a15",
    storageBucket: "bank-robot-45a15.firebasestorage.app",
    messagingSenderId: "21273596349",
    appId: "1:21273596349:web:a31ed62b5ff09c350542d4"
};

// 2. 填入您的 Cloud Functions API 基礎網址
// 格式: https://<region>-<project-id>.cloudfunctions.net/api
// 例如: https://asia-east1-bank-robot-45a15.cloudfunctions.net/api
const API_BASE_URL = "https://asia-east1-bank-robot-45a15.cloudfunctions.net/api";

// --- END: ⚠️ 重要設定區 ⚠️ ---


// --- Firebase App 初始化 ---
// 【修正】我們使用 v8 (compat) 版本的 SDK，初始化方式如下，請勿加入其他 initializeApp 或 getAnalytics 的程式碼
firebase.initializeApp(firebaseConfig);
const auth = firebase.auth();
const db = firebase.firestore();


// --- 全域變數 ---
let currentUser = null;


// --- [核心] 身份驗證狀態監聽 ---
// 這個函式會在使用者登入、登出或頁面剛載入時自動執行
// --- [核心] 身份驗證狀態監聽 ---
// 這個函式會在使用者登入、登出或頁面剛載入時自動執行
auth.onAuthStateChanged(user => {
    const navUserSection = document.getElementById('nav-user-section');
    if (user) {
        // 使用者已登入
        currentUser = user;
        console.log("使用者已登入:", user.uid);

        // 【修正重點】從 user 物件中取得名稱，如果沒有顯示名稱，則使用 Email
        const userName = user.displayName || user.email;

        if (navUserSection) {
            // 【修正重點】使用下拉式選單來顯示使用者名稱和登出按鈕
            navUserSection.innerHTML = `
                <li class="nav-item">
                    <a class="nav-link" href="index.html">所有課程</a>
                </li>
                <li class="nav-item">
                    <a class="nav-link" href="my_courses.html">我的課程</a>
                </li>
                <li class="nav-item dropdown">
                    <a class="nav-link dropdown-toggle" href="#" id="navbarUserDropdown" role="button" data-bs-toggle="dropdown" aria-expanded="false">
                        你好, ${userName}
                    </a>
                    <ul class="dropdown-menu dropdown-menu-end" aria-labelledby="navbarUserDropdown">
                        <li><a class="dropdown-item" href="#" id="logout-btn">登出</a></li>
                    </ul>
                </li>
            `;
            // 為新的登出按鈕加上事件監聽
            document.getElementById('logout-btn').addEventListener('click', (e) => {
                e.preventDefault();
                auth.signOut().then(() => {
                    console.log('使用者已登出');
                    window.location.href = '/index.html'; // 登出後跳回首頁
                });
            });
        }
        
    } else {
        // 使用者未登入
        currentUser = null;
        console.log("使用者未登入");
        if (navUserSection) {
            // 維持原本的未登入狀態顯示
            navUserSection.innerHTML = `
                <li class="nav-item">
                    <a class="nav-link" href="index.html">所有課程</a>
                </li>
                <li class="nav-item">
                    <a class="nav-link" href="login.html">登入 / 註冊</a>
                </li>
            `;
        }
    }
    
    // 重新渲染頁面內容，以更新登入/未登入狀態下的按鈕
    // 這是一個很好的觸發點，確保在拿到認證狀態後才去抓取頁面資料
    if (document.getElementById('course-list')) {
        fetchAndRenderCourses();
    }
    if (document.getElementById('my-course-list')) {
        fetchMyCourses();
    }
    if (document.getElementById('course-detail-container')) {
        fetchCourseDetail();
    }
    if (document.getElementById('admin-course-list')) {
        fetchAdminCourses();
    }
});


// --- [核心] 自動附加 Token 的 fetch 函式 ---
async function fetchWithAuth(url, options = {}) {
    const headers = options.headers || {};
    if (currentUser) {
        try {
            // 每次請求都強制刷新 token，確保是最新且有效的
            const token = await currentUser.getIdToken(true);
            headers['Authorization'] = `Bearer ${token}`;
        } catch (error) {
            console.error("取得 ID Token 失敗:", error);
            // 可以在此處處理 token 過期或失效的情況，例如強制登出
            auth.signOut();
        }
    }
    return fetch(`${API_BASE_URL}${url}`, { ...options, headers });
}


// --- 頁面邏輯 (從您原本的程式碼修改而來) ---
document.addEventListener('DOMContentLoaded', function() {
    
    // 因為 onAuthStateChanged 會在 DOM 載入後執行，
    // 所以大部分的 fetch 邏輯都移到 onAuthStateChanged 回呼函式中觸發，
    // 以確保在發送 API 請求前，我們已經知道使用者的登入狀態。
    // 這裡只保留不需要立即 fetch 資料的 UI 互動邏輯。
    
    // ---- START: 「後台課程表單」模式切換邏輯 ----
    const adminCourseForm = document.querySelector('form[action*="/admin/courses"]');
    if (adminCourseForm) {
        const allowUserChoiceCheckbox = document.getElementById('allow_user_to_choose_time');
        const userChoiceSection = document.getElementById('user-choice-range-section');
        const fixedSlotsSection = document.getElementById('time-slots-section');

        function toggleCourseTimeMode() {
            if (!allowUserChoiceCheckbox) return; // 防錯
            const isUserChoiceMode = allowUserChoiceCheckbox.checked;

            if (userChoiceSection) userChoiceSection.style.display = isUserChoiceMode ? 'block' : 'none';
            if (fixedSlotsSection) fixedSlotsSection.style.display = isUserChoiceMode ? 'none' : 'block';

            if (userChoiceSection) {
                userChoiceSection.querySelectorAll('input').forEach(input => {
                    input.disabled = !isUserChoiceMode;
                    input.required = isUserChoiceMode;
                });
            }
            if (fixedSlotsSection) {
                fixedSlotsSection.querySelectorAll('input, button').forEach(control => {
                    control.disabled = isUserChoiceMode;
                });
                 // 確保固定梯次中的 input 必填狀態正確
                const slotInputs = fixedSlotsSection.querySelectorAll('input');
                slotInputs.forEach(input => input.required = !isUserChoiceMode);
            }
        }
        
        if (allowUserChoiceCheckbox) {
            toggleCourseTimeMode();
            allowUserChoiceCheckbox.addEventListener('change', toggleCourseTimeMode);
        }
    }
    // ---- END ----

    // ---- START: 梯次管理程式碼 ----
    // (這段程式碼與您原本的幾乎相同，無需修改)
    const timeSlotsSection = document.getElementById('time-slots-section');
    const addSlotBtn = document.getElementById('add-slot-btn');
    const slotsContainer = document.getElementById('time-slots-container');
    const slotTemplate = document.getElementById('time-slot-template');

    if (timeSlotsSection && addSlotBtn && slotsContainer && slotTemplate) {
        addSlotBtn.addEventListener('click', () => {
            const newRowContainer = document.createElement('div');
            newRowContainer.innerHTML = slotTemplate.innerHTML;
            const newRowElement = newRowContainer.firstElementChild;
            newRowElement.querySelectorAll('input, button').forEach(control => {
                control.disabled = false;
            });
            slotsContainer.appendChild(newRowElement);
        });

        slotsContainer.addEventListener('click', (e) => {
            const removeButton = e.target.closest('.remove-slot-btn');
            if (removeButton) {
                e.target.closest('.time-slot-row').remove();
            }
        });
    }
    // ---- END: 梯次管理程式碼 ----

    // ---- 上傳檔案預覽程式 ----
    // (這段程式碼與您原本的幾乎相同，無需修改)
    const fileInput = document.getElementById('file');
    const fileListContainer = document.getElementById('file-list-container');
    
    let selectedFiles = new DataTransfer();

    if (fileInput && fileListContainer) {
        fileInput.addEventListener('change', () => {
            // ... (您的檔案預覽邏輯)
        });
    }

    // --- 【修正】登入/註冊表單邏輯 ---
    // 改為使用 Firebase Auth SDK
    const loginForm = document.getElementById('login-form');
    if (loginForm) {
        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const email = loginForm.email.value;
            const password = loginForm.password.value;
            try {
                await auth.signInWithEmailAndPassword(email, password);
                // onAuthStateChanged 會自動處理後續邏輯
                window.location.href = '/index.html';
            } catch (error) {
                alert(`登入失敗: ${error.message}`);
            }
        });
    }

    const registerForm = document.getElementById('register-form');
    if (registerForm) {
        registerForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const email = registerForm.email.value;
            const password = registerForm.password.value;
            // 注意：Firebase Auth 的 username 是 displayName，且註冊時無法直接設定
            // 我們需要在後端建立一個 Cloud Function 來同步 username
            try {
                await auth.createUserWithEmailAndPassword(email, password);
                alert('註冊成功！請登入。');
                window.location.href = '/login.html';
            } catch (error)
            {
                alert(`註冊失敗: ${error.message}`);
            }
        });
    }

}); // END of DOMContentLoaded


// --- 全域可呼叫的函式 (從您原本的程式碼修改而來) ---

// [首頁] 抓取並渲染課程列表
async function fetchAndRenderCourses() {
    try {
        const response = await fetchWithAuth(`/courses`); 
        if (!response.ok) throw new Error(`無法載入課程: ${response.statusText}`);
        const courses = await response.json();
        const courseList = document.getElementById('course-list');
        courseList.innerHTML = ''; 
        if (courses.length === 0) {
            courseList.innerHTML = '<p class="text-center text-muted">目前沒有符合條件的課程。</p>';
            return;
        }

        courses.forEach(course => {
             let statusBadge;
            switch (course.status) {
                case '報名中': statusBadge = '<span class="badge bg-success">報名中</span>'; break;
                case '尚未開放': statusBadge = `<span class="badge bg-warning text-dark">尚未開放</span>`; break;
                case '報名截止': statusBadge = '<span class="badge bg-secondary">報名截止</span>'; break;
                default: statusBadge = `<span class="badge bg-light text-dark">${course.status}</span>`; break;
            }

            let actionButton;
            if (course.status === '報名中') {
                if (currentUser) {
                    // is_registered 欄位需要後端 API 根據當前使用者 ID 來判斷並提供
                    if (course.is_registered) {
                        actionButton = '<button class="btn btn-outline-secondary w-100" disabled>已報名</button>';
                    } else {
                        actionButton = `<a href="course_detail.html?id=${course.id}" class="btn btn-primary w-100">立即報名</a>`;
                    }
                } else {
                    actionButton = `<button class="btn btn-primary w-100" onclick="promptLogin()">立即報名</button>`;
                }
            } else {
                 actionButton = `<a href="course_detail.html?id=${course.id}" class="btn btn-secondary w-100" disabled>${course.status}</a>`;
            }

            const card = `
            <div class="col-md-4 mb-4">
                <div class="card h-100">
                    <div class="card-body d-flex flex-column">
                        <h5 class="card-title">
                            <a href="course_detail.html?id=${course.id}" class="text-decoration-none text-dark stretched-link">${course.name}</a>
                            ${statusBadge}
                        </h5>
                        <h6 class="card-subtitle mb-2 text-muted">講者: ${course.speaker_info || ''}</h6>
                        <p class="card-text flex-grow-1">${(course.description || '').substring(0, 80)}...</p>
                        <p class="card-text"><small class="text-muted">開放報名: ${course.registration_start_time}</small></p>
                        <p class="card-text"><small class="text-muted">報名截止: ${course.registration_end_time}</small></p> 
                    </div>
                    <div class="card-footer bg-transparent border-top-0">
                        ${actionButton}
                    </div>
                </div>
            </div>`;
            courseList.innerHTML += card;
        });

    } catch (error) {
        console.error("抓取課程失敗:", error);
        document.getElementById('course-list').innerHTML = `<p class="text-danger text-center">課程載入失敗，請稍後再試。</p>`;
    }
}


// [我的課程頁] 抓取並渲染我報名的課程
async function fetchMyCourses() {
    if (!currentUser) {
        document.getElementById('my-course-list').innerHTML = `<p class="text-center">請先<a href="login.html">登入</a>以查看您報名的課程。</p>`;
        return;
    }
    try {
        const response = await fetchWithAuth(`/my_courses`);
        if (!response.ok) throw new Error(`無法載入您的課程: ${response.statusText}`);
        const registrations = await response.json();
        const myCourseListPage = document.getElementById('my-course-list');
        myCourseListPage.innerHTML = '';

        if (registrations.length === 0) {
            myCourseListPage.innerHTML = '<p class="text-center text-muted">您尚未報名任何課程。</p>';
            return;
        }

        registrations.forEach(reg => {
            // ... (您原本的渲染邏輯)
        });

    } catch (error) {
        console.error("抓取我的課程失敗:", error);
        document.getElementById('my-course-list').innerHTML = `<p class="text-danger text-center">載入您的課程時發生錯誤。</p>`;
    }
}

// [課程詳情頁] 抓取單一課程的詳細資訊
async function fetchCourseDetail() {
    const params = new URLSearchParams(window.location.search);
    const courseId = params.get('id');
    if (!courseId) return;

    try {
        // 後端需要一個能獲取單一課程的 API 端點
        const response = await fetchWithAuth(`/courses/${courseId}`);
        if (!response.ok) throw new Error(`無法載入課程詳情: ${response.statusText}`);
        const data = await response.json();
        // ... (您原本的渲染邏輯)
        
    } catch(error) {
        console.error("抓取課程詳情失敗:", error);
        document.getElementById('course-detail-container').innerHTML = `<p class="text-danger text-center">無法載入課程詳情。</p>`;
    }
}

// [管理後台] 抓取所有課程
async function fetchAdminCourses() {
    const adminCourseListPage = document.getElementById('admin-course-list');
    if (!adminCourseListPage) return;
    try {
        const response = await fetchWithAuth('/courses');
        if (!response.ok) throw new Error(`無法載入課程: ${response.statusText}`);
        const courses = await response.json();
        adminCourseListPage.innerHTML = '';
        courses.forEach(course => {
            const row = `
            <tr>
                <td>${course.id}</td>
                <td>${course.name}</td>
                <td>${course.status}</td>
                <td>${course.registration_start_time}</td>
                <td>${course.registration_end_time}</td>
                <td>
                    <button class="btn btn-sm" onclick="viewRegistrants('${course.id}', '${course.name.replace(/'/g, "\\'")}')" title="查看報名"><i class="bi bi-eye-fill"></i></button>
                    <a href="admin_course_form.html?id=${course.id}" class="btn btn-sm" title="修改"><i class="bi bi-pencil-square text-warning"></i></a>
                    <button class="btn btn-sm" onclick="deleteCourse('${course.id}')" title="刪除"><i class="bi bi-trash-fill text-danger"></i></button>
                </td>
            </tr>`;
            adminCourseListPage.innerHTML += row;
        });
    } catch(error) {
        console.error("抓取管理課程列表失敗:", error);
        adminCourseListPage.innerHTML = `<tr><td colspan="7" class="text-danger text-center">載入課程列表失敗</td></tr>`;
    }
}

// 提示登入
function promptLogin() {
    if (confirm('請先登入才能報名。\n您要現在前往登入頁面嗎？')) {
        window.location.href = 'login.html';
    }
}

