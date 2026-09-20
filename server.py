import os
import requests
import uvicorn
from telegram import Bot
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHANNEL_ID = os.getenv("CHANNEL_ID", "")
LINKEDIN_ACCESS_TOKEN = os.getenv("LINKEDIN_ACCESS_TOKEN", "")
LINKEDIN_USER_SUB = os.getenv("LINKEDIN_USER_SUB", "")

mcp = FastMCP(
    "Telegram-LinkedIn-Mirror-Bridge",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False)
)

@mcp.tool()
async def get_latest_telegram_post() -> str:
    """يجلب النص الكامل والأصلي لآخر منشور من قناة تليجرام دون أي تعديل."""
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

@mcp.tool()
def publish_to_linkedin(exact_text: str) -> str:
    """ينشر النص الأصلي حرفياً إلى لينكد إن دون تغيير."""
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app = mcp.sse_app()
    
    # دعم ترويسات CORS الكاملة لكي يقبل متصفح Spark الاتصال
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    uvicorn.run(app, host="0.0.0.0", port=port)
