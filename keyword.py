import re, time, asyncio, requests, os, json
from sys import exit
from os import path, mkdir, remove, makedirs, getcwd
from shutil import copyfile, move, rmtree
from uuid import uuid4
from base64 import b64encode, b64decode
from importlib import import_module
from main import bot, reg_handler, des_handler, par_handler, redis


working_dir = getcwd()
msg_freq = 1
group_last_time = {}
read_context = {}


def redis_status():
    try:
        redis.ping()
        return True
    except BaseException:
        return False


def is_num(x: str):
    try:
        x = int(x)
        return isinstance(x, int)
    except ValueError:
        return False


def encode(s: str):
    return str(b64encode(s.encode('utf-8')), 'utf-8')


def decode(s: str):
    return str(b64decode(s.encode('utf-8')), 'utf-8')


def random_str():
    return str(uuid4()).replace('-', '')


def parse_rules(rules: str):
    n_rules = {}
    rules_parse = rules.split(";")
    for p in rules_parse:
        d = p.split(":")
        if len(d) == 2:
            key = decode(d[0])
            value = decode(d[1])
            n_rules[key] = value
    return n_rules


def save_rules(rules: dict, placeholder: str):
    n_rules = ""
    for k, v in rules.items():
        if placeholder:
            k = k.replace(placeholder, "'")
            v = v.replace(placeholder, "'")
        n_rules += encode(k) + ":" + encode(v) + ";"
    return n_rules


def validate(user_id: str, mode: int, user_list: list):
    if mode == 0:
        return user_id not in user_list
    elif mode == 1:
        return user_id in user_list
    else:
        return False


def get_redis(db_key: str):
    byte_data = redis.get(db_key)
    byte_data = byte_data if byte_data else b""
    byte_data = str(byte_data, "ascii")
    return parse_rules(byte_data)


def parse_multi(rule: str):
    sep_ph = random_str()
    col_ph = random_str()
    rule = rule.replace(r"\||", sep_ph)
    rule = rule.replace(r"\::", col_ph)
    rule = rule.split("||")
    n_rule = []
    for r in rule:
        p = r.split("::")
        p = [i.replace(sep_ph, "||") for i in p]
        p = [i.replace(col_ph, "::") for i in p]
        data = ['plain', '']
        if len(p) == 2:
            data = p
        else:
            data[1] = p[0]
        n_rule.append(data)
    return n_rule


def get_capture(search_data, group_name: str):
    try:
        capture_data = search_data.group(group_name)
        return capture_data
    except:
        return None


def get_rule(chat_id, rule_type, rule_index):
    rule_index = int(rule_index)
    rule_data = get_redis(f"keyword.{chat_id}.{rule_type}")
    index = 0
    for k in rule_data.keys():
        if index == rule_index:
            return encode(k)
        index += 1
    return None


def valid_time(chat_id):
    global msg_freq, group_last_time
    cus_freq = get_redis(f"keyword.{chat_id}.settings").get("freq", msg_freq)
    try:
        cus_freq = float(cus_freq)
    except:
        cus_freq = msg_freq
    n_time = time.time()
    chat_id = int(chat_id)
    if chat_id in group_last_time:
        if n_time - group_last_time[chat_id] >= cus_freq:
            return True
        else:
            return False
    else:
        return True


def has_cache(chat_id, mode, trigger, filename):
    basepath = f"data/keyword_cache/{chat_id}/{mode}:{encode(trigger)}"
    filepath = f"{basepath}/{filename}"
    if not path.exists(basepath):
        makedirs(basepath)
        return (False, filepath)
    if not path.exists(filepath):
        return (False, filepath)
    return (True, filepath)


def cache_opened(chat_id, mode, trigger):
    rule_data = get_redis(f"keyword.{chat_id}.single"
                          f".{mode}.{encode(trigger)}").get("cache", None)
    chat_data = get_redis(f"keyword.{chat_id}.settings").get("cache", None)
    global_data = get_redis("keyword.settings").get("cache", None)
    if rule_data:
        return True if rule_data == "1" else False
    elif chat_data:
        return True if chat_data == "1" else False
    elif global_data:
        return True if global_data == "1" else False
    return False


