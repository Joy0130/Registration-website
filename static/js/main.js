// 主要的 JavaScript 程式碼
// 會被所有頁面載入

// 確保 DOM 完全載入後再執行
// eslint-disable-next-line max-lines-per-function
document.addEventListener('DOMContentLoaded', function() {
    
    // ---- START: 新增的「後台課程表單」模式切換邏輯 ----
    const adminCourseForm = document.querySelector('form[action*="/api/admin/courses"]');
    if (adminCourseForm) {
        const allowUserChoiceCheckbox = document.getElementById('allow_user_to_choose_time');
        const userChoiceSection = document.getElementById('user-choice-range-section');
        const fixedSlotsSection = document.getElementById('time-slots-section');

        function toggleCourseTimeMode() {
            const isUserChoiceMode = allowUserChoiceCheckbox.checked;

            // 切換區塊的顯示/隱藏
            userChoiceSection.style.display = isUserChoiceMode ? 'block' : 'none';
            fixedSlotsSection.style.display = isUserChoiceMode ? 'none' : 'block';

            // 啟用/禁用對應區塊內的輸入欄位
            userChoiceSection.querySelectorAll('input').forEach(input => {
                input.disabled = !isUserChoiceMode;
            });
            fixedSlotsSection.querySelectorAll('input, button').forEach(control => {
                control.disabled = isUserChoiceMode;
            });
        }

        // 1. 頁面載入時，根據 checkbox 的初始狀態執行一次
        toggleCourseTimeMode();

        // 2. 每次 checkbox 狀態改變時，都執行
        allowUserChoiceCheckbox.addEventListener('change', toggleCourseTimeMode);
    }
    // ---- END ----

    // ---- START: 新增的梯次管理程式碼 ----
    const timeSlotsSection = document.getElementById('time-slots-section');
    const addSlotBtn = document.getElementById('add-slot-btn');
    const slotsContainer = document.getElementById('time-slots-container');
    const slotTemplate = document.getElementById('time-slot-template');
    const alerts = document.querySelectorAll('.alert.alert-dismissible');
        alerts.forEach(function(alert) {
            setTimeout(function() {
                // 使用 Bootstrap 5 的 Alert API 來優雅地關閉它
                // 這會觸發 Bootstrap 的淡出 (fade out) 動畫效果
                const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
                bsAlert.close();
            }, 3000); // 3seconds
        });

    // 檢查頁面上是否存在這些元素
    if (timeSlotsSection && addSlotBtn && slotsContainer && slotTemplate) {
        // 點擊「新增梯次」按鈕的邏輯
        addSlotBtn.addEventListener('click', () => {
            // 複製模板的內容
            const newRowContainer = document.createElement('div');
            newRowContainer.innerHTML = slotTemplate.innerHTML;
            const newRowElement = newRowContainer.firstElementChild;

            // 找到新建立的這一列中的所有 input 和 button 欄位
            const controls = newRowElement.querySelectorAll('input, button');

            // 移除它們的 disabled 屬性，將它們“喚醒”
            controls.forEach(control => {
                control.disabled = false;
            });

            // 將處理好的新列加到容器中
            slotsContainer.appendChild(newRowElement);
        });

        // 點擊「移除」按鈕的邏輯 (使用事件委派)
        slotsContainer.addEventListener('click', (e) => {
            // 由於使用者可能會點擊到 <button> 或裡面的 <i> 圖示
            // 我們使用 .closest() 來找到最接近的 .remove-slot-btn 按鈕
            const removeButton = e.target.closest('.remove-slot-btn');
            
            if (removeButton) {
                // 從按鈕往上找到它所在的整列 (.time-slot-row) 並移除
                e.target.closest('.time-slot-row').remove();
            }
        });
    }

    // --- 管理者自選時間功能的 UI 控制 ---
    const allowUserChoiceCheckbox = document.getElementById('allow_user_to_choose_time');
    const userChoiceRangeSection = document.getElementById('user-choice-range-section');
    // const timeSlotsSection = document.getElementById('time-slots-section'); // 已在前面宣告

    if (allowUserChoiceCheckbox && userChoiceRangeSection && timeSlotsSection) {
        function toggleCourseTimeOptions() {
            const isUserChoiceAllowed = allowUserChoiceCheckbox.checked;

            // 控制「使用者自選範圍」區塊的顯示/隱藏與啟用/禁用
            userChoiceRangeSection.style.display = isUserChoiceAllowed ? 'block' : 'none';
            const rangeInputs = userChoiceRangeSection.querySelectorAll('input');
            rangeInputs.forEach(input => {
                input.disabled = !isUserChoiceAllowed;
                input.required = isUserChoiceAllowed; // 如果啟用，就設為必填
            });

            // 控制「固定梯次」區塊的顯示/隱藏與啟用/禁用
            timeSlotsSection.style.display = isUserChoiceAllowed ? 'none' : 'block';
            const slotInputs = timeSlotsSection.querySelectorAll('input');
            slotInputs.forEach(input => {
                // 注意：這裡的 disabled 狀態與上面相反
                input.disabled = isUserChoiceAllowed;
                // 如果啟用固定梯次，則設為必填
                input.required = !isUserChoiceAllowed;
            });
        }

        // 頁面載入時先執行一次，根據資料庫的值設定初始狀態
        toggleCourseTimeOptions();

        // 每次點擊 checkbox 時都重新判斷
        allowUserChoiceCheckbox.addEventListener('change', toggleCourseTimeOptions);
    }

    // ---- 上傳檔案程式 ----
    const fileInput = document.getElementById('file');
    const fileListContainer = document.getElementById('file-list-container');
    
    // DataTransfer 物件:管理檔案列表
    let selectedFiles = new DataTransfer();

    // 如果頁面上有檔案輸入和列表容器，才啟用這段邏輯
    if (fileInput && fileListContainer) {
        fileInput.addEventListener('change', () => {
            // 將新選擇的檔案添加到現有列表中
            for (let i = 0; i < fileInput.files.length; i++) {
                // 檢查是否重複
                let isDuplicate = false;
                // `selectedFiles.items` 是 DataTransferItemList
                for(let j = 0; j < selectedFiles.items.length; j++) {
                    if (selectedFiles.items[j].getAsFile().name === fileInput.files[i].name) {
                        isDuplicate = true;
                        break;
                    }
                }
                // 如果不是重複的檔案，才加入
                if (!isDuplicate) {
                    selectedFiles.items.add(fileInput.files[i]);
                }
            }
            // 將更新後的檔案列表放回 input 中，並更新畫面
            fileInput.files = selectedFiles.files;
            renderFileList();
        });
        // 渲染目前選擇的檔案列表
        function renderFileList() {
            fileListContainer.innerHTML = ''; // 清空列表
            if (selectedFiles.items.length > 0) { // 有檔案
                 const list = document.createElement('ul');// 建立 ul 元素
                 list.className = 'list-group';// Bootstrap 樣式
                 for (let i = 0; i < selectedFiles.files.length; i++) { // 遍歷檔案
                     const file = selectedFiles.files[i]; // 取得檔案物件
                     const listItem = document.createElement('li'); // 建立 li 元素
                     listItem.className = 'list-group-item d-flex justify-content-between align-items-center'; // Bootstrap 樣式
                     listItem.textContent = file.name; // 顯示檔案名稱
                     // 建立刪除按鈕
                     const deleteBtn = document.createElement('button'); 
                     deleteBtn.type = 'button'; //  按鈕類型
                     deleteBtn.className = 'btn btn-sm btn-outline-danger'; // 統一風格
                     deleteBtn.title = '移除此檔案'; // 加上滑鼠提示文字
                     deleteBtn.innerHTML = '<i class="bi bi-trash-fill"></i>'; 
                     deleteBtn.dataset.index = i; // 儲存索引以便識別
                     // 刪除按鈕事件
                     deleteBtn.addEventListener('click', (e) => { // 點擊事件
                         const indexToRemove = parseInt(e.target.dataset.index, 10); // 取得要刪除的索引
                         const newFiles = new DataTransfer(); // 新的 DataTransfer 物件
                         for(let j = 0; j < selectedFiles.files.length; j++) { // 遍歷現有檔案
                             if(j !== indexToRemove) { // 排除要刪除的檔案
                                 newFiles.items.add(selectedFiles.files[j]); // 加入新的列表
                             }
                         }
                         // 更新選取的檔案列表
                         selectedFiles = newFiles;
                         fileInput.files = selectedFiles.files; // 同步更新 input 的檔案
                         renderFileList(); // 重新渲染列表
                     });
                     // 將按鈕加入列表項目
                     listItem.appendChild(deleteBtn);
                     list.appendChild(listItem); //列出列表項目
                 }
                 fileListContainer.appendChild(list); // 將列表加入list
            }
        }
    }

    // --- 首頁邏輯 (index.html) ---
    const courseListPage = document.getElementById('course-list');
    //  如果頁面上有課程列表，才啟用這段邏輯
    if (courseListPage) {
        let currentStatus = 'all'; // 預設顯示所有課程
        let currentSearch = ''; // 預設搜尋關鍵字為空
        //  取得搜尋輸入框和篩選按鈕
        const searchInput = document.getElementById('searchInput'); // 搜尋框
        const filterBtns = document.querySelectorAll('.filter-btn'); //篩選按鈕
        // 取得並渲染課程列表
        async function fetchAndRenderCourses() {
            const response = await fetch(`/api/courses?status=${currentStatus}&search=${currentSearch}`);
            const courses = await response.json();
            const courseList = document.getElementById('course-list');
            courseList.innerHTML = ''; 

            if (courses.length === 0) {
                courseList.innerHTML = '<p class="text-center text-muted">目前沒有符合條件的課程。</p>';
                return;
            }
            //  渲染每個課程卡片   
            courses.forEach(course => {
                let statusBadge; // 狀態標籤
                // 根據課程狀態決定標籤樣式
                switch (course.status) { 
                    case '報名中': statusBadge = '<span class="badge bg-success">報名中</span>'; break;
                    case '尚未開放': statusBadge = `<span class="badge bg-warning text-dark">尚未開放</span>`; break;
                    case '報名截止': statusBadge = '<span class="badge bg-secondary">報名截止</span>'; break;
                }
                // 如果有教材檔案，顯示下載連結
                const fileLink = course.file_url ? `<a href="${course.file_url}" class="card-link" target="_blank">下載教材</a>` : '';

                // 根據登入狀態和課程狀態，決定按鈕的行為
                let actionButton;
                if (course.status === '報名中') {
                    if (course.is_full) {
                        actionButton = '<button class="btn btn-secondary w-100" disabled>已額滿</button>';
                    } else if (IS_USER_AUTHENTICATED) {
                        if (course.is_registered) {
                            actionButton = '<button class="btn btn-outline-secondary w-100" disabled>已報名</button>';
                        } else {
                            actionButton = `<button class="btn btn-primary w-100" onclick="registerForCourse(${course.id})">立即報名</button>`;
                        }
                    } else {
                        // 如果未登入，按鈕會呼叫 promptLogin() 函式
                        actionButton = `<button class="btn btn-primary w-100" onclick="promptLogin()">立即報名</button>`;
                    }
                } else {
                    // 其他狀態（尚未開放、報名截止）的按鈕保持禁用
                    actionButton = `<button class="btn btn-secondary w-100" disabled>${course.status}</button>`;
                }

                let classTimeDisplayHTML = '';
                if (course.allow_user_to_choose_time) {
                    // 如果是自選時間模式
                    classTimeDisplayHTML = `<h6 class="card-subtitle mb-2 text-primary fw-bold"><i class="bi bi-calendar-check"></i> 上課時間: 自行選擇</h6>`;
                } else {
                    // 如果是固定梯次模式
                    classTimeDisplayHTML = `<h6 class="card-subtitle mb-2 text-muted">上課時間: ${course.class_time_summary}</h6>`;
                }

                // 建立課程卡片
                const card = `
                <div class="col-md-4 mb-4">
                    <div class="card h-100">
                        <div class="card-body d-flex flex-column">
                            <h5 class="card-title">
                                <a href="/course/${course.id}" class="text-decoration-none text-dark stretched-link">${course.name}</a>
                                ${statusBadge}
                            </h5>
                            <h6 class="card-subtitle mb-3 text-primary fw-bold">上課時間: ${course.class_time_summary}</h6>
                            
                            <h6 class="card-subtitle mb-2 text-muted">講者: ${course.speaker_info}</h6>
                            <p class="card-text flex-grow-1">${course.description.substring(0, 80)}...</p>
                            <p class="card-text"><small class="text-muted">開放報名: ${course.registration_start_time}</small></p>
                            <p class="card-text"><small class="text-muted">報名截止: ${course.registration_end_time}</small></p> 
                            
                        </div>
                        <div class="card-footer bg-transparent border-top-0">
                            ${actionButton}
                        </div>
                    </div>
                </div>`;
                courseList.innerHTML += card; // 加入列表
            });
        }

        // 篩選按鈕事件
        filterBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                // 1. 重置所有按鈕為預設的 outline-secondary 樣式
                filterBtns.forEach(b => {
                    b.className = 'btn btn-outline-secondary filter-btn';
                });

                // 2. 根據被點擊按鈕的狀態，設定其對應的實心顏色
                const clickedStatus = btn.dataset.status;
                btn.className = 'btn filter-btn'; // 先清除舊樣式
                switch (clickedStatus) {
                    case 'all': btn.classList.add('btn-primary'); break; 
                    case '報名中': btn.classList.add('btn-success'); break;
                    case '尚未開放': btn.classList.add('btn-warning'); break;
                    case '報名截止': btn.classList.add('btn-secondary'); break;
                }

                // 3. 更新狀態並重新取得課程
                currentStatus = btn.dataset.status;
                fetchAndRenderCourses();
            });
        });
        // 搜尋輸入事件
        searchInput.addEventListener('input', () => {
            currentSearch = searchInput.value;
            fetchAndRenderCourses();
        });

        fetchAndRenderCourses(); // 頁面初始載入
    }

