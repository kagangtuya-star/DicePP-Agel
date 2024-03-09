from array import array
from pickle import TRUE
from tokenize import String
from typing import List, Tuple, Any

from core.bot import Bot
from core.data import DataChunkBase, custom_data_chunk
from core.command.const import *
from core.command import UserCommandBase, custom_user_command
from core.command import BotCommandBase, BotSendMsgCommand
from core.communication import MessageMetaData, PrivateMessagePort, GroupMessagePort
from core.config import CFG_MASTER, CFG_ADMIN

LOC_GROUP_CONFIG_SET = "group_config_set"
LOC_GROUP_CONFIG_GET = "group_config_get"
LOC_GROUP_CONFIG_SHOW = "group_config_show"

DC_GROUPCONFIG = "group_config"

DEFAULT_GROUP_CONFIG = {
    #基础内容
    "backroom" : False,
    "default_dice" : 20,
    "mode" : "DND",
    #功能开关
    "roll_dnd_enable" : True,
    "roll_coc_enable" : False,
    "roll_hide_enable" : False,
    "deck_enable" : True,
    "query_enable" : True,
    "random_gen_enable" : True,
    "query_database" : "DND5E",
    "homebrew_database" : False,
    #娱乐内容
    "cool_jrrp" : True,
    "chat" : True,
    "april_fool" : False
}

# 存放群配置数据
@custom_data_chunk(identifier=DC_GROUPCONFIG)
class _(DataChunkBase):
    def __init__(self):
        super().__init__()


@custom_user_command(readable_name="群配置指令", priority=-1,  # 要比掷骰命令前, 否则.c会覆盖.config
                     flag=DPP_COMMAND_FLAG_MANAGE, group_only=True)
