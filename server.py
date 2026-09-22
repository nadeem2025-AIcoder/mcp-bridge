import os
import re
import html
import requests
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from telegram import Bot
import uvicorn

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

def ensure_cover_image():
    """التحقق من وجود صورة الغلاف محلياً أو تنزيلها تلقائياً من GitHub."""
    if not os.path.exists(IMAGE_PATH):
        try:
            raw_url = "https://raw.githubusercontent.com/nadeem2025-AIcoder/mcp-bridge/main/post_cover.png"
            res = requests.get(raw_url, timeout=15)
            if res.status_code == 200:
                with open(IMAGE_PATH, "wb") as f:
                    f.write(res.content)
        except Exception:
            pass

def upload_linkedin_image(author_urn: str) -> str:
    """رفع صورة الغلاف التعبيرية إلى خوادم لينكد إن."""
    ensure_cover_image()
    if not os.path.exists(IMAGE_PATH) or not LINKEDIN_ACCESS_TOKEN:
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
            
            with open(IMAGE_PATH, "rb") as img_file:
                put_res = requests.put(
                    upload_url,
                    headers={"Content-Type": "image/png"},
                    data=img_file,
                    timeout=30
                )
                if put_res.status_code in (200, 201):
                    return image_urn
    except Exception:
        pass
    return ""

async def post_to_telegram(message_text: str) -> str:
    """نشر نصي فقط على تليجرام دون صورة."""
    if not TELEGRAM_BOT_TOKEN or not CHANNEL_ID:
        return "خطأ: بيانات تليجرام غير مكتملة."
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        msg = await bot.send_message(chat_id=CHANNEL_ID, text=message_text)
        return f"تم النشر في قناة تليجرام بنجاح! معرف الرسالة: {msg.message_id}"
    except Exception as e:
        return f"خطأ تليجرام: {str(e)}"

def publish_to_linkedin(exact_text: str) -> str:
    """نشر المنشور على لينكد إن مع إرفاق صورة الغلاف حصراً."""
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
    image_urn = upload_linkedin_image(author_urn)

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
        res = requests.post(post_url, headers=post_headers, json=payload, timeout=20)
        if res.status_code == 201:
            status_msg = "تم النشر بنجاح على لينكد إن!"
            if image_urn:
                status_msg += " (مع صورة الغلاف)"
            return status_msg
        return f"فشل لينكد إن ({res.status_code}): {res.text[:200]}"
    except Exception as e:
        return f"خطأ اتصال لينكد إن: {str(e)}"

def get_latest_telegram_post() -> str:
    """قراءة آخر منشور من واجهة القناة العامة على تليجرام."""
    try:
        url = "https://t.me/s/GuadaraQms"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if res.status_code == 200:
            matches = re.findall(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', res.text, re.DOTALL)
            if matches:
                last_msg = matches[-1]
                clean = re.sub(r'<br\s*/?>', '\n', last_msg)
                clean = re.sub(r'<[^>]+>', '', clean)
                return html.unescape(clean).strip()
    except Exception as e:
        return f"تعذر جلب المنشور: {str(e)}"
    return "لا توجد منشورات متاحة حالياً."

@app.get("/")
@app.get("/health")
def health():
    return {"status": "ready", "bridge": "active"}

class PublishPayload(BaseModel):
    text: str

@app.post("/publish")
async def publish(payload: PublishPayload):
    tg_res = await post_to_telegram(payload.text)
    li_res = publish_to_linkedin(payload.text)
    return {"telegram": tg_res, "linkedin": li_res}

@app.post("/mcp")
async def mcp_endpoint(request: Request):
    """المسار المعتمد لبروتوكول MCP الذي يتصل به سبارك."""
    try:
        data = await request.json()
    except Exception:
        return Response(status_code=400)
    
    method = data.get("method")
    req_id = data.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "GuadaraBridge", "version": "1.0.0"}
            }
        }
    elif method == "notifications/initialized":
        return Response(status_code=200)
    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {
                        "name": "get_latest_telegram_post",
                        "description": "يجلب النص الكامل والأصلي لآخر منشور من قناة تليجرام.",
                        "inputSchema": {"type": "object", "properties": {}}
                    },
                    {
                        "name": "post_to_telegram",
                        "description": "ينشر نصاً أو ملخصاً مباشرة إلى قناة تليجرام المحددة (@GuadaraQms).",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "message_text": {
                                    "type": "string",
                                    "description": "النص أو التلخيص المراد نشره في قناة تليجرام."
                                }
                            },
                            "required": ["message_text"]
                        }
                    },
                    {
                        "name": "publish_to_linkedin",
                        "description": "ينشر النص الأصلي حرفياً إلى لينكد إن دون أي تغيير.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "exact_text": {
                                    "type": "string",
                                    "description": "النص الكامل للمنشور المراد نشره على لينكد إن."
                                }
                            },
                            "required": ["exact_text"]
                        }
                    }
                ]
            }
        }
    elif method == "tools/call":
        params = data.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})
        result_text = ""
        
        if tool_name == "post_to_telegram":
            msg = args.get("message_text", "")
            result_text = await post_to_telegram(msg)
        elif tool_name == "publish_to_linkedin":
            msg = args.get("exact_text", "")
            result_text = publish_to_linkedin(msg)
        elif tool_name == "get_latest_telegram_post":
            result_text = get_latest_telegram_post()
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}
            }
            
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": result_text}]
            }
        }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not supported: {method}"}
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