// --- 我報名的課程頁邏輯 (my_courses.html) ---
const myCourseListPage = document.getElementById('my-course-list');
if (myCourseListPage) {
    let currentMyCourseStatus = 'all'; // 預設顯示所有

    async function fetchMyCourses() {
        const response = await fetch(`/api/my_courses?status=${currentMyCourseStatus}`);
        const registrations = await response.json(); // API 回傳的是「報名紀錄」列表
        myCourseListPage.innerHTML = '';
        if (registrations.length === 0) {
            myCourseListPage.innerHTML = '<p class="text-center text-muted">沒有符合條件的課程。</p>';
            return;
        }

        registrations.forEach(reg => { // 遍歷每一筆報名紀錄
            let fileLinksHTML = '';
            if (reg.files && reg.files.length > 0) {
                fileLinksHTML += '<h6 class="mt-3">課程教材:</h6><div class="list-group list-group-flush">';
                reg.files.forEach(file => {
                    fileLinksHTML += `<a href="${file.url}" class="list-group-item list-group-item-action" target="_blank">${file.name}</a>`;
                });
                fileLinksHTML += '</div>';
            }

            // --- 新增：狀態標籤 ---
            let statusBadgeHTML = '';
            switch (reg.status) {
                case '課程即將開始': statusBadgeHTML = '<span class="badge text-white" style="background-color: #ae57a4;">即將開始</span>'; break;
                case '課程進行中': statusBadgeHTML = '<span class="badge bg-success">進行中</span>'; break;
                case '課程已結束': statusBadgeHTML = '<span class="badge bg-secondary">已結束</span>'; break;
            }
            
            // --- 新增：取消報名按鈕的邏輯 ---
            let cancelButtonHTML = '';
            const slotStartTime = new Date(reg.slot_start_time);
            const cancellationDeadline = new Date(slotStartTime.getTime() - (1 * 24 * 60 * 60 * 1000)); // 課程開始前 1 天
            const now = new Date();

            if (now > cancellationDeadline) {
                // 已超過取消期限
                cancelButtonHTML = `
                    <button class="btn btn-outline-secondary btn-sm mt-3" disabled title="已超過取消期限，請聯繫管理員。">
                        取消報名
                    </button>`;
            } else {
                // 仍在期限內
                cancelButtonHTML = `
                    <button class="btn btn-outline-danger btn-sm mt-3" onclick="cancelMyRegistration(${reg.registration_id}, '${reg.course_name}')">取消報名</button>`;
            }

            const card = `
            <div class="col-md-6 mb-4">
                <div class="card h-100">
                    <div class="card-body">
                        <h5 class="card-title">
                            ${reg.course_name}
                            ${statusBadgeHTML}
                        </h5>
                        <h6 class="card-subtitle mb-2 text-muted">講者: ${reg.speaker_info}</h6>
                        <h6 class="card-subtitle mb-3 text-primary fw-bold">您的上課時間: ${reg.class_time}</h6>
                        <p class="card-text">${reg.course_description}</p>
                        ${fileLinksHTML}
                        ${cancelButtonHTML}
                    </div>
                </div>
            </div>`;
            myCourseListPage.innerHTML += card;
        });
    }

    // --- 新增：篩選按鈕的事件監聽 ---
    const filterBtns = document.querySelectorAll('.my-course-filter-btn');
    filterBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            // 1. 將所有按鈕重設為預設的 outline 樣式，並清除可能存在的行內樣式
            filterBtns.forEach(b => {
                b.className = 'btn btn-outline-secondary my-course-filter-btn';
                b.removeAttribute('style'); // 清除行內樣式，解決顏色殘留問題
            });

            // 2. 根據被點擊按鈕的狀態，設定其對應的實心顏色
            const clickedStatus = btn.dataset.status;
            btn.className = 'btn my-course-filter-btn'; // 先清除舊樣式
            switch (clickedStatus) {
                case 'all': btn.classList.add('btn-primary'); break;
                case '課程即將開始': btn.classList.add('btn-custom-purple'); break; // 改為使用 class
                case '課程進行中': btn.classList.add('btn-success'); break;
                case '課程已結束': btn.classList.add('btn-secondary'); break;
                default: btn.classList.add('btn-primary'); break;
            }

            // 更新狀態並重新取得課程
            currentMyCourseStatus = btn.dataset.status;
            fetchMyCourses();
        });
    });

    // 頁面載入時，將 "全部" 按鈕設為 active
    document.querySelector('.my-course-filter-btn[data-status="all"]').className = 'btn btn-primary my-course-filter-btn';

    fetchMyCourses(); // 頁面初始載入

    // --- 新增：每分鐘自動更新課程狀態 ---
    setInterval(fetchMyCourses, 60000); // 60000 毫秒 = 1 分鐘
}
// ---- END ----

