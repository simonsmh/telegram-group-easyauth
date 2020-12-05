#!/usr/bin/env python
# Source: http://code.activestate.com/recipes/325905-memoize-decorator-with-timeout/#c1
import logging
import logging.handlers
import os
import sys
import time
from hashlib import blake2s
from typing import IO, Any, Union

import ruamel.yaml
from telegram import ChatPermissions
from telegram.bot import Bot

FullChatPermissions = ChatPermissions(
    can_send_messages=True,
    can_send_media_messages=True,
    can_send_polls=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
    can_change_info=True,
    can_invite_users=True,
    can_pin_messages=True,
)

logger = logging.getLogger("Telegram_Group_Easyauth")
logger.setLevel(logging.DEBUG)

formater = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(funcName)s[%(module)s:%(lineno)d] - %(message)s"
)
streamhandler = logging.StreamHandler()
streamhandler.setLevel(logging.INFO)
streamhandler.setFormatter(formater)
logger.addHandler(streamhandler)


yaml = ruamel.yaml.YAML()


class MWT(object):
    """Memoize With Timeout"""

    _caches: dict = dict()
    _timeouts: dict = dict()

    def __init__(self, timeout: int = 2):
        self.timeout = timeout

    def collect(self):
        """Clear cache of results which have timed out"""
        for func in self._caches:
            cache = {}
            for key in self._caches[func]:
                if (time.time() - self._caches[func][key][1]) < self._timeouts[func]:
                    cache[key] = self._caches[func][key]
            self._caches[func] = cache

    def __call__(self, f):
        self.cache = self._caches[f] = {}
        self._timeouts[f] = self.timeout

        def func(*args, **kwargs):
            kw = sorted(kwargs.items())
            key = (args, tuple(kw))
            try:
                v = self.cache[key]
                if (time.time() - v[1]) > self.timeout:
                    raise KeyError
            except KeyError:
                v = self.cache[key] = f(*args, **kwargs), time.time()
            return v[0]

        func.func_name = f.__name__

        return func


@MWT(timeout=60 * 60)
def get_chat_admins(bot: Bot, chat_id: int, extra_user=None) -> list:
    if extra_user is not None and isinstance(extra_user, int):
        users: list = [extra_user]
    else:
        users: list = extra_user
    admins: list = [
        admin.user.id
        for admin in bot.get_chat_administrators(chat_id)
        if admin.user.id != bot.get_me().id
    ]
    if users:
        admins.extend(users)
    return admins


@MWT(timeout=60 * 60)
def get_chat_admins_name(bot: Bot, chat_id: int, extra_user=None) -> str:
    if extra_user is not None and isinstance(extra_user, int):
        users: list = [extra_user]
    else:
        users: list = extra_user
    admins: list = [
        f"@{admin.user.username}"
        for admin in bot.get_chat_administrators(chat_id)
        if admin.user.id != bot.get_me().id
    ]
    return " ".join(admins)


def save_yml(config: dict, file: Union[IO[str], IO[bytes]]) -> Any:
    return yaml.dump(config, file)


def load_yml(file: Union[IO[str], IO[bytes], bytes]) -> Any:
    return yaml.load(file)


def load_yml_path(filename: str = "config.yml") -> Any:
    try:
        with open(filename, "r", encoding="utf-8") as file:
            config = load_yml(file)
    except FileNotFoundError:
        try:
            filename = f"{os.path.split(os.path.realpath(__file__))[0]}/{filename}"
            with open(filename, "r", encoding="utf-8") as file:
                config = load_yml(file)
        except FileNotFoundError:
            logger.error(f"Cannot find {filename}.")
            sys.exit(1)
    logger.info(f"Yaml: Loaded {filename}")
    filehandler = logging.handlers.RotatingFileHandler(
        f"{filename}.log", maxBytes=1048576, backupCount=5, encoding="utf-8"
    )
    filehandler.setLevel(logging.DEBUG)
    filehandler.setFormatter(formater)
    logger.addHandler(filehandler)
    return config


