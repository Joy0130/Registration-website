/**
 * Firebase Functions 後端 API
 * 這是 Python Flask app.py 的 Node.js + Express.js + Firebase Functions 完整重構版本。
 *
 * 主要變更：
 * 1. 認證機制：從 Flask-Login Session 改為 Firebase Auth ID Token。
 * 2. 路由管理：使用 Express.js 框架管理所有 API 端點。
 * 3. 定時任務：從 APScheduler 改為 Firebase Scheduled Functions (Pub/Sub)。
 * 4. 檔案處理：使用 Busboy 處理檔案上傳，Admin SDK 處理檔案儲存與下載。
 * 5. 錯誤處理與回應：所有端點均回傳 JSON 格式。
 */

/**
 * Firebase Functions 後端 API (路由修正版)
 * 移除了所有 Express 路由定義中多餘的 '/api' 前綴。
 */

// --- 核心模組 ---
const functions = require("firebase-functions");
const admin = require("firebase-admin");
const express = require("express");
const cors = require("cors");
const Busboy = require("busboy");
const path = require("path");
const os = require("os");
const fs = require("fs");
const { v4: uuidv4 } = require("uuid");
const { formatInTimeZone } = require("date-fns-tz");

// --- Firebase Admin SDK 初始化 ---
admin.initializeApp();
const db = admin.firestore();
const auth = admin.auth();
const bucket = admin.storage().bucket("bank-robot-45a15.firebasestorage.app");

// --- Express App 初始化 ---
const app = express();
app.use(cors({ origin: true })); // 允許跨域請求
const jsonParser = express.json(); // 建立一個 JSON 解析器中介軟體

// --- 時區設定 ---
const TAIWAN_TZ = "Asia/Taipei";

// --- 時間格式化輔助函式 ---
const toTaiwanTimeStr = (timestamp, fmt = "yyyy-MM-dd HH:mm:ss") => {
    if (!timestamp || typeof timestamp.toDate !== "function") {
        return "";
    }
    const date = timestamp.toDate();
    return formatInTimeZone(date, TAIWAN_TZ, fmt);
};

// --- [核心] 身份驗證中介軟體 ---
const verifyFirebaseToken = async (req, res, next) => {
    const authorization = req.headers.authorization;
    if (!authorization || !authorization.startsWith("Bearer ")) {
        console.error("未找到 Firebase ID token。");
        return res.status(403).send({ error: "未經授權" });
    }

    const idToken = authorization.split("Bearer ")[1];
    try {
        const decodedToken = await admin.auth().verifyIdToken(idToken);
        req.user = decodedToken;
        next();
    } catch (error) {
        console.error("驗證 Firebase ID token 時出錯:", error);
        return res.status(403).send({ error: "未經授權" });
    }
};

const requireAdmin = (req, res, next) => {
    if (req.user && req.user.admin === true) {
        return next();
    }
    return res.status(403).send({ error: "需要管理員權限" });
};

// --- [核心] 定時任務 ---
exports.checkCourseStatus = functions.region("asia-east1").pubsub
    .schedule("every 5 minutes")
    .timeZone(TAIWAN_TZ)
    .onRun(async (context) => {
        console.log("[Scheduler] 正在檢查課程狀態...");
        const now = new Date();
        const batch = db.batch();

        const coursesToOpenQuery = db.collection("courses").where("status", "==", "尚未開放");
        const coursesToOpenSnapshot = await coursesToOpenQuery.get();
        coursesToOpenSnapshot.forEach(doc => {
            const course = doc.data();
            if (course.registration_start_time.toDate() <= now) {
                if (now < course.registration_end_time.toDate()) {
                    batch.update(doc.ref, { status: "報名中" });
                } else {
                    batch.update(doc.ref, { status: "報名截止" });
                }
            }
        });

        const coursesToCloseQuery = db.collection("courses").where("status", "==", "報名中");
        const coursesToCloseSnapshot = await coursesToCloseQuery.get();
        coursesToCloseSnapshot.forEach(doc => {
            const course = doc.data();
            if (course.registration_end_time.toDate() <= now) {
                batch.update(doc.ref, { status: "報名截止" });
            }
        });

        await batch.commit();
        console.log("[Scheduler] 課程狀態檢查完成。");
        return null;
    });

