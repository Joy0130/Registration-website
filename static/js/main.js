// 主要的 JavaScript 程式碼
// 會被所有頁面載入

// 確保 DOM 完全載入後再執行
document.addEventListener('DOMContentLoaded', function() {
    
    // ---- START: 新增的梯次管理程式碼 ----
    const hasTimeSlotsCheckbox = document.getElementById('has_time_slots');
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
            }, 1000); // 2seconds
        });
    // 檢查頁面上是否存在這些元素
    if (hasTimeSlotsCheckbox && timeSlotsSection && addSlotBtn && slotsContainer && slotTemplate) {
        
        // 根據 checkbox 狀態顯示或隱藏梯次設定區塊
        function toggleTimeSlotsSection() {
            const isChecked = hasTimeSlotsCheckbox.checked;

            // 根據 checkbox 狀態顯示或隱藏整個區塊
            timeSlotsSection.style.display = isChecked ? 'block' : 'none';

            // 找到區塊內所有的輸入控制項 (input, textarea, select)
            const controls = timeSlotsSection.querySelectorAll('input, textarea, select');

            // 根據 checkbox 狀態來啟用或停用這些控制項
            controls.forEach(control => {
                control.disabled = !isChecked;
            });

}

        // 1. 頁面載入時先執行一次
        toggleTimeSlotsSection();

        // 2. 每次 checkbox 變動時執行
        hasTimeSlotsCheckbox.addEventListener('change', toggleTimeSlotsSection);

        // 3. 點擊「新增梯次」按鈕的邏輯
        addSlotBtn.addEventListener('click', () => {
            // 複製模板的內容
            const newRowContainer = document.createElement('div');
            newRowContainer.innerHTML = slotTemplate.innerHTML;
            const newRowElement = newRowContainer.firstElementChild;

            // 找到新建立的這一列中的所有 input 欄位
            const inputs = newRowElement.querySelectorAll('input');

            // 移除它們的 disabled 屬性，將它們“喚醒”
            inputs.forEach(input => {
                input.disabled = false;
            });

            // 將處理好的新列加到容器中
            slotsContainer.appendChild(newRowElement);
        });

        // 4. 點擊「移除」按鈕的邏輯 (使用事件委派)
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
            const response = await fetch(`/api/courses?status=${currentStatus}&search=${currentSearch}`); // 呼叫 API
            const courses = await response.json(); // 解析回應
            const courseList = document.getElementById('course-list'); // 課程列表容器
            courseList.innerHTML = ''; // 清空
            // 如果沒有課程，顯示提示訊息
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
                    if (IS_USER_AUTHENTICATED) {
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
                filterBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
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
    async function fetchMyCourses() {
        const response = await fetch('/api/my_courses');
        const registrations = await response.json(); // API 回傳的是「報名紀錄」列表
        myCourseListPage.innerHTML = '';

        if (registrations.length === 0) {
            myCourseListPage.innerHTML = '<p class="text-center text-muted">您目前沒有報名任何課程。</p>';
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

            const card = `
            <div class="col-md-6 mb-4">
                <div class="card h-100">
                    <div class="card-body">
                        <h5 class="card-title">${reg.course_name}</h5>
                        <h6 class="card-subtitle mb-2 text-muted">講者: ${reg.speaker_info}</h6>
                        <h6 class="card-subtitle mb-3 text-primary fw-bold">您的上課時間: ${reg.class_time}</h6>
                        <p class="card-text">${reg.course_description}</p>
                        ${fileLinksHTML}
                    </div>
                </div>
            </div>`;
            myCourseListPage.innerHTML += card;
        });
    }
    fetchMyCourses(); // 頁面初始載入
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
                    <button class="btn btn-sm btn-info" onclick="viewRegistrants(${course.id}, '${course.name}')">查看報名</button>
                    <a href="/admin/course/edit/${course.id}" class="btn btn-sm btn-warning">修改</a>
                    <button class="btn btn-sm btn-danger" onclick="deleteCourse(${course.id})">刪除</button>
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
});

// --- 全域可呼叫的函式 (因為 onclick 屬性需要它們在全域範疇) ---

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
    const selectedSlot = document.querySelector('input[name="time_slot_id"]:checked');
    if (!selectedSlot) {
        alert('請先選擇一個上課時間梯次！');
        return;
    }

    const slotId = selectedSlot.value; // 取得選中的梯次 ID

    // 發送報名請求
    fetch('/api/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ time_slot_id: slotId })
    })
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            alert(result.message);
            location.reload();
        } else {
            alert(`報名失敗: ${result.message}`);
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

/**
 * 當未登入使用者點擊需要權限的按鈕時，提示登入並導向。
 */
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