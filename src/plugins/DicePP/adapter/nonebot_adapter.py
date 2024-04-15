"""
NoneBot API https://v2.nonebot.dev/api/plugin.html
"""
from typing import List, Dict, Optional, Any
import asyncio
from fastapi import FastAPI

import nonebot
from nonebot import on_message, on_notice, on_request
from nonebot.rule import Rule
from nonebot.adapters.onebot.v11.event import MessageEvent, PrivateMessageEvent, GroupMessageEvent
from nonebot.adapters.onebot.v11.event import NoticeEvent, GroupIncreaseNoticeEvent, FriendAddNoticeEvent
from nonebot.adapters.onebot.v11.event import RequestEvent, FriendRequestEvent, GroupRequestEvent
from nonebot.adapters.onebot.v11.bot import Bot as NoneBot
from nonebot.adapters.onebot.v11 import Message as CQMessage
from nonebot.adapters.onebot.v11 import ActionFailed

from core.bot import Bot as DicePPBot
from core.communication import MessageMetaData, MessageSender, GroupMemberInfo, GroupInfo
from core.communication import NoticeData, FriendAddNoticeData, GroupIncreaseNoticeData
from core.communication import RequestData, FriendRequestData, JoinGroupRequestData, InviteGroupRequestData
from core.command import BotCommandBase, BotSendMsgCommand, BotDelayCommand, BotLeaveGroupCommand, BotSendForwardMsgCommand, BotSendFileCommand
from utils.logger import dice_log

from adapter.client_proxy import ClientProxy

from module.fastapi import dpp_api

try:
    app: FastAPI = nonebot.get_app()
    app.mount("/dpp", dpp_api)
except ValueError:
    dice_log("DPP API is not amounted because NoneBot has not been initialized")

command_matcher = on_message(block=False)
notice_matcher = on_notice()
request_matcher = on_request()

all_bots: Dict[str, DicePPBot] = {}


def convert_group_info(nb_group_info: Dict) -> GroupInfo:
    res = GroupInfo(group_id=str(nb_group_info["group_id"]))
    res.group_name = nb_group_info["group_name"]
    res.member_count = nb_group_info["member_count"]
    res.max_member_count = nb_group_info["max_member_count"]
    return res


def convert_group_member_info(nb_group_member_info: Dict) -> GroupMemberInfo:
    res = GroupMemberInfo(group_id=str(nb_group_member_info["group_id"]), user_id=str(nb_group_member_info["user_id"]))
    res.nickname = nb_group_member_info["nickname"]
    res.card = nb_group_member_info["card"]
    res.role = nb_group_member_info["role"]
    res.title = nb_group_member_info["title"]
    return res


class NoneBotClientProxy(ClientProxy):
    def __init__(self, bot: NoneBot):
        self.bot = bot

    # noinspection PyBroadException
    async def process_bot_command(self, command: BotCommandBase):
        dice_log(f"[OneBot] [BotCommand] {command}")
        try:
            if isinstance(command, BotSendMsgCommand):
                for target in command.targets:
                    if target.group_id:
                        await self.bot.send_group_msg(group_id=int(target.group_id), message=CQMessage(command.msg))
                    else:
                        await self.bot.send_private_msg(user_id=int(target.user_id), message=CQMessage(command.msg))
            elif isinstance(command, BotLeaveGroupCommand):
                await self.bot.set_group_leave(group_id=int(command.target_group_id))
            elif isinstance(command, BotSendForwardMsgCommand):
                try:
                    for target in command.targets:
                        await self.bot.call_api("send_group_forward_msg", group_id=int(target.group_id), messages=command.msg_json_list)
                except:
                    if target.group_id:
                        await self.bot.send_group_msg(group_id=int(target.group_id), message="合并转发失败！")
                        for target in command.targets:
                            for msg in command.msg:
                                await self.bot.send_group_msg(group_id=int(target.group_id), message=CQMessage(msg))
                    else:
                        await self.bot.send_group_msg(user_id=int(target.used_id), message="合并转发失败！")
                        for target in command.targets:
                            for msg in command.msg:
                                await self.bot.send_private_msg(user_id=int(target.user_id), message=CQMessage(msg))
            elif isinstance(command, BotSendFileCommand):
                try:
                    for target in command.targets:
                        await self.bot.call_api("upload_group_file", group_id=int(target.group_id), file=command.file, name=command.display_name)
                except:
                    await self.bot.send_group_msg(group_id=int(target.group_id), message="文件发送失败！")
            elif isinstance(command, BotDelayCommand):
                await asyncio.sleep(command.seconds)
            else:
                raise NotImplementedError("未定义的BotCommand类型")
        except ActionFailed as e:
            dice_log(f"[OneBot] [ActionFailed] {e}")
        except Exception as e:
            dice_log(f"[OneBot] [UnknownException] {e}")

    async def process_bot_command_list(self, command_list: List[BotCommandBase]):
        if len(command_list) > 1:
            log_str = "\n".join([str(command) for command in command_list])
            dice_log(f"[Proxy Bot Command List]\n[{log_str}]")
        for command in command_list:
            await self.process_bot_command(command)

    async def get_group_list(self) -> List[GroupInfo]:
        group_info_list: List[Dict] = await self.bot.get_group_list()
        return [convert_group_info(info) for info in group_info_list]

    async def get_group_info(self, group_id: str) -> GroupInfo:
        group_info: Dict = await self.bot.get_group_info(group_id=int(group_id))
        return convert_group_info(group_info)

    async def get_group_member_list(self, group_id: str) -> List[GroupMemberInfo]:
        group_member_list: List[Dict] = await self.bot.get_group_member_list(group_id=int(group_id))
        return [convert_group_member_info(info) for info in group_member_list]

    async def get_group_member_info(self, group_id: str, user_id: str) -> GroupMemberInfo:
        group_member_info: Dict = await self.bot.get_group_member_info(group_id=int(group_id), user_id=int(user_id))
        return convert_group_member_info(group_member_info)

    async def get_group_file_system_info(self, group_id: str) -> Any:
        data = await bot.call_api("get_group_file_system_info", group_id=int(group_id))
        return data

    async def get_group_root_files(self, group_id: str) -> Any:
        data = await bot.call_api("get_group_root_files", group_id=int(group_id))
        return data

    async def get_group_files_by_folder(self, group_id: str, folder_id: str) -> Any:
        data = await bot.call_api("get_group_files_by_folder", group_id=int(group_id), folder_id=folder_id)
        return data

    async def get_group_file_url(self, group_id: str, file_id: str, bus_id: str) -> str:
        url = await bot.call_api("get_group_file_url", group_id=int(group_id), file_id=file_id, busid=bus_id)
        return url