async def del_msg(context, t_lim):
    await asyncio.sleep(t_lim)
    try:
        await context.delete()
    except:
        pass


async def send_reply(bot, chat_id, trigger, mode, reply_msg, context):
    try:
        real_chat_id = chat_id
        chat = context.chat
        sender = context.from_user
        replace_data = {}
        if chat_id < 0:
            replace_data = {
                "chat_id": chat.id,
                "chat_name": chat.title
            }
            if sender:
                replace_data["user_id"] = sender.id
                replace_data["first_name"] = sender.first_name
                replace_data["last_name"] = sender.last_name if sender.last_name else ""
        else:
            replace_data["user_id"] = chat_id
            if sender:
                replace_data["first_name"] = sender.first_name
                replace_data["last_name"] = sender.last_name if sender.last_name else ""
            if chat:
                replace_data["chat_id"] = chat.id
                last_name = chat.last_name
                if not last_name:
                    last_name = ""
                replace_data["chat_name"] = f"{chat.first_name} {last_name}"
        update_last_time = False
        could_send_msg = valid_time(chat_id)
        for re_type, re_msg in reply_msg:
            try:
                catch_pattern = r"\$\{func_(?P<str>((?!\}).)+)\}"
                count = 0
                while re.search(catch_pattern, re_msg) and count < 20:
                    func_name = re.search(catch_pattern, re_msg).group("str")
                    try:
                        module = import_module(f"data.keyword_func.{func_name}")
                        context.client = bot
                        func_data = await module.main(context)
                        os.chdir(working_dir)
                    except:
                        func_data = "[RE]"
                    re_msg = re_msg.replace("${func_%s}" % func_name, str(func_data))
                    count += 1
                for k, v in replace_data.items():
                    re_type = re_type.replace(f"${k}", str(v))
                    re_msg = re_msg.replace(f"${k}", str(v))
                type_parse = re_type.split(",")
                for s in type_parse:
                    if len(s) >= 5 and "ext_" == s[0:4] and is_num(s[4:]):
                        chat_id = int(s[4:])
                        type_parse.remove(s)
                        break
                if ("file" in type_parse or "photo" in type_parse) and len(re_msg.split()) >= 2:
                    if could_send_msg:
                        update_last_time = True
                        re_data = re_msg.split(" ")
                        cache_exists, cache_path = has_cache(chat_id, mode, trigger, re_data[0])
                        is_opened = cache_opened(chat_id, mode, trigger)
                        filename = "/tmp/" + re_data[0]
                        if is_opened:
                            filename = cache_path
                            if not cache_exists:
                                if re_data[1][0:7] == "file://":
                                    re_data[1] = re_data[1][7:]
                                    copyfile(" ".join(re_data[1:]), filename)
                                else:
                                    fileget = requests.get(" ".join(re_data[1:]))
                                    with open(filename, "wb") as f:
                                        f.write(fileget.content)
                        else:
                            if re_data[1][0:7] == "file://":
                                re_data[1] = re_data[1][7:]
                                copyfile(" ".join(re_data[1:]), filename)
                            else:
                                fileget = requests.get(" ".join(re_data[1:]))
                                with open(filename, "wb") as f:
                                    f.write(fileget.content)
                        reply_to = None
                        if "reply" in type_parse:
                            reply_to = context.message_id
                        if "file" in type_parse:
                            await bot.send_document(chat_id, filename, reply_to_message_id=reply_to)
                        else:
                            await bot.send_photo(chat_id, filename, reply_to_message_id=reply_to)
                        if not is_opened:
                            remove(filename)
                elif ("tgfile" in type_parse or "tgphoto" in type_parse) and len(re_msg.split()) >= 2:
                    if could_send_msg:
                        update_last_time = True
                        if not path.exists("/tmp"):
                            mkdir("/tmp")
                        re_data = re_msg.split()
                        file_name = "/tmp/" + re_data[0]
                        re_new_data = re_data[1].split("/")[-2:]
                        try:
                            msg_chat_id = int('-100' + str(re_new_data[0]))
                        except:
                            msg_chat_id = re_new_data[0]
                        msg_id_inchat = int(re_new_data[1])
                        media_msg = await bot.get_messages(msg_chat_id, msg_id_inchat)
                        if media_msg and media_msg.media:
                            await bot.download_media(media_msg, file_name)
                            reply_to = None
                            if "reply" in type_parse:
                                reply_to = context.message_id
                            if "tgfile" in type_parse:
                                await bot.send_document(chat_id, file_name, reply_to_message_id=reply_to)
                            else:
                                await bot.send_photo(chat_id, file_name, reply_to_message_id=reply_to)
                            remove(file_name)
                elif "plain" in type_parse:
                    if could_send_msg:
                        update_last_time = True
                        await bot.send_message(chat_id, re_msg)
                elif "reply" in type_parse and chat_id == real_chat_id:
                    if could_send_msg:
                        update_last_time = True
                        await bot.send_message(chat_id, re_msg, reply_to_message_id=context.message_id)
                elif "op" in type_parse:
                    if re_msg == "delete":
                        await context.delete()
                    elif re_msg.split()[0] == "sleep" and len(re_msg.split()) == 2:
                        sleep_time = re_msg.split()[1]
                        await asyncio.sleep(float(sleep_time))
            except:
                pass
            chat_id = real_chat_id
        if update_last_time:
            global group_last_time
            group_last_time[int(chat_id)] = time.time()
    except:
        pass