// --- 後台管理頁邏輯 (admin_dashboard.html) ---
const adminCourseListPage = document.getElementById('admin-course-list');

// 確保我們在後台管理頁面
if (adminCourseListPage) {

    // 函式定義必須在 if 區塊內部
    async function fetchAdminCourses() {
        const response = await fetch('/api/courses');
        const courses = await response.json();
        adminCourseListPage.innerHTML = '';
        courses.forEach(course => {
            const row = `
            <tr>
                <td>${course.id}</td>
                <td>${course.name}</td>
                <td>${course.class_time_summary}</td>
                <td>${course.status}</td>
                <td>${course.registration_start_time}</td>
                <td>${course.registration_end_time}</td>
                <td>
                    <button class="btn btn-sm" onclick="viewRegistrants(${course.id}, '${course.name}')" title="查看報名">
                        <i class="bi bi-eye-fill" style="color: #ae57a4;"></i>
                    </button>
                    <a href="/admin/course/edit/${course.id}" class="btn btn-sm" title="修改">
                        <i class="bi bi-pencil-square text-warning"></i>
                    </a>
                    <button class="btn btn-sm" onclick="deleteCourse(${course.id})" title="刪除">
                        <i class="bi bi-trash-fill text-danger"></i>
                    </button>
                </td>
            </tr>`;
            adminCourseListPage.innerHTML += row;
        });
    }

    // 函式呼叫也必須在 if 區塊內部
    fetchAdminCourses();
}