@command_matcher.handle()
async def handle_command(bot: NoneBot, event: MessageEvent):
    cq_message = event.get_message()
    plain_msg = cq_message.extract_plain_text()
    raw_msg = str(cq_message)

    # 构建Meta信息
    group_id: str = ""
    user_id: str = str(event.get_user_id())
    if isinstance(event, GroupMessageEvent):
        group_id = str(event.group_id)

    # log_str = f"[Proxy Message] Bot \033[0;37m{bot.self_id}\033[0m receive message \033[0;33m{raw_msg}\033[0m from "
    # if group_id:
    #     log_str += f"\033[0;34m|Group: {group_id} User: {user_id}|\033[0m"
    # else:
    #     log_str += f"\033[0;35m|Private: {user_id}|\033[0m"
    # dice_log(log_str)

    sender = MessageSender(user_id, event.sender.nickname)
    sender.sex, sender.age, sender.card = event.sender.sex, event.sender.age, event.sender.card
    sender.area, sender.level, sender.role = event.sender.area, event.sender.level, event.sender.role
    sender.title = event.sender.title

    to_me = event.to_me

    meta = MessageMetaData(plain_msg, raw_msg, sender, group_id, to_me)

    # 让机器人处理信息
    await all_bots[bot.self_id].process_message(plain_msg, meta)


@notice_matcher.handle()
async def handle_notice(bot: NoneBot, event: NoticeEvent):
    dice_log(f"[Proxy Notice] {event.get_event_name()}")

    # 构建data
    data: Optional[NoticeData] = None
    if event.notice_type == "group_increase":
        try:
            data = GroupIncreaseNoticeData(str(event.user_id), str(event.group_id), str(event.operator_id))
        except:
            data = GroupIncreaseNoticeData(str(event.user_id), str(event.group_id), "0")
    elif event.notice_type == "friend_add":
        data = FriendAddNoticeData(str(event.user_id))

    # 处理消息提示
    if data:
        await all_bots[bot.self_id].process_notice(data)

@request_matcher.handle()
async def handle_request(bot: NoneBot, event: RequestEvent):
    dice_log(f"[Proxy Request] {event.get_event_name()}")

    # 构建data
    data: Optional[RequestData] = None
    if event.request_type == "friend":
        data = FriendRequestData(str(event.user_id), event.comment)
    elif event.request_type == "group":
        if event.sub_type == "add":
            data = JoinGroupRequestData(str(event.user_id), str(event.group_id))
        elif event.sub_type == "invite":
            data = InviteGroupRequestData(str(event.user_id), str(event.group_id))

    # 处理请求
    if data:
        approve: Optional[bool] = all_bots[bot.self_id].process_request(data)
        if approve:
            if event.request_type == "friend":
                await bot.set_friend_add_request(flag=event.flag, approve=True, remark="")
            elif event.request_type == "group":
                await bot.set_group_add_request(flag=event.flag, sub_type=event.sub_type, approve=True)
        else:
            if event.request_type == "friend":
                await bot.set_friend_add_request(flag=event.flag, approve=False)
            elif event.request_type == "group" and event.sub_type == "invite":
                await bot.set_group_add_request(flag=event.flag, sub_type=event.sub_type, approve=False, reason="已自动拒绝该申请。")
        '''
        # 已无法使用
        if approve:
            try:
                await event.approve(bot)
                print(f"[Proxy Request] 已接受{type(event)}请求。")
            except:
                print(f"[Proxy Request] 接受{type(event)}请求时出错。")
        elif (approve is not None) and (not approve):
            try:
                await event.reject(bot)
                print(f"[Proxy Request] 已拒绝{type(event)}请求。")
            except:
                print(f"[Proxy Request] 拒绝{type(event)}请求时出错。")
        else:
            print(f"[Proxy Request] 已忽略{type(event)}请求。")
        '''


# 全局Driver
try:
    driver = nonebot.get_driver()


    # 在Bot连接时调用

    @driver.on_bot_connect
    async def connect(bot: NoneBot) -> None:
        proxy = NoneBotClientProxy(bot)
        all_bots[bot.self_id] = DicePPBot(bot.self_id)
        all_bots[bot.self_id].set_client_proxy(proxy)
        await all_bots[bot.self_id].delay_init_command()
        dice_log(f"[NB Adapter] Bot {bot.self_id} Connected!")


    @driver.on_bot_disconnect
    async def disconnect(bot: NoneBot) -> None:
        await all_bots[bot.self_id].shutdown_async()
        del all_bots[bot.self_id]
        dice_log(f"[NB Adapter] Bot {bot.self_id} Disconnected!")
except ValueError:
    dice_log("[NB Adapter] NoneBot has not been initialized")