def load_config(config: dict, check_token: bool = True) -> dict:
    if check_token:
        assert config.get("TOKEN"), "Config: No TOKEN."
    if config.get("CHAT"):
        assert isinstance(
            config.get("CHAT"), int
        ), "Config: CHAT Must be ID, not username."
    else:
        logger.warning("Config: CHAT is not set! Use /start to get one in chat.")
    if config.get("SUPER_ADMIN"):
        assert isinstance(
            config.get("SUPER_ADMIN"), int
        ), "Config: SUPER_ADMIN Must be ID, not username."
    if not config.get("TIME"):
        config["TIME"] = 120
    if not config.get("BANTIME"):
        config["BANTIME"] = 120
    if config.get("QUIZ"):
        assert (
            len(config.get("QUIZ", "")) > 2
        ), "Config: QUIZ command Should be longer than 2 chars"
        if not config.get("QUIZTIME"):
            config["QUIZTIME"] = 1200
    if config.get("ADMIN"):
        assert (
            len(config.get("ADMIN", "")) > 2
        ), "Config: ADMIN command Should be longer than 2 chars"
    if not config.get("START"):
        config["START"] = "CHAT ID: \\`{chat}\\`\nUSER ID: \\`{user}\\`"
    if not config.get("GREET"):
        config["GREET"] = "Question: {question}\nPlease answer it in {time}s."
    if not config.get("SUCCESS"):
        config["SUCCESS"] = "Succeed."
    if not config.get("RETRY"):
        config["RETRY"] = "Failed. Please retry after {time}s."
    if not config.get("PASS"):
        config[
            "PASS"
        ] = "{user} passed the verification.\nQuestion: {question}\nAnswer: {ans}"
    if not config.get("NOT_KICK"):
        config[
            "NOT_KICK"
        ] = "{user} didn't pass the verification.\nQuestion: {question}\nAnswer: {ans}"
    if not config.get("KICK"):
        config["KICK"] = "{user} have been kicked.\nQuestion: {question}\nAnswer: {ans}"
    if not config.get("PASS_BTN"):
        config["PASS_BTN"] = "Pass"
    if not config.get("KICK_BTN"):
        config["KICK_BTN"] = "Kick"
    if not config.get("ADMIN_PASS"):
        config["ADMIN_PASS"] = "{user} is allowed by admin {admin}."
    if not config.get("ADMIN_KICK"):
        config["ADMIN_KICK"] = "{user} is kicked by admin {admin}."
    if not config.get("OTHER"):
        config["OTHER"] = "Don't play with buttons."
    if not config.get("RELOAD"):
        config["RELOAD"] = "Reload finished. Now there are {num} questions."
    if not config.get("PENDING"):
        config["PENDING"] = "Adding reload task to task list."
    if not config.get("CORRUPT"):
        config["CORRUPT"] = "The file is corrupted.\n{text}"
    if not config.get("BACK"):
        config["BACK"] = "<- Back"
    if not config.get("ADD_NEW_QUESTION_BTN"):
        config["ADD_NEW_QUESTION_BTN"] = "Add new question"
    if not config.get("LIST_ALL_QUESTION_BTN"):
        config["LIST_ALL_QUESTION_BTN"] = "List all questions"
    if not config.get("EDIT_QUESTION_BTN"):
        config["EDIT_QUESTION_BTN"] = "Edit question"
    if not config.get("DELETE_QUESTION_BTN"):
        config["DELETE_QUESTION_BTN"] = "Delete question"
    if not config.get("SAVE_QUESTION_BTN"):
        config["SAVE_QUESTION_BTN"] = "Save question"
    if not config.get("REEDIT_QUESTION_BTN"):
        config["REEDIT_QUESTION_BTN"] = "Re-edit question"
    if not config.get("START_PRIVATE"):
        config[
            "START_PRIVATE"
        ] = "This bot is working for {link}.\n  /cancel -- exit\n  /config -- pull config\n  /reload -- reload config\nOr send config file to me directly."
    if not config.get("START_UNAUTHORIZED_PRIVATE"):
        config["START_UNAUTHORIZED_PRIVATE"] = "Unauthorized request."
    if not config.get("LIST_PRIVATE"):
        config["LIST_PRIVATE"] = "Current questions:"
    if not config.get("EDIT_PRIVATE"):
        config["EDIT_PRIVATE"] = "Editing questions: {text}"
    if not config.get("EDIT_QUESTION_PRIVATE"):
        config[
            "EDIT_QUESTION_PRIVATE"
        ] = "Editing questions No.{num}, please send your question:"
    if not config.get("EDIT_ANSWER_PRIVATE"):
        config["EDIT_ANSWER_PRIVATE"] = "Question: {text}\nPlease send your answer:"
    if not config.get("EDIT_WRONG_PRIVATE"):
        config[
            "EDIT_WRONG_PRIVATE"
        ] = "Answer: {text}\nPlease send your misleading text:"
    if not config.get("EDIT_MORE_WRONG_PRIVATE"):
        config[
            "EDIT_MORE_WRONG_PRIVATE"
        ] = "Misleading text: {text}\nPlease send more or /finish"
    if not config.get("DETAIL_QUESTION_PRIVATE"):
        config[
            "DETAIL_QUESTION_PRIVATE"
        ] = "Question: {question}\nAnswer: {ans}\nMisleading text:\n{wrong}"
    if not config.get("EDIT_UNFINISH_PRIVATE"):
        config["EDIT_UNFINISH_PRIVATE"] = "Need more misleading texts."
    if not config.get("EDIT_FINISH_PRIVATE"):
        config["EDIT_FINISH_PRIVATE"] = "Questions No.{num} finish."
    if not config.get("CANCEL_PRIVATE"):
        config["CANCEL_PRIVATE"] = "Process canceled."
    if not config.get("SAVING_PRIVATE"):
        config["SAVING_PRIVATE"] = "Saving..."
    if not config.get("DELETING_PRIVATE"):
        config["DELETING_PRIVATE"] = "Deleting..."
    for flag in config.get("CHALLENGE"):
        assert flag.get("QUESTION"), "Config: No QUESTION tile for question."
        assert isinstance(
            flag.get("QUESTION"), str
        ), f"Config: QUESTION {flag.get('QUESTION')} should be string object."
        assert flag.get(
            "ANSWER"
        ), f"Config: No ANSWER tile for question: {flag.get('QUESTION')}"
        assert isinstance(
            flag.get("ANSWER"), str
        ), f"Config: ANSWER {flag.get('ANSWER')} should be string object for question: {flag.get('QUESTION')}"
        assert flag.get(
            "WRONG"
        ), f"Config: No WRONG tile for question: {flag.get('QUESTION')}"
        assert (
            digest_size := len(flag.get("WRONG"))
        ) < 20, f"Config: Too many tiles for WRONG for question: {flag.get('QUESTION')}"
        assert all(
            isinstance(u, str) for u in flag.get("WRONG")
        ), f"Config: WRONG {flag.get('WRONG')} should all be string object for question: {flag.get('QUESTION')}"
        flag.insert(
            0,
            "answer",
            blake2s(
                str(flag.get("ANSWER")).encode(),
                salt=os.urandom(8),
                digest_size=digest_size,
            ).hexdigest(),
        )
        flag.insert(
            0,
            "wrong",
            [
                blake2s(
                    str(flag.get("WRONG")[t]).encode(),
                    salt=os.urandom(8),
                    digest_size=digest_size,
                ).hexdigest()
                for t in range(digest_size)
            ],
        )
    logger.debug(config)
    return config
