import os
import requests
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from telegram import Bot
import uvicorn

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHANNEL_ID = os.getenv("CHANNEL_ID", "")
LINKEDIN_ACCESS_TOKEN = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
LINKEDIN_USER_SUB = os.getenv("LINKEDIN_USER_SUB", "")

app = FastAPI(title="Guadara-Telegram-LinkedIn-MCP")

# تمكين CORS بالكامل لجميع خوادم وواجهات Google
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def run_get_latest_telegram_post() -> str:
    if not TELEGRAM_BOT_TOKEN or not CHANNEL_ID:
        return "خطأ: بيانات تليجرام غير مكتملة."
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

def run_publish_to_linkedin(exact_text: str) -> str:
    if not LINKEDIN_ACCESS_TOKEN or not LINKEDIN_USER_SUB:
        return "خطأ: بيانات لينكد إن غير مكتملة."
    url = "https://api.linkedin.com/rest/posts"
    headers = {
        "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
        "LinkedIn-Version": "202401",
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json"
    }
    payload = {
        "author": f"urn:li:person:{LINKEDIN_USER_SUB}",
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
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 201:
            return "تم النشر بنجاح على لينكد إن!"
        else:
            return f"فشل النشر ({response.status_code}): {response.text}"
    except Exception as e:
        return f"خطأ في الاتصال بـ LinkedIn API: {str(e)}"

# قائمة الأدوات المعرفة وفق معيار بروتوكول MCP
TOOLS_DEFINITION = [
    {
        "name": "get_latest_telegram_post",
        "description": "يجلب النص الكامل والأصلي لآخر منشور من قناة تليجرام دون أي تعديل.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
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
    """استجابة فحص الصحة والتواجد"""
    return {"status": "ok", "service": "Telegram-LinkedIn MCP Server"}

@app.post("/")
@app.post("/mcp")
async def handle_mcp_rpc(request: Request):
    """معالج طلبات بروتوكول MCP JSON-RPC المتوافق مع Gemini Spark"""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None})

    req_id = body.get("id")
    method = body.get("method")

    # 1. مرحلة المصافحة المبدئية للتعرف على الخادم
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
                    "version": "1.0.0"
                }
            }
        }

    # 2. إرجاع قائمة الأدوات لـ Gemini Spark
    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": TOOLS_DEFINITION
            }
        }

    # 3. تنفيذ الأداة عند استدعاء الوكيل لها
    elif method == "tools/call":
        params = body.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})

        if tool_name == "get_latest_telegram_post":
            result_text = await run_get_latest_telegram_post()
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

    # استجابات الإشعارات العادية
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
