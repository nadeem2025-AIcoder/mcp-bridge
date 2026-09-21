import os
import random
import io
import time
import requests
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from telegram import Bot
from pypdf import PdfReader

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

# قائمة بمراجع ومواصفات Guadara_Books المعتمدة
LIBRARY_BOOKS = [
    {"title": "المواصفة القياسية ISO 14001:2015 لنظم الإدارة البيئية", "id": "1QHWA2ixyV7q_YI6faCQK0-MB7ZKP52c1"},
    {"title": "مواصفة ISO 19011 الإرشادية لإدارة المراجعة والتدقيق", "id": "1VNtdEwfKqv4XRTt0RLGuA-smvVmK8fBx"},
    {"title": "مواصفة ISO 45001 لإدارة السلامة والصحة المهنية", "id": "1vmv6riPyg9M-Glxs62m7jOF4xxJNk39M"},
    {"title": "ترجمة وشرح للمواصفة ISO 45002", "id": "1lYhI1GuN1eVco3lyeDHoVgySfmfGRZRf"},
    {"title": "المواصفة القياسية ISO/IEC 27001 لأنظمة إدارة أمن المعلومات", "id": "1dpZpHq7X3ZgzbIXC1KejeKoiRRCL79p3"},
    {"title": "مواصفة الأيزو 22002-1 لبرامج الاشتراطات المسبقة لسلامة الغذاء", "id": "1leLZmJegbrq8xU6tOlvljMPKQQmrWz08"},
    {"title": "نظم إدارة سلامة الغذاء ISO 22000", "id": "1onjbTW0Seg8NnZmdWRz-0YqWPv1BtOmh"},
    {"title": "المعيار العالمي للتعبئة والتغليف BRCGS Packaging Issue 7", "id": "1YxlZFN--SPGII2VMNoQZUcHMGUee0yjZ"},
    {"title": "مواصفة BRC لسلامة الغذاء - الإصدار الثامن", "id": "1yOpD523eFgwgQik62XFazYdtPeL8ka2d"},
    {"title": "دليل قياس الاستدامة وتقييم الأداء البيئي", "id": "1tcqep-tqpnyHwfi6CpWUcC7WzBzWAfNS"},
    {"title": "دليل نقاط التحقق للوقاية من الإجهاد في بيئة العمل", "id": "14eDW5YNdTp93WHC66HJVzDSfAs7cLfWL"},
    {"title": "المواصفات القياسية لفترات صلاحية المنتجات الغذائية", "id": "1055Qlba70lYzaFipLass5e85TAmDC2ui"},
    {"title": "شرح بنود قائمة اعتماد هيئة سلامة الغذاء للمصانع", "id": "1KpzbtXOR4g466Fyh39tXfTQTmay9Zzny"},
    {"title": "دورة تدريب المدربين TOT وأساليب العرض والتقديم", "id": "1HbLG34fQ2pTR8agFxANYJgHVm_KfQgtS"},
    {"title": "مواصفة وتطبيقات علامة الحلال وجودة المنتجات", "id": "1x8NYr_HXqvhYRlZJVjuFP0h03NpnucxG"},
    {"title": "دليل أساسيات سلامة الغذاء والنظافة المهنية", "id": "1kpJwX8_MmoRhCqE6A5k6yobVAe4bFdlt"},
    {"title": "أسس ومعايير السلامة المهنية والمخاطر الصناعية", "id": "17KezXDNMafj0CJw5td7c-BEXVDU4COMj"}
]

def download_book_excerpt():
    """اختيار كتاب وقراءة صفحات منه مباشرة من Google Drive."""
    book = random.choice(LIBRARY_BOOKS)
    book_title = book["title"]
    file_id = book["id"]

    urls = [
        f"https://drive.usercontent.google.com/download?id={file_id}&export=download&authuser=0",
        f"https://docs.google.com/uc?export=download&id={file_id}"
    ]
    
    session = requests.Session()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    for url in urls:
        try:
            res = session.get(url, headers=headers, stream=True, timeout=20)
            if res.status_code == 200:
                for k, v in res.cookies.items():
                    if k.startswith('download_warning'):
                        res = session.get(f"{url}&confirm={v}", headers=headers, stream=True, timeout=20)
                        break

                if res.content.startswith(b'%PDF'):
                    pdf = PdfReader(io.BytesIO(res.content))
                    total = len(pdf.pages)
                    if total > 4:
                        start = random.randint(4, max(4, total - 4))
                        text = ""
                        for p in range(start, min(start + 3, total)):
                            text += (pdf.pages[p].extract_text() or "") + "\n"
                        clean = " ".join(text.split())
                        if len(clean) > 100:
                            return book_title, clean[:2500]
        except Exception:
            continue

    return book_title, ""

