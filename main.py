#!/usr/bin/env python
# -*- coding: utf-8 -*-
import logging
import os
import random
import sys
from datetime import datetime
from hashlib import blake2b

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.error import BadRequest
from telegram.ext import (CallbackQueryHandler, CommandHandler, Filters,
                          MessageHandler, Updater)
from telegram.ext.dispatcher import run_async
from yaml import dump, load

try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)


if len(sys.argv) >= 2 and os.path.exists(sys.argv[1]):
    config = load(open(sys.argv[1]), Loader=Loader)
    logger.info(f"Loaded {sys.argv[1]}")
else:
    try:
        config = load(open(f'{os.path.split(os.path.realpath(__file__))[0]}/config.yml'), Loader=Loader)
        logger.info("Loaded config.yml")
    except FileNotFoundError:
        logger.exception("Cannot find config.yml.")
        sys.exit(1)

for flag in config['CHALLENGE']:
    digest_size = len(flag['WRONG'])
    flag['wrong'] = []
    for t in range(digest_size):
        flag['wrong'].append(blake2b(str(flag['WRONG'][t]).encode(), digest_size=digest_size).hexdigest())
    flag['answer'] = blake2b(str(flag['ANSWER']).encode(), digest_size=digest_size).hexdigest()

queue = {}

@run_async
def start(update, context):
    update.message.reply_text(config['START'])


@run_async
def error(update, context):
    logger.warning('Update "%s" caused error "%s"', context, error)


@run_async
def kick(context):
    data = context.job.context.split('|')
    try:
        context.bot.kick_chat_member(chat_id=data[0], user_id=data[1],
                                     until_date=datetime.timestamp(datetime.today()) + config['BANTIME'])
    except BadRequest:
        logger.warning(
            f"Not enough rights to kick chat member {data[1]} at group {data[0]}")


@run_async
def clean(context):
    data = context.job.context.split('|')
    try:
        context.bot.delete_message(chat_id=data[0], message_id=data[1])
    except BadRequest:
        logger.warning(
            f"Not enough rights to delete message {data[1]} for chat {data[0]}")


@run_async
def newmem(update, context):
    message_id = update.message.message_id
    chat = update.message.chat
    from_user = update.message.from_user
    new_chat_members = update.message.new_chat_members
    num = random.randint(0, len(config['CHALLENGE']) - 1)
    flag = config['CHALLENGE'][num]
    if from_user.id not in [admin.user.id for admin in context.bot.get_chat_administrators(chat.id)]:
        for user in new_chat_members:
            if not user.is_bot:
                try:
                    context.bot.restrict_chat_member(
                        chat_id=chat.id,
                        user_id=user.id,
                        permissions=ChatPermissions(can_send_messages=False)
                    )
                except BadRequest:
                    logger.warning(
                        f"Not enough rights to restrict chat member {chat.id} at group {user.id}")
                buttons = [[InlineKeyboardButton(
                    text=flag['ANSWER'],
                    callback_data=f"challenge|{user.id}|{num}|{flag['answer']}"
                )]]
                for t in range(len(flag['WRONG'])):
                    buttons.append([InlineKeyboardButton(
                        text=flag['WRONG'][t],
                        callback_data=f"challenge|{user.id}|{num}|{flag['wrong'][t]}")]
                    )
                random.shuffle(buttons)
                buttons.append([InlineKeyboardButton(
                    text=config['PASS_BTN'],
                    callback_data=f"admin|pass|{user.id}"),
                    InlineKeyboardButton(
                    text=config['KICK_BTN'],
                    callback_data=f"admin|kick|{user.id}")]
                )
                msg = update.message.reply_text(config['GREET'].format(question=flag['QUESTION'], time=config['TIME']),
                                                reply_markup=InlineKeyboardMarkup(buttons))
                queue[f'{chat.id}{user.id}kick'] = updater.job_queue.run_once(
                    kick, config['TIME'], context=f"{chat.id}|{user.id}")
                queue[f'{chat.id}{user.id}clean1'] = updater.job_queue.run_once(
                    clean, config['TIME'], context=f"{chat.id}|{message_id}")
                queue[f'{chat.id}{user.id}clean2'] = updater.job_queue.run_once(
                    clean, config['TIME'], context=f"{chat.id}|{msg.message_id}")