// --- API 路由 (供前端 JavaScript 呼叫) ---

// [公開] 取得所有課程列表
app.get("/courses", async (req, res) => {
    try {
        const coursesSnapshot = await db.collection("courses").get();
        const coursesDataPromises = coursesSnapshot.docs.map(async (doc) => {
            const course = doc.data();
            course.id = doc.id;

            course.registration_start_time = toTaiwanTimeStr(course.registration_start_time, "yyyy-MM-dd HH:mm");
            course.registration_end_time = toTaiwanTimeStr(course.registration_end_time, "yyyy-MM-dd HH:mm");

            return course;
        });
        const coursesData = await Promise.all(coursesDataPromises);
        return res.status(200).json(coursesData);
    } catch (error) {
        console.error("獲取課程時出錯:", error);
        return res.status(500).json({ error: "伺服器發生錯誤" });
    }
});

// [需登入] 取得使用者已報名的課程
app.get("/my_courses", verifyFirebaseToken, async (req, res) => {
    const userId = req.user.uid;
    try {
        const regsSnapshot = await db.collection("registrations").where("user_id", "==", userId).get();
        const myCoursesPromises = regsSnapshot.docs.map(async (regDoc) => {
            const reg = regDoc.data();
            const courseDoc = await db.collection("courses").doc(reg.course_id).get();
            const slotDoc = await db.collection("courses").doc(reg.course_id).collection("time_slots").doc(reg.time_slot_id).get();

            if (!courseDoc.exists || !slotDoc.exists) return null;

            const course = courseDoc.data();
            const slot = slotDoc.data();
            const now = new Date();
            let status = "狀態未知";

            if (now < slot.slot_start_time.toDate()) status = "課程即將開始";
            else if (now >= slot.slot_start_time.toDate() && now < slot.slot_end_time.toDate()) status = "課程進行中";
            else status = "課程已結束";

            return {
                registration_id: regDoc.id,
                course_id: reg.course_id,
                course_name: course.name,
                class_time: `${toTaiwanTimeStr(slot.slot_start_time, "yyyy-MM-dd HH:mm")} ~ ${toTaiwanTimeStr(slot.slot_end_time, "HH:mm")}`,
                status: status,
                files: course.files || []
            };
        });
        const myCourses = (await Promise.all(myCoursesPromises)).filter(c => c !== null);
        return res.status(200).json(myCourses);
    } catch (error) {
        console.error("取得我的課程時出錯:", error);
        return res.status(500).json({ error: "無法取得您的課程列表" });
    }
});


// [需登入] 報名課程
app.post("/register", jsonParser, verifyFirebaseToken, async (req, res) => {
    const userId = req.user.uid;
    const { course_id, time_slot_id, user_selected_time } = req.body;

    if (!course_id || (!time_slot_id && !user_selected_time)) {
        return res.status(400).json({ success: false, message: '報名資訊不完整' });
    }

    const courseRef = db.collection('courses').doc(course_id);
    let slotRef;

    try {
        await db.runTransaction(async (transaction) => {
            const courseDoc = await transaction.get(courseRef);
            if (!courseDoc.exists || courseDoc.data().status !== '報名中') {
                throw new Error('此課程目前未開放報名');
            }

            const existingRegQuery = db.collection('registrations').where('user_id', '==', userId).where('course_id', '==', course_id);
            const existingRegSnapshot = await transaction.get(existingRegQuery);
            if (!existingRegSnapshot.empty) {
                throw new Error('您已經報名過此課程');
            }

            if (user_selected_time) {
                const courseData = courseDoc.data();
                const durationHours = courseData.duration_hours || 1;
                const startTime = new Date(user_selected_time);
                const endTime = new Date(startTime.getTime() + durationHours * 60 * 60 * 1000);

                slotRef = courseRef.collection("time_slots").doc();
                transaction.set(slotRef, {
                    slot_start_time: admin.firestore.Timestamp.fromDate(startTime),
                    slot_end_time: admin.firestore.Timestamp.fromDate(endTime),
                    capacity: 1,
                    booked_count: 0,
                    is_user_choice: true
                });

            } else {
                slotRef = courseRef.collection('time_slots').doc(time_slot_id);
                const slotDoc = await transaction.get(slotRef);
                if (!slotDoc.exists) throw new Error('找不到指定的梯次');
                const slotData = slotDoc.data();
                if (slotData.booked_count >= slotData.capacity) throw new Error('此梯次名額已滿');
                transaction.update(slotRef, { booked_count: admin.firestore.FieldValue.increment(1) });
            }

            const regRef = db.collection('registrations').doc();
            transaction.set(regRef, {
                user_id: userId,
                course_id: course_id,
                time_slot_id: slotRef.id,
                registration_time: admin.firestore.FieldValue.serverTimestamp()
            });
        });
        return res.status(200).json({ success: true, message: '報名成功！' });
    } catch (error) {
        console.error("報名時發生錯誤:", error);
        return res.status(500).json({ success: false, message: error.message });
    }
});


