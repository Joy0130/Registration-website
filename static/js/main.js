// 主要的 JavaScript 程式碼
// 會被所有頁面載入

// 確保 DOM 完全載入後再執行
// eslint-disable-next-line max-lines-per-function
document.addEventListener('DOMContentLoaded', function() {
    
    // ---- START: 「後台課程表單」模式切換邏輯 ----
    const adminCourseForm = document.querySelector('form[action*="/api/admin/courses"]');
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
                });
            }
            if (fixedSlotsSection) {
                fixedSlotsSection.querySelectorAll('input, button').forEach(control => {
                    control.disabled = isUserChoiceMode;
                });
            }
        }
        
        if (allowUserChoiceCheckbox) {
            toggleCourseTimeMode();
            allowUserChoiceCheckbox.addEventListener('change', toggleCourseTimeMode);
        }
    }
    // ---- END ----

    // ---- START: 梯次管理程式碼 ----
    const timeSlotsSection = document.getElementById('time-slots-section');
    const addSlotBtn = document.getElementById('add-slot-btn');
    const slotsContainer = document.getElementById('time-slots-container');
    const slotTemplate = document.getElementById('time-slot-template');
    const durationInput = document.getElementById('duration_hours'); // 取得上課時數的 input
    
    // 自動關閉提示訊息
    const alerts = document.querySelectorAll('.alert.alert-dismissible');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
            bsAlert.close();
        }, 4000); // 3 秒後自動關閉
    });

    if (timeSlotsSection && addSlotBtn && slotsContainer && slotTemplate) {
        // 點擊「新增梯次」按鈕的邏輯
        addSlotBtn.addEventListener('click', () => {
            const newRowContainer = document.createElement('div');
            newRowContainer.innerHTML = slotTemplate.innerHTML;
            const newRowElement = newRowContainer.firstElementChild;
            newRowElement.querySelectorAll('input, button').forEach(control => {
                control.disabled = false;
            });
            slotsContainer.appendChild(newRowElement);
        });

        // 點擊「移除」按鈕的邏輯 (使用事件委派)
        slotsContainer.addEventListener('click', (e) => {
            const removeButton = e.target.closest('.remove-slot-btn');
            if (removeButton) {
                e.target.closest('.time-slot-row').remove();
            }
        });

        // --- START: NEW Automatic End Time Calculation ---
        const calculateEndTime = (startTimeInput) => {
            if (!durationInput) return;
            const durationHours = parseFloat(durationInput.value);
            const timeSlotRow = startTimeInput.closest('.time-slot-row');
            if (!timeSlotRow) return;

            const endTimeInput = timeSlotRow.querySelector('input[name="slot_end_times"]');
            if (!endTimeInput) return;

            // 只有當上課時數 > 0 且已填寫開始時間時，才進行計算
            if (!isNaN(durationHours) && durationHours > 0 && startTimeInput.value) {
                try {
                    const startTime = new Date(startTimeInput.value);
                    const endTime = new Date(startTime.getTime() + durationHours * 60 * 60 * 1000);

                    // 格式化為 YYYY-MM-DDTHH:mm 以符合 datetime-local 的要求
                    const year = endTime.getFullYear();
                    const month = String(endTime.getMonth() + 1).padStart(2, '0');
                    const day = String(endTime.getDate()).padStart(2, '0');
                    const hours = String(endTime.getHours()).padStart(2, '0');
                    const minutes = String(endTime.getMinutes()).padStart(2, '0');
                    const formattedEndTime = `${year}-${month}-${day}T${hours}:${minutes}`;
                    
                    endTimeInput.value = formattedEndTime;
                    endTimeInput.readOnly = true; // 設為唯讀，不可手動修改
                } catch (error) {
                    console.error("計算結束時間時出錯:", error);
                    endTimeInput.value = '';
                    endTimeInput.readOnly = false; // 出錯時恢復可編輯
                }
            } else {
                // 如果沒有有效的時數或開始時間，清空結束時間並使其可編輯
                endTimeInput.value = '';
                endTimeInput.readOnly = false;
            }
        };

        // 使用事件委派，監聽整個梯次容器的 input 事件
        slotsContainer.addEventListener('input', (e) => {
            if (e.target && e.target.matches('input[name="slot_start_times"]')) {
                calculateEndTime(e.target);
            }
        });

        // 當「上課時數」欄位變動時，重新計算所有梯次的結束時間
        if (durationInput) {
            durationInput.addEventListener('input', () => {
                const allStartTimeInputs = slotsContainer.querySelectorAll('input[name="slot_start_times"]');
                allStartTimeInputs.forEach(startTimeInput => {
                    calculateEndTime(startTimeInput);
                });
            });
        }
        
        // 頁面載入時，為已存在的梯次（例如在編輯頁面）計算一次結束時間
        const existingStartTimeInputs = slotsContainer.querySelectorAll('input[name="slot_start_times"]');
        existingStartTimeInputs.forEach(startTimeInput => {
            calculateEndTime(startTimeInput);
        });
        // --- END: NEW Automatic End Time Calculation ---
    }
    // ---- END: 梯次管理程式碼 ----

    // ---- 上傳檔案預覽程式 (此部分無需修改) ----
    const fileInput = document.getElementById('file');
    const fileListContainer = document.getElementById('file-list-container');
    
    let selectedFiles = new DataTransfer();

    if (fileInput && fileListContainer) {
        fileInput.addEventListener('change', () => {
            for (let i = 0; i < fileInput.files.length; i++) {
                let isDuplicate = false;
                for(let j = 0; j < selectedFiles.items.length; j++) {
                    if (selectedFiles.items[j].getAsFile().name === fileInput.files[i].name) {
                        isDuplicate = true;
                        break;
                    }
                }
                if (!isDuplicate) {
                    selectedFiles.items.add(fileInput.files[i]);
                }
            }
            fileInput.files = selectedFiles.files;
            renderFileList();
        });

        function renderFileList() {
            fileListContainer.innerHTML = '';
            if (selectedFiles.items.length > 0) {
                 const list = document.createElement('ul');
                 list.className = 'list-group';
                 for (let i = 0; i < selectedFiles.files.length; i++) {
                     const file = selectedFiles.files[i];
                     const listItem = document.createElement('li');
                     listItem.className = 'list-group-item d-flex justify-content-between align-items-center';
                     listItem.textContent = file.name;
                     
                     const deleteBtn = document.createElement('button'); 
                     deleteBtn.type = 'button';
                     deleteBtn.className = 'btn btn-sm btn-outline-danger';
                     deleteBtn.title = '移除此檔案';
                     deleteBtn.innerHTML = '<i class="bi bi-trash-fill"></i>'; 
                     deleteBtn.dataset.index = i;
                     
                     deleteBtn.addEventListener('click', (e) => {
                         const button = e.target.closest('button');
                         const indexToRemove = parseInt(button.dataset.index, 10);
                         const newFiles = new DataTransfer();
                         for(let j = 0; j < selectedFiles.files.length; j++) {
                             if(j !== indexToRemove) {
                                 newFiles.items.add(selectedFiles.files[j]);
                             }
                         }
                         selectedFiles = newFiles;
                         fileInput.files = selectedFiles.files;
                         renderFileList();
                     });
                     listItem.appendChild(deleteBtn);
                     list.appendChild(listItem);
                 }
                 fileListContainer.appendChild(list);
            }
        }
    }

    // --- 首頁邏輯 (index.html) ---
    const courseListPage = document.getElementById('course-list');
    if (courseListPage) {
        let currentStatus = 'all';
        let currentSearch = '';
        const searchInput = document.getElementById('searchInput');
        const filterBtns = document.querySelectorAll('.filter-btn');

        async function fetchAndRenderCourses() {
            const response = await fetch(`/api/courses?status=${currentStatus}&search=${currentSearch}`);
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
                    if (course.is_full) {
                        actionButton = '<button class="btn btn-secondary w-100" disabled>已額滿</button>';
                    } else if (IS_USER_AUTHENTICATED) {
                        if (course.is_registered) {
                            actionButton = '<button class="btn btn-outline-secondary w-100" disabled>已報名</button>';
                        } else {
                            actionButton = `<button class="btn btn-primary w-100">立即報名</button>`;
                        }
                    } else {
                        actionButton = `<button class="btn btn-primary w-100" onclick="promptLogin()">立即報名</button>`;
                    }
                } else {
                    actionButton = `<button class="btn btn-secondary w-100" disabled>${course.status}</button>`;
                }

                const card = `
                <div class="col-md-4 mb-4">
                    <div class="card h-100">
                        <div class="card-body d-flex flex-column">
                            <h5 class="card-title">
                                <a href="/course/${course.id}" class="text-decoration-none text-dark stretched-link">${course.name}</a>
                                ${statusBadge}
                            </h5>
                            <h6 class="card-subtitle mb-3 text-primary fw-bold">上課時間: ${course.class_time_summary || '詳見課程內容'}</h6>
                            <h6 class="card-subtitle mb-2 text-muted">講者: ${course.speaker_info}</h6>
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
        }

        filterBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                filterBtns.forEach(b => b.className = 'btn btn-outline-secondary filter-btn');
                const clickedStatus = btn.dataset.status;
                btn.className = 'btn filter-btn';
                switch (clickedStatus) {
                    case 'all': btn.classList.add('btn-primary'); break; 
                    case '報名中': btn.classList.add('btn-success'); break;
                    case '尚未開放': btn.classList.add('btn-warning'); break;
                    case '報名截止': btn.classList.add('btn-secondary'); break;
                }
                currentStatus = clickedStatus;
                fetchAndRenderCourses();
            });
        });

        if (searchInput) {
            searchInput.addEventListener('input', () => {
                currentSearch = searchInput.value;
                fetchAndRenderCourses();
            });
        }

        fetchAndRenderCourses();
    }

// --- START: 【修正】補全「我報名的課程」頁面邏輯 ---
const myCourseListPage = document.getElementById('my-course-list');
if (myCourseListPage) {
    let currentMyCourseStatus = 'all'; // 預設顯示所有

    async function fetchMyCourses() {
        try {
            const response = await fetch(`/api/my_courses?status=${currentMyCourseStatus}`);
            if (!response.ok) {
                throw new Error(`伺服器錯誤: ${response.statusText}`);
            }
            const registrations = await response.json();
            myCourseListPage.innerHTML = '';
            if (registrations.length === 0) {
                myCourseListPage.innerHTML = '<p class="text-center text-muted">沒有符合條件的課程。</p>';
                return;
            }

            registrations.forEach(reg => {
                let fileLinksHTML = '';
                if (reg.files && reg.files.length > 0) {
                    fileLinksHTML += '<h6 class="mt-3">課程教材:</h6><div class="list-group list-group-flush">';
                    reg.files.forEach(file => {
                        // 使用後端傳來的 url (已包含 download_file 路由)
                        fileLinksHTML += `<a href="${file.url}" class="list-group-item list-group-item-action" target="_blank">${file.display_name}</a>`;
                    });
                    fileLinksHTML += '</div>';
                }

                let statusBadgeHTML = '';
                switch (reg.status) {
                    case '課程即將開始': statusBadgeHTML = '<span class="badge text-white" style="background-color: #ae57a4;">即將開始</span>'; break;
                    case '課程進行中': statusBadgeHTML = '<span class="badge bg-success">進行中</span>'; break;
                    case '課程已結束': statusBadgeHTML = '<span class="badge bg-secondary">已結束</span>'; break;
                }
                
                let cancelButtonHTML = '';
                const slotStartTime = new Date(reg.slot_start_time);
                // 取消期限為課程開始前 1 天
                const cancellationDeadline = new Date(slotStartTime.getTime() - (1 * 24 * 60 * 60 * 1000));
                const now = new Date();

                if (now > cancellationDeadline) {
                    cancelButtonHTML = `<button class="btn btn-outline-secondary btn-sm mt-3" disabled title="已超過取消期限，請聯繫管理員。">取消報名</button>`;
                } else {
                    cancelButtonHTML = `<button class="btn btn-outline-danger btn-sm mt-3" onclick="cancelMyRegistration('${reg.registration_id}', '${reg.course_name.replace(/'/g, "\\'")}')">取消報名</button>`;
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
        } catch (error) {
            console.error("取得我的課程時發生錯誤:", error);
            myCourseListPage.innerHTML = '<p class="text-center text-danger">載入課程失敗，請稍後再試。</p>';
        }
    }

    const filterBtns = document.querySelectorAll('.my-course-filter-btn');
    filterBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            filterBtns.forEach(b => {
                b.className = 'btn btn-outline-secondary my-course-filter-btn';
                b.removeAttribute('style');
            });

            const clickedStatus = btn.dataset.status;
            btn.className = 'btn my-course-filter-btn';
            switch (clickedStatus) {
                case 'all': btn.classList.add('btn-primary'); break;
                case '課程即將開始': btn.classList.add('btn-custom-purple'); break;
                case '課程進行中': btn.classList.add('btn-success'); break;
                case '課程已結束': btn.classList.add('btn-secondary'); break;
                default: btn.classList.add('btn-primary'); break;
            }

            currentMyCourseStatus = clickedStatus;
            fetchMyCourses();
        });
    });

    // 頁面載入時，將 "全部" 按鈕設為 active 並載入資料
    document.querySelector('.my-course-filter-btn[data-status="all"]').className = 'btn btn-primary my-course-filter-btn';
    fetchMyCourses();
    // 每分鐘自動更新課程狀態
    setInterval(fetchMyCourses, 60000);
}
// --- END ---