class GroupconfigCommand(UserCommandBase):
    """
    .set 群配置指令 & .mode 群模式设置指令
    """

    def __init__(self, bot: Bot):
        super().__init__(bot)
        bot.loc_helper.register_loc_text(LOC_GROUP_CONFIG_SET, "", "设置指令")

    def can_process_msg(self, msg_str: str, meta: MessageMetaData) -> Tuple[bool, bool, Any]:
        should_proc: bool = True
        should_pass: bool = False
        master_list = self.bot.cfg_helper.get_config(CFG_MASTER)
        admin_list = self.bot.cfg_helper.get_config(CFG_ADMIN)
        hint: str = ""
        if not meta.group_id:
            should_proc = False
        elif msg_str.startswith(".设置"):
            hint = meta.plain_msg[3:].strip()
            if (meta.user_id not in master_list) and (meta.user_id not in admin_list):
                return should_proc, should_pass, None
        elif msg_str.startswith(".config"):
            hint = meta.plain_msg[7:].strip()
            if (meta.user_id not in master_list) and (meta.user_id not in admin_list):
                return should_proc, should_pass, None
        elif msg_str.startswith(".模式"):
            hint =  msg_str[3:].strip()
        elif msg_str.startswith(".mode"):
            hint =  msg_str[5:].strip()
        elif msg_str.startswith(".chat"):
            hint =  "set chat " + msg_str[5:].strip()
        elif msg_str.startswith(".dset"):
            hint =  msg_str[5:].strip()
        else:
            should_proc = False
        return should_proc, should_pass, hint

    def process_msg(self, msg_str: str, meta: MessageMetaData, hint: Any) -> List[BotCommandBase]:
        port = GroupMessagePort(meta.group_id) if meta.group_id else PrivateMessagePort(meta.user_id)
        # 解析语句
        arg_list = hint.split()
        arg_num = len(arg_list)
        feedback: str = "无效内容"

        if arg_num == 0:
            feedback = "无参数"
        elif msg_str.startswith(".dset"):
            try:
                dice: int = int(arg_list[0])
                self.set_group_config(meta.group_id,"default_dice",dice)
                feedback = "已将本群默认骰设置为 " + str(dice) + " 面!"
            except:
                feedback = "无效数值"
        elif msg_str.startswith(".mode"):
            if arg_num >= 1:
                feed_back = self.switch_mode(meta.group_id,arg_list[0])
        elif arg_list[0] == "set":
            if arg_num == 3:
                if arg_list[2] in ["真","是","开","true","yes","on"]:
                    self.set_group_config(meta.group_id,arg_list[1],True)
                elif arg_list[2] in ["假","否","关","false","no","off"]:
                    self.set_group_config(meta.group_id,arg_list[1],False)
                elif arg_list[2].isdigit():
                    self.set_group_config(meta.group_id,arg_list[1],int(arg_list[2]))
                else:
                    self.set_group_config(meta.group_id,arg_list[1],arg_list[2])
                feedback = "已将群配置 "+ arg_list[1] + " 设置为 " + arg_list[2]
        elif arg_list[0] == "get":
            if arg_num == 2:
                feedback = str(self.get_group_config(meta.group_id,arg_list[1]))
                feedback = "群配置 "+ arg_list[1] + " 的值为 " + feedback
        elif arg_list[0] == "show":
            config_dict = self.bot.data_manager.get_data(DC_GROUPCONFIG, [meta.group_id],default_val="")
            feedback = "当前已配置的群配置: "
            for key in config_dict.keys():
                feedback += "\n · " + str(key) + " : " + str(config_dict[key])
        elif arg_list[0] == "list":
            feedback = "以下是所有可用的群配置与默认值: "
            for key in DEFAULT_GROUP_CONFIG.keys():
                feedback += "\n · " + str(key) + " : " + str(DEFAULT_GROUP_CONFIG[key])
        elif arg_list[0] == "clear":
            self.clear_group_config(meta.group_id)
            feedback = "群配置已清空"
        else:
            feedback = "未知指令"
            

        return [BotSendMsgCommand(self.bot.account, feedback, [port])]
    
    def switch_mode(self, group_id: str, mode: str) -> str:
        if mode in ["coc","coc7"]:
            self.clear_group_config(group_id)
            self.set_group_config(group_id,"mode","COC")
            self.set_group_config(group_id,"default_dice",100)
            self.set_group_config(group_id,"query_database","COC7")
            return "已切换至COC7模式（默认100面骰点，查询数据库使用COC7.db（如果有））"
        elif mode in ["dnd3","dnd3r"]:
            self.clear_group_config(group_id)
            self.set_group_config(group_id,"mode","DND")
            self.set_group_config(group_id,"default_dice",20)
            self.set_group_config(group_id,"query_database","DND3R")
            return "已切换至DND3R模式（默认20面骰点，查询数据库使用DND3R.db（如果有））"
        elif mode in ["dnd4","dnd4e"]:
            self.clear_group_config(group_id)
            self.set_group_config(group_id,"mode","DND")
            self.set_group_config(group_id,"default_dice",20)
            self.set_group_config(group_id,"query_database","DND4E")
            feedback = "已切换至DND4E模式（默认20面骰点，查询数据库使用DND4E.db（如果有））"
        elif mode in ["dnd","dnd5","dnd5e"]:
            self.clear_group_config(group_id)
            self.set_group_config(group_id,"mode","DND")
            self.set_group_config(group_id,"default_dice",20)
            self.set_group_config(group_id,"query_database","DND5E")
            return "已切换至DND5E模式（默认20面骰点，查询数据库使用DND5E.db（如果有））"
        elif mode in ["pf","pf1","pf1e"]:
            self.clear_group_config(group_id)
            self.set_group_config(group_id,"mode","PF1E")
            self.set_group_config(group_id,"default_dice",20)
            self.set_group_config(group_id,"query_database","PF1E")
            return "已切换至PF1E模式（默认20面骰点，查询数据库使用PF1E.db（如果有））"
        elif mode in ["pf2","pf2e"]:
            self.clear_group_config(group_id)
            self.set_group_config(group_id,"mode","PF2E")
            self.set_group_config(group_id,"default_dice",20)
            self.set_group_config(group_id,"query_database","PF2E")
            return "已切换至PF2E模式（默认20面骰点，查询数据库使用PF2E.db（如果有）））"
        elif mode in ["ygo","游戏王"]:
            self.clear_group_config(group_id)
            self.set_group_config(group_id,"mode","YGO")
            self.set_group_config(group_id,"roll_dnd_enable",False)
            self.set_group_config(group_id,"roll_coc_enable",False)
            self.set_group_config(group_id,"query_database","YGO")
            return "已切换至游戏王模式（查询数据库使用YGO.db（如果有））"
        elif mode in ["nechronica","后日谈"]:
            self.clear_group_config(group_id)
            self.set_group_config(group_id,"mode","Nechronica")
            self.set_group_config(group_id,"roll_dnd_enable",False)
            self.set_group_config(group_id,"roll_coc_enable",False)
            self.set_group_config(group_id,"default_dice",10)
            self.set_group_config(group_id,"query_database","NECHRONICA")
            return "已切换至永夜后日谈模式（默认10面骰点，查询数据库使用NECHRONICA.db（如果有））"
        else:
            return "可选模式：pf1、coc、pf2、dnd5e、dnd3r、后日谈（除了dnd其实功能都不是很完善）"

    def set_group_config(self, group_id: str, name: str, data: Any) -> None:
        self.bot.data_manager.set_data(DC_GROUPCONFIG, [group_id,name],data)

    def get_group_config(group_id: str, name: str) -> Any:
        data : Any = self.bot.data_manager.get_data(DC_GROUPCONFIG, [group_id,name],default_val=None)
        if not data:
            data = DEFAULT_GROUP_CONFIG[name]
        return data

    def clear_group_config(self, group_id: str) -> None:
        self.bot.data_manager.delete_data(DC_GROUPCONFIG, [group_id])

    def get_help(self, keyword: str, meta: MessageMetaData) -> str:
        if keyword == "config" or keyword == "mode":  # help后的接着的内容
            feedback: str = ".config set [设置名] [参数值1]" \
                            "设置群配置" \
                            ".config get [设置名]" \
                            "获取群当前设置，与介绍和格式" \
                            ".config remove [设置名]" \
                            "取消某个本群的群配置" \
                            ".config clear" \
                            "清空本群的群配置" \
                            ".config show" \
                            "显示当前群已设置的全部设置名" \
                            ".config list" \
                            "显示全部可用设置" \
                            ".mode dnd/coc/ygo" \
                            "套用模式设置" 
            return feedback
        return ""

    def get_description(self) -> str:
        return ".welcome 设置入群欢迎词"  # help指令中返回的内容
