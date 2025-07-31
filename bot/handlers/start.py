import os
from os import getenv
from aiogram import F
from aiogram.filters import StateFilter
from aiogram.filters.command import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery,ReplyKeyboardRemove,ContentType
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
import requests
from dispatcher import dp
from bot.buttons.inline import *
from bot.buttons.reply import *
from bot.state.main import *
from bot.utils import *
from aiogram.types import FSInputFile
from glob import glob
from urllib.parse import urlparse, parse_qs

def extract_video_id(url):
    parsed = urlparse(url)

    # youtu.be shortlink
    if "youtu.be" in url:
        return parsed.path.lstrip("/")

    # youtube.com/watch?v=...
    if "youtube.com" in url:
        query = parse_qs(parsed.query).get("v")
        if query:
            return query[0]

        # support youtube shorts
        if parsed.path.startswith("/shorts/"):
            return parsed.path.split("/shorts/")[-1].split("?")[0]

    return None


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
    #if not await check_user_subscription(tg_id):
        
     #   await message.answer(
      #      text=f"Salom {message.from_user.first_name}!\n\nBotdan foydalanish uchun quyidagi kanalga a'zo bo'ling:",
       #     reply_markup=join_channels()
   # )
    #    return
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
    tg_id = message.from_user.id

   # if not await check_user_subscription(tg_id):
    #    await message.answer(
     #       text="🚫 Siz hali kanalga a’zo emassiz.",
      #      reply_markup=join_channels()
      #  )
       # return

    file = message.video or message.document
    if not file:
        await message.answer("📹 Iltimos, video yoki hujjat yuboring.")
        return
    await message.answer(text="Video yumaloq videoga aylantirilmoqda ")

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

@dp.message(F.text.startswith(("http",)))
async def process_link(message: Message, state: FSMContext):
    chat_id = message.chat.id
    url = message.text
    loading_msg = await message.answer("🔍 Havola tekshirilmoqda...")

    try:
        # YouTube uchun
        if "youtube.com" in url or "youtu.be" in url:
            if message.chat.type in ["group", "supergroup"]:
                video_id = extract_video_id(url)

                info_res = requests.get("https://fastsaverapi.com/get-info", params={
                    "url": url,
                    "token": getenv("FASTSAVER_API_TOKEN")
                })

                res2 = requests.get("https://fastsaverapi.com/download", params={
                    "video_id": video_id,
                    "format": "720p",
                    "bot_username": "DumaloqYuklaBot",
                    "token": getenv("FASTSAVER_API_TOKEN")
                })

                download_info = res2.json()
                
                if download_info.get("error"):
                    await message.reply("❌ Yuklab olishda xatolik yuz berdi.")
                    return

                file_url = download_info.get("file_id") 
                if not file_url:
                    await message.reply("❌ Faylni yuklab bo‘lmadi.")
                    return
                print(file_url)
                
                await message.answer_video(
                    video=file_url,
                    caption=info_res.json().get("title", "YouTube Video"),
                    reply_to_message_id=message.message_id
                )
                await loading_msg.delete()
                return

            # Private chat uchun tugmalar
            video_info_cache[chat_id] = {
                "hosting": "youtube",
                "yutu_url": url
            }

            if message.chat.type == "private":
                buttons = [
                    [InlineKeyboardButton(text="📥 Yuklab olish (video)", callback_data="video|default")],
                    [InlineKeyboardButton(text="🎧 Yuklab olish (audio)", callback_data="audio|default")]
                ]
                markup = InlineKeyboardMarkup(inline_keyboard=buttons)

                await loading_msg.delete()
                await message.answer(
                    f"🎬 Qanday formatda yuklab olmoqchisiz?",
                    reply_markup=markup,
                    parse_mode="Markdown"
                )
            return

        # Instagram, TikTok va boshqalar
        info_res = requests.get("https://fastsaverapi.com/get-info", params={
            "url": url,
            "token": getenv("FASTSAVER_API_TOKEN")
        })

        if info_res.status_code != 200 or info_res.json().get("error"):
            await loading_msg.edit_text("❌ Video topilmadi yoki format qo‘llab-quvvatlanmaydi.")
            return

        info = info_res.json()
        video_info_cache[chat_id] = info
        title = info.get("caption", "Video")

        # Guruhda: video reply qilinadi
        if message.chat.type in ["group", "supergroup"]:
            file_url = info.get("download_url")
            filename = f"downloads/{title[:50].replace(' ', '_')}.mp4"

            response = requests.get(file_url)
            with open(filename, 'wb') as f:
                f.write(response.content)

            file = FSInputFile(filename)
            await message.answer_video(
                video=file,
                caption=title,
                reply_to_message_id=message.message_id
            )
            await loading_msg.delete()
            return

        # Private chat uchun tugmalar
        if message.chat.type == "private":
            buttons = [
                [InlineKeyboardButton(text="📥 Yuklab olish (video)", callback_data="video|default")],
                [InlineKeyboardButton(text="🎧 Yuklab olish (audio)", callback_data="audio|default")]
            ]
            markup = InlineKeyboardMarkup(inline_keyboard=buttons)

            await loading_msg.delete()
            await message.answer(
                f"🎬 *{title}*\nQanday formatda yuklab olmoqchisiz?",
                reply_markup=markup,
                parse_mode="Markdown"
            )

    except Exception as e:
        print("Xato:", e)
        try:
            await loading_msg.edit_text("❌ Formatni aniqlashda xatolik yuz berdi.")
        except:
            await message.answer("❌ Formatni aniqlashda xatolik yuz berdi.")

