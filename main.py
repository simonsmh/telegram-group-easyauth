#!/usr/bin/env python
# -*- coding: utf-8 -*-
import logging
import random
import yaml
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler
from telegram.ext.dispatcher import run_async

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

try:
    config = yaml.load(open('config.yml'))
except FileNotFoundError:
    logger.log(logging.exception, "Cannot find config.yml.")
    exit(1)


@run_async
def start(update, context):
    update.message.reply_text(config['START'])


@run_async
def error(update, context):
    logger.warning('Update "%s" caused error "%s"', context, error)


@run_async
def kick(context):
    data = context.job.context.split('|')
    context.bot.kick_chat_member(chat_id=data[0], user_id=data[1],
                                 until_date=datetime.timestamp(datetime.today()) + config['BANTIME'])


@run_async
def clean(context):
    data = context.job.context.split('|')
    context.bot.delete_message(chat_id=data[0], message_id=data[1])


@run_async
def newmem(update, context):
    chat = update.message.chat
    users = update.message.new_chat_members
    flag = random.randint(0, len(config['CHALLENGE']) - 1)
    for user in users:
        if not user.is_bot:
            buttons = [[InlineKeyboardButton(
                text=config['CHALLENGE'][flag]['ANSWER'], callback_data=f"newmem|pass|{user.id}|{flag}")]]
            for t in config['CHALLENGE'][flag]['WRONG']:
                buttons.append([InlineKeyboardButton(
                    text=t, callback_data=f"newmem|fail|{user.id}|{flag}|{t}")])
            random.shuffle(buttons)
            msg = update.message.reply_text(config['GREET'] % (config['CHALLENGE'][flag]['QUESTION'], config['TIME']),
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
                context.chat_data[str(chat.id) + str(user.id)
                                  ].schedule_removal()
            context.chat_data[str(chat.id) + str(user.id) + 'kick'] = context.job_queue.run_once(
                kick, config['TIME'], context=f"{chat.id}|{user.id}"
            )
            context.chat_data[str(chat.id) + str(user.id) + 'clean'] = context.job_queue.run_once(
                clean, config['TIME'], context=f"{chat.id}|{msg.message_id}"
            )


@run_async
def query(update, context):
    user = update.callback_query.from_user
    message = update.callback_query.message
    chat = message.chat
    data = update.callback_query.data.split('|')
    if str(user.id) == data[2]:
        if data[1] == 'pass':
            context.bot.answer_callback_query(
                text=config['SUCCESS'],
                show_alert=False,
                callback_query_id=update.callback_query.id
            )
            context.bot.edit_message_text(
                text=f"[{user.first_name}](tg://user?id={user.id})\n{config['PASS']}",
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
                text=config['RETRY'] % config['BANTIME'],
                show_alert=True,
                callback_query_id=update.callback_query.id
            )
            try:
                context.bot.kick_chat_member(chat_id=chat.id, user_id=user.id,
                                             until_date=datetime.timestamp(datetime.today()) + config['BANTIME'])
            except:
                context.bot.edit_message_text(
                    text=f"[{user.first_name}](tg://user?id={user.id})\n{config['CHALLENGE'][data[3]]['QUESTION']}:{data[4]}\n{config['NOT_KICK']}",
                    message_id=message.message_id,
                    chat_id=chat.id, parse_mode='Markdown')
            else:
                context.bot.edit_message_text(
                    text=f"[{user.first_name}](tg://user?id={user.id})\n{config['CHALLENGE'][data[3]]['QUESTION']}:{data[4]}\n{config['KICK']}",
                    message_id=message.message_id,
                    chat_id=chat.id, parse_mode='Markdown')
        context.chat_data[str(chat.id) + str(user.id) +
                          'kick'].schedule_removal()
    else:
        context.bot.answer_callback_query(
            text=config['OTHER'], show_alert=True, callback_query_id=update.callback_query.id)


if __name__ == '__main__':
    updater = Updater(config['TOKEN'], use_context=True)
    updater.dispatcher.add_handler(CommandHandler("start", start))
    updater.dispatcher.add_handler(MessageHandler(
        Filters.status_update.new_chat_members, newmem))
    updater.dispatcher.add_handler(
        CallbackQueryHandler(query, pattern=r'newmem'))
    updater.dispatcher.add_error_handler(error)
    updater.start_polling()
    updater.idle()
