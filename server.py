import os
import random
import io
import requests
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from telegram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
from pypdf import PdfReader

# المتغيرات البيئية
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHANNEL_ID = os.getenv("CHANNEL_ID", "")
LINKEDIN_ACCESS_TOKEN = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
LINKEDIN_USER_SUB = os.getenv("LINKEDIN_USER_SUB", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

TIMEZONE = pytz.timezone("Asia/Aden")
scheduler = AsyncIOScheduler(timezone=TIMEZONE)

# قائمة بمعرفات وعناوين كتب مجلد Guadara_Books على Google Drive
DRIVE_BOOKS = [
    {"title": "المواصفة القياسية ISO 14001:2015 لنظم الإدارة البيئية", "id": "1QHWA2ixyV7q_YI6faCQK0-MB7ZKP52c1"},
    {"title": "مواصفة ISO 19011 الإرشادية لإدارة المراجعة والتدقيق", "id": "1VNtdEwfKqv4XRTt0RLGuA-smvVmK8fBx"},
    {"title": "مواصفة ISO 45001:2018 لإدارة السلامة والصحة المهنية", "id": "1LCD41Z14j2EB5J3vZLtabwtok9MlsMiI"},
    {"title": "المواصفة القياسية ISO/IEC 27001 لأنظمة إدارة أمن المعلومات", "id": "1dpZpHq7X3ZgzbIXC1KejeKoiRRCL79p3"},
    {"title": "مواصفة الأيزو 22002-1 لسلامة وتصنيع الغذاء", "id": "1leLZmJegbrq8xU6tOlvljMPKQQmrWz08"},
    {"title": "نظم إدارة سلامة الغذاء ISO 22000", "id": "1onjbTW0Seg8NnZmdWRz-0YqWPv1BtOmh"},
    {"title": "المعيار العالمي لسلامة الغذاء والتعبئة BRCGS Packaging Issue 7", "id": "1YxlZFN--SPGII2VMNoQZUcHMGUee0yjZ"},
    {"title": "دليل قياس الاستدامة المؤسسية", "id": "1tcqep-tqpnyHwfi6CpWUcC7WzBzWAfNS"},
    {"title": "دليل نقاط التحقق للوقاية من الإجهاد في بيئة العمل", "id": "14eDW5YNdTp93WHC66HJVzDSfAs7cLfWL"}
]

# --- دالة استخراج نص عشوائي من كتاب في Google Drive ---

def get_excerpt_from_drive_book():
    """تنزيل صفحات محددة من أحد كتب درايف واستخراج النص مباشرة."""
    book = random.choice(DRIVE_BOOKS)
    download_url = f"https://drive.google.com/uc?export=download&id={book['id']}"
    
    try:
        response = requests.get(download_url, timeout=30)
        if response.status_code == 200:
            pdf_file = io.BytesIO(response.content)
            reader = PdfReader(pdf_file)
            total_pages = len(reader.pages)
            
            if total_pages > 5:
                # اختيار مقطع من 3 إلى 5 صفحات متتالية
                start_page = random.randint(3, max(3, total_pages - 5))
                excerpt = ""
                for p in range(start_page, min(start_page + 4, total_pages)):
                    page_text = reader.pages[p].extract_text() or ""
                    excerpt += page_text + "\n"
                
                if len(excerpt.strip()) > 150:
                    return book["title"], excerpt[:3000]
    except Exception as e:
        print(f"تعذر استخراج النص من الكتاب: {e}")

    return book["title"], ""

# --- دالة التوليد عبر Gemini بناءً على الكتاب ---

def generate_quality_summary() -> str:
    """صياغة ملخص احترافي بالاعتماد الحصري على كتاب من Google Drive."""
    api_key = GEMINI_API_KEY.strip() if GEMINI_API_KEY else ""
    if not api_key:
        return "خطأ: متغير GEMINI_API_KEY غير متوفر في بيئة الخادم."

    book_title, excerpt = get_excerpt_from_drive_book()

    if excerpt:
        prompt = (
            f"أنت خبير استشاري في نظم إدارة الجودة والمواصفات الدولية.\n"
            f"قم بصياغة منشور مهني تطبيقي دقيق (بين 150 و250 كلمة) مستخلص حصراً من المرجع التالي:\n"
            f"الكتاب/المعيار: {book_title}\n\n"
            f"النص المقتبس من المرجع:\n\"\"\"\n{excerpt}\n\"\"\"\n\n"
            f"شروط الصياغة:\n"
            f"1. ابدأ بعنوان مهني جذاب يشير إلى المرجع أو المفهوم.\n"
            f"2. لخص الفكرة الإدارية أو المتطلب في نقاط عملية واضحة قابلة للتطبيق في المنظمات.\n"
            f"3. اذكر في السطر الأخير اسم المرجع: (المصدر: {book_title}).\n"
            f"4. أضف الوسوم المهنية المناسبة (#إدارة_الجودة #المواصفات_الدولية وغيرها).\n"
            f"5. لا تضف أي مقدمات أو عبارات ترحيبية، اجعل النص جاهزاً للنشر المباشر."
        )
    else:
        prompt = (
            f"أنت خبير استشاري في نظم إدارة الجودة والمواصفات القياسية.\n"
            f"اكتب منشوراً مهنياً عملياً ومحكماً (بين 150 و250 كلمة) يشرح أحد البنود أو المبادئ الجوهرية في:\n"
            f"({book_title}).\n"
            f"اجعل النص في نقاط عملية تطبيقية، واختم بذكر اسم المرجع والوسوم المهنية المناسبة دون مقدمات جانبية."
        )

    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    headers = {"Content-Type": "application/json"}

    candidate_urls = [
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={api_key}",
        f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
        f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={api_key}"
    ]

    last_error = ""
    for url in candidate_urls:
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=30)
            if res.status_code == 200:
                data = res.json()
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
            else:
                last_error = f"كود {res.status_code}: {res.text[:200]}"
        except Exception as e:
            last_error = str(e)

    return f"خطأ من Gemini API: {last_error}"

