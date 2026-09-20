import os
import requests
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from telegram import Bot

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHANNEL_ID = os.getenv("CHANNEL_ID", "")
LINKEDIN_ACCESS_TOKEN = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
LINKEDIN_USER_SUB = os.getenv("LINKEDIN_USER_SUB", "")

app = FastAPI(title="Guadara-Telegram-LinkedIn-MCP")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def run_get_latest_telegram_post() -> str:
    """جلب آخر منشور نصي من قناة تليجرام دون أي تعديل."""
    if not TELEGRAM_BOT_TOKEN or not CHANNEL_ID:
        return "خطأ: بيانات تليجرام غير مكتملة في متغيرات البيئة."
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        updates = await bot.get_updates(limit=10)
        for u in reversed(updates):
            if u.channel_post and u.channel_post.chat.username:
                if f"@{u.channel_post.chat.username}".lower() == CHANNEL_ID.lower():
                    text = u.channel_post.text or u.channel_post.caption or ""
                    if text:
                        return text
        return "لا توجد منشورات نصية حديثة في القناة."
    except Exception as e:
        return f"حدث خطأ أثناء الاتصال بتليجرام: {str(e)}"

async def run_post_to_telegram(message_text: str) -> str:
    """نشر نص أو ملخص مباشرة إلى قناة تليجرام عبر البوت."""
    if not TELEGRAM_BOT_TOKEN or not CHANNEL_ID:
        return "خطأ: بيانات تليجرام غير مكتملة في متغيرات البيئة."
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        msg = await bot.send_message(chat_id=CHANNEL_ID, text=message_text)
        return f"تم النشر في قناة تليجرام بنجاح! معرف الرسالة: {msg.message_id}"
    except Exception as e:
        return f"حدث خطأ أثناء النشر في تليجرام: {str(e)}"

def run_publish_to_linkedin(exact_text: str) -> str:
    """نشر النص حرفياً إلى لينكد إن."""
    if not LINKEDIN_ACCESS_TOKEN:
        return "خطأ: رمز الوصول للينكد إن غير متوفر."
    
    auth_headers = {
        "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}"
    }

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
        return "خطأ: تعذر تحديد معرف المستخدم (Author ID) تلقائياً أو عبر المتغيرات."

    author_urn = f"urn:li:person:{sub}"

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

    try:
        response = requests.post(post_url, headers=post_headers, json=payload)
        if response.status_code == 201:
            return "تم النشر بنجاح على لينكد إن!"
        else:
            return f"فشل النشر ({response.status_code}): {response.text}"
    except Exception as e:
        return f"خطأ في الاتصال بـ LinkedIn API: {str(e)}"

# تعريف الأدوات لبروتوكول MCP
TOOLS_DEFINITION = [
    {
        "name": "get_latest_telegram_post",
        "description": "يجلب النص الكامل والأصلي لآخر منشور من قناة تليجرام.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
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

@app.get("/")
@app.get("/mcp")
async def health_check():
    return {"status": "ok", "service": "Telegram-LinkedIn MCP Server"}

@app.post("/")
@app.post("/mcp")
async def handle_mcp_rpc(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None})

    req_id = body.get("id")
    method = body.get("method")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": False}
                },
                "serverInfo": {
                    "name": "GuadaraBridge",
                    "version": "1.1.0"
                }
            }
        }

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": TOOLS_DEFINITION
            }
        }

    elif method == "tools/call":
        params = body.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})

        if tool_name == "get_latest_telegram_post":
            result_text = await run_get_latest_telegram_post()
        elif tool_name == "post_to_telegram":
            msg_text = args.get("message_text", "")
            result_text = await run_post_to_telegram(msg_text)
        elif tool_name == "publish_to_linkedin":
            post_text = args.get("exact_text", "")
            result_text = run_publish_to_linkedin(post_text)
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Tool '{tool_name}' not found"}
            }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [
                    {"type": "text", "text": result_text}
                ]
            }
        }

    elif method == "notifications/initialized":
        return JSONResponse(status_code=200, content={})

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": "Method not supported"}
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