// ---- END ----


    // --- 課程編輯頁邏輯 (admin_course_form.html) ---
    const deleteFileButtons = document.querySelectorAll('.delete-file-btn'); // 取得所有刪除按鈕
    deleteFileButtons.forEach(button => {
        button.addEventListener('click', async function() { // 點擊事件
            const courseId = this.dataset.courseId; // 取得課程ID
            const filename = this.dataset.filename; // 取得檔案名稱
            // 確認刪除
            if (confirm(`確定要刪除附件 "${filename}" 嗎？`)) {
                try {
                    const response = await fetch(`/api/admin/courses/${courseId}/files/delete`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ filename: filename }),
                    });
                    // 解析回應
                    const result = await response.json();
                    if (response.ok && result.success) {
                        alert(result.message);
                        // 從畫面上移除該 li 元素
                        this.closest('li').remove();
                    } else {
                        alert(`刪除失敗: ${result.message}`);
                    }
                } catch (error) {
                    console.error('刪除附件時發生錯誤:', error);
                    alert('刪除過程中發生網路錯誤。');
                }
            }
        });
    });

    // --- 新增課程頁，預覽待上傳檔案 ---
    const newCourseFileInput = document.getElementById('file'); // 更改變數名稱以避免衝突
    const newFilesList = document.getElementById('new-files-list'); // 新增檔案列表容器

    // 如果頁面上有新增課程的檔案輸入和列表容器，才啟用這段邏輯 
    if (newCourseFileInput && newFilesList) {
        // 使用 DataTransfer 來管理檔案列表，因為 input.files 是唯讀的
        let fileStore = new DataTransfer();

        // 當檔案輸入改變時
        newCourseFileInput.addEventListener('change', () => {
            // 將新選擇的檔案加入到我們的存儲中
            // 每次都從頭開始，先清空 DataTransfer，再把 input 中最新的檔案列表加進去
            // 這樣可以正確處理使用者重新選擇檔案（而不是追加）的情況
            const newFiles = newCourseFileInput.files;
            fileStore = new DataTransfer(); // 清空舊的
            Array.from(newFiles).forEach(file => fileStore.add(file)); // 加入新的檔案
            // 更新 input 的檔案列表
            newCourseFileInput.files = fileStore.files;
            renderNewFiles(); // 重新渲染列表

        });
        // 渲染目前選擇的檔案列表
        function renderNewFiles() {
            newFilesList.innerHTML = ''; // 清空列表
            if (fileStore.files.length === 0) {
                newFilesList.innerHTML = '<li class="list-group-item text-muted">尚未選擇檔案</li>';
            }
            // 有檔案，逐一列出 
            else {
                Array.from(fileStore.files).forEach((file, index) => {
                    const li = document.createElement('li');
                    li.className = 'list-group-item d-flex justify-content-between align-items-center';
                    li.innerHTML = `
                        <span>${file.name}</span>
                        <button type="button" class="btn btn-outline-danger btn-sm remove-new-file-btn" data-index="${index}" title="移除此檔案">
                            <i class="bi bi-trash-fill"></i>
                        </button>
                    `;
                    newFilesList.appendChild(li);
                });

                // 為新的 "移除" 按鈕加上事件監聽
                document.querySelectorAll('.remove-new-file-btn').forEach(button => {
                    button.addEventListener('click', function() {
                        fileStore.items.remove(parseInt(this.dataset.index, 10)); // 確保是數字索引
                        newCourseFileInput.files = fileStore.files; // 同步更新 input 的檔案
                        renderNewFiles(); // 重新渲染列表
                    });
                });
            }
        }
        renderNewFiles(); // 初始渲染
    }

    // --- 優化 datetime-local 輸入框體驗  ---
    // 為所有 datetime-local 輸入框加上點擊事件，點擊時自動開啟選擇器
    // 使用事件委派來處理靜態和動態新增的輸入框
    document.body.addEventListener('click', function(event) {
        // 檢查被點擊的元素是否是 datetime-local 輸入框
        if (event.target && event.target.matches('input[type="datetime-local"]')) {
            try {
                // 呼叫瀏覽器的原生選擇器
                event.target.showPicker();
            } catch (error) {
                // 某些舊版瀏覽器可能不支援 showPicker()，這裡可以捕捉錯誤以避免腳本中斷
                console.warn('Browser does not support showPicker() for this input type.', error);
            }
        }
    });
});