// --- 後台管理頁邏輯 (admin_dashboard.html) ---
const adminCourseListPage = document.getElementById('admin-course-list');
if (adminCourseListPage) {
    async function fetchAdminCourses() {
        const response = await fetch('/api/courses');
        const courses = await response.json();
        adminCourseListPage.innerHTML = '';
        courses.forEach(course => {
            const row = `
            <tr>
                <td>${course.id}</td>
                <td>${course.name}</td>
                <td>${course.class_time_summary || 'N/A'}</td>
                <td>${course.status}</td>
                <td>${course.registration_start_time}</td>
                <td>${course.registration_end_time}</td>
                <td>
                    <button class="btn btn-sm" onclick="viewRegistrants('${course.id}', '${course.name.replace(/'/g, "\\'")}')" title="查看報名">
                        <i class="bi bi-eye-fill" style="color: #ae57a4;"></i>
                    </button>
                    <a href="/admin/course/edit/${course.id}" class="btn btn-sm" title="修改">
                        <i class="bi bi-pencil-square text-warning"></i>
                    </a>
                    <button class="btn btn-sm" onclick="deleteCourse('${course.id}')" title="刪除">
                        <i class="bi bi-trash-fill text-danger"></i>
                    </button>
                </td>
            </tr>`;
            adminCourseListPage.innerHTML += row;
        });
    }
    fetchAdminCourses();
}

    // --- 【修正】課程編輯頁刪除檔案的邏輯 ---
    const deleteFileButtons = document.querySelectorAll('.delete-file-btn');
    deleteFileButtons.forEach(button => {
        button.addEventListener('click', async function() {
            const courseId = this.dataset.courseId;
            const storagePath = this.dataset.storagePath; 
            const fileObject = JSON.parse(this.dataset.fileObject);

            if (confirm(`確定要刪除附件 "${fileObject.display_name}" 嗎？此操作無法復原。`)) {
                try {
                    const response = await fetch(`/api/admin/courses/${courseId}/files/delete`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ 
                            storage_path: storagePath,
                            file_object: fileObject 
                        }),
                    });
                    
                    const result = await response.json();
                    if (response.ok && result.success) {
                        alert(result.message);
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

    // --- 優化 datetime-local 輸入框體驗 (此部分無需修改) ---
    document.body.addEventListener('click', function(event) {
        if (event.target && event.target.matches('input[type="datetime-local"]')) {
            try {
                event.target.showPicker();
            } catch (error) {
                console.warn('Browser does not support showPicker() for this input type.', error);
            }
        }
    });

    // --- START: 【新增】後台取消報名表單的確認提示 ---
    // 使用事件委派來處理所有取消報名的表單
    document.body.addEventListener('submit', function(event) {
        const form = event.target;
        if (form && form.classList.contains('admin-cancel-form')) {
            const message = form.dataset.confirmMessage || '確定要執行此操作嗎？';
            if (!confirm(message)) {
                event.preventDefault(); // 如果使用者點擊「取消」，就阻止表單提交
            }
        }
    });
    // --- END ---

});

// --- 全域可呼叫的函式 ---

/**
 * 刪除指定 ID 的課程
 * @param {string} courseId - 課程的 Firestore 文件 ID
 */
async function deleteCourse(courseId) {
    if (confirm('確定要刪除這門課程嗎？此操作將一併刪除所有相關的報名紀錄與檔案，且無法復原。')) {
        try {
            const response = await fetch(`/api/admin/courses/${courseId}`, {
                method: 'DELETE',
            });
            const result = await response.json();
            if (response.ok && result.success) {
                alert(result.message);
                location.reload();
            } else {
                alert(`刪除失敗: ${result.message}`);
            }
        } catch (error) {
            console.error('刪除課程時發生錯誤:', error);
            alert('操作失敗，請檢查網路連線或查看主控台。');
        }
    }
}

/**
 * 檢視指定課程的報名者列表
 * @param {string} courseId - 課程的 Firestore 文件 ID
 * @param {string} courseName - 課程的名稱
 */
async function viewRegistrants(courseId, courseName) {
    try {
        const response = await fetch(`/api/admin/courses/${courseId}/registrations`);
        if (!response.ok) {
            throw new Error(`伺服器錯誤: ${response.statusText}`);
        }
        const registrants = await response.json();
        const modalTitle = document.getElementById('registrantsModalLabel');
        const modalList = document.getElementById('registrantsList');
        
        modalTitle.textContent = `「${courseName}」的報名者列表`;
        modalList.innerHTML = '';

        if (registrants.length > 0) {
            registrants.forEach(r => {
                modalList.innerHTML += `<tr><td>${r.username}</td><td>${r.slot_time}</td><td>${r.registration_time}</td></tr>`;
            });
        } else {
            modalList.innerHTML = '<tr><td colspan="3" class="text-center">目前無人報名</td></tr>';
        }

        const modal = new bootstrap.Modal(document.getElementById('registrantsModal'));
        modal.show();
    } catch (error) {
        console.error('檢視報名者時發生錯誤:', error);
        alert('無法取得報名者列表，請查看主控台。');
    }
}

// --- START: NEW/RESTORED Registration Logic ---
/**
 * 處理課程報名
 * 由 course_detail.html 中的按鈕觸發
 */
// 格式化日期與時間，例如：2025/10/11 14:00 ~ 16:00
function formatSlotDisplay(slot) {
    const start = new Date(slot.start_time);
    const end = new Date(slot.end_time);

    const pad = (num) => String(num).padStart(2, '0');

    const formattedDate = `${start.getFullYear()}/${pad(start.getMonth() + 1)}/${pad(start.getDate())}`;
    const formattedTime = `${pad(start.getHours())}:${pad(start.getMinutes())} ~ ${pad(end.getHours())}:${pad(end.getMinutes())}`;

    return `${formattedDate} ${formattedTime}`;
}

async function handleRegistration() {
    const pathParts = window.location.pathname.split('/');
    const courseId = pathParts[pathParts.length - 1];
    let payload = { course_id: courseId };

    // --- START: 【修正】區分兩種報名模式 ---
    const userSelectedTimeInput = document.getElementById('user_selected_time');

    if (userSelectedTimeInput) {
        // --- 模式一：使用者自選時間 ---
        const selectedTime = userSelectedTimeInput.value;
        if (!selectedTime) {
            alert('請選擇您的上課日期與時間！');
            return;
        }
        
        // 檢查選擇的時間是否在允許範圍內
        const minTime = userSelectedTimeInput.min;
        const maxTime = userSelectedTimeInput.max;
        if ((minTime && selectedTime < minTime) || (maxTime && selectedTime > maxTime)) {
            alert(`您選擇的時間不在允許的範圍內。\n請選擇 ${minTime.replace('T', ' ')} 到 ${maxTime.replace('T', ' ')} 之間的時間。`);
            return;
        }

        payload.user_selected_time = selectedTime;

    } else {
        // --- 模式二：固定梯次 ---
        let selectedSlot = document.querySelector('input[name="time_slot_id"]:checked');

        // 如果沒有選擇，但頁面有固定梯次，則自動使用第一個可用梯次
        const firstAvailableSlot = document.querySelector('input[name="time_slot_id"]');
        if (!selectedSlot && firstAvailableSlot) {
            selectedSlot = firstAvailableSlot;
            selectedSlot.checked = true; // 自動勾選
        }

        if (!selectedSlot) {
            alert('請先選擇一個上課梯次！');
            return;
        }

        // 如果前端有完整梯次資料，可以顯示完整日期時間
        const slotData = selectedSlot.dataset.slot ? JSON.parse(selectedSlot.dataset.slot) : null;
        if (slotData) {
            const displayText = formatSlotDisplay(slotData);
            selectedSlot.nextElementSibling.textContent = displayText;
        }

        payload.time_slot_id = selectedSlot.value;
    }
    // --- END: 【修正】 ---

    try {
        const response = await fetch('/api/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const result = await response.json();
        alert(result.message);

        if (response.ok && result.success) {
            location.reload();
        }
    } catch (error) {
        console.error('報名時發生錯誤:', error);
        alert('報名時發生網路錯誤，請查看主控台。');
    }
}

// --- END: NEW/RESTORED Registration Logic ---

// --- START: NEW/RESTORED Cancel Registration Logic ---
/**
 * 使用者取消自己的報名
 * @param {string} registrationId - 報名紀錄的 ID
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
                location.reload(); // 簡單地重新整理頁面來更新列表
            } else {
                alert(`取消失敗: ${result.message}`);
            }
        } catch (error) {
            console.error('取消報名時發生錯誤:', error);
            alert('操作失敗，請檢查網路連線或查看主控台。');
        }
    }
}
// --- END ---

/**
 * 當未登入使用者點擊需要權限的按鈕時，提示登入並導向。
 */
function promptLogin() {
    if (confirm('請先登入才能報名。\n您要現在前往登入頁面嗎？')) {
        window.location.href = '/login';
    }
}