// [需登入] 取消報名
app.post("/registrations/:registration_id/cancel", verifyFirebaseToken, async (req, res) => {
    const userId = req.user.uid;
    const { registration_id } = req.params;
    const regRef = db.collection("registrations").doc(registration_id);

    try {
        await db.runTransaction(async (t) => {
            const regDoc = await t.get(regRef);
            if (!regDoc.exists || regDoc.data().user_id !== userId) {
                throw new Error("找不到您的報名紀錄或無權限操作。");
            }
            const regData = regDoc.data();
            const slotRef = db.collection("courses").doc(regData.course_id).collection("time_slots").doc(regData.time_slot_id);
            const slotDoc = await t.get(slotRef);

            if (slotDoc.exists) {
                const slotData = slotDoc.data();
                const deadline = new Date(slotData.slot_start_time.toDate().getTime() - 24 * 60 * 60 * 1000);
                if (new Date() > deadline) {
                    throw new Error("已超過取消期限 (課程開始前24小時)，無法取消報名。");
                }

                if (slotData.is_user_choice) {
                    t.delete(slotRef);
                } else {
                    t.update(slotRef, { booked_count: admin.firestore.FieldValue.increment(-1) });
                }
            }
            t.delete(regRef);
        });
        return res.status(200).json({ success: true, message: "已成功取消報名。" });
    } catch (error) {
        console.error("取消報名時發生錯誤:", error);
        return res.status(500).json({ success: false, message: error.message });
    }
});

// --- 後台管理路由與 API ---

app.get("/admin/all_registrations", verifyFirebaseToken, requireAdmin, async (req, res) => {
     try {
        const regsSnapshot = await db.collection("registrations").orderBy("registration_time", "desc").get();
        const regsDataPromises = regsSnapshot.docs.map(async (doc) => {
            const reg = doc.data();
            const userDoc = await db.collection("users").doc(reg.user_id).get();
            const courseDoc = await db.collection("courses").doc(reg.course_id).get();
            const slotDoc = await db.collection("courses").doc(reg.course_id).collection("time_slots").doc(reg.time_slot_id).get();

            return {
                id: doc.id,
                username: userDoc.exists ? userDoc.data().username : "未知用戶",
                course_name: courseDoc.exists ? courseDoc.data().name : "未知課程",
                slot_time: slotDoc.exists ? toTaiwanTimeStr(slotDoc.data().slot_start_time, "yyyy-MM-dd HH:mm") : "未知梯次",
                registration_time: toTaiwanTimeStr(reg.registration_time)
            };
        });
        const regsData = await Promise.all(regsDataPromises);
        return res.status(200).json(regsData);
    } catch (error) {
        console.error("管理員獲取報名紀錄時出錯:", error);
        return res.status(500).json({ error: "伺服器錯誤" });
    }
});

