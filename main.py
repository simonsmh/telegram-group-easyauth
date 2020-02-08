#!/usr/bin/env python
# -*- coding: utf-8 -*-
import copy
import logging
import os
import random
import sys
import time
from hashlib import blake2s

from telegram import (
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ParseMode,
)
from telegram.error import (
    BadRequest,
    ChatMigrated,
    NetworkError,
    TelegramError,
    TimedOut,
    Unauthorized,
)
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    Filters,
    MessageHandler,
    PicklePersistence,
    Updater,
)
from telegram.ext.dispatcher import run_async
from telegram.ext.filters import MergedFilter
from telegram.utils.helpers import mention_markdown

from utils import FullChatPermissions, collect_error, get_chat_admins, logger, yaml


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
            f"New challenge parse callback:\nuser_id: {user_id}\nresult: {result}\nquestion: {question}\nanswer: {answer}"
        )
        return user_id, result, question, answer
    elif data[0] == "admin":
        if data[1] == "pass":
            result = True
        else:
            result = False
        user_id = int(data[2])
        logger.info(f"New admin parse callback:\nuser_id: {user_id}\nresult: {result}")
        return result, user_id
    elif data[0] in [
        "detail_question_private",
        "edit_question_private",
        "delete_question_private",
    ]:
        number = int(data[1])
        logger.info(f"New private parse callback:\nresult: {number}")
        return number
    return


@run_async
def start_command(update, context):
    message = update.message
    chat = message.chat
    user = message.from_user
    message.reply_text(
        config.get("START").format(chat=chat.id, user=user.id),
        parse_mode=ParseMode.MARKDOWN,
    )
    logger.info(f"Current Jobs: {[t.name for t in context.job_queue.jobs()]}")


@run_async
def error(update, context):
    logger.warning(f"Update {context} caused error {error}")


