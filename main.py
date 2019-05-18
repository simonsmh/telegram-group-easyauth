#!/usr/bin/env python
# -*- coding: utf-8 -*-
import logging
import random
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

TOKEN = ''

TIME = 120

BANTIME = 120

GREET = "欢迎加入 神楽めあ/Kagura Mea Group！"

# CHALLENGE Format ["Question", "Right Answer", ("Wrong Answer List")]
CHALLENGE = [
    ["绘文字🍥⚓代表的象征意义是？", "Meaqua", ("鱼板船锚", "知らない", "酱油通道", "What's up?")],
    ["请问 Mea 人设为哪国人？", "法国", ("英国", "梵蒂冈", "墨西哥", "不清楚呀")],
    ["请问 Mea 人设的创造者是谁？", "Paryi", ("佃煮海苔男", "京华", "ゆゆうた", "凪白みと")],
    ["请问 Mea 因为在初次直播中OO而被称为？", "手冲女仆", ("冲国财布", "不知道", "鱼板船锚", "爱我苏联")],
    ["请问 Mea 最擅长玩哪个游戏？", "Tetris Online Poland", ("Spaltoon 2", "Tetris 99", "PUBG", "Minecraft")],
    ["请问 Mea 和谁是穴兄弟组？", "Umori Hinako", 
        ("Inaba Haneru", "Ran", "Minato Aqua", "Ayame")],
    ["请问 Mea 什么时候通过收益化？", "2018-12-24", 
        ("2019-4-1", "2018-11-26", "2018-6-28", "2018-12-25")],
    ["请问 Mea 因和谁比赛输掉而发布谢罪视频？", "Natsuiro Matsuri", 
        ("Nobuhime", "Minato Aqua", "Inuyama Tamaki", "DWU")]
]


def start(update, context):
    update.message.reply_text('🍥请将我设定为管理员以使用验证功能！🍥')


def error(update, context):
    logger.warning('Update "%s" caused error "%s"', context, error)


def kick(context):
    data = context.job.context.split(' ')
    context.bot.kick_chat_member(chat_id=data[0], user_id=data[1],
                                 until_date=datetime.timestamp(datetime.today()) + BANTIME)


def clean(context):
    data = context.job.context.split(' ')
    context.bot.delete_message(chat_id=data[0], message_id=data[1])


def newmem(update, context):
    chat = update.message.chat
    users = update.message.new_chat_members
    flag = random.randint(0, len(CHALLENGE) - 1)
    for user in users:
        if not user.is_bot:
            buttons = [[InlineKeyboardButton(
                text=CHALLENGE[flag][1], callback_data=f"newmem pass {user.id}")]]
            for t in CHALLENGE[flag][2]:
                buttons.append([InlineKeyboardButton(
                    text=t, callback_data=f"newmem {random.randint(1, 9999)} {user.id}")])
            random.shuffle(buttons)
            msg = update.message.reply_text(f"{GREET}\n{CHALLENGE[flag][0]}\n请在{TIME}秒内点击按钮选择答案：\n",
                                            reply_markup=InlineKeyboardMarkup(buttons))
            context.bot.restrict_chat_member(
                chat_id=chat.id,
                user_id=user.id,
                can_send_messages=False,
                can_send_media_messages=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False
            )
            if context.chat_data.get(str(chat.id) + str(user.id)):
                context.chat_data[str(chat.id) + str(user.id)].schedule_removal()
            context.chat_data[str(chat.id) + str(user.id) + 'kick'] = context.job_queue.run_once(
                kick, TIME, context=f"{chat.id} {user.id}"
            )
            context.chat_data[str(chat.id) + str(user.id) + 'clean'] = context.job_queue.run_once(
                clean, TIME, context=f"{chat.id} {msg.message_id}"
            )


def query(update, context):
    user = update.callback_query.from_user
    message = update.callback_query.message
    chat = message.chat
    data = update.callback_query.data.split(' ')
    if str(user.id) == data[2]:
        if data[1] == 'pass':
            context.bot.answer_callback_query(
                text="验证成功",
                show_alert=False,
                callback_query_id=update.callback_query.id
            )
            context.bot.edit_message_text(
                text=f"[{user.first_name}](tg://user?id={user.id}) 验证通过，请仔细阅读群组公告和置顶后参与讨论！",
                message_id=message.message_id,
                chat_id=chat.id, parse_mode='Markdown'
            )
            context.bot.restrict_chat_member(
                chat_id=chat.id,
                user_id=user.id,
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        else:
            context.bot.answer_callback_query(
                text=f"验证失败，请{BANTIME}秒后重试",
                show_alert=True,
                callback_query_id=update.callback_query.id
            )
            try:
                context.bot.kick_chat_member(chat_id=chat.id, user_id=user.id,
                                             until_date=datetime.timestamp(datetime.today()) + BANTIME)
            except:
                context.bot.edit_message_text(
                    text=f"[{user.first_name}](tg://user?id={user.id}) 验证失败，请管理员多加留意！",
                    message_id=message.message_id,
                    chat_id=chat.id, parse_mode='Markdown')
            else:
                context.bot.edit_message_text(
                    text=f"[{user.first_name}](tg://user?id={user.id}) 验证失败，已被移出群组！",
                    message_id=message.message_id,
                    chat_id=chat.id, parse_mode='Markdown')
        context.chat_data[str(chat.id) + str(user.id) + 'kick'].schedule_removal()
    else:
        context.bot.answer_callback_query(
            text="别点啦，你已经在群里了", show_alert=True, callback_query_id=update.callback_query.id)


def main():
    updater = Updater(TOKEN, use_context=True)
    updater.dispatcher.add_handler(CommandHandler("start", start))
    updater.dispatcher.add_handler(MessageHandler(
        Filters.status_update.new_chat_members, newmem))
    updater.dispatcher.add_handler(
        CallbackQueryHandler(query, pattern=r'newmem'))
    updater.dispatcher.add_error_handler(error)
    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
