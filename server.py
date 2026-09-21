import os
import requests
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from telegram import Bot

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHANNEL_ID = os.getenv("CHANNEL_ID", "").strip()
LINKEDIN_ACCESS_TOKEN = os.getenv("LINKEDIN_ACCESS_TOKEN", "").strip()
LINKEDIN_USER_SUB = os.getenv("LINKEDIN_USER_SUB", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

app = FastAPI(title="Guadara-MCP-Bridge")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PublishPayload(BaseModel):
    text: str

def generate_test_summary() -> str:
    """اختبار استدعاء Gemini باستخدام المهلة الموسعة لتفادي انقطاع الاتصال."""
    if not GEMINI_API_KEY:
        return "خطأ: متغير GEMINI_API_KEY غير متوفر في بيئة الخادم."

    prompt = "اكتب نصيحة إدارية سريعة وموجزة في إدارة الجودة (بين 50 و100 كلمة) مع وسم #إدارة_الجودة."
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        # رفع مهلة الانتظار إلى 60 ثانية لضمان استلام التوليد كاملاً
        res = requests.post(url, headers=headers, json=payload, timeout=60)
        if res.status_code == 200:
            data = res.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        return f"كود الخطأ: {res.status_code} - التفاصيل: {res.text[:200]}"
    except Exception as e:
        return f"خطأ اتصال: {str(e)}"

async def post_to_telegram(text: str) -> str:
    if not TELEGRAM_BOT_TOKEN or not CHANNEL_ID:
        return "خطأ: بيانات تليجرام غير مكتملة."
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        msg = await bot.send_message(chat_id=CHANNEL_ID, text=text)
        return f"تم النشر في تليجرام بنجاح (ID: {msg.message_id})"
    except Exception as e:
        return f"خطأ تليجرام: {str(e)}"

def upload_linkedin_image(author_urn: str, image_path: str = "post_cover.png") -> str:
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
        init_res = requests.post(init_url, headers=headers, json=init_payload, timeout=20)
        if init_res.status_code == 200:
            init_data = init_res.json().get("value", {})
            upload_url = init_data.get("uploadUrl")
            image_urn = init_data.get("image")
            with open(image_path, "rb") as img_file:
                put_res = requests.put(
                    upload_url,
                    headers={"Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}", "Content-Type": "image/png"},
                    data=img_file,
                    timeout=30
                )
                if put_res.status_code in (200, 201):
                    return image_urn
    except Exception:
        pass
    return ""

def post_to_linkedin(text: str) -> str:
    if not LINKEDIN_ACCESS_TOKEN:
        return "خطأ: رمز وصول لينكد إن غير متوفر."
    auth_headers = {"Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}"}
    sub = None
    try:
        u_resp = requests.get("https://api.linkedin.com/v2/userinfo", headers=auth_headers, timeout=15)
        if u_resp.status_code == 200:
            sub = u_resp.json().get("sub")
    except Exception:
        pass
    if not sub:
        sub = LINKEDIN_USER_SUB
    if not sub:
        return "خطأ: تعذر تحديد حساب لينكد إن."

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
        "commentary": text,
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
        res = requests.post(post_url, headers=post_headers, json=payload, timeout=25)
        if res.status_code == 201:
            return "تم النشر بنجاح على لينكد إن!"
        return f"فشل لينكد إن ({res.status_code}): {res.text[:150]}"
    except Exception as e:
        return f"خطأ اتصال لينكد إن: {str(e)}"

@app.get("/")
@app.get("/health")
def health():
    return {"status": "Bridge is healthy and ready to publish"}

@app.post("/publish")
async def publish(payload: PublishPayload):
    """استقبال النص المجهز ونشره مباشرة على القناتين مع الغلاف."""
    tg_res = await post_to_telegram(payload.text)
    li_res = post_to_linkedin(payload.text)
    return {
        "telegram": tg_res,
        "linkedin": li_res
    }

@app.get("/trigger-now")
@app.post("/trigger-now")
async def trigger_now():
    """اختبار فوري: يولد النص من Gemini ثم ينشره فوراً على تيليجرام ولينكد إن."""
    generated_text = generate_test_summary()

    if generated_text.startswith("كود الخطأ") or generated_text.startswith("خطأ"):
        return {
            "status": "gemini_error",
            "details": generated_text
        }

    tg_res = await post_to_telegram(generated_text)
    li_res = post_to_linkedin(generated_text)

    return {
        "status": "success",
        "generated_text": generated_text,
        "telegram": tg_res,
        "linkedin": li_res
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
