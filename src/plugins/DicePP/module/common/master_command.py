"""
命令模板, 复制到新创建的文件里修改
"""

from typing import List, Tuple, Any

from core.bot import Bot
from core.command.const import *
from core.command import UserCommandBase, custom_user_command
from core.command import BotCommandBase, BotSendMsgCommand, BotLeaveGroupCommand
from core.communication import MessageMetaData, PrivateMessagePort, GroupMessagePort
from core.config import CFG_MASTER, CFG_ADMIN
from core.data import custom_data_chunk, DataChunkBase
from module.common.activate_command import get_default_activate_data, DC_ACTIVATE

LOC_REBOOT = "master_reboot"
LOC_SEND_MASTER = "master_send_to_master"
LOC_SEND_TARGET = "master_send_to_target"

DC_CTRL = "master_control"

@custom_data_chunk(identifier=DC_CTRL,
                   include_json_object=True)
class _(DataChunkBase):
    def __init__(self):
        super().__init__()

@custom_user_command(readable_name="Master指令", priority=DPP_COMMAND_PRIORITY_MASTER,flag=DPP_COMMAND_FLAG_MANAGE,
                     permission_require=3 # 限定骰管理使用
                     )
class MasterCommand(UserCommandBase):
    """
    Master指令
    包括: reboot, send
    """

    def __init__(self, bot: Bot):
        super().__init__(bot)
        bot.loc_helper.register_loc_text(LOC_REBOOT, "重启已开始。", "开始重启")
        bot.loc_helper.register_loc_text(LOC_SEND_MASTER,
                                         "发送消息: {msg} 至 {id} (类型:{type})",
                                         "用.m send指令发送消息时给Master的回复")
        bot.loc_helper.register_loc_text(LOC_SEND_TARGET, "自Master: {msg}", "用.m send指令发送消息时给目标的回复")

    def can_process_msg(self, msg_str: str, meta: MessageMetaData) -> Tuple[bool, bool, Any]:
        should_proc: bool = False
        should_pass: bool = False
        
        arg_str: str = ""
        if msg_str.startswith(".m"):
            should_proc = True
            arg_str = msg_str[2:].strip()
        elif msg_str.startswith(".master"):
            should_proc = True
            arg_str = msg_str[7:].strip()
        return should_proc, should_pass, arg_str

    def process_msg(self, msg_str: str, meta: MessageMetaData, hint: Any) -> List[BotCommandBase]:
        port = GroupMessagePort(meta.group_id) if meta.group_id else PrivateMessagePort(meta.user_id)
        # 解析语句
        arg_str: str = hint
        feedback: str
        command_list: List[BotCommandBase] = []

        if arg_str == "reboot":
            # 记录下本次的reboot者，下次重启时读取
            self.bot.data_manager.set_data(DC_CTRL, ["rebooter"], meta.user_id)
            # noinspection PyBroadException
            try:
                self.bot.reboot()
                feedback = self.format_loc(LOC_REBOOT)
            except Exception:
                return self.bot.handle_exception("重启时出现错误")
        elif arg_str.startswith("reload"):
            arg_str = arg_str[6:].strip()
            if arg_str.startswith("local") or arg_str.startswith("本地化"):
                self.bot.loc_helper.load_localization()
                self.bot.loc_helper.save_localization()
                feedback = f"已尝试重新载入本地化文件localization.xlsx"
            elif arg_str.startswith("chat") or "聊天" in arg_str:
                self.bot.loc_helper.load_chat()
                self.bot.loc_helper.save_chat()
                feedback = f"已尝试重新载入自定义聊天文件chat.xlsx"
        elif arg_str.startswith("send"):
            arg_list = arg_str[4:].split(":", 2)
            if len(arg_list) == 3:
                target_type, target, msg = (arg.strip() for arg in arg_list)
                if target_type in ["user", "group"]:
                    feedback = self.format_loc(LOC_SEND_MASTER, msg=msg, id=target, type=target_type)
                    target_port = PrivateMessagePort(target) if target_type == "user" else GroupMessagePort(target)
                    command_list.append(BotSendMsgCommand(self.bot.account, msg, [target_port]))
                else:
                    feedback = "目标必须为user或group"
            else:
                feedback = f"非法输入\n使用方法: {self.get_help('m send', meta)}"
        elif arg_str.startswith("bot"):
            arg_str = arg_str[3:].strip()
            if arg_str.startswith("on"):
                arg_str = arg_str[2:].strip()
                if arg_str.isdigit():
                    target = int(arg_str)
                    target_port = GroupMessagePort(target)
                    feedback = f"已尝试远程为指定群聊{target}开启骰娘"
                    self.bot.data_manager.set_data(DC_ACTIVATE, [target], get_default_activate_data(True))
                    command_list.append(BotSendMsgCommand(self.bot.account, "（骰主已远程为本群开启骰娘。）", [target_port]))
                else:
                    feedback = "目标必须为一个群聊的QQ号"
            elif arg_str.startswith("off"):
                arg_str = arg_str[3:].strip()
                if arg_str.isdigit():
                    target = int(arg_str)
                    target_port = GroupMessagePort(target)
                    feedback = f"已尝试远程为指定群聊{target}关闭骰娘"
                    self.bot.data_manager.set_data(DC_ACTIVATE, [target], get_default_activate_data(False))
                    command_list.append(BotSendMsgCommand(self.bot.account, "（骰主已远程为本群关闭骰娘。）", [target_port]))
                else:
                    feedback = "目标必须为一个群聊的QQ号"
            elif arg_str.startswith("dismiss"):
                arg_str = arg_str[7:].strip()
                if arg_str.isdigit():
                    target = int(arg_str)
                    target_port = GroupMessagePort(target)
                    feedback = f"已尝试让骰娘退出指定群聊{target}"
                    command_list.append(BotSendMsgCommand(self.bot.account, "骰主已远程操作骰娘退出本群。", [target_port]))
                    command_list.append(BotLeaveGroupCommand(self.bot.account, target))
                else:
                    feedback = "目标必须为一个群聊的QQ号"
            else:
                feedback = "未知指令，目前仅可用bot on、bot off、bot dismiss。"
        elif arg_str == "update":
            async def async_task():
                update_group_result = await self.bot.update_group_info_all()
                update_feedback = f"已更新{len(update_group_result)}条群信息:"
                update_group_result = list(sorted(update_group_result, key=lambda x: -x.member_count))[:50]
                for group_info in update_group_result:
                    update_feedback += f"\n{group_info.group_name}({group_info.group_id}): 群成员{group_info.member_count}/{group_info.max_member_count}"
                return [BotSendMsgCommand(self.bot.account, update_feedback, [port])]

            self.bot.register_task(async_task, timeout=60, timeout_callback=lambda: [BotSendMsgCommand(self.bot.account, "更新超时!", [port])])
            feedback = "更新开始..."
        elif arg_str == "clean":
            async def clear_expired_data():
                res = await self.bot.clear_expired_data()
                return res

            self.bot.register_task(clear_expired_data, timeout=3600)
            feedback = "清理开始..."
        elif arg_str == "debug-tick":
            feedback = f"异步任务状态: {self.bot.tick_task.get_name()} Done:{self.bot.tick_task.done()} Cancelled:{self.bot.tick_task.cancelled()}\n" \
                       f"{self.bot.tick_task}"
        elif arg_str == "redo-tick":
            import asyncio
            self.bot.tick_task = asyncio.create_task(self.bot.tick_loop())
            self.bot.todo_tasks = {}
            feedback = "Redo tick finish!"
        else:
            feedback = self.get_help("m", meta)

        command_list.append(BotSendMsgCommand(self.bot.account, feedback, [port]))
        return command_list

    def get_help(self, keyword: str, meta: MessageMetaData) -> str:
        if keyword == "m":  # help后的接着的内容
            return ".m reboot 重启骰娘" \
                   ".m send 命令骰娘发送信息" \
                   ".m bot off/on/dismiss 命令骰娘远程操作群聊"
        if keyword.startswith("m"):
            if keyword.endswith("reboot"):
                return "该指令将重启DicePP进程"
            elif keyword.endswith("send"):
                return ".m send [user/group]:[账号/群号]:[消息内容]"
            elif keyword.endswith("bot"):
                return ".m bot on [群号] 远程开启骰娘" \
                       ".m bot off [群号] 远程关闭骰娘" \
                       ".m bot dismiss [群号] 远程让骰娘尝试退群" 
        return ""

    def get_description(self) -> str:
        return ".m Master才能使用的指令"  # help指令中返回的内容
