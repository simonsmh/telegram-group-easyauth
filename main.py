#!/usr/bin/env python
# -*- coding: utf-8 -*-
import logging
import os
import random
import sys
import time
from hashlib import blake2b

from telegram import ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, ChatMigrated, NetworkError, TelegramError, TimedOut, Unauthorized
from telegram.ext import CallbackQueryHandler, CommandHandler, Filters, MessageHandler, PicklePersistence, Updater
from telegram.ext.dispatcher import run_async
from yaml import dump, load

from utils import FullChatPermissions, get_chat_admins

try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO)

logger = logging.getLogger(__name__)


def parse_callback(data):
    data = data.split("|")
    print(data)
    if data[0] == "challenge":
        user_id = int(data[1])
        number = int(data[2])
        answer_encode = data[3]
        question = config["CHALLENGE"][number]["QUESTION"]
        if answer_encode == config["CHALLENGE"][number]["answer"]:
            result = True
            answer = config["CHALLENGE"][number]["ANSWER"]
        else:
            result = False
            for t in range(len(config["CHALLENGE"][number]["wrong"])):
                if answer_encode == config["CHALLENGE"][number]["wrong"][t]:
                    answer = config["CHALLENGE"][number]["WRONG"][t]
                    break
        logger.info(
            "New challenge parse callback:\nuser_id: %d\nresult: %r\nquestion: %s\nanswer: %s",
            user_id,
            result,
            question,
            answer,
        )
        return user_id, result, question, answer
    elif data[0] == "admin":
        if data[1] == "pass":
            result = True
        else:
            result = False
        user_id = int(data[2])
        logger.info("New admin parse callback:\nuser_id: %d\nresult: %r",
                    user_id, result)
        return result, user_id
    return


@run_async
def start(update, context):
    update.message.reply_text(config["START"])
    logger.info("Current Jobs: %s",
                str([t.name for t in context.job_queue.jobs()]))


@run_async
def error(update, context):
    logger.warning('Update "%s" caused error "%s"', context, error)


def kick(context, chat_id, user_id):
    if context.bot.kick_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            until_date=int(time.time()) + config["BANTIME"],
    ):
        logger.info(
            f"Job kick: Successfully kicked user {user_id} at group {chat_id}")
        return True
    else:
        logger.warning(
            f"Job kick: No enough permissions to kick user {user_id} at group {chat_id}"
        )
        return False


@run_async
def kick_queue(context):
    job = context.job
    kick(context, job.context["chat_id"], job.context["user_id"])


def restore(context, chat_id, user_id):
    if context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=FullChatPermissions,
    ):
        logger.info(
            f"Job restore: Successfully restored user {user_id} at group {chat_id}"
        )
        return True
    else:
        logger.warning(
            f"Job restore: No enough permissions to restore user {user_id} at group {chat_id}"
        )
        return False


def clean(context, chat_id, user_id, message_id):
    if context.bot.delete_message(chat_id=chat_id, message_id=message_id):
        logger.info(
            f"Job clean: Successfully delete message {message_id} from {user_id} at group {chat_id}"
        )
        return True
    else:
        logger.warning(
            f"Job clean: No enough permissions to delete message {message_id} from {user_id} at group {chat_id}"
        )
        return False


@run_async
def clean_queue(context):
    job = context.job
    clean(
        context,
        job.context["chat_id"],
        job.context["user_id"],
        job.context["message_id"],
    )