async def reply(context, args, origin_text):
    if not redis_status():
        await context.edit("?????????????????? ~ Redis ?????????????????????")
        await del_msg(context, 5)
        return
    context.parameter = context.text.split(" ")[1:]
    chat_id = context.chat.id
    plain_dict = get_redis(f"keyword.{chat_id}.plain")
    regex_dict = get_redis(f"keyword.{chat_id}.regex")
    params = context.parameter
    params = " ".join(params)
    placeholder = random_str()
    params = params.replace(r"\'", placeholder)
    tmp_parse = params.split("'")
    parse = []
    for i in range(len(tmp_parse)):
        if len(tmp_parse[i].split()) != 0:
            parse.append(tmp_parse[i])
    if len(parse) == 0 or (
            len(parse[0].split()) == 1 and parse[0].split()[0] in ("new", "del", "delid", "clear")) or len(
        parse[0].split()) > 2:
        await context.edit(
            "[Code: -1] ???????????????????????? `-keyword` ?????? `new <plain|regex> '<??????>' '<????????????>'` ?????? "
            "`del <plain|regex> '<??????>'` ?????? `list` ?????? `clear <plain|regex>`", parse_mode='md')
        await del_msg(context, 10)
        return
    else:
        parse[0] = parse[0].split()
    if parse[0][0] == "new" and len(parse) == 3:
        if parse[0][1] == "plain":
            plain_dict[parse[1]] = parse[2]
            redis.set(f"keyword.{chat_id}.plain", save_rules(plain_dict, placeholder))
        elif parse[0][1] == "regex":
            regex_dict[parse[1]] = parse[2]
            redis.set(f"keyword.{chat_id}.regex", save_rules(regex_dict, placeholder))
        else:
            await context.edit(
                "[Code: -1] ???????????????????????? `-keyword` ?????? `new <plain|regex> '<??????>' '<????????????>'` ?????? "
                "`del <plain|regex> '<??????>'` ?????? `list` ?????? `clear <plain|regex>`")
            await del_msg(context, 10)
            return
        await context.edit("????????????")
        await del_msg(context, 5)
    elif parse[0][0] in ("del", "delid") and len(parse) == 2:
        if parse[0][0] == "delid":
            parse[1] = get_rule(chat_id, parse[0][1], parse[1])
            if parse[1]:
                parse[1] = decode(parse[1])
        if parse[0][1] == "plain":
            if parse[1] and parse[1] in plain_dict:
                redis.delete(f"keyword.{chat_id}.single.plain.{encode(parse[1])}")
                plain_dict.pop(parse[1])
                redis.set(f"keyword.{chat_id}.plain", save_rules(plain_dict, placeholder))
            else:
                await context.edit("???????????????")
                await del_msg(context, 5)
                return
        elif parse[0][1] == "regex":
            if parse[1] and parse[1] in regex_dict:
                redis.delete(f"keyword.{chat_id}.single.regex.{encode(parse[1])}")
                regex_dict.pop(parse[1])
                redis.set(f"keyword.{chat_id}.regex", save_rules(regex_dict, placeholder))
            else:
                await context.edit("???????????????")
                await del_msg(context, 5)
                return
        else:
            await context.edit(
                "[Code: -1] ???????????????????????? `-keyword` ?????? `new <plain|regex> '<??????>' '<????????????>'` ?????? "
                "`del <plain|regex> '<??????>'` ?????? `list` ?????? `clear <plain|regex>`")
            await del_msg(context, 10)
            return
        await context.edit("????????????")
        await del_msg(context, 5)
    elif parse[0][0] == "list" and len(parse) == 1:
        plain_msg = "Plain: \n"
        index = 0
        for k, v in plain_dict.items():
            plain_msg += f"`{index}`: `{k}` -> `{v}`\n"
            index += 1
        regex_msg = "Regex: \n"
        index = 0
        for k, v in regex_dict.items():
            regex_msg += f"`{index}`: `{k}` -> `{v}`\n"
            index += 1
        await context.edit(plain_msg + "\n" + regex_msg)
    elif parse[0][0] == "clear" and len(parse) == 1:
        if parse[0][1] == "plain":
            for k in plain_dict.keys():
                redis.delete(f"keyword.{chat_id}.single.plain.{encode(k)}")
            redis.set(f"keyword.{chat_id}.plain", "")
        elif parse[0][1] == "regex":
            for k in regex_dict.keys():
                redis.delete(f"keyword.{chat_id}.single.regex.{encode(k)}")
            redis.set(f"keyword.{chat_id}.regex", "")
        else:
            await context.edit("????????????")
            await del_msg(context, 5)
            return
        await context.edit("????????????")
        await del_msg(context, 5)
    else:
        await context.edit(
            "[Code: -1] ???????????????????????? `-keyword` ?????? `new <plain|regex> '<??????>' '<????????????>'` ?????? "
            "`del <plain|regex> '<??????>'` ?????? `list` ?????? `clear <plain|regex>`")
        await del_msg(context, 10)
        return


