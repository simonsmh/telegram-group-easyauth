#!/usr/bin/env python
# Source: http://code.activestate.com/recipes/325905-memoize-decorator-with-timeout/#c1
import copy
import logging
import os
import sys
import time
import traceback
from hashlib import blake2s

import ruamel.yaml
from telegram import ChatPermissions

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

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)

logger = logging.getLogger("Telegram_Group_Easyauth")

yaml = ruamel.yaml.YAML()


class MWT(object):
    """Memoize With Timeout"""

    _caches = {}
    _timeouts = {}

    def __init__(self, timeout=2):
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
def get_chat_admins(bot, chat_id, extra_user):
    if extra_user is not None and isinstance(extra_user, int):
        users = [extra_user]
    else:
        users = extra_user
    admins = [admin.user.id for admin in bot.get_chat_administrators(chat_id)]
    if users:
        admins.extend(users)
    return admins


def collect_error(func):
    def wrapped(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception:
            logger.info(traceback.format_exc())

    return wrapped


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
    config.insert(0, "filename", filename)
    return config


def load_config():
    if len(sys.argv) >= 2 and os.path.exists(sys.argv[1]):
        filename = sys.argv[1]
        config = load_yaml(filename)
    else:
        config = load_yaml()
    if config.get("CHAT"):
        assert isinstance(
            config.get("CHAT"), int
        ), "Config: CHAT Must be ID, not username."
        assert config.get("BACK"), "Config: BACK Does not set"
        assert config.get(
            "ADD_NEW_QUESTION_BTN"
        ), "Config: ADD_NEW_QUESTION_BTN Does not set"
        assert config.get(
            "LIST_ALL_QUESTION_BTN"
        ), "Config: LIST_ALL_QUESTION_BTN Does not set"
        assert config.get("EDIT_QUESTION_BTN"), "Config: EDIT_QUESTION_BTN Does not set"
        assert config.get(
            "DELETE_QUESTION_BTN"
        ), "Config: DELETE_QUESTION_BTN Does not set"
        assert config.get("SAVE_QUESTION_BTN"), "Config: SAVE_QUESTION_BTN Does not set"
        assert config.get(
            "REEDIT_QUESTION_BTN"
        ), "Config: REEDIT_QUESTION_BTN Does not set"
        assert config.get("START_PRIVATE"), "Config: START_PRIVATE Does not set"
        assert config.get(
            "START_UNAUTHORIZED_PRIVATE"
        ), "Config: START_UNAUTHORIZED_PRIVATE Does not set"
        assert config.get("LIST_PRIVATE"), "Config: LIST_PRIVATE Does not set"
        assert config.get("EDIT_PRIVATE"), "Config: EDIT_PRIVATE Does not set"
        assert config.get(
            "EDIT_QUESTION_PRIVATE"
        ), "Config: EDIT_QUESTION_PRIVATE Does not set"
        assert config.get(
            "EDIT_ANSWER_PRIVATE"
        ), "Config: EDIT_ANSWER_PRIVATE Does not set"
        assert config.get(
            "EDIT_WRONG_PRIVATE"
        ), "Config: EDIT_WRONG_PRIVATE Does not set"
        assert config.get(
            "EDIT_MORE_WRONG_PRIVATE"
        ), "Config: EDIT_MORE_WRONG_PRIVATE Does not set"
        assert config.get(
            "DETAIL_QUESTION_PRIVATE"
        ), "Config: DETAIL_QUESTION_PRIVATE Does not set"
        assert config.get(
            "EDIT_UNFINISH_PRIVATE"
        ), "Config: EDIT_UNFINISH_PRIVATE Does not set"
        assert config.get(
            "EDIT_FINISH_PRIVATE"
        ), "Config: EDIT_FINISH_PRIVATE Does not set"
        assert config.get("CANCEL_PRIVATE"), "Config: CANCEL_PRIVATE Does not set"
        assert config.get("SAVING_PRIVATE"), "Config: SAVING_PRIVATE Does not set"
        assert config.get("DELETING_PRIVATE"), "Config: DELETING_PRIVATE Does not set"
    else:
        logger.warning(f"Config: CHAT is not set! Use /start to get one in chat.")
    if config.get("SUPER_ADMIN"):
        assert isinstance(
            config.get("SUPER_ADMIN"), int
        ), "Config: SUPER_ADMIN Must be ID, not username."
    assert config.get("TIME"), "Config: TIME Does not set"
    assert config.get("BANTIME"), "Config: BANTIME Does not set"
    assert config.get("START"), "Config: START Does not set"
    assert config.get("GREET"), "Config: GREET Does not set"
    assert config.get("SUCCESS"), "Config: SUCCESS Does not set"
    assert config.get("RETRY"), "Config: RETRY Does not set"
    assert config.get("PASS"), "Config: PASS Does not set"
    assert config.get("NOT_KICK"), "Config: NOT_KICK Does not set"
    assert config.get("KICK"), "Config: KICK Does not set"
    assert config.get("PASS_BTN"), "Config: PASS_BTN Does not set"
    assert config.get("KICK_BTN"), "Config: KICK_BTN Does not set"
    assert config.get("ADMIN_PASS"), "Config: ADMIN_PASS Does not set"
    assert config.get("OTHER"), "Config: OTHER Does not set"
    assert config.get("RELOAD"), "Config: RELOAD Does not set"
    assert config.get("PENDING"), "Config: PENDING Does not set"
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


def save_config(config, name=None):
    save = copy.deepcopy(config)
    if not name:
        name = f"{save.get('filename')}.bak"
    save.pop("filename")
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
    if jobs:
        context.job_queue.run_once(
            reload_config, context.bot_data.get("config").get("TIME"), name="reload"
        )
        logger.info(f"Job reload: Waiting for {jobs}")
        return context.bot_data.get("config").get("PENDING")
    else:
        context.bot_data.update(config=load_config())
        logger.info(
            f"Job reload: Successfully reloaded {context.bot_data.get('config').get('filename')}"
        )
        return (
            context.bot_data.get("config")
            .get("RELOAD")
            .format(num=len(context.bot_data.get("config").get("CHALLENGE")))
        )