@run_async
def query(update, context):
    user = update.callback_query.from_user
    message = update.callback_query.message
    chat = message.chat
    data = update.callback_query.data.split('|')
    if user.id == int(data[1]):
        if data[3] == config['CHALLENGE'][int(data[2])]['answer']:
            context.bot.answer_callback_query(
                text=config['SUCCESS'],
                show_alert=False,
                callback_query_id=update.callback_query.id
            )
            context.bot.edit_message_text(
                text=config['PASS'].format(user=f"[{user.first_name}](tg://user?id={user.id})"),
                message_id=message.message_id,
                chat_id=chat.id, parse_mode='Markdown'
            )
            try:
                context.bot.restrict_chat_member(
                    chat_id=chat.id,
                    user_id=user.id,
                    permissions=ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_polls=True, can_send_other_messages=True, can_add_web_page_previews=True, can_change_info=True, can_invite_users=True, can_pin_messages=True)
                )
            except BadRequest:
                logger.warning(
                    f"Not enough rights to restrict chat member {chat.id} at group {user.id}")
            queue[f'{chat.id}{user.id}clean1'].schedule_removal()
        else:
            context.bot.answer_callback_query(
                text=config['RETRY'].format(time=config['BANTIME']),
                show_alert=True,
                callback_query_id=update.callback_query.id
            )
            for t in range(len(config['CHALLENGE'][int(data[2])]['wrong'])):
                if config['CHALLENGE'][int(data[2])]['wrong'][t] == data[3]:
                    ans = config['CHALLENGE'][int(data[2])]['WRONG'][t]
            try:
                context.bot.kick_chat_member(chat_id=chat.id, user_id=user.id,
                                             until_date=datetime.timestamp(datetime.today()) + config['BANTIME'])
            except BadRequest:
                context.bot.edit_message_text(
                    text=config['NOT_KICK'].format(user=f"[{user.first_name}](tg://user?id={user.id})" ,question=config['CHALLENGE'][int(data[2])]['QUESTION'], ans=ans),
                    message_id=message.message_id,
                    chat_id=chat.id, parse_mode='Markdown')
                logger.warning(
                    f"Not enough rights to kick chat member {chat.id} at group {user.id}")
            else:
                context.bot.edit_message_text(
                    text=config['KICK'].format(user=f"[{user.first_name}](tg://user?id={user.id})", question=config['CHALLENGE'][int(data[2])]['QUESTION'], ans=ans),
                    message_id=message.message_id,
                    chat_id=chat.id, parse_mode='Markdown')
        queue[f'{chat.id}{user.id}kick'].schedule_removal()
    else:
        context.bot.answer_callback_query(
            text=config['OTHER'], show_alert=True, callback_query_id=update.callback_query.id)


@run_async
def admin(update, context):
    user = update.callback_query.from_user
    message = update.callback_query.message
    chat = message.chat
    data = update.callback_query.data.split('|')
    if data[1] == 'pass':
        if user.id in [admin.user.id for admin in context.bot.get_chat_administrators(chat.id)]:
            context.bot.answer_callback_query(
                text=config['PASS_BTN'], show_alert=False, callback_query_id=update.callback_query.id)
            context.bot.edit_message_text(
                text=config['ADMIN_PASS'].format(admin=f"[{user.first_name}](tg://user?id={user.id})", user=f"[{data[2]}](tg://user?id={data[2]})"),
                message_id=message.message_id,
                chat_id=chat.id, parse_mode='Markdown'
            )
            try:
                context.bot.restrict_chat_member(
                    chat_id=chat.id,
                    user_id=int(data[2]),
                    permissions=ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_polls=True, can_send_other_messages=True, can_add_web_page_previews=True, can_change_info=True, can_invite_users=True, can_pin_messages=True)
                )
            except BadRequest:
                logger.warning(
                    f"Not enough rights to restrict chat member {data[2]} at group {chat.id}")
            queue[f'{chat.id}{data[2]}kick'].schedule_removal()
            queue[f'{chat.id}{data[2]}clean1'].schedule_removal()
        else:
            context.bot.answer_callback_query(
                text=config['OTHER'], show_alert=True, callback_query_id=update.callback_query.id)
    elif data[1] == 'kick':
        if user.id in [admin.user.id for admin in context.bot.get_chat_administrators(chat.id)]:
            context.bot.answer_callback_query(
                text=config['KICK_BTN'], show_alert=False, callback_query_id=update.callback_query.id)
            context.bot.edit_message_text(
                text=config['ADMIN_KICK'].format(admin=f"[{user.first_name}](tg://user?id={user.id})", user=f"[{data[2]}](tg://user?id={data[2]})"),
                message_id=message.message_id,
                chat_id=chat.id, parse_mode='Markdown'
            )
            try:
                context.bot.kick_chat_member(chat_id=chat.id, user_id=int(data[2]),
                                             until_date=datetime.timestamp(datetime.today()) + config['BANTIME'])
            except BadRequest:
                logger.warning(
                    f"Not enough rights to kick chat member {data[2]} at group {chat.id}")
            queue[f'{chat.id}{data[2]}kick'].schedule_removal()
        else:
            context.bot.answer_callback_query(
                text=config['OTHER'], show_alert=True, callback_query_id=update.callback_query.id)


if __name__ == '__main__':
    updater = Updater(config['TOKEN'], use_context=True)
    updater.dispatcher.add_handler(CommandHandler("start", start))
    updater.dispatcher.add_handler(MessageHandler(
        Filters.status_update.new_chat_members, newmem))
    updater.dispatcher.add_handler(
        CallbackQueryHandler(query, pattern=r'challenge'))
    updater.dispatcher.add_handler(
        CallbackQueryHandler(admin, pattern=r'admin'))
    updater.dispatcher.add_error_handler(error)
    updater.start_polling()
    updater.idle()