async def reply_set(context, args, origin_text):
    if not redis_status():
        await context.edit("?????????????????? ~ Redis ?????????????????????")
        await del_msg(context, 5)
        return
    context.parameter = context.text.split(" ")[1:]
    chat_id = context.chat.id
    params = context.parameter
    redis_data = f"keyword.{chat_id}.settings"
    if len(params) >= 1 and params[0] == "global":
        redis_data = "keyword.settings"
        del params[0]
    elif len(params) >= 2 and params[0] in ("plain", "regex") and is_num(params[1]):
        rule_data = get_rule(chat_id, params[0], params[1])
        if rule_data:
            redis_data = f"keyword.{chat_id}.single.{params[0]}.{rule_data}"
            del params[0:2]
    settings_dict = get_redis(redis_data)
    cmd_list = ["help", "mode", "list", "freq", "show", "cache", "clear"]
    cmd_dict = {
        "help": (1,),
        "mode": (2,),
        "list": (2, 3),
        "freq": (2,),
        "show": (1,),
        "cache": (2,),
        "clear": (1,)
    }
    if len(params) < 1:
        await context.edit("????????????")
        await del_msg(context, 5)
        return
    if params[0] in cmd_list and len(params) in cmd_dict[params[0]]:
        if params[0] == "help":
            await context.edit('''
`-replyset show` ???
`-replyset clear` ???
`-replyset mode <0/1/clear>` ( 0 ??????????????????1 ??????????????? ) ???
`-replyset list <add/del/show/clear> [user_id]` ???
`-replyset freq <float/clear>` ( float ??????????????????????????????clear ????????? )???
??? `-replyset` ???????????? `global` ?????????????????????
??? `-replyset` ???????????? `plain/regex` ???????????? ?????????????????????????????????''')
            await del_msg(context, 15)
            return
        elif params[0] == "show":
            defaults = {
                "mode": "????????? (???????????????)",
                "list": "????????? (????????????)",
                "freq": "????????? (????????? 1)",
                "cache": "????????? (????????????)"
            }
            msg = "Settings: \n"
            for k, v in defaults.items():
                msg += f"`{k}` -> `{settings_dict[k] if k in settings_dict else v}`\n"
            await context.edit(msg)
            return
        elif params[0] == "mode":
            if params[1] in ("0", "1"):
                settings_dict["mode"] = params[1]
                redis.set(redis_data, save_rules(settings_dict, None))
                if params[1] == "0":
                    await context.edit("???????????????????????????")
                elif params[1] == "1":
                    await context.edit("???????????????????????????")
                await del_msg(context, 5)
                return
            elif params[1] == "clear":
                if "mode" in settings_dict:
                    del settings_dict["mode"]
                redis.set(redis_data, save_rules(settings_dict, None))
                await context.edit("????????????")
                await del_msg(context, 5)
                return
            else:
                await context.edit("????????????")
                await del_msg(context, 5)
                return
        elif params[0] == "list":
            if params[1] == "show" and len(params) == 2:
                user_list = settings_dict.get("list", None)
                if user_list:
                    msg = "List: \n"
                    for p in user_list.split(","):
                        msg += f"`{p}`\n"
                    await context.edit(msg)
                    return
                else:
                    await context.edit("????????????")
                    await del_msg(context, 5)
                    return
            elif params[1] == "add" and len(params) == 3:
                if is_num(params[2]):
                    tmp = settings_dict.get("list", None)
                    if not tmp:
                        settings_dict["list"] = params[2]
                    else:
                        settings_dict["list"] += f",{params[2]}"
                    redis.set(redis_data, save_rules(settings_dict, None))
                    await context.edit("????????????")
                    await del_msg(context, 5)
                    return
                else:
                    await context.edit("user_id ????????????")
                    await del_msg(context, 5)
                    return
            elif params[1] == "del" and len(params) == 3:
                if is_num(params[2]):
                    tmp = settings_dict.get("list", None)
                    if tmp:
                        user_list = settings_dict["list"].split(",")
                        if params[2] in user_list:
                            user_list.remove(params[2])
                            settings_dict["list"] = ",".join(user_list)
                            redis.set(redis_data, save_rules(settings_dict, None))
                            await context.edit("????????????")
                            await del_msg(context, 5)
                            return
                        else:
                            await context.edit("user_id ????????????")
                            await del_msg(context, 5)
                            return
                    else:
                        await context.edit("????????????")
                        await del_msg(context, 5)
                        return
                else:
                    await context.edit("user_id ????????????")
                    await del_msg(context, 5)
                    return
            elif params[1] == "clear" and len(params) == 2:
                if "list" in settings_dict:
                    del settings_dict["list"]
                redis.set(redis_data, save_rules(settings_dict, None))
                await context.edit("????????????")
                await del_msg(context, 5)
                return
            else:
                await context.edit("????????????")
                await del_msg(context, 5)
                return
        elif params[0] == "freq":
            if params[1] == "clear":
                if "freq" in settings_dict:
                    del settings_dict["freq"]
                redis.set(redis_data, save_rules(settings_dict, None))
                await context.edit("????????????")
                await del_msg(context, 5)
                return
            else:
                try:
                    tmp = float(params[1])
                    if tmp > 0:
                        settings_dict["freq"] = params[1]
                        redis.set(redis_data, save_rules(settings_dict, None))
                        await context.edit("????????????")
                        await del_msg(context, 5)
                        return
                    else:
                        await context.edit("??????????????????")
                        await del_msg(context, 5)
                        return
                except:
                    await context.edit("??????????????????")
                    await del_msg(context, 5)
                    return
        elif params[0] == "cache":
            if params[1] == "0":
                settings_dict["cache"] = "0"
                redis.set(redis_data, save_rules(settings_dict, None))
                await context.edit("?????????????????????")
                await del_msg(context, 5)
                return
            elif params[1] == "1":
                settings_dict["cache"] = "1"
                redis.set(redis_data, save_rules(settings_dict, None))
                await context.edit("?????????????????????")
                await del_msg(context, 5)
                return
            elif params[1] == "remove":
                if redis_data == "keyword.settings":
                    rmtree("data/keyword_cache")
                elif redis_data.split(".")[2] == "single":
                    rmtree(f"data/keyword_cache/{chat_id}/"
                           f"{redis_data.split('.')[3]}:{redis_data.split('.')[4]}")
                else:
                    rmtree(f"data/keyword_cache/{chat_id}")
                await context.edit("???????????????")
                await del_msg(context, 5)
                return
            elif params[1] == "clear":
                if "cache" in settings_dict:
                    del settings_dict["cache"]
                redis.set(redis_data, save_rules(settings_dict, None))
                await context.edit("????????????")
                await del_msg(context, 5)
                return
            else:
                await context.edit(f"????????????")
                await del_msg(context, 5)
                return
        elif params[0] == "clear":
            redis.delete(redis_data)
            await context.edit("????????????")
            await del_msg(context, 5)
            return
    else:
        await context.edit("????????????")
        await del_msg(context, 5)
        return


