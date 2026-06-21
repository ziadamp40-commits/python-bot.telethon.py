import os
import sqlite3
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
from telethon import TelegramClient

# --- إضافة مكتبات تشغيل الـ 24 ساعة ---
from flask import Flask
from threading import Thread

# ضع بيانات البوت الخاص بك هنا فقط
BOT_TOKEN = "8883405476:AAFcOXftl9FuljK-S-AHWueHNM_EzP_KNkQ"  # توكن بوتك من BotFather
ADMIN_ID = 92816237         # الأيدي الرقمي لحسابك لحمايته

# ----------------------------------------------------------------
# خادم ويب وهمي لمنع الاستضافة من الدخول في وضع الخمول (Sleep)
app = Flask('')

@app.route('/')
def home():
    return "Bot is running perfectly 24/7!"

def run_server():
    # المنصة تعين المنفذ تلقائياً في متغير البيئة PORT، ولو مش موجود بيشتغل على 8080
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    """تشغيل خادم الويب في خلفية النظام (Thread منفصل) دون تداخل مع البوت"""
    t = Thread(target=run_server)
    t.start()
# ----------------------------------------------------------------

if not os.path.exists("sessions"):
    os.makedirs("sessions")

def get_session_credentials(db_path):
    """دالة لقرأة الـ API_ID والـ API_HASH من ملف السيشين تلقائياً"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # الطريقة الأولى: الفحص من جدول sessions الافتراضي
        try:
            cursor.execute("SELECT id, hash FROM sessions LIMIT 1;")
            row = cursor.fetchone()
            if row and row[0] and row[1]:
                conn.close()
                return int(row[0]), str(row[1])
        except:
            pass

        # الطريقة الثانية: إذا كانت الأسماء مختلفة (مثل version)
        try:
            cursor.execute("SELECT api_id, api_hash FROM version LIMIT 1;")
            row = cursor.fetchone()
            if row and row[0] and row[1]:
                conn.close()
                return int(row[0]), str(row[1])
        except:
            pass
            
        # الطريقة الثالثة: الفرز التلقائي داخل جدول sessions كخيار أخير
        try:
            cursor.execute("SELECT * FROM sessions LIMIT 1;")
            row = cursor.fetchone()
            if row:
                api_id = None
                api_hash = None
                for item in row:
                    if isinstance(item, int) and item > 1000:
                        api_id = item
                    elif isinstance(item, str) and len(item) == 32:
                        api_hash = item
                if api_id and api_hash:
                    conn.close()
                    return api_id, api_hash
        except:
            pass

        conn.close()
    except Exception as e:
        print(f"Error reading DB: {e}")
    return None, None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    welcome_text = (
        "👋 مرحباً بك في بوت تسجيل خروج الجلسات.\n\n"
        "📥 يرجى إرسال ملف السيشين (`.session`) الآن للبدء في إنهاء الجلسة وتدميرها."
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def handle_session_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    document = update.message.document
    if not document.file_name.endswith('.session'):
        await update.message.reply_text("❌ عذراً، هذا ليس ملف سيشين تيليجرام (`.session`).")
        return

    status_message = await update.message.reply_text("⏳ جاري تحميل وتجهيز ملف الجلسة وفحص صلاحيتها...")
    
    file_path = f"sessions/{document.file_name}"
    tg_file = await context.bot.get_file(document.file_id)
    await tg_file.download_to_drive(file_path)
    
    # قراءة بيانات السيشين أولاً
    api_id, api_hash = get_session_credentials(file_path)
    if not api_id or not api_hash:
        api_id = 6
        api_hash = "eb06d4abfb49dc3eeb1aeb98ae0f581e"

    # --- التعديل الجوهري: فحص الجلسة فوراً قبل عرض الأزرار ---
    client = TelegramClient(file_path, api_id, api_hash)
    is_valid = False
    try:
        await client.connect()
        is_valid = await client.is_user_authorized()
    except Exception as e:
        print(f"فحص فوري فشل: {e}")
    finally:
        if client.is_connected():
            await client.disconnect()

    # لو الجلسة طلعت بايظة أو منتهية
    if not is_valid:
        if os.path.exists(file_path):
            os.remove(file_path) # مسح الملف التالف فوراً
        await status_message.edit_text("❌ عذراً، هذا الملف **غير صالح أو منتهي الصلاحية** مسبقاً!")
        return
    # --------------------------------------------------------

    # لو الجلسة سليمة وشغالة، هيعرض الزرار عادي جداً
    keyboard = [
        [InlineKeyboardButton("🚪 تسجيل الخروج نهائياً", callback_data=f"logout_{document.file_name}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await status_message.edit_text(
        f"✅ تم فحص الجلسة بنجاح: `{document.file_name}` وهي **صالحة ونشطة حالياً**.\n"
        f"اضغط على الزر أدناه لتسجيل الخروج وتدميرها نهائياً:", 
        reply_markup=reply_markup, 
        parse_mode="Markdown"
    )

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return

    data = query.data.split('_', 1)
    action = data[0]
    file_name = data[1]
    session_path = f"sessions/{file_name}"

    if not os.path.exists(session_path):
        await query.edit_message_text("❌ ملف الجلسة لم يعد موجوداً في السيرفر.")
        return

    await query.edit_message_text("🔄 جاري تسجيل الخروج وتدمير الجلسة...")

    api_id, api_hash = get_session_credentials(session_path)
    if not api_id or not api_hash:
        api_id = 6
        api_hash = "eb06d4abfb49dc3eeb1aeb98ae0f581e"

    client = TelegramClient(session_path, api_id, api_hash)
    
    try:
        await client.connect()
        if action == "logout":
            await client.log_out()
            if os.path.exists(session_path):
                os.remove(session_path)
            await query.edit_message_text("🚪 تم تسجيل الخروج من الحساب بنجاح وحذف ملف الجلسة نهائياً من البوت.")
    except Exception as e:
        await query.edit_message_text(f"❌ حدث خطأ غير متوقع أثناء المعالجة:\n`{str(e)}`", parse_mode="Markdown")
    finally:
        if client.is_connected():
            await client.disconnect()

async def start_bot():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_session_file))
    app.add_handler(CallbackQueryHandler(button_click))
    
    print("⚡ البوت شغال الآن وبنظام الفحص المسبق للجلسات...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    
    while True:
        await asyncio.sleep(1)

if __name__ == '__main__':
    try:
        # تشغيل خادم الويب الوهمي أولاً للبقاء مستيقظاً 24 ساعة
        keep_alive()
        
        # تشغيل سكريبت البوت الأساسي
        asyncio.run(start_bot())
    except (KeyboardInterrupt, SystemExit):
        print("🛑 تم إيقاف البوت.")
