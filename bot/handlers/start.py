import os
from aiogram import F
from aiogram.filters import StateFilter
from aiogram.filters.command import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery,ReplyKeyboardRemove,ContentType
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from yt_dlp import YoutubeDL
from dispatcher import dp
from bot.buttons.inline import *
from bot.buttons.reply import *
from bot.state.main import *
from bot.utils import *
from aiogram.types import FSInputFile
from glob import glob

@dp.message(Command("about"), StateFilter(None))
async def about(message: Message,state: FSMContext) -> None:
    pass

@dp.message(Command("start"), StateFilter(None))
async def start(message: Message, state: FSMContext) -> None:
    tg_id = message.from_user.id
    data = await state.get_data()
    data['tg_id']=tg_id
    await state.update_data(data)
    user, created = User.objects.get_or_create(tg_id=tg_id)
    if not await check_user_subscription(tg_id):
        print('kirdi')
        await message.answer(
            text=f"Salom {message.from_user.first_name}!\n\nBotdan foydalanish uchun quyidagi kanalga a'zo bo'ling:",
            reply_markup=join_channels()
    )
        return
    await message.answer(text="✅ Tabriklayman! Endi video yuboring yoki YouTube/Instagram link jo‘nating.")
    return


async def menu_handler(message: Message, state: FSMContext) -> None:
    pass



@dp.callback_query(F.data=="check_subscription")
async def handle_sub_calback(calback:CallbackQuery,state:FSMContext)->None:
    await calback.answer()
    await calback.message.delete()
    data = await state.get_data()
    tg_id = data.get('tg_id')
    if  not await check_user_subscription(tg_id):
        await calback.message.answer(text="🚫 Siz hali kanalga a’zo emassiz.",reply_markup=join_channels())
    else:
        await calback.message.answer(text="✅ Tabriklayman! Endi video yuboring yoki YouTube/Instagram link jo‘nating.",reply_markup=ReplyKeyboardRemove())
    return
    

    
@dp.message(F.content_type.in_([ContentType.VIDEO, ContentType.DOCUMENT]))
async def video_document_handler(message: Message, state: FSMContext, ):
    data = await state.get_data()
    tg_id = data.get('tg_id')

    if not await check_user_subscription(tg_id):
        await message.answer(
            text="🚫 Siz hali kanalga a’zo emassiz.",
            reply_markup=join_channels()
        )
        return

    file = message.video or message.document
    if not file:
        await message.answer("📹 Iltimos, video yoki hujjat yuboring.")
        return
    await message.answer(text="Video yumaloq videoga ylantirilmoqda ")

    file_id = file.file_id
    new_filename = f"{file_id}.mp4"

    # papkalarni yaratish
    os.makedirs("downloads", exist_ok=True)
    os.makedirs("outputs", exist_ok=True)

    raw_path = f"downloads/{new_filename}"
    output_path = f"outputs/round_{new_filename}"

    # Telegram serverdan faylni olish va yuklab olish
    file_obj = await bot.get_file(file_id)
    await bot.download_file(file_obj.file_path, destination=raw_path)

    # Konvertatsiya
    convert_to_round(raw_path, output_path)

    # Natijani yuborish
    vid = FSInputFile(output_path)
    await message.answer_video_note(video_note=vid)

    # Ortiqcha fayllarni o‘chirish
    os.remove(raw_path)
    os.remove(output_path)
    


video_info_cache = {}

@dp.message(F.text.startswith(("https://youtu", "https://www.youtube", "https://www.instagram.com")))
async def process_link(message: Message, state: FSMContext):
    chat_id = message.chat.id
    url = message.text

    msg = await message.answer("🔍 Formatlar aniqlanmoqda...")

    ydl_opts = {
        'quiet': True,
        'noplaylist': True,
        'cookies': 'instagram_cookies.txt',  # ← cookie qo‘shildi
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        formats = info.get('formats', [])
        title = info.get('title') or "Noma'lum video"
        video_info_cache[chat_id] = info

        buttons = []
        added_res = set()

        for f in formats:
            if not f.get("format_id") or f.get("vcodec") == "none":
                continue

            resolution = f.get('format_note') or f.get('height')
            ext = f.get('ext')
            format_id = f.get('format_id')

            try:
                if isinstance(resolution, str) and 'p' in resolution.lower():
                    height = int(resolution.lower().replace('p', ''))
                else:
                    height = int(resolution)
            except (ValueError, TypeError):
                continue

            if height < 480 or ext != 'mp4':
                continue

            str_res = f"{height}p"
            if str_res not in added_res:
                added_res.add(str_res)
                buttons.append([
                    InlineKeyboardButton(
                        text=str_res,
                        callback_data=f"video|{format_id}"
                    )
                ])

        buttons.append([
            InlineKeyboardButton(text="🎧 MP3 (audio)", callback_data="audio|bestaudio")
        ])

        markup = InlineKeyboardMarkup(inline_keyboard=buttons)

        await msg.delete()
        await message.answer(
            f"🎬 *{title}*\nQaysi formatda yuklab olishni tanlang:",
            reply_markup=markup,
            parse_mode="Markdown"
        )

    except Exception as e:
        await message.answer("❌ Formatlarni aniqlashda xatolik yuz berdi.")
        print("Format aniqlash xatosi:", e)

video_info_cache = {}  # global cache agar sizda allaqachon bo'lmasa
@dp.callback_query(F.data.startswith(("video|", "audio|")))
async def download_selected_format(query: CallbackQuery):
    user_id = query.from_user.id
    await query.answer()

    if user_id not in video_info_cache:
        await query.message.answer("❌ Video ma'lumotlari topilmadi. Qayta YouTube havolasini yuboring.")
        return

    filename = None

    try:
        choice_type, format_id = query.data.split('|')
        await query.message.delete()
        downloading_msg = await query.message.answer("⏳ Yuklab olinmoqda...")

        info = video_info_cache[user_id]
        url = info.get("webpage_url")
        output_template = 'downloads/%(title).50s.%(ext)s'

        if choice_type == "audio":
            ydl_opts = {
                'format': 'bestaudio',
                'outtmpl': output_template,
                'quiet': True,
                'restrictfilenames': True,
                'cookies': 'instagram_cookies.txt',  # ← cookie qo‘shildi
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }
        else:
            ydl_opts = {
                'format': f'{format_id}+bestaudio/best',
                'outtmpl': output_template,
                'quiet': True,
                'restrictfilenames': True,
                'cookies': 'instagram_cookies.txt',  # ← cookie qo‘shildi
                'merge_output_format': 'mp4',
            }

        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        downloaded_files = sorted(glob("downloads/*.mp*"), key=os.path.getmtime, reverse=True)
        filename = downloaded_files[0] if downloaded_files else None

        if not filename or not os.path.exists(filename):
            await downloading_msg.delete()
            await query.message.answer("❌ Faylni topib bo‘lmadi.")
            return

        await downloading_msg.delete()
        file = FSInputFile(filename)
        print("Fayl hajmi:", os.path.getsize(filename) / (1024 * 1024), "MB")

        if choice_type == "audio":
            await query.message.answer_audio(audio=file)
        else:
            await query.message.answer_video(video=file)

    except Exception as e:
        await query.message.answer("❌ Yuklab olishda xatolik yuz berdi.")
        print("Yuklab olish xatosi:", e)

    finally:
        if filename and os.path.exists(filename):
            try:
                os.remove(filename)
            except Exception as remove_error:
                print("❌ Faylni o‘chirishda xatolik:", remove_error)

        video_info_cache.pop(user_id, None)