async def funcset(context, args, origin_text):
    if not path.exists("data/keyword_func"):
        makedirs("data/keyword_func")
    try:
        context.parameter = context.text.split(" ")[1:]
        params = context.parameter
        params = " ".join(params).split("\n")
        cmd = []
        if len(params) >= 1:
            cmd = params[0].split()
        if len(cmd) > 0:
            if len(cmd) == 1 and cmd[0] == "ls":
                send_msg = "Functions:\n"
                count = 1
                for p in os.listdir("data/keyword_func"):
                    if path.isfile(f"data/keyword_func/{p}"):
                        try:
                            send_msg += f"{count}: `{p[:-3]}`\n"
                            count += 1
                        except:
                            pass
                await context.edit(send_msg)
                return
            elif len(cmd) == 2 and cmd[0] == "show":
                file_path = f"data/keyword_func/{cmd[1]}.py"
                if path.exists(file_path) and path.isfile(file_path):
                    await bot.send_document(context.chat.id, file_path)
                    await context.edit("????????????")
                    await del_msg(context, 5)
                else:
                    await context.edit("???????????????")
                    await del_msg(context, 5)
                return
            elif len(cmd) == 2 and cmd[0] == "del":
                file_path = f"data/keyword_func/{cmd[1]}.py"
                if path.exists(file_path) and path.isfile(file_path):
                    remove(file_path)
                    await context.edit("???????????????PagerMaid-Modify Beta ?????????????????????")
                    exit()
                else:
                    await context.edit("???????????????")
                    await del_msg(context, 5)
                return
            elif len(cmd) == 2 and cmd[0] == "new":
                message = context.reply_to_message
                if context.media:
                    message = context
                cmd[1] = cmd[1].replace(".py", "")
                if message and message.media:
                    try:
                        await bot.download_media(message, f"data/keyword_func/{cmd[1]}.py")
                        await context.edit(f"?????? {cmd[1]} ????????????PagerMaid-Modify Beta ?????????????????????")
                        exit()
                    except SystemExit:
                        exit()
                    except:
                        await context.edit("??????????????????")
                        await del_msg(context, 5)
                else:

                    await context.edit("???????????????????????????????????????????????????")
                    await del_msg(context, 5)
                return
            elif len(cmd) == 2 and cmd[0] == "install":
                func_name = cmd[1]
                func_online = \
                    json.loads(
                        requests.get("https://raw.githubusercontent.com/xtaodada/PagerMaid_Plugins/master"
                                     "/keyword_func/list.json").content)['list']
                if func_name in func_online:
                    func_directory = f"data/keyword_func/"
                    file_path = func_name + ".py"
                    func_content = requests.get(
                        f"https://raw.githubusercontent.com/xtaodada/PagerMaid_Plugins/master"
                        f"/keyword_func/{func_name}.py").content
                    with open(file_path, 'wb') as f:
                        f.write(func_content)
                    if path.exists(f"{func_directory}{file_path}"):
                        remove(f"{func_directory}{file_path}")
                        move(file_path, func_directory)
                    else:
                        move(file_path, func_directory)
                    await context.edit(f"?????? {path.basename(file_path)[:-3]} ????????????PagerMaid-Modify ?????????????????????")
                    exit()
                else:
                    await context.edit(f"{func_name} ???????????????")
                    await del_msg(context, 5)
                return
            elif len(cmd) == 1 and cmd[0] == "help":
                await context.edit("""
    `-funcset new <func_name>` (???????????????????????????????????????????????????)
    `-funcset install <func_name>` ??????????????????????????????
    `-funcset del <func_name>`
    `-funcset show <func_name>` (????????????)
    `-funcset ls` (??????????????????)""")
            else:
                await context.edit("????????????")
                await del_msg(context, 5)
                return
        else:
            await context.edit("????????????")
            await del_msg(context, 5)
            return
    except:
        pass


