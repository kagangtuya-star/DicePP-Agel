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
LOC_GROUP_DICE_SET = "group_dice_set"
LOC_GROUP_CHAT_ON = "group_chat_on"
LOC_GROUP_CHAT_OFF = "group_chat_off"

DC_GROUPCONFIG = "group_config"

DEFAULT_GROUP_CONFIG = {
    #基础内容
    "backroom" : False,
    "default_dice" : 20,
    "mode" : "",
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
    "chat" : True
}

# 存放群配置数据
@custom_data_chunk(identifier=DC_GROUPCONFIG)
class _(DataChunkBase):
    def __init__(self):
        super().__init__()


@custom_user_command(readable_name="群配置指令", priority=-1,  # 要比掷骰命令前, 否则.c会覆盖.config
                     flag=DPP_COMMAND_FLAG_MANAGE, group_only=True,
                     permission_require=1 # 限定群管理/骰管理使用
                     )
class GroupconfigCommand(UserCommandBase):
    """
    .config 群配置指令
    """

    def __init__(self, bot: Bot):
        super().__init__(bot)
        bot.loc_helper.register_loc_text(LOC_GROUP_CONFIG_SET, "已将本群 {var_name} 的值改为 {var}。", "群配置指令（需要骰管理），将一项群配置设定为特定值时的回复，var_name：变量名，var：具体值")
        bot.loc_helper.register_loc_text(LOC_GROUP_CONFIG_GET, "本群 {var_name} 的值是 {var}。", "群配置指令，将一项群配置设定为特定值时的回复，var_name：变量名，var：具体值")
        bot.loc_helper.register_loc_text(LOC_GROUP_DICE_SET, "本群的默认掷骰面数已改为{var}面。", "修改群内默认掷骰骰面的回复，var：具体骰面")
        bot.loc_helper.register_loc_text(LOC_GROUP_CHAT_ON, "本群的自定义聊天功能已开启。", "开启聊天功能的回复")
        bot.loc_helper.register_loc_text(LOC_GROUP_CHAT_OFF, "本群的自定义聊天功能已关闭。", "关闭聊天功能的回复")
    
    def delay_init(self) -> List[str]:
        init_info: List[str] = []
        #初始化默认数据
        for name in DEFAULT_GROUP_CONFIG.keys():
            self.bot.data_manager.set_data(DC_GROUPCONFIG, ["default",name],DEFAULT_GROUP_CONFIG[name])
        #定义一些可配置的默认数据
        self.bot.data_manager.set_data(DC_GROUPCONFIG, ["default","mode"],self.bot.cfg_helper.get_config("mode_default")[0]) #设定默认模式
        return init_info

    def can_process_msg(self, msg_str: str, meta: MessageMetaData) -> Tuple[bool, bool, Any]:
        should_proc: bool = True
        should_pass: bool = False
        arg_str: str = ""
        show_mode: str = ""
        
        if msg_str.startswith(".设置"):
            arg_str = meta.plain_msg[3:].strip()
        elif msg_str.startswith(".config"):
            arg_str = meta.plain_msg[7:].strip()
        elif msg_str.startswith(".聊天"):
            arg_str =  "set chat " + msg_str[3:].strip()
            show_mode = "chat"
        elif msg_str.startswith(".chat"):
            arg_str =  "set chat " + msg_str[5:].strip()
            show_mode = "chat"
        elif msg_str.startswith(".骰面"):
            arg_str =  "set default_dice " + msg_str[3:].strip()
            show_mode = "dice"
        elif msg_str.startswith(".dice"):
            arg_str =  "set default_dice " + msg_str[5:].strip()
            show_mode = "dice"
        else:
            should_proc = False

        hint = (arg_str, show_mode)
        return should_proc, should_pass, hint

    def process_msg(self, msg_str: str, meta: MessageMetaData, hint: Any) -> List[BotCommandBase]:
        port = GroupMessagePort(meta.group_id)
        # 解析语句
        if hint[0] == "":
            arg_list = []
            arg_num = 0
        else:
            arg_list = [arg for arg in hint[0].split(" ") if arg != ""]
            arg_num = len(arg_list)
        show_mode = hint[1]
        feedback: str = ""
        set_format: str = ""

        if arg_num == 0:
            feedback = self.get_help(".config",meta)
        elif arg_list[0] == "set":
            if arg_num == 3 and arg_list[1] in DEFAULT_GROUP_CONFIG.keys():
                var_data = None
                var_str = ""
                var_type = type(DEFAULT_GROUP_CONFIG[arg_list[1]])
                # 检测输入类型
                if arg_list[2] in ["真","是","开","开启","true","yes","on"]:
                    #self.set_group_config(meta.group_id,arg_list[1],True)
                    var_data = True
                    var_str = "开启(True)"
                elif arg_list[2] in ["假","否","关","关闭","false","no","off"]:
                    #self.set_group_config(meta.group_id,arg_list[1],False)
                    var_data = False
                    var_str = "关闭(False)"
                elif arg_list[2].isdigit():
                    #self.set_group_config(meta.group_id,arg_list[1],int(arg_list[2]))
                    var_data = int(arg_list[2])
                    var_str = arg_list[2]
                else:
                    var_data = arg_list[2]
                    var_str = arg_list[2]
                # 检测输入类型是否合规，修改设置
                if isinstance(var_data,var_type):
                    self.set_group_config(meta.group_id,arg_list[1],var_data)
                    #特定简写改数据指令的回复会使用到特定loc文本
                    if show_mode == "chat": #对话开关
                        if var_data:
                            feedback = self.bot.loc_helper.format_loc_text(LOC_GROUP_CHAT_ON)
                        else:
                            feedback = self.bot.loc_helper.format_loc_text(LOC_GROUP_CHAT_OFF)
                    elif show_mode == "dice": #掷骰开关
                        feedback = self.bot.loc_helper.format_loc_text(LOC_GROUP_DICE_SET,var=var_str)
                    else:
                        feedback = self.bot.loc_helper.format_loc_text(LOC_GROUP_CONFIG_SET,var_name=arg_list[1],var=var_str)
                else:
                    feedback = "违规的数据类型。"
            else:
                feedback = "参数错误"
        elif arg_list[0] == "get":
            if arg_num == 2:
                feedback = str(self.get_group_config(meta.group_id,arg_list[1]))
                feedback = self.bot.loc_helper.format_loc_text(LOC_GROUP_CONFIG_SET,var_name=arg_list[1],var=feedback)
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
            feedback = "未知指令。"
            

        return [BotSendMsgCommand(self.bot.account, feedback, [port])]

    def set_group_config(self, group_id: str, name: str, data: Any) -> None:
        self.bot.data_manager.set_data(DC_GROUPCONFIG, [group_id,name],data)

    def get_group_config(group_id: str, name: str) -> Any:
        data : Any = self.bot.data_manager.get_data(DC_GROUPCONFIG, [group_id,name],default_val=None)
        if not data:
            data = DEFAULT_GROUP_CONFIG[name]
        return data

    def clear_group_config(self, group_id: str) -> None:
        self.bot.data_manager.delete_data(DC_GROUPCONFIG, [group_id])
    
    def update_group_config(self, group_id: str, setting: List[str], var:List[str]):
        self.clear_group_config(group_id) 
        for index in range(len(setting)):
            self.set_group_config(group_id,setting[index],var[index])


    def get_help(self, keyword: str, meta: MessageMetaData) -> str:
        if keyword == "config":  # help后的接着的内容
            feedback: str = ".config set [设置名] [参数值]" \
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
                            "显示全部可用设置"
            return feedback
        elif keyword == "dice":  # help后的接着的内容
            feedback: str = ".dice [骰面]" \
                            "设置群内默认投掷的骰子面数"
            return feedback
        elif keyword == "chat":  # help后的接着的内容
            feedback: str = ".chat on" \
                            "开启群内骰娘个性化对话功能（默认开启）" \
                            ".chat off" \
                            "关闭群内骰娘个性化对话功能"
            return feedback
        return ""

    def get_description(self) -> str:
        return ".config 群配置系统"  # help指令中返回的内容