def kick(context, chat_id, user_id):
    if context.bot.kick_chat_member(
        chat_id=chat_id,
        user_id=user_id,
        until_date=int(time.time()) + config.get("BANTIME"),
    ):
        logger.info(f"Job kick: Successfully kicked user {user_id} at group {chat_id}")
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
        chat_id=chat_id, user_id=user_id, permissions=FullChatPermissions,
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
    if message.from_user.id in get_chat_admins(
        context.bot, chat.id, config.get("SUPER_ADMIN")
    ):
        return
    for user in message.new_chat_members:
        if user.is_bot:
            continue
        num = random.randint(0, config.get("number") - 1)
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
        buttons = [
            [
                InlineKeyboardButton(
                    flag["WRONG"][t],
                    callback_data=f"challenge|{user.id}|{num}|{flag['wrong'][t]}",
                )
            ]
            for t in range(len(flag.get("WRONG")))
        ]
        buttons.append(
            [
                InlineKeyboardButton(
                    flag.get("ANSWER"),
                    callback_data=f"challenge|{user.id}|{num}|{flag.get('answer')}",
                )
            ]
        )
        random.shuffle(buttons)
        buttons.append(
            [
                InlineKeyboardButton(
                    config.get("PASS_BTN"), callback_data=f"admin|pass|{user.id}",
                ),
                InlineKeyboardButton(
                    config.get("KICK_BTN"), callback_data=f"admin|kick|{user.id}",
                ),
            ]
        )
        question_message = message.reply_text(
            config.get("GREET").format(
                question=flag.get("QUESTION"), time=config.get("TIME")
            ),
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.MARKDOWN,
        )
        updater.job_queue.run_once(
            kick_queue,
            config.get("TIME"),
            context={"chat_id": chat.id, "user_id": user.id,},
            name=f"{chat.id}|{user.id}|kick",
        )
        updater.job_queue.run_once(
            clean_queue,
            config.get("TIME"),
            context={
                "chat_id": chat.id,
                "user_id": user.id,
                "message_id": message.message_id,
            },
            name=f"{chat.id}|{user.id}|clean_join",
        )
        updater.job_queue.run_once(
            clean_queue,
            config.get("TIME"),
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
        callback_query.answer(
            text=config.get("OTHER"), show_alert=True,
        )
        return
    cqconf = (
        config.get("SUCCESS")
        if result
        else config.get("RETRY").format(time=config.get("BANTIME"))
    )
    callback_query.answer(
        text=cqconf, show_alert=False if result else True,
    )
    if result:
        conf = config.get("PASS")
        restore(context, chat.id, user_id)
        for job in context.job_queue.get_jobs_by_name(
            f"{chat.id}|{user.id}|clean_join"
        ):
            job.schedule_removal()
    else:
        if kick(context, chat.id, user_id):
            conf = config.get("KICK")
        else:
            conf = config.get("NOT_KICK")
    message.edit_text(
        conf.format(
            user=mention_markdown(user.id, user.full_name),
            question=question,
            ans=answer,
        ),
        parse_mode=ParseMode.MARKDOWN,
    )
    for job in context.job_queue.get_jobs_by_name(f"{chat.id}|{user.id}|kick"):
        job.schedule_removal()


@run_async
def admin(update, context):
    callback_query = update.callback_query
    user = callback_query.from_user
    message = callback_query.message
    chat = message.chat
    if user.id not in get_chat_admins(context.bot, chat.id, config.get("SUPER_ADMIN")):
        callback_query.answer(
            text=config.get("OTHER"), show_alert=True,
        )
        return
    result, user_id = parse_callback(callback_query.data)
    cqconf = config.get("PASS_BTN") if result else config.get("KICK_BTN")
    conf = config.get("ADMIN_PASS") if result else config.get("ADMIN_KICK")
    callback_query.answer(
        text=cqconf, show_alert=False,
    )
    if result:
        restore(context, chat.id, user_id)
        for job in context.job_queue.get_jobs_by_name(
            f"{chat.id}|{user.id}|clean_join"
        ):
            job.schedule_removal()
    else:
        kick(context, chat.id, user_id)
    message.edit_text(
        conf.format(
            admin=mention_markdown(user.id, user.full_name),
            user=mention_markdown(user_id, user_id),
        ),
        parse_mode=ParseMode.MARKDOWN,
    )
    for job in context.job_queue.get_jobs_by_name(f"{chat.id}|{user.id}|kick"):
        job.schedule_removal()


def load_yaml(filename="config.yml"):
    try:
        with open(filename, "r") as file:
            config = yaml.load(file)
    except FileNotFoundError:
        try:
            filename = f"{os.path.split(os.path.realpath(__file__))[0]}/{filename}"
            with open(filename, "r") as file:
                config = yaml.load(file)
        except FileNotFoundError:
            logger.exception(f"Cannot find {filename}.")
            sys.exit(1)
    logger.info(f"Yaml: Loaded {filename}")
    config["filename"] = filename
    return config


def load_config():
    if len(sys.argv) >= 2 and os.path.exists(sys.argv[1]):
        filename = sys.argv[1]
        config = load_yaml(filename)
    else:
        config = load_yaml()
    if config.get("CHAT"):
        assert isinstance(config.get("CHAT"), int), "Config: CHAT Must be ID, not username."
    else:
        logger.warning(f"Config: CHAT is not set! Use /start to get one in chat.")
    if config.get("SUPER_ADMIN"):
        assert isinstance(config.get("SUPER_ADMIN"), int), "Config: SUPER_ADMIN Must be ID, not username."
    for flag in config.get("CHALLENGE"):
        assert flag.get("QUESTION"), "Config: No QUESTION tile for question."
        assert isinstance(flag.get("QUESTION"), str), f"Config: QUESTION {flag.get('QUESTION')} should be string object."
        assert flag.get("ANSWER"), f"Config: No ANSWER tile for question: {flag.get('QUESTION')}"
        assert isinstance(flag.get("ANSWER"), str), f"Config: ANSWER {flag.get('ANSWER')} should be string object for question: {flag.get('QUESTION')}"
        assert flag.get("WRONG"), f"Config: No WRONG tile for question: {flag.get('QUESTION')}"
        assert (
            digest_size := len(flag.get("WRONG"))
        ) < 20, f"Config: Too many tiles for WRONG for question: {flag.get('QUESTION')}"
        assert all(isinstance(u, str) for u in flag.get("WRONG")), f"Config: WRONG {flag.get('WRONG')} should all be string object for question: {flag.get('QUESTION')}"
        flag["answer"] = blake2s(
            str(flag.get("ANSWER")).encode(),
            salt=os.urandom(8),
            digest_size=digest_size,
        ).hexdigest()
        flag["wrong"] = [
            blake2s(
                str(flag["WRONG"][t]).encode(),
                salt=os.urandom(8),
                digest_size=digest_size,
            ).hexdigest()
            for t in range(digest_size)
        ]
    config["number"] = len(config.get("CHALLENGE"))
    logger.debug(config)
    return config


def save_config(config, name=None):
    save = copy.deepcopy(config)
    if not name:
        name = f"{save.get('filename')}.bak"
    save.pop("filename")
    save.pop("number")
    for flag in save.get("CHALLENGE"):
        if flag.get("answer"):
            flag.pop("answer")
        if flag.get("wrong"):
            flag.pop("wrong")
    with open(name, "w") as file:
        yaml.dump(save, file)
    logger.info(f"Config: Dumped {name}")
    logger.debug(save)


def reload_config(context):
    for job in context.job_queue.get_jobs_by_name("reload"):
        job.schedule_removal()
    jobs = [t.name for t in context.job_queue.jobs()]
    global config
    if jobs:
        context.job_queue.run_once(reload_config, config.get("TIME"), name="reload")
        logger.info(f"Job reload: Waiting for {jobs}")
        return False
    else:
        config = load_config()
        logger.info(f"Job reload: Successfully reloaded {config.get('filename')}")
        return True


@run_async
def reload_command(update, context):
    message = update.message
    chat = message.chat
    user = message.from_user
    if user.id not in get_chat_admins(context.bot, chat.id, config.get("SUPER_ADMIN")):
        logger.info(f"Reload: User {user.id} is unauthorized, blocking")
        message.reply_text(config.get("START_UNAUTHORIZED_PRIVATE"))
        return
    message.reply_text(
        config.get("RELOAD").format(num=config.get("number"))
        if reload_config(context)
        else config.get("PENDING"),
    )


@collect_error
def start_private(update, context):
    message = update.message
    callback_query = update.callback_query
    if callback_query:
        callback_query.answer()
        user = callback_query.from_user
    else:
        user = message.from_user
    if user.id not in get_chat_admins(
        context.bot, config.get("CHAT"), config.get("SUPER_ADMIN")
    ):
        logger.info(f"Private: User {user.id} is unauthorized, blocking")
        message.reply_text(config.get("START_UNAUTHORIZED_PRIVATE"))
        return ConversationHandler.END
    keyboard = [
        [InlineKeyboardButton(config.get("SAVE_QUESTION_BTN"), callback_data="save")],
        [
            InlineKeyboardButton(
                config.get("ADD_NEW_QUESTION_BTN"),
                callback_data=f'edit_question_private|{config.get("number")}',
            )
        ],
        [
            InlineKeyboardButton(
                config.get("LIST_ALL_QUESTION_BTN"),
                callback_data="list_question_private",
            )
        ],
    ]
    markup = InlineKeyboardMarkup(keyboard)
    if callback_query:
        callback_query.edit_message_text(
            config.get("START_PRIVATE").format(link=config.get("CHAT")),
            reply_markup=markup,
        )
    else:
        message.reply_text(
            config.get("START_PRIVATE").format(link=config.get("CHAT")),
            reply_markup=markup,
        )
    logger.info("Private: Start")
    logger.debug(callback_query)
    return CHOOSING


@collect_error
def list_question_private(update, context):
    callback_query = update.callback_query
    callback_query.answer()
    keyboard = [
        [
            InlineKeyboardButton(
                flag.get("QUESTION"), callback_data=f"detail_question_private|{num}"
            )
        ]
        for (num, flag) in enumerate(config.get("CHALLENGE"))
    ]
    keyboard.insert(0, [InlineKeyboardButton(config.get("BACK"), callback_data="back")])
    markup = InlineKeyboardMarkup(keyboard)
    callback_query.edit_message_text(config.get("LIST_PRIVATE"), reply_markup=markup)
    logger.info("Private: List question")
    logger.debug(callback_query)
    return LIST_VIEW


@collect_error
def detail_question_private(update, context):
    callback_query = update.callback_query
    callback_query.answer()
    num = parse_callback(callback_query.data)
    keyboard = [
        [InlineKeyboardButton(config.get("BACK"), callback_data="back")],
        [
            InlineKeyboardButton(
                config.get("EDIT_QUESTION_BTN"),
                callback_data=f"edit_question_private|{num}",
            )
        ],
        [
            InlineKeyboardButton(
                config.get("DELETE_QUESTION_BTN"),
                callback_data=f"delete_question_private|{num}",
            )
        ],
    ]
    markup = InlineKeyboardMarkup(keyboard)
    flag = config["CHALLENGE"][num]
    callback_query.edit_message_text(
        config.get("DETAIL_QUESTION_PRIVATE").format(
            question=flag.get("QUESTION"),
            ans=flag.get("ANSWER"),
            wrong="\n".join(flag.get("WRONG")),
        ),
        reply_markup=markup,
    )
    logger.info("Private: Detail question")
    logger.debug(callback_query)
    return DETAIL_VIEW


@run_async
def save_private(context, callback_query):
    save_config(config, config.get("filename"))
    context.chat_data.clear()
    keyboard = [
        [InlineKeyboardButton(config.get("BACK"), callback_data="back")],
    ]
    markup = InlineKeyboardMarkup(keyboard)
    callback_query.edit_message_text(
        config.get("RELOAD").format(num=config.get("number"))
        if reload_config(context)
        else config.get("PENDING"),
        reply_markup=markup,
    )
    logger.info(f"Private: Saved config")
    logger.debug(config)


@collect_error
def delete_question_private(update, context):
    callback_query = update.callback_query
    callback_query.answer()
    callback_query.edit_message_text(config.get("DELETING_PRIVATE"))
    num = parse_callback(callback_query.data)
    tile = config["CHALLENGE"].pop(num)
    logger.info(f"Private: Delete question {tile}")
    save_private(context, callback_query)
    return DETAIL_VIEW


@collect_error
def edit_question_private(update, context):
    message = update.message
    callback_query = update.callback_query
    if callback_query:
        text = "Begin"
        callback_query.answer()
        index = parse_callback(callback_query.data)
        context.chat_data.clear()
        context.chat_data["index"] = index
        callback_query.edit_message_text(
            config.get("EDIT_QUESTION_PRIVATE").format(num=index + 1)
        )
    elif message:
        text = message.text
        if not context.chat_data.get("QUESTION"):
            context.chat_data["QUESTION"] = text
            return_text = config.get("EDIT_ANSWER_PRIVATE").format(text=text)
        elif not context.chat_data.get("ANSWER"):
            context.chat_data["ANSWER"] = text
            return_text = config.get("EDIT_WRONG_PRIVATE").format(text=text)
        else:
            if not context.chat_data.get("WRONG"):
                context.chat_data["WRONG"] = list()
            context.chat_data["WRONG"].append(text)
            return_text = config.get("EDIT_MORE_WRONG_PRIVATE").format(text=text)
        message.reply_text(config.get("EDIT_PRIVATE").format(text=return_text))
        logger.info(f"Private: Edit question {text}")
    return QUESTION_EDIT


@collect_error
def finish_edit_private(update, context):
    message = update.message
    if not context.chat_data.get("WRONG"):
        logger.info(context.chat_data)
        message.reply_text(config.get("EDIT_UNFINISH_PRIVATE"))
        return QUESTION_EDIT
    index = context.chat_data.get("index")
    keyboard = [
        [InlineKeyboardButton(config.get("SAVE_QUESTION_BTN"), callback_data="save")],
        [
            InlineKeyboardButton(
                config.get("REEDIT_QUESTION_BTN"),
                callback_data=f"edit_question_private|{index}",
            )
        ],
    ]
    markup = InlineKeyboardMarkup(keyboard)
    message.reply_text(
        "\n".join(
            [
                config.get("EDIT_FINISH_PRIVATE").format(num=index + 1),
                config.get("DETAIL_QUESTION_PRIVATE").format(
                    question=context.chat_data.get("QUESTION"),
                    ans=context.chat_data.get("ANSWER"),
                    wrong="\n".join(context.chat_data.get("WRONG")),
                ),
            ]
        ),
        reply_markup=markup,
    )
    context.chat_data.pop("index")
    logger.info(f"Private: Finish edit {context.chat_data}")
    return DETAIL_VIEW


@collect_error
def save_question_private(update, context):
    callback_query = update.callback_query
    callback_query.answer()
    callback_query.edit_message_text(config.get("SAVING_PRIVATE"))
    if context.chat_data:
        config["CHALLENGE"].append(context.chat_data)
        logger.info(f"Private: Saving question {context.chat_data}")
    save_private(context, callback_query)
    return DETAIL_VIEW


@collect_error
def cancel_private(update, context):
    message = update.message
    context.chat_data.clear()
    message.reply_text(config.get("CANCEL_PRIVATE"))
    logger.info(f"Private: Cancel")
    return ConversationHandler.END


if __name__ == "__main__":
    config = load_config()
    save_config(config)
    pp = PicklePersistence(filename=f"{config.get('filename')}.pickle", on_flush=True)
    updater = Updater(config.get("TOKEN"), persistence=pp, use_context=True)
    chatfilter = Filters.chat(config.get("CHAT")) if config.get("CHAT") else None
    updater.dispatcher.add_handler(
        CommandHandler("start", start_command, filters=Filters.group)
    )
    updater.dispatcher.add_handler(
        CommandHandler("reload", reload_command, filters=chatfilter)
    )
    updater.dispatcher.add_handler(
        MessageHandler(
            MergedFilter(Filters.status_update.new_chat_members, and_filter=chatfilter),
            newmem,
        )
    )
    updater.dispatcher.add_handler(CallbackQueryHandler(query, pattern=r"^challenge\|"))
    updater.dispatcher.add_handler(CallbackQueryHandler(admin, pattern=r"^admin\|"))
    if config.get("CHAT"):
        CHOOSING, LIST_VIEW, DETAIL_VIEW, QUESTION_EDIT = range(4)
        conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler("start", start_private, filters=Filters.private)
            ],
            states={
                CHOOSING: [
                    CallbackQueryHandler(save_question_private, pattern=r"^save$"),
                    CallbackQueryHandler(
                        edit_question_private, pattern=r"^edit_question_private"
                    ),
                    CallbackQueryHandler(
                        list_question_private, pattern=r"^list_question_private"
                    ),
                ],
                LIST_VIEW: [
                    CallbackQueryHandler(start_private, pattern=r"^back$"),
                    CallbackQueryHandler(
                        detail_question_private, pattern=r"^detail_question_private"
                    ),
                ],
                DETAIL_VIEW: [
                    CallbackQueryHandler(save_question_private, pattern=r"^save$"),
                    CallbackQueryHandler(list_question_private, pattern=r"^back$"),
                    CallbackQueryHandler(
                        delete_question_private, pattern=r"^delete_question_private"
                    ),
                    CallbackQueryHandler(
                        edit_question_private, pattern=r"^edit_question_private"
                    ),
                ],
                QUESTION_EDIT: [
                    MessageHandler(Filters.text, edit_question_private),
                    CommandHandler("finish", finish_edit_private),
                ],
            },
            fallbacks=[CommandHandler("cancel", cancel_private)],
            name="setting",
            allow_reentry=True,
            persistent=True,
        )
        updater.dispatcher.add_handler(conv_handler)
    updater.dispatcher.add_error_handler(error)
    updater.start_polling()
    updater.idle()
