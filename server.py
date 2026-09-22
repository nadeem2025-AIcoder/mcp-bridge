import os
import re
import html
import json
import random
import datetime
import requests
import uvicorn
import pytz
from pypdf import PdfReader
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from telegram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_PATH = os.path.join(BASE_DIR, "post_cover.png")
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")
# تحديد مسار مجلد الكتب بصورة مباشرة وصحيحة
BOOKS_DIR = os.path.join(BASE_DIR, "books")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHANNEL_ID = os.getenv("CHANNEL_ID", "").strip()
LINKEDIN_ACCESS_TOKEN = os.getenv("LINKEDIN_ACCESS_TOKEN", "").strip()
LINKEDIN_USER_SUB = os.getenv("LINKEDIN_USER_SUB", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

app = FastAPI(title="Guadara-Autonomous-Publisher")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

scheduler = AsyncIOScheduler()

def find_all_pdf_files() -> list:
    """البحث المباشر والشامل عن كافة ملفات PDF داخل مجلد books ومجلدات المشروع."""
    matched = []
    seen = set()
    
    # قائمة المسارات المحتملة للبحث لضمان إيجاد الكتب بكل الظروف
    search_roots = [
        BOOKS_DIR,
        BASE_DIR,
        os.path.join(os.getcwd(), "books")
    ]
    
    for s_root in search_roots:
        if os.path.exists(s_root):
            for root, dirs, files in os.walk(s_root):
                if any(x in root for x in ("site-packages", ".venv", ".git")):
                    continue
                for file in files:
                    if file.lower().endswith(".pdf"):
                        full_path = os.path.join(root, file)
                        if full_path not in seen:
                            seen.add(full_path)
                            matched.append(full_path)
    return matched

def load_history() -> list:
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_history(entry: dict):
    history = load_history()
    history.append(entry)
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def ensure_cover_image():
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
    if not TELEGRAM_BOT_TOKEN or not CHANNEL_ID:
        return "خطأ: بيانات تليجرام غير مكتملة."
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        msg = await bot.send_message(chat_id=CHANNEL_ID, text=message_text)
        return f"تم النشر في قناة تليجرام بنجاح! معرف الرسالة: {msg.message_id}"
    except Exception as e:
        return f"خطأ تليجرام: {str(e)}"

def publish_to_linkedin(exact_text: str) -> str:
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

    safe_text = re.sub(r'([(){}\[\]<>|~_*])', r'\\\1', exact_text)

    post_url = "https://api.linkedin.com/rest/posts"
    post_headers = {
        "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
        "LinkedIn-Version": "202607",
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json"
    }
    payload = {
        "author": author_urn,
        "commentary": safe_text,
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
            status_msg = "تم النشر بنجاح على لينكد إن!"
            if image_urn:
                status_msg += " (مع صورة الغلاف)"
            return status_msg
        return f"فشل لينكد إن ({res.status_code}): {res.text[:200]}"
    except Exception as e:
        return f"خطأ اتصال لينكد إن: {str(e)}"

def extract_content_from_random_book() -> tuple:
    """استخراج نص حقيقي من الكتب المكتشفة في المشروع."""
    pdf_files = find_all_pdf_files()
    if not pdf_files:
        return "", "لا توجد ملفات PDF في المستودع"
    
    random.shuffle(pdf_files)
    for pdf_path in pdf_files:
        book_name = os.path.basename(pdf_path)
        try:
            reader = PdfReader(pdf_path)
            num_pages = len(reader.pages)
            if num_pages == 0:
                continue
            
            start_page = random.randint(min(5, num_pages - 1), max(0, num_pages - 4))
            extracted_text = ""
            for p in range(start_page, min(start_page + 4, num_pages)):
                text = reader.pages[p].extract_text() or ""
                extracted_text += text + "\n"
            
            if len(extracted_text.strip()) > 300:
                return extracted_text.strip(), book_name
        except Exception:
            continue
            
    return "", "تعذر استخراج نص كافٍ"

def generate_summary_with_gemini(raw_book_text: str, book_name: str) -> str:
    prompt = f"""أنت خبير استشاري أول في نظم إدارة الجودة، التميز المؤسسي، والتطوير الإداري لشركة جدارا.
بناءً على النص المرفق حصراً والمستخرج من كتاب ({book_name}):

قم بصياغة ملخص تنفيذي واحترافي ورصين للنشر (من 250 إلى 350 كلمة تقريباً) يركز على التطبيق العملي، ويتضمن:
1. عنواناً مهنياً دقيقاً للمفهوم.
2. الفكرة الجوهرية والدرس المستفاد من زاوية إدارة الجودة، التميز المؤسسي، وتطوير العمليات.
3. خاتمة تفاعلية بطرح تساؤل عملي لتطوير الأداء المؤسسي.
4. الوسوم المعتمدة: #إدارة_الجودة #التميز_المؤسسي #جدارا

قواعد صياغة صارمة وإلزامية:
- يُمنع منعاً باتاً استخدام الأقواس الهلالية ( ) أو المعقوفة [ ] في أي موضع من العنوان أو النص.
- اكتب المصطلحات الإنجليزية أو التوضيحية مدمجة بسلاسة أو مفصولة بشرطات عادية دون أقواس نهائياً.
- اكتب النص مباشرة دون أي مقدمات أو هوامش إضافية.

النص المأخوذ من الكتاب:
{raw_book_text[:4000]}
"""
    gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1000}
    }
    try:
        resp = requests.post(gemini_url, json=payload, timeout=30)
        if resp.status_code == 200:
            result = resp.json()
            return result["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print("Gemini generation error:", e)
    return ""

async def execute_scheduled_cycle():
    print(f"[{datetime.datetime.now()}] بدء دورة النشر التلقائية...")
    raw_text, book_name = extract_content_from_random_book()
    if not raw_text:
        print("خطأ: لم يتم العثور على محتوى من الكتب.")
        return
    
    summary = generate_summary_with_gemini(raw_text, book_name)
    if not summary:
        print("خطأ: تعذر توليد الملخص من Gemini.")
        return
    
    tg_res = await post_to_telegram(summary)
    print("Telegram:", tg_res)
    
    li_res = publish_to_linkedin(summary)
    print("LinkedIn:", li_res)
    
    save_history({
        "timestamp": datetime.datetime.now().isoformat(),
        "book": book_name,
        "summary_preview": summary[:100],
        "telegram": tg_res,
        "linkedin": li_res
    })
    print("اكتملت دورة النشر بنجاح.")

@app.on_event("startup")
async def start_scheduler():
    ensure_cover_image()
    timezone = pytz.timezone("Asia/Aden")
    scheduler.add_job(
        execute_scheduled_cycle,
        CronTrigger(hour="9,14,20", minute=0, timezone=timezone),
        id="quality_posts_job",
        replace_existing=True
    )
    scheduler.start()
    print("APScheduler started: 9:00, 14:00, 20:00 (Asia/Aden).")

@app.get("/")
@app.get("/health")
def health():
    pdf_files = find_all_pdf_files()
    books_in_dir = os.listdir(BOOKS_DIR) if os.path.exists(BOOKS_DIR) else []
    
    return {
        "status": "ready",
        "bridge": "active",
        "scheduler": "running",
        "books_count": len(pdf_files),
        "sample_books": [os.path.basename(f) for f in pdf_files[:10]],
        "BASE_DIR": BASE_DIR,
        "BOOKS_DIR": BOOKS_DIR,
        "books_directory_exists": os.path.exists(BOOKS_DIR),
        "files_in_books_folder": books_in_dir[:10]
    }

@app.get("/run-now")
@app.post("/run-now")
async def trigger_now():
    """مسار التجربة الفورية السريعة."""
    await execute_scheduled_cycle()
    return {"status": "success", "message": "Cycle executed successfully"}

@app.post("/mcp")
async def mcp_endpoint(request: Request):
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
                        "name": "post_to_telegram",
                        "description": "ينشر نصاً أو ملخصاً مباشرة إلى قناة تليجرام المحددة.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "message_text": {"type": "string", "description": "النص المراد نشره."}
                            },
                            "required": ["message_text"]
                        }
                    },
                    {
                        "name": "publish_to_linkedin",
                        "description": "ينشر النص الأصلي حرفياً إلى لينكد إن مع صورة الغلاف.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "exact_text": {"type": "string", "description": "النص الكامل للمنشور."}
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
            result_text = await post_to_telegram(args.get("message_text", ""))
        elif tool_name == "publish_to_linkedin":
            result_text = publish_to_linkedin(args.get("exact_text", ""))
        else:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Unknown tool"}}
            
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"content": [{"type": "text", "text": result_text}]}
        }

    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Method not supported"}}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