app.post("/admin/courses", verifyFirebaseToken, requireAdmin, (req, res) => {
    // 檔案上傳使用 busboy
    const busboy = Busboy({ headers: req.headers });
    const tmpdir = os.tmpdir();
    
    const fields = {};
    const fileWrites = [];
    const uploads = {};

    busboy.on('field', (fieldname, val) => {
        if (fieldname.includes('[')) {
            const [key, index, subkey] = fieldname.replace(/]/g, '').split('[');
            if (!fields[key]) fields[key] = [];
            if (!fields[key][index]) fields[key][index] = {};
            fields[key][index][subkey] = val;
        } else {
            fields[fieldname] = val;
        }
    });

    busboy.on('file', (fieldname, file, filenameInfo) => {
        const { filename, mimeType } = filenameInfo;
        const filepath = path.join(tmpdir, filename);
        uploads[fieldname] = { filepath, mimeType, filename };
        
        const writeStream = fs.createWriteStream(filepath);
        file.pipe(writeStream);
        
        const promise = new Promise((resolve, reject) => {
            file.on('end', () => writeStream.end());
            writeStream.on('finish', resolve);
            writeStream.on('error', reject);
        });
        fileWrites.push(promise);
    });

    busboy.on('finish', async () => {
        await Promise.all(fileWrites);
        
        try {
            const courseRef = db.collection('courses').doc();
            const courseId = courseRef.id;

            const filesMetadata = [];
            for (const fileKey in uploads) {
                const file = uploads[fileKey];
                const storagePath = `course_files/${courseId}/${uuidv4()}-${file.filename}`;
                await bucket.upload(file.filepath, { destination: storagePath, metadata: { contentType: file.mimeType } });
                filesMetadata.push({
                    display_name: file.filename,
                    storage_path: storagePath,
                    upload_time: admin.firestore.FieldValue.serverTimestamp()
                });
                fs.unlinkSync(file.filepath);
            }

            const startTime = new Date(fields.registration_start_time);
            const endTime = new Date(fields.registration_end_time);
            const now = new Date();
            let status = "尚未開放";
            if (startTime <= now && now < endTime) status = "報名中";
            else if (now >= endTime) status = "報名截止";
            
            const courseData = {
                name: fields.name,
                description: fields.description,
                speaker_info: fields.speaker_info,
                status: status,
                registration_start_time: admin.firestore.Timestamp.fromDate(startTime),
                registration_end_time: admin.firestore.Timestamp.fromDate(endTime),
                files: filesMetadata,
            };
            await courseRef.set(courseData);
            
            res.status(201).json({ success: true, message: "課程新增成功", id: courseId });

        } catch (error) {
            console.error("處理課程新增時出錯:", error);
            res.status(500).json({ success: false, message: `伺服器錯誤: ${error.message}` });
        }
    });

    busboy.end(req.rawBody);
});

app.delete("/admin/courses/:course_id", verifyFirebaseToken, requireAdmin, async (req, res) => {
    const { course_id } = req.params;
    const courseRef = db.collection("courses").doc(course_id);
    try {
        const courseDoc = await courseRef.get();
        if (!courseDoc.exists) {
            return res.status(404).json({ success: false, message: '找不到課程' });
        }
        await courseRef.delete();
        return res.status(200).json({ success: true, message: "課程已成功刪除" });
    } catch (error) {
        console.error("刪除課程時出錯:", error);
        return res.status(500).json({ success: false, message: `刪除時發生錯誤: ${error.message}` });
    }
});


// 輔助函式：設定管理員
exports.addAdminRole = functions.region("asia-east1").https.onCall(async (data, context) => {
    if (context.auth.token.admin !== true) {
        return { error: '只有管理員能執行此操作' };
    }
    const email = data.email;
    try {
        const user = await auth.getUserByEmail(email);
        await auth.setCustomUserClaims(user.uid, { admin: true });
        return { message: `成功！ ${email} 現在是管理員。` };
    } catch (error) {
        return { error: error.message };
    }
});

// 將 Express app 封裝成一個 Cloud Function
exports.api = functions.region("asia-east1").https.onRequest(app);

