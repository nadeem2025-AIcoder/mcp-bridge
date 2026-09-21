import os
import requests
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from telegram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

# المتغيرات البيئية
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHANNEL_ID = os.getenv("CHANNEL_ID", "")
LINKEDIN_ACCESS_TOKEN = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
LINKEDIN_USER_SUB = os.getenv("LINKEDIN_USER_SUB", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

TIMEZONE = pytz.timezone("Asia/Aden")
scheduler = AsyncIOScheduler(timezone=TIMEZONE)

# --- دوال النشر ---

async def run_post_to_telegram(message_text: str) -> str:
    """نشر النص مباشرة إلى قناة تليجرام."""
    if not TELEGRAM_BOT_TOKEN or not CHANNEL_ID:
        return "خطأ: بيانات تليجرام غير مكتملة."
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        msg = await bot.send_message(chat_id=CHANNEL_ID, text=message_text)
        return f"تم النشر في تليجرام بنجاح! ID: {msg.message_id}"
    except Exception as e:
        return f"خطأ تليجرام: {str(e)}"

def upload_linkedin_image(author_urn: str, image_path: str = "post_cover.png") -> str:
    """رفع الصورة إلى لينكد إن وإرجاع المعرف الدائم (Image URN)."""
    if not os.path.exists(image_path) or not LINKEDIN_ACCESS_TOKEN:
        return ""

    headers = {
        "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
        "LinkedIn-Version": "202607",
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json"
    }

    init_url = "https://api.linkedin.com/rest/images?action=initializeUpload"
    init_payload = {
        "initializeUploadRequest": {
            "owner": author_urn
        }
    }

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
    """نشر الملخص كاملاً إلى لينكد إن مع الصورة التعبيرية الثابتة."""
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
        payload["content"] = {
            "media": {
                "id": image_urn
            }
        }

    try:
        response = requests.post(post_url, headers=post_headers, json=payload)
        if response.status_code == 201:
            return "تم النشر بنجاح على لينكد إن!"
        else:
            return f"فشل نشر لينكد إن ({response.status_code}): {response.text}"
    except Exception as e:
        return f"خطأ اتصال بلينكد إن: {str(e)}"

# --- دالة توليد الملخص عبر Gemini API المباشر ---

def generate_quality_summary() -> str:
    """صياغة ملخص احترافي في إدارة الجودة عبر Gemini API مباشرة."""
    if not GEMINI_API_KEY:
        return "إدارة الجودة الشاملة هي نهج إداري يهدف لتحقيق النجاح طويل الأمد من خلال إرضاء العملاء وتحسين الأداء المؤسسي المستمر."

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = (
        "بصفتك خبيراً استشارياً في نظم إدارة الجودة والتميز المؤسسي، "
        "اكتب منشوراً مهنياً مكتملاً ومحكماً (من 150 إلى 250 كلمة) حول أحد المفاهيم أو الأدوات المتقدمة في الجودة "
        "(مثل: Six Sigma, Kaizen, Lean, ISO Standards, TQM). "
        "ابدأ بعنوان جذاب، يليه صلب الموضوع في نقاط مركزة قابلة للتطبيق العملي، واختم بوسوم مناسبة. "
        "اجعل النص جاهزاً للنشر المباشر دون أي مقدمات أو تعليقات جانبية."
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }

    try:
        res = requests.post(url, json=payload, timeout=30)
        if res.status_code == 200:
            data = res.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"خطأ في توليد المحتوى: {e}")

    return "إدارة الجودة والتحسين المستمر هما الركيزة الأساسية لتميز واستدامة المنظمات الحديثة."

# --- دالة دورة النشر المجدولة التلقائية ---

async def scheduled_publishing_cycle():
    """توليد ونشر المحتوى تلقائياً في الخلفية دون أي تدخل يدوي."""
    print("بدء دورة النشر التلقائي المستقلة...")
    summary_text = generate_quality_summary()

    tg_result = await run_post_to_telegram(summary_text)
    li_result = run_publish_to_linkedin(summary_text)

    print(f"تيليجرام: {tg_result}")
    print(f"لينكد إن: {li_result}")

# --- دورة حياة التطبيق والجدولة ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    # تشغيل المهمة يومياً عند 9:00 صباحاً، 2:00 ظهراً، و8:00 مساءً بتوقيت اليمن
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
