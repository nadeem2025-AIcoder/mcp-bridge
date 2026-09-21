import os
import requests
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from telegram import Bot

# المسار المطلق للصورة في نفس مجلد المشروع على Railway
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_PATH = os.path.join(BASE_DIR, "post_cover.png")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHANNEL_ID = os.getenv("CHANNEL_ID", "").strip()
LINKEDIN_ACCESS_TOKEN = os.getenv("LINKEDIN_ACCESS_TOKEN", "").strip()
LINKEDIN_USER_SUB = os.getenv("LINKEDIN_USER_SUB", "").strip()

app = FastAPI(title="Spark-Publishing-Bridge")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PublishPayload(BaseModel):
    text: str

async def post_to_telegram(text: str) -> str:
    """نشر المنشور إلى تليجرام كنص فقط دون صورة."""
    if not TELEGRAM_BOT_TOKEN or not CHANNEL_ID:
        return "خطأ: بيانات تليجرام غير مكتملة."
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        msg = await bot.send_message(chat_id=CHANNEL_ID, text=text)
        return f"تم النشر في تليجرام بنجاح (ID: {msg.message_id})"
    except Exception as e:
        return f"خطأ تليجرام: {str(e)}"

def upload_linkedin_image(author_urn: str, image_path: str = IMAGE_PATH) -> str:
    """رفع صورة الغلاف التعبيرية إلى خوادم لينكد إن."""
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
        init_res = requests.post(init_url, headers=headers, json=init_payload, timeout=15)
        if init_res.status_code == 200:
            init_data = init_res.json().get("value", {})
            upload_url = init_data.get("uploadUrl")
            image_urn = init_data.get("image")
            
            with open(image_path, "rb") as img_file:
                # ملاحظة هامة: لا نضع هيدر Authorization في طلب PUT المباشر للرابط المؤقت
                put_res = requests.put(
                    upload_url,
                    headers={"Content-Type": "image/png"},
                    data=img_file,
                    timeout=25
                )
                if put_res.status_code in (200, 201):
                    return image_urn
    except Exception:
        pass
    return ""

def post_to_linkedin(text: str, image_path: str = IMAGE_PATH) -> str:
    """نشر المنشور على حساب لينكد إن مع صورة الغلاف حصراً."""
    if not LINKEDIN_ACCESS_TOKEN:
        return "خطأ: رمز وصول لينكد إن غير متوفر."
    auth_headers = {"Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}"}
    sub = None
    
    try:
        u_resp = requests.get("https://api.linkedin.com/v2/userinfo", headers=auth_headers, timeout=10)
        if u_resp.status_code == 200:
            sub = u_resp.json().get("sub")
    except Exception:
        pass
        
    if not sub:
        try:
            me_resp = requests.get("https://api.linkedin.com/v2/me", headers=auth_headers, timeout=10)
            if me_resp.status_code == 200:
                sub = me_resp.json().get("id")
        except Exception:
            pass

    if not sub:
        sub = LINKEDIN_USER_SUB
        
    if not sub:
        return "خطأ: تعذر تحديد معرف المستخدم لـ LinkedIn."

    author_urn = f"urn:li:person:{sub}"
    image_urn = upload_linkedin_image(author_urn, image_path)

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
        res = requests.post(post_url, headers=post_headers, json=payload, timeout=20)
        if res.status_code == 201:
            status_msg = "تم النشر بنجاح على لينكد إن!"
            if image_urn:
                status_msg += " (مع صورة الغلاف)"
            return status_msg
        return f"فشل لينكد إن ({res.status_code}): {res.text[:200]}"
    except Exception as e:
        return f"خطأ اتصال لينكد إن: {str(e)}"

@app.get("/")
@app.get("/health")
def health():
    return {"status": "ready", "bridge": "active"}

@app.post("/publish")
async def publish(payload: PublishPayload):
    """نشر نصي فقط في تليجرام، ونشر مع صورة الغلاف حصراً في لينكد إن."""
    tg_res = await post_to_telegram(payload.text)
    li_res = post_to_linkedin(payload.text, IMAGE_PATH)
    return {
        "telegram": tg_res,
        "linkedin": li_res
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