// --- 全域可呼叫的函式 (因為 onclick 屬性需要它們在全域範疇) ---

/**
 * 使用者取消自己的報名
 * @param {number} registrationId - 報名紀錄的 ID
 * @param {string} courseName - 課程名稱
 */
async function cancelMyRegistration(registrationId, courseName) {
    if (confirm(`您確定要取消報名「${courseName}」嗎？`)) {
        try {
            const response = await fetch(`/api/registrations/${registrationId}/cancel`, {
                method: 'POST',
            });
            const result = await response.json();
            if (response.ok && result.success) {
                alert(result.message);
                // 簡單地重新整理頁面來更新列表
                location.reload();
            } else {
                alert(`取消失敗: ${result.message}`);
            }
        } catch (error) {
            console.error('取消報名時發生錯誤:', error);
            alert('操作失敗，請檢查網路連線或查看主控台。');
        }
    }
}


/**
 * 處理課程報名 @param {number} courseId - 課程的 ID
 */

//  報名課程 函式
async function registerForCourse(courseId) {
    const response = await fetch(`/api/courses/${courseId}/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
    });
    
    // 檢查回應是否為 JSON，若否，則處理導向登入頁的狀況
    const contentType = response.headers.get("content-type");
    if (contentType && contentType.indexOf("application/json") !== -1) {
        const result = await response.json();
        if (response.ok && result.success) {
            alert(result.message);
            location.reload(); // 重新整理頁面以更新狀態
        } else {
            alert(`報名失敗: ${result.message}`);
        }
    } else {
        // 如果收到的不是 JSON，很可能是因為未登入被導向到 HTML 登入頁
        // 雖然前端已有防護，但這是第二層保險
        promptLogin();
    }
}

/**
 * 刪除指定 ID 的課程
 * @param {number} courseId - 課程的 ID
 */

// 刪除課程 函式
async function deleteCourse(courseId) {
    if (confirm('確定要刪除這門課程嗎？此操作無法復原。')) {
        const response = await fetch(`/api/admin/courses/${courseId}`, {
            method: 'DELETE',
        });
        const result = await response.json();
        if (response.ok && result.success) {
            alert(result.message);
            location.reload();
        } 
        else {
            alert(`刪除失敗: ${result.message}`);
        }
    }
}

// 在 main.js 全域範疇新增此函式
function handleRegistration() {
    // 檢查是否為固定梯次模式
    const selectedSlot = document.querySelector('input[name="time_slot_id"]:checked');
    // 檢查是否為使用者自選時間模式
    const userSelectedTimeInput = document.getElementById('user_selected_time');
    
    let payload = {};
    let endpoint = '/api/register';

    if (selectedSlot) {
        // --- 模式一：固定梯次報名 ---
        payload = { time_slot_id: selectedSlot.value };
    } else if (userSelectedTimeInput) {
        // --- 模式二：使用者自選時間報名 ---
        const selectedTime = userSelectedTimeInput.value;
        if (!selectedTime) {
            alert('請先選擇您的上課時間！');
            return;
        }

        // --- Frontend validation for the selected time ---
        const minTime = userSelectedTimeInput.min;
        const maxTime = userSelectedTimeInput.max;
        if ((minTime && selectedTime < minTime) || (maxTime && selectedTime > maxTime)) {
            alert('您選擇的時間不在允許的範圍內，請重新選擇。');
            return; // Stop the API request
        }

        // --- ▼▼▼ 新增：檢查是否選到已被預約的時段 ▼▼▼ ---
        const bookedSlotsJSON = userSelectedTimeInput.dataset.bookedSlots;
        if (bookedSlotsJSON) {
            const bookedSlots = JSON.parse(bookedSlotsJSON);
            // The selectedTime format is "YYYY-MM-DDTHH:mm", we need to add seconds to match the ISO format from the backend
            if (bookedSlots.includes(selectedTime + ':00')) {
                alert('您選擇的時段已被預約，請選擇其他時間。');
                return;
            }
        }

        // Get course_id from the URL
        const courseId = window.location.pathname.split('/').pop();
        payload = {
            course_id: courseId,
            user_selected_time: selectedTime
        };
    } else {
        alert('無法確定報名類型。');
        return;
    }

    // 發送報名請求
    fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
    .then(response => response.json())
    .then(result => {
        alert(result.message);
        if (result.success) {
            location.reload();
        } 
    })
    .catch(error => {
        console.error('Error:', error);
        alert('報名時發生錯誤，請查看錯誤訊息。');
    });
}

/**
 * 檢視指定課程的報名者列表
 * @param {number} courseId - 課程的 ID
 * @param {string} courseName - 課程的名稱
 */

//  檢視報名者列表 函式
async function viewRegistrants(courseId, courseName) {
    const response = await fetch(`/api/admin/courses/${courseId}/registrations`);
    const registrants = await response.json();
    const modalTitle = document.getElementById('registrantsModalLabel');
    const modalList = document.getElementById('registrantsList');
    
    modalTitle.textContent = `「${courseName}」的報名者列表`;
    modalList.innerHTML = '';

    if (registrants.length > 0) {
        registrants.forEach(r => {
            //  r.slot_time 
            modalList.innerHTML += `<tr><td>${r.username}</td><td>${r.slot_time}</td><td>${r.registration_time}</td></tr>`;
        });
    } else {
        modalList.innerHTML = '<tr><td colspan="3" class="text-center">目前無人報名</td></tr>';
    }

    const modal = new bootstrap.Modal(document.getElementById('registrantsModal'));
    modal.show();
}

/* 當未登入使用者點擊需要權限的按鈕時，提示登入並導向。*/
function promptLogin() {
    if (confirm('請先登入才能報名。\n您要現在前往登入頁面嗎？')) {
        window.location.href = '/login';
    }
}

/**
 * 處理編輯頁面中，刪除已上傳檔案的請求
 * @param {number} fileId - 要刪除的檔案的 ID
 * @param {HTMLElement} buttonElement - 被點擊的按鈕元素
 */
// 刪除已上傳檔案 函式
async function deleteFile(fileId, buttonElement) {
    if (confirm('確定要永久刪除這個檔案嗎？此操作無法復原。')) {
        try {
            const response = await fetch(`/api/admin/files/${fileId}`, {
                method: 'DELETE',
            });

            const result = await response.json();

            if (response.ok && result.success) {
                // 從畫面上移除該檔案的 li 元素，提供即時回饋
                buttonElement.closest('li').remove();
                alert(result.message);
            } else {
                alert(`刪除失敗: ${result.message}`);
            }
        } catch (error) {
            console.error('刪除檔案時發生錯誤:', error);
            alert('刪除檔案失敗，請檢查網路連線或查看主控台。');
        }
    }
}