def generate_book_summary() -> tuple:
    """توليد التلخيص مع معالجة ذكية لأخطاء 503 بالتبديل وإعادة المحاولة."""
    book_title, excerpt = download_book_excerpt()

    if excerpt:
        prompt = (
            f"أنت خبير استشاري ومراجع معتمد في نظم إدارة الجودة والمواصفات القياسية الدولية.\n"
            f"قم بصياغة منشور احترافي متكامل وعملي (بين 130 و200 كلمة) مستخلص مباشرة من هذا المرجع:\n"
            f"المرجع: {book_title}\n\n"
            f"النص المقتبس من الكتاب:\n\"\"\"\n{excerpt}\n\"\"\"\n\n"
            f"شروط المنشور:\n"
            f"1. ابدأ بعنوان مهني جذاب.\n"
            f"2. لخص الفكرة الإدارية أو المتطلب القياسي في نقاط عملية قابلة للتطبيق الفوري.\n"
            f"3. اذكر اسم المرجع في السطر الأخير: (المصدر: {book_title}).\n"
            f"4. ضع وسوم مهنية مناسبة (#إدارة_الجودة #المواصفات_القياسية #التميز_المؤسسي).\n"
            f"5. لا تضف أي مقدمات أو هوامش دردشة."
        )
    else:
        prompt = (
            f"أنت خبير استشاري ومراجع معتمد في نظم إدارة الجودة.\n"
            f"اكتب منشوراً مهنياً عملياً ومحكماً (بين 130 و200 كلمة) حول أحد المبادئ التطبيقية الهامة في مرجع:\n"
            f"({book_title}).\n"
            f"اجعل النص في نقاط عملية واختم بالمرجع والوسوم دون مقدمات جانبية."
        )

    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    # قائمة بالنماذج المستقرة للتبديل الفوري في حال انشغال أحدها (503)
    models = ["gemini-3.6-flash", "gemini-2.0-flash", "gemini-2.5-flash"]
    last_error = ""

    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        for attempt in range(2):  # محاولتان لكل نموذج مع فاصل ثانية
            try:
                res = requests.post(url, headers=headers, json=payload, timeout=40)
                if res.status_code == 200:
                    summary = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                    return book_title, summary
                elif res.status_code == 503:
                    time.sleep(1.5)
                    continue
                else:
                    last_error = f"{model} -> كود {res.status_code}: {res.text[:120]}"
                    break
            except Exception as e:
                last_error = str(e)
                time.sleep(1)

    return book_title, f"خطأ توليد: {last_error}"

async def post_to_telegram(text: str, image_path: str = "post_cover.png") -> str:
    """نشر المنشور مع الصورة إلى قناة تيليجرام."""
    if not TELEGRAM_BOT_TOKEN or not CHANNEL_ID:
        return "خطأ: بيانات تليجرام غير مكتملة."
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        if os.path.exists(image_path):
            with open(image_path, "rb") as photo:
                msg = await bot.send_photo(chat_id=CHANNEL_ID, photo=photo, caption=text[:1024])
                if len(text) > 1024:
                    await bot.send_message(chat_id=CHANNEL_ID, text=text[1024:])
                return f"تم النشر في تليجرام مع الصورة بنجاح (ID: {msg.message_id})"
        else:
            msg = await bot.send_message(chat_id=CHANNEL_ID, text=text)
            return f"تم النشر نصياً (الصورة غير متوفرة في المجلد) ID: {msg.message_id}"
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
        init_res = requests.post(init_url, headers=headers, json=init_payload, timeout=15)
        if init_res.status_code == 200:
            init_data = init_res.json().get("value", {})
            upload_url = init_data.get("uploadUrl")
            image_urn = init_data.get("image")
            with open(image_path, "rb") as img_file:
                put_res = requests.put(
                    upload_url,
                    headers={"Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}", "Content-Type": "image/png"},
                    data=img_file,
                    timeout=25
                )
                if put_res.status_code in (200, 201):
                    return image_urn
    except Exception:
        pass
    return ""

def post_to_linkedin(text: str, image_path: str = "post_cover.png") -> str:
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
        sub = LINKEDIN_USER_SUB
    if not sub:
        return "خطأ: تعذر تحديد حساب لينكد إن."

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
                status_msg += " (مع الصورة)"
            return status_msg
        return f"فشل لينكد إن ({res.status_code}): {res.text[:150]}"
    except Exception as e:
        return f"خطأ اتصال لينكد إن: {str(e)}"

@app.get("/")
@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/trigger-now")
@app.post("/trigger-now")
async def trigger_now():
    """سحب كتاب من درايف وتلخيصه ونشره مع الصورة."""
    book_title, summary = generate_book_summary()

    if summary.startswith("خطأ"):
        return {"status": "error", "book": book_title, "details": summary}

    tg_res = await post_to_telegram(summary, "post_cover.png")
    li_res = post_to_linkedin(summary, "post_cover.png")

    return {
        "status": "success",
        "book": book_title,
        "summary": summary,
        "telegram": tg_res,
        "linkedin": li_res
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