# --- دوال النشر إلى تليجرام ولينكد إن ---

async def run_post_to_telegram(message_text: str) -> str:
    """نشر النص إلى قناة تيليجرام."""
    if not TELEGRAM_BOT_TOKEN or not CHANNEL_ID:
        return "خطأ: بيانات تليجرام غير مكتملة."
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        msg = await bot.send_message(chat_id=CHANNEL_ID, text=message_text)
        return f"تم النشر في تليجرام بنجاح! ID: {msg.message_id}"
    except Exception as e:
        return f"خطأ تليجرام: {str(e)}"

def upload_linkedin_image(author_urn: str, image_path: str = "post_cover.png") -> str:
    """رفع الصورة التعبيرية إلى لينكد إن."""
    if not os.path.exists(image_path) or not LINKEDIN_ACCESS_TOKEN:
        return ""

    headers = {
        "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
        "LinkedIn-Version": "202607",
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json"
    }

    init_url = "https://api.linkedin.com/rest/images?action=initializeUpload"
    init_payload = {"initializeUploadRequest": {"owner": author_urn}}

    try:
        init_res = requests.post(init_url, headers=headers, json=init_payload)
        if init_res.status_code != 200:
            return ""

        init_data = init_res.json().get("value", {})
        upload_url = init_data.get("uploadUrl")
        image_urn = init_data.get("image")

        with open(image_path, "rb") as img_file:
            upload_headers = {
                "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
                "Content-Type": "image/png"
            }
            put_res = requests.put(upload_url, headers=upload_headers, data=img_file)
            if put_res.status_code in (200, 201):
                return image_urn
    except Exception:
        pass

    return ""

def run_publish_to_linkedin(exact_text: str) -> str:
    """نشر الملخص كاملاً مع الصورة إلى لينكد إن."""
    if not LINKEDIN_ACCESS_TOKEN:
        return "خطأ: رمز وصول لينكد إن غير متوفر."

    auth_headers = {"Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}"}
    sub = None

    try:
        userinfo_resp = requests.get("https://api.linkedin.com/v2/userinfo", headers=auth_headers)
        if userinfo_resp.status_code == 200:
            sub = userinfo_resp.json().get("sub")
    except Exception:
        pass

    if not sub:
        try:
            me_resp = requests.get("https://api.linkedin.com/v2/me", headers=auth_headers)
            if me_resp.status_code == 200:
                sub = me_resp.json().get("id")
        except Exception:
            pass

    if not sub:
        sub = LINKEDIN_USER_SUB

    if not sub:
        return "خطأ: تعذر الحصول على معرف المستخدم لـ LinkedIn."

    author_urn = f"urn:li:person:{sub}"
    image_urn = upload_linkedin_image(author_urn, "post_cover.png")

    post_url = "https://api.linkedin.com/rest/posts"
    post_headers = {
        "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
        "LinkedIn-Version": "202607",
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json"
    }

    payload = {
        "author": author_urn,
        "commentary": exact_text,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": []
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False
    }

    if image_urn:
        payload["content"] = {"media": {"id": image_urn}}

    try:
        response = requests.post(post_url, headers=post_headers, json=payload)
        if response.status_code == 201:
            return "تم النشر بنجاح على لينكد إن!"
        else:
            return f"فشل نشر لينكد إن ({response.status_code}): {response.text}"
    except Exception as e:
        return f"خطأ اتصال بلينكد إن: {str(e)}"

# --- دورة النشر التلقائية والجدولة ---

async def scheduled_publishing_cycle():
    """دورة النشر الكاملة: قراءة الكتاب -> تلخيص -> نشر تليجرام ولينكد إن."""
    print("بدء دورة التلخيص والنشر من كتب Google Drive...")
    summary_text = generate_quality_summary()

    tg_result = await run_post_to_telegram(summary_text)
    li_result = run_publish_to_linkedin(summary_text)

    print(f"تيليجرام: {tg_result}")
    print(f"لينكد إن: {li_result}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # تشغيل المهمة يومياً 3 مرات: 9:00 ص، 2:00 ظ، 8:00 م بتوقيت اليمن
    scheduler.add_job(
        scheduled_publishing_cycle,
        CronTrigger(hour="9,14,20", minute="0", timezone=TIMEZONE),
        id="quality_summary_job",
        replace_existing=True
    )
    scheduler.start()
    print("تم تفعيل المؤقت المجدول الداخلي بنجاح (Asia/Aden).")
    yield
    scheduler.shutdown()

app = FastAPI(title="Guadara-Autonomous-Engine", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
@app.get("/health")
async def health_check():
    jobs = [str(job.next_run_time) for job in scheduler.get_jobs()]
    return {
        "status": "running",
        "scheduler_active": scheduler.running,
        "next_runs": jobs
    }

@app.post("/trigger-now")
@app.get("/trigger-now")
async def trigger_now():
    """رابط للتجربة الفورية في أي وقت والتأكد من النشر."""
    await scheduled_publishing_cycle()
    return {"status": "triggered_successfully"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