@dp.callback_query(F.data.startswith(("video|", "audio|")))
async def download_selected_format(query: CallbackQuery):
    user_id = query.from_user.id
    await query.answer()

    if user_id not in video_info_cache:
        await query.message.answer("❌ Video ma'lumotlari topilmadi. Qayta havola yuboring.")
        return

    filename = None

    try:
        choice_type, _ = query.data.split('|')
        await query.message.delete()
        downloading_msg = await query.message.answer("⏳ Yuklab olinmoqda...")

        info = video_info_cache[user_id]
        if info.get("hosting") == "youtube":
            url=info.get("yutu_url")
            video_id = extract_video_id(url)
            ext = "mp3" if choice_type == "audio" else "720p"
            info_res = requests.get("https://fastsaverapi.com/get-info", params={
                "url": url,
                "token": getenv("FASTSAVER_API_TOKEN")
        })
            res2 = requests.get("https://fastsaverapi.com/download", params={
            "video_id": video_id,
            "format": ext,  # yoki "video" / "mp3"
            "bot_username": "DumaloqYuklaBot",  # @ belgisiz
            "token": getenv('FASTSAVER_API_TOKEN')
            })
            download_info = res2.json()
            print("Download response:", download_info)
            if download_info.get("error"):
                await query.message.answer("❌ Yuklab olishda xatolik yuz berdi.")
                return
            print("Download response:", res2.json())
            # Download URL oli    


            file_url = download_info.get("file_id")

            if not file_url:
                await query.message.answer("Faylni yuklab bo‘lmadi.")
                return
            await downloading_msg.delete()
            button1 = [
                [InlineKeyboardButton(text="📥 Yuklab olish (video)", callback_data="video|default")],
                ]
            button2 = [
                [InlineKeyboardButton(text="🎧 Yuklab olish (audio)", callback_data="audio|default")]
            ]
            markup = InlineKeyboardMarkup(inline_keyboard=button2 if choice_type == "video" else button1)

            if choice_type == "audio":
                await query.message.answer_audio(audio=file_url, title=info_res.json().get("title"),reply_markup=markup)
            else:
                await query.message.answer_video(video=file_url, caption=info_res.json().get("title"),reply_markup=markup)

            return
        title = info.get("caption", "video")
        file_url = info.get("download_url")
        ext = "mp3" if choice_type == "audio" else "mp4"
        filename = f"downloads/{title[:50].replace(' ', '_')}.{ext}"

        response = requests.get(file_url)
        with open(filename, 'wb') as f:
            f.write(response.content)

        file = FSInputFile(filename)
        title = info.get("caption", "Video")
        await downloading_msg.delete()
        button1 = [
                [InlineKeyboardButton(text="📥 Yuklab olish (video)", callback_data="video|default")],
                ]
        button2 = [
                [InlineKeyboardButton(text="🎧 Yuklab olish (audio)", callback_data="audio|default")]
            ]
        markup = InlineKeyboardMarkup(inline_keyboard=button2 if choice_type == "video" else button1)

        if choice_type == "audio":
            await query.message.answer_audio(audio=file,caption=title,reply_markup=markup)
        else:
            await query.message.answer_video(video=file,caption=title,reply_markup=markup)

    except Exception as e:
        await query.message.answer("❌ Yuklab olishda xatolik yuz berdi.")
        print("Yuklash xatosi:", e)

    finally:
        if filename and os.path.exists(filename):
            try:
                os.remove(filename)
            except Exception as remove_error:
                print("❌ Faylni o‘chirishda xatolik:", remove_error)

            