@run_async
def newmem(update, context):
    message = update.message
    chat = message.chat
    if message.from_user.id in get_chat_admins(context.bot, chat.id):
        return
    for user in message.new_chat_members:
        if user.is_bot:
            continue
        num = random.randint(0, len(config["CHALLENGE"]) - 1)
        flag = config["CHALLENGE"][num]
        if context.bot.restrict_chat_member(
                chat_id=chat.id,
                user_id=user.id,
                permissions=ChatPermissions(can_send_messages=False),
        ):
            logger.info(
                f"New member: Successfully restricted user {user.id} at group {chat.id}"
            )
        else:
            logger.warning(
                f"New member: No enough permissions to restrict user {user.id} at group {chat.id}"
            )
        buttons = [[
            InlineKeyboardButton(
                text=flag["ANSWER"],
                callback_data=f"challenge|{user.id}|{num}|{flag['answer']}",
            )
        ]]
        for t in range(len(flag["WRONG"])):
            buttons.append([
                InlineKeyboardButton(
                    text=flag["WRONG"][t],
                    callback_data=
                    f"challenge|{user.id}|{num}|{flag['wrong'][t]}",
                )
            ])
        random.shuffle(buttons)
        buttons.append([
            InlineKeyboardButton(
                text=config["PASS_BTN"],
                callback_data=f"admin|pass|{user.id}",
            ),
            InlineKeyboardButton(
                text=config["KICK_BTN"],
                callback_data=f"admin|kick|{user.id}",
            ),
        ])
        question_message = message.reply_text(
            config["GREET"].format(question=flag["QUESTION"],
                                   time=config["TIME"]),
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        updater.job_queue.run_once(
            kick_queue,
            config["TIME"],
            context={
                "chat_id": chat.id,
                "user_id": user.id,
            },
            name=f"{chat.id}|{user.id}|kick",
        )
        updater.job_queue.run_once(
            clean_queue,
            config["TIME"],
            context={
                "chat_id": chat.id,
                "user_id": user.id,
                "message_id": message.message_id,
            },
            name=f"{chat.id}|{user.id}|clean_join",
        )
        updater.job_queue.run_once(
            clean_queue,
            config["TIME"],
            context={
                "chat_id": chat.id,
                "user_id": user.id,
                "message_id": question_message.message_id,
            },
            name=f"{chat.id}|{user.id}|clean_question",
        )


@run_async
def query(update, context):
    callback_query = update.callback_query
    user = callback_query.from_user
    message = callback_query.message
    chat = message.chat
    user_id, result, question, answer = parse_callback(callback_query.data)
    if user.id != user_id:
        context.bot.answer_callback_query(
            text=config["OTHER"],
            show_alert=True,
            callback_query_id=callback_query.id,
        )
        return
    cqconf = (config["SUCCESS"] if result else config["RETRY"].format(
        time=config["BANTIME"]))
    context.bot.answer_callback_query(
        text=cqconf,
        show_alert=True,
        callback_query_id=callback_query.id,
    )
    if result:
        conf = config["PASS"]
        restore(context, chat.id, user_id)
        for job in context.job_queue.get_jobs_by_name(
                f"{chat.id}|{user.id}|clean_join"):
            job.schedule_removal()
    else:
        if kick(context, chat.id, user_id):
            conf = config["KICK"]
        else:
            conf = config["NOT_KICK"]
    context.bot.edit_message_text(
        text=conf.format(
            user=f"[{user.full_name}](tg://user?id={user.id})",
            question=question,
            ans=answer,
        ),
        message_id=message.message_id,
        chat_id=chat.id,
        parse_mode="Markdown",
    )
    for job in context.job_queue.get_jobs_by_name(f"{chat.id}|{user.id}|kick"):
        job.schedule_removal()


@run_async
def admin(update, context):
    callback_query = update.callback_query
    user = callback_query.from_user
    message = callback_query.message
    chat = message.chat
    if user.id not in get_chat_admins(context.bot, chat.id):
        context.bot.answer_callback_query(
            text=config["OTHER"],
            show_alert=True,
            callback_query_id=callback_query.id,
        )
        return
    result, user_id = parse_callback(callback_query.data)
    cqconf = config["PASS_BTN"] if result else config["KICK_BTN"]
    conf = config["ADMIN_PASS"] if result else config["ADMIN_KICK"]
    context.bot.answer_callback_query(
        text=cqconf,
        show_alert=False,
        callback_query_id=callback_query.id,
    )
    if result:
        restore(context, chat.id, user_id)
        for job in context.job_queue.get_jobs_by_name(
                f"{chat.id}|{user.id}|clean_join"):
            job.schedule_removal()
    else:
        kick(context, chat.id, user_id)
    context.bot.edit_message_text(
        text=conf.format(
            admin=f"[{user.full_name}](tg://user?id={user.id})",
            user=f"[{user_id}](tg://user?id={user_id})",
        ),
        message_id=message.message_id,
        chat_id=chat.id,
        parse_mode="Markdown",
    )
    for job in context.job_queue.get_jobs_by_name(f"{chat.id}|{user.id}|kick"):
        job.schedule_removal()


if __name__ == "__main__":
    if len(sys.argv) >= 2 and os.path.exists(sys.argv[1]):
        config = load(open(sys.argv[1]), Loader=Loader)
        name = sys.argv[1]
    else:
        try:
            name = "config.yml"
            config = load(
                open(f"{os.path.split(os.path.realpath(__file__))[0]}/{name}"),
                Loader=Loader,
            )
        except FileNotFoundError:
            logger.exception(f"Cannot find {name}.")
            sys.exit(1)
    logger.info(f"Loaded {name}")
    for flag in config["CHALLENGE"]:
        digest_size = len(flag["WRONG"])
        flag["wrong"] = []
        for t in range(digest_size):
            flag["wrong"].append(
                blake2b(str(flag["WRONG"][t]).encode(),
                        digest_size=digest_size).hexdigest())
        flag["answer"] = blake2b(str(flag["ANSWER"]).encode(),
                                 digest_size=digest_size).hexdigest()

    pp = PicklePersistence(filename=f"{name}.pickle", on_flush=True)
    updater = Updater(config["TOKEN"], persistence=pp, use_context=True)
    updater.dispatcher.add_handler(CommandHandler("start", start))
    updater.dispatcher.add_handler(
        MessageHandler(Filters.status_update.new_chat_members, newmem))
    updater.dispatcher.add_handler(
        CallbackQueryHandler(query, pattern=r"challenge"))
    updater.dispatcher.add_handler(
        CallbackQueryHandler(admin, pattern=r"admin"))
    updater.dispatcher.add_error_handler(error)
    updater.start_polling()
    updater.idle()