async def auto_reply(client, context):
    try:
        chat_id = context.chat.id
        sender_id = context.from_user.id
    except:
        return
    if f"{chat_id}:{context.message_id}" not in read_context:
        plain_dict = get_redis(f"keyword.{chat_id}.plain")
        regex_dict = get_redis(f"keyword.{chat_id}.regex")
        g_settings = get_redis("keyword.settings")
        n_settings = get_redis(f"keyword.{chat_id}.settings")
        g_mode = g_settings.get("mode", None)
        n_mode = n_settings.get("mode", None)
        mode = "0"
        g_list = g_settings.get("list", None)
        n_list = n_settings.get("list", None)
        user_list = []
        if g_mode and n_mode:
            mode = n_mode
        elif g_mode or n_mode:
            mode = g_mode if g_mode else n_mode
        if g_list and n_list:
            user_list = n_list
        elif g_list or n_list:
            user_list = g_list if g_list else n_list
        send_text = context.text
        if not send_text:
            send_text = ""
        for k, v in plain_dict.items():
            if k in send_text:
                tmp = get_redis(f"keyword.{chat_id}.single.plain.{encode(k)}")
                could_reply = validate(str(sender_id), int(mode), user_list)
                if tmp:
                    could_reply = validate(str(sender_id), int(tmp.get("mode", "0")), tmp.get("list", []))
                if could_reply:
                    read_context[f"{chat_id}:{context.message_id}"] = None
                    await send_reply(client, chat_id, k, "plain", parse_multi(v), context)
        for k, v in regex_dict.items():
            pattern = re.compile(k)
            if pattern.search(send_text):
                tmp = get_redis(f"keyword.{chat_id}.single.regex.{encode(k)}")
                could_reply = validate(str(sender_id), int(mode), user_list)
                if tmp:
                    could_reply = validate(str(sender_id), int(tmp.get("mode", "0")), tmp.get("list", []))
                if could_reply:
                    read_context[f"{chat_id}:{context.message_id}"] = None
                    catch_pattern = r"\$\{regex_(?P<str>((?!\}).)+)\}"
                    count = 0
                    while re.search(catch_pattern, v) and count < 20:
                        search_data = re.search(k, send_text)
                        group_name = re.search(catch_pattern, v).group("str")
                        capture_data = get_capture(search_data, group_name)
                        if not capture_data:
                            capture_data = ""
                        if re.search(catch_pattern, capture_data):
                            capture_data = ""
                        v = v.replace("${regex_%s}" % group_name, capture_data)
                        count += 1
                    await send_reply(client, chat_id, k, "regex", parse_multi(v), context)
    else:
        del read_context[f"{chat_id}:{context.message_id}"]


reg_handler('keyword', reply)
reg_handler('replyset', reply_set)
reg_handler('funcset', funcset)
des_handler('keyword', '????????????????????????')
des_handler('replyset', '?????????????????????')
des_handler('funcset', '????????????????????????')
par_handler('keyword', "``new <plain|regex> '<??????>' '<????????????>'` ?????? `del <plain|regex> '<??????>'` ?????? `list` ?????? "
            "`clear <plain|regex>")
par_handler('replyset', 'help')
par_handler('funcset', 'help')
