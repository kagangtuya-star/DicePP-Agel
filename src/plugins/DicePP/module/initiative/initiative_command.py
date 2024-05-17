from typing import List, Tuple, Dict, Any

from core.bot import Bot
from core.data import DataManagerError
from core.command.const import *
from core.command import UserCommandBase, custom_user_command
from core.command import BotCommandBase, BotSendMsgCommand
from core.communication import MessageMetaData, PrivateMessagePort, GroupMessagePort, preprocess_msg
from module.roll import RollResult, RollExpression, preprocess_roll_exp, parse_roll_exp, RollDiceError, is_roll_exp, sift_roll_exp_and_reason

from module.initiative.initiative_list import DC_INIT, InitList, InitiativeError
from module.initiative.initiative_entity import InitEntity
from module.initiative.battleroll_command import LOC_BR_ROUND_SHOW
from utils.string import match_substring

LOC_INIT_ROLL = "initiative_roll"
LOC_INIT_INFO = "initiative_info"
LOC_INIT_INFO_NOT_EXIST = "initiative_info_not_exist"
LOC_INIT_ENTITY_NOT_FOUND = "initiative_entity_not_found"
LOC_INIT_ENTITY_VAGUE = "initiative_entity_vague"
LOC_INIT_ENTITY_TEN_PLACEHOLDERS = "initiative_entity_ten_placeholders"
LOC_INIT_ENTITY_REPEAT = "initiative_entity_repeat"
LOC_INIT_ENTITY_SAME = "initiative_entity_same"
LOC_INIT_ENTITY_SAME_LIST = "initiative_entity_same_list"
LOC_INIT_ENTITY_FIRST = "initiative_entity_first"
LOC_INIT_ENTITY_SWAP = "initiative_entity_swap"
LOC_INIT_INFO_CLR = "initiative_info_clear"
LOC_INIT_INFO_DEL = "initiative_info_delete"
LOC_INIT_INFO_DEL_THIS_TURN = "initiative_info_delete_this_turn"
LOC_INIT_UNKNOWN = "initiative_unknown_command"
LOC_INIT_ERROR = "initiative_error"


@custom_user_command(readable_name="先攻指令",
                     priority=-1,  # 要比掷骰命令前, 否则.r会覆盖.ri
                     group_only=True,
                     flag=DPP_COMMAND_FLAG_DND | DPP_COMMAND_FLAG_BATTLE)
class InitiativeCommand(UserCommandBase):
    """
    先攻指令, 以.init开头
    """

    def __init__(self, bot: Bot):
        super().__init__(bot)
        bot.loc_helper.register_loc_text(LOC_INIT_ROLL,
                                         "{name}的先攻值是 {init_result}",
                                         ".ri返回的语句 {name}:昵称; {init_result}:先攻掷骰结果")
        bot.loc_helper.register_loc_text(LOC_INIT_INFO,
                                         "先攻列表如下: \n{init_info}",
                                         ".init返回的语句 {init_info}: 先攻列表信息")
        bot.loc_helper.register_loc_text(LOC_INIT_INFO_NOT_EXIST,
                                         "没有找到先攻列表",
                                         "输入.init但没有设置过先攻时返回的语句")
        bot.loc_helper.register_loc_text(LOC_INIT_INFO_CLR,
                                         "已清除先攻列表",
                                         ".init clr返回的语句")
        bot.loc_helper.register_loc_text(LOC_INIT_ENTITY_NOT_FOUND,
                                         "先攻里不存在",
                                         "使用.init指令选择不存在的条目时返回")
        bot.loc_helper.register_loc_text(LOC_INIT_ENTITY_VAGUE,
                                         "存在多种可能的结果：{name_list}",
                                         "使用.init指令选择的条目存在歧义 {name_list}:所有匹配的结果")
        bot.loc_helper.register_loc_text(LOC_INIT_ENTITY_REPEAT,
                                         "你重复投掷了先攻",
                                         "重复投掷先攻时的提示")
        bot.loc_helper.register_loc_text(LOC_INIT_ENTITY_TEN_PLACEHOLDERS,
                                         "{name}A\n{name}B\n{name}C\n{name}D\n{name}E\n{name}F\n{name}G\n{name}H\n{name}I\n{name}J",
                                         "进行一次性多单位投掷时，为每个生物名称添加的变化。注意，每个必须是正好10行，不能多不能少。")
        bot.loc_helper.register_loc_text(LOC_INIT_ENTITY_SAME,
                                         "出现相同先攻值，请DM来决定由谁先行动，若不决定将保持默认顺序：",
                                         "出现相同先攻值时的提示")
        bot.loc_helper.register_loc_text(LOC_INIT_ENTITY_SAME_LIST,
                                         "回复.init fst {entity_list}",
                                         "出现相同先攻值时，重复者的列表 {entity_list}:重复对象A/重复对象B")
        bot.loc_helper.register_loc_text(LOC_INIT_ENTITY_FIRST,
                                         "{name}的先攻已在相同先攻值中被提前",
                                         "提前相同先攻值中对象的位置 {name}:提前对象")
        bot.loc_helper.register_loc_text(LOC_INIT_ENTITY_SWAP,
                                         "{name1}与{name2}的先攻值已互换",
                                         "互换两个对象的先攻值与位置 {name1}与{name2}:互换对象")
        bot.loc_helper.register_loc_text(LOC_INIT_INFO_DEL,
                                         "已从先攻列表中移除 {entity_list}",
                                         ".init del [目标名称]删除目标后返回的语句")
        bot.loc_helper.register_loc_text(LOC_INIT_INFO_DEL_THIS_TURN,
                                         "已从先攻列表中移除本回合的参战者 {entity}",
                                         ".init del不带任何目标时，删除本回合条目时返回的语句")
        bot.loc_helper.register_loc_text(LOC_INIT_UNKNOWN,
                                         "子指令{invalid_command}无效," +
                                         "可用子指令如下：{sub_command_list}",
                                         ".init 后面跟的子指令无效, {invalid_command}:用户输入的指令;" +
                                         " {sub_command_list}:当前所有可用的子指令")
        bot.loc_helper.register_loc_text(LOC_INIT_ERROR,
                                         "进行先攻或先攻掷骰指令时出现问题： {error_info}",
                                         "处理.init或.ri指令时出现问题 {error_info}:错误信息")

    def can_process_msg(self, msg_str: str, meta: MessageMetaData) -> Tuple[bool, bool, Any]:
        should_proc: bool = msg_str.startswith(".ri") or msg_str.startswith(".init") or msg_str.startswith(".先攻")
        # 处理一下录卡的.先攻检定指令
        if (msg_str.startswith(".先攻检定")):
            should_proc = False
        should_pass: bool = False
        return should_proc, should_pass, None

    def process_msg(self, msg_str: str, meta: MessageMetaData, hint: Any) -> List[BotCommandBase]:
        # 回复端口
        port = GroupMessagePort(meta.group_id) if meta.group_id else PrivateMessagePort(meta.user_id)

        # 解析语句
        mode: str
        feedback: str = ""
        if msg_str.startswith(".ri"):
            mode = "roll"
            arg_str = meta.plain_msg[3:].strip()
        elif msg_str.startswith(".init") or msg_str.startswith(".先攻"):
            if msg_str.startswith(".先攻"):
                arg_str = msg_str[3:].strip()
            else:
                arg_str = msg_str[5:].strip()
            # 模式
            if not arg_str or arg_str.startswith("list") or arg_str.startswith("列表"):
                mode = "inspect"
                arg_str = ""
            elif arg_str.startswith("clr") or arg_str.startswith("清除"):
                mode = "clear"
                arg_str = ""
            elif arg_str.startswith("del"):
                mode = "delete"
                arg_str = arg_str[3:]
            elif arg_str.startswith("刪除"):
                mode = "delete"
                arg_str = arg_str[2:]
            elif arg_str.startswith("fst"):
                mode = "first"
                arg_str = arg_str[3:]
            elif arg_str.startswith("提前"):
                mode = "first"
                arg_str = arg_str[2:]
            elif arg_str.startswith("swap"):
                mode = "swap"
                arg_str = arg_str[4:]
            elif arg_str.startswith("交换"):
                mode = "swap"
                arg_str = arg_str[2:]
            elif arg_str.startswith("import"):
                mode = "import"
                arg_str = arg_str[6:]
            elif arg_str.startswith("导入"):
                mode = "import"
                arg_str = arg_str[2:]
            else:
                feedback = self.format_loc(LOC_INIT_UNKNOWN, invalid_command=arg_str,
                                           sub_command_list=["list/列表", "clr/清除", "del/刪除","fst/提前","swap/交换","import/导入"])
                return [BotSendMsgCommand(self.bot.account, feedback, [port])]
        else:
            return [
                BotSendMsgCommand(self.bot.account, "Undefined error occur during process initiative command", [port])]
        feedback: str

        # 处理指令
        if mode == "roll":  # 创造先攻条目
            # 分割条目名称与掷骰表达式
            exp_str: str = arg_str.strip()
            name: str = ""
            if len(exp_str) > 0:
                if exp_str[0] in ["+","-","*","/"]:
                    exp_str = "D20" + exp_str  # 因为要处理优劣势所以不能写1D20
                elif exp_str[0] == "=":
                    exp_str = exp_str[1:]
                elif "优势" in exp_str or "劣势" in exp_str:
                    exp_str = "D20" + exp_str  # 因为要处理优劣势所以不能写1D20
            # 新版本直接利用这种方式进行拆分
            exp_str, name = sift_roll_exp_and_reason(exp_str)
            """
            # 显式给出空格时
            if " " in arg_str:
                exp_str, name = arg_str.split(" ", 1)
                arg_str = exp_str
            # 为了支持类似 .ri+1强盗 .ri20巢穴动作 的用法, 不使用空格分割姓名与字符串时从后到前暴力测试
            for name_index in range(len(arg_str), -1, -1):
                arg_test = arg_str[:name_index].strip()
                name_test = arg_str[name_index:].strip()
                if name_test and name_test[0] in ["#", "/"]:  # 名称不能以这些单词开头
                    continue
                if not name_test:
                    name_test = name
                if not arg_test:  # 类似.ri 或 .ri强盗 这样的用法
                    exp_str, name = "d20", name_test
                    break
                elif is_roll_exp(arg_test) and arg_test[0] != "+" and arg_test[0] != "-":  # 类似.ri15 或 .ri20巢穴动作 的用法
                    exp_str, name = arg_test, name_test
                    break
                elif is_roll_exp("d20"+arg_test):  # 类似.ri优势 或 .ri+1 的用法
                    exp_str, name = "d20"+arg_test, name_test
                    break
                if name:  # 如果此时name不为空, 说明已经通过空格显式分割了表达式与姓名, 失败则不用继续尝试
                    break
                if len(arg_str) - name_index > 100:  # 避免尝试太多次
                    break
            """
            # 如果没有设置名称, 说明用自己的昵称, 否则是NPC
            owner_id = ""
            if not name:
                # 已知在这个位置处理昵称会出现问题，因此后置
                # name = self.bot.get_nickname(meta.user_id, meta.group_id)
                name = "self"
                owner_id = meta.user_id

            # 处理复数先攻
            name_dict: Dict[str, RollResult] = {}
            for n in name.split("/"):  # 对于 .ri 地精/大地精 这种情况
                n = n.strip()
                advantage = n.endswith("优势") or n.endswith("優勢")
                disadvantage = n.endswith("劣势") or n.endswith("劣勢")

                final_exp_str = exp_str  # 处理 .ri 地精+1/地精优势这种情况
                if advantage or disadvantage:  # 处理额外优劣势
                    if advantage:
                        if "d20优势" in final_exp_str:
                            pass
                        elif "d20劣势" in final_exp_str:
                            final_exp_str = final_exp_str.replace("d20劣势", "d20", 1)
                        elif "d20" in final_exp_str:
                            final_exp_str = final_exp_str.replace("d20", "d20优势", 1)
                        n = n[:-2]
                    elif disadvantage:
                        if "d20劣势" in final_exp_str:
                            pass
                        elif "d20优势" in final_exp_str:
                            final_exp_str = final_exp_str.replace("d20优势", "d20", 1)
                        elif "d20" in final_exp_str:
                            final_exp_str = final_exp_str.replace("d20", "d20劣势", 1)
                        n = n[:-2]
                # 尝试处理额外加值, 额外加值必须以+/-开头
                if "+" in n or "-" in n:
                    add_index = n.find("+") if "+" in n else 2**20
                    sub_index = n.find("-") if "-" in n else 2**20
                    split_index = min(add_index, sub_index)
                    final_exp_str = final_exp_str + n[split_index:]
                    n = n[:split_index]

                # 得到先攻结果
                try:
                    roll_exp: RollExpression = parse_roll_exp(preprocess_roll_exp(final_exp_str))
                except RollDiceError as e:  # 无效的掷骰表达式
                    return [BotSendMsgCommand(self.bot.account, e.info, [port])]

                if not n:
                    continue
                if "#" in n:  # 对于 .ri 3#地精 这种情况
                    num, n = n.split("#", 1)
                    try:
                        num = int(num)
                        assert 1 <= num <= 10
                    except (ValueError, AssertionError):
                        return [BotSendMsgCommand(self.bot.account, f"{num}不是一个有效的数字 (1~10)", [port])]
                    # 获取先攻名称
                    placeholders = self.format_loc(LOC_INIT_ENTITY_TEN_PLACEHOLDERS,name=n).strip().split("\n")
                    if len(placeholders) == 10: # 必须正好10个
                        for i in range(num):
                            name_dict[placeholders[i]] = roll_exp.get_result()
                    else: # 真的么，你居然不是10个
                        for i in range(num):
                            name_dict[n + chr(ord("A") + i)] = roll_exp.get_result()
                else:
                    # 获取先攻结果
                    try:
                        name_dict[n] = roll_exp.get_result()
                    except RollDiceError as e:  # 无效的掷骰表达式
                        return [BotSendMsgCommand(self.bot.account, e.info, [port])]

            result_dict: Dict[str, Tuple[int, str]] = dict()
            for name, res in name_dict.items():
                if name in ["self","我"] :
                    name = self.bot.get_nickname(meta.user_id, meta.group_id)
                result_dict[name] = (res.get_val(), res.get_complete_result())

            feedback = self.add_initiative_entities(result_dict, owner_id, meta.group_id)

            return [BotSendMsgCommand(self.bot.account, feedback, [port])]
        
        # 处理不需要有表存在就能使用的指令
        if mode == "import":  # 导入先攻数据
            lines: List[str] = arg_str.strip().splitlines()
            result_dict: Dict[str, Tuple[int, str]] = dict()
            for line in lines:
                if "." in line and " 先攻:" in line:
                    data = line.split(".",1)[1].split(" 先攻:")
                    if " " in data[-1]:
                        data[-1] = data[-1].split(" ",1)[0]
                    if data[-1].isdigit():
                        result_dict["".join(data[:-1])] = (int(data[-1]),data[-1] + "(导入)")
            
            if len(result_dict) > 0:
                feedback = self.add_initiative_entities(result_dict, "", meta.group_id)
            else:
                feedback = self.format_loc(LOC_INIT_INFO_NOT_EXIST)
            return [BotSendMsgCommand(self.bot.account, feedback, [port])]
        
        # 先找到先攻数据是否存在
        init_data: dict
        try:
            init_data = self.bot.data_manager.get_data(DC_INIT, [meta.group_id], get_ref=True)
        except DataManagerError:
            feedback = self.format_loc(LOC_INIT_INFO_NOT_EXIST)
            return [BotSendMsgCommand(self.bot.account, feedback, [port])]
        # 更新玩家姓名
        for entity in init_data.entities:
            if entity.owner:  
                entity.name = self.bot.get_nickname(entity.owner, meta.group_id)
                entity.compatible_name = preprocess_msg(entity.name)

        # 处理需要有表存在才能使用的指令
        if mode == "inspect":  # 查看先攻信息
            # 尝试获取生命值信息
            from module.character.dnd5e import DC_CHAR_HP, DC_CHAR_DND, HPInfo, DNDCharInfo
            hp_dict: Dict[str, HPInfo] = self.bot.data_manager.get_data(DC_CHAR_HP, [meta.group_id], default_val={})
            char_dict: Dict[str, DNDCharInfo] = self.bot.data_manager.get_data(DC_CHAR_DND, [meta.group_id], default_val={})
            hp_dict.update(dict([(user_id, char_info.hp_info) for user_id, char_info in char_dict.items()]))
            init_info = ""
            for index, entity in enumerate(init_data.entities):
                entity: InitEntity = entity
                # 生命值信息
                entity_hp_info: str = ""
                if entity.owner and entity.owner in hp_dict:  # 玩家HP信息
                    entity_hp_info = f"{hp_dict[entity.owner].get_info()}"
                if not entity.owner and entity.compatible_name in hp_dict:  # NPC信息
                    entity_hp_info = f"{hp_dict[entity.compatible_name].get_info()}"
                init_info += f"{index + 1}.{entity.get_info()} {entity_hp_info}\n"
            init_info = init_info.strip()  # 去掉末尾的换行
            feedback = self.format_loc(LOC_INIT_INFO, init_info=init_info)
            return [BotSendMsgCommand(self.bot.account, feedback, [port])]

        elif mode == "clear":  # 清除所有先攻信息
            feedback = ""
            # 尝试删除临时生命值信息
            try:
                from module.character.dnd5e import DC_CHAR_HP, HPInfo
                init_data: InitList = self.bot.data_manager.get_data(DC_INIT, [meta.group_id])
                for entity in init_data.entities:
                    if not entity.owner:
                        try:
                            hp_info: HPInfo = self.bot.data_manager.get_data(DC_CHAR_HP, [meta.group_id, entity.compatible_name])
                            assert hp_info.hp_max == 0  # 不清除已经设置了最大生命值的生命值信息
                            self.bot.data_manager.delete_data(DC_CHAR_HP, [meta.group_id, entity.compatible_name])
                        except DataManagerError:  # 没有设置生命值信息
                            pass
                        except AssertionError:  # 已经设置最大生命值
                            if not feedback:
                                feedback = "注意: 没有清除已设置最大生命值的 "
                            feedback += entity.name + " "
            except (ImportError, DataManagerError):  # 没有生命值模块或没有先攻信息
                pass
            if feedback:
                feedback = feedback.strip() + "的生命值信息\n"
            # 尝试删除先攻信息
            self.bot.data_manager.delete_data(DC_INIT, [meta.group_id])
            feedback += self.format_loc(LOC_INIT_INFO_CLR)
            return [BotSendMsgCommand(self.bot.account, feedback, [port])]

        elif mode == "first":  # 提前先攻条目
            index = None
            names, feedback = self.find_valid_entities([arg_str.strip()],init_data)
            if feedback != "":
                return [BotSendMsgCommand(self.bot.account, feedback, [port])]
            # 寻找目标的位置
            name = names[0]
            init_val: int = 0
            for i, entity in enumerate(init_data.entities):
                if entity.compatible_name == name:
                    index = i
                    init_val = entity.init
                    break

            for i, entity in enumerate(init_data.entities):
                if i <= index and entity.init == init_val:
                    init_data.entities[i], init_data.entities[index] = init_data.entities[index], init_data.entities[i]
            feedback = self.format_loc(LOC_INIT_ENTITY_FIRST, name = name)
            return [BotSendMsgCommand(self.bot.account, feedback, [port])]

        elif mode == "swap":  # 交换先攻条目
            arg_str = arg_str.strip()
            swap_target_l: str = ""
            swap_target_r: str = ""
            # 处理目标
            if "/" in arg_str:
                swap_target_l = arg_str.split("/",1)[0].strip()
                swap_target_r = arg_str.split("/",1)[1].strip()
            elif " " in arg_str:
                swap_target_l = arg_str.split(" ",1)[0].strip()
                swap_target_r = arg_str.split(" ",1)[1].strip()
            else:
                swap_target_l = self.bot.get_nickname(meta.user_id, meta.group_id)
                swap_target_r = arg_str
            # 寻找更换目标
            name_list_valid_l: List[str]
            name_list_valid_r: List[str]
            feedback_a: str
            name_list_valid_l, feedback = self.find_valid_entities([swap_target_l],init_data)
            name_list_valid_r, feedback_a = self.find_valid_entities([swap_target_r],init_data)
            if feedback != "":
                feedback = feedback.strip() + "\n" + feedback_a.strip()
            else:
                feedback = feedback_a.strip()
            # 必须各有一体，否则无法互换
            if len(name_list_valid_l) > 0 and len(name_list_valid_r) > 0:
                l_index: int = 0
                r_index: int = 0
                for i, entity in enumerate(init_data.entities):
                    if entity.compatible_name == name_list_valid_l[0]:
                        l_index = i
                    elif entity.compatible_name == name_list_valid_r[0]:
                        r_index = i
                feedback = self.format_loc(LOC_INIT_ENTITY_SWAP, name1 = init_data.entities[l_index].name, name2 = init_data.entities[r_index].name)
                init_data.entities[l_index].init,init_data.entities[r_index].init = init_data.entities[r_index].init,init_data.entities[l_index].init
                init_data.entities[l_index],init_data.entities[r_index] = init_data.entities[r_index],init_data.entities[l_index]
                feedback = self.format_loc(LOC_INIT_ENTITY_SWAP, name1 = name_list_valid_l[0], name2 = name_list_valid_r[0])
            # 检测是否因此更改了回合，是的话提示一下回合变化
            if not init_data.first_turn and (init_data.turn == l_index+1 or init_data.turn == r_index+1):
                feedback += "\n" + self.format_loc(LOC_BR_ROUND_SHOW,round=str(init_data.round),turn=str(init_data.turn),turn_name=init_data.entities[init_data.turn-1].name)
            # 错误信息已经给出了
            return [BotSendMsgCommand(self.bot.account, feedback, [port])]

        elif mode == "delete":  # 删除先攻条目
            # 在列表中搜索名字, 结果加入到name_list_valid
            arg_str = arg_str.strip()
            name_list_valid: List[str]
            turn_skipped = False
            if arg_str == "":
                if not init_data.first_turn:
                    name_list_valid = [init_data.entities[init_data.turn-1].compatible_name]
                    turn_skipped = True
                else:
                    feedback += self.format_loc(LOC_INIT_ENTITY_NOT_FOUND)
                    return [BotSendMsgCommand(self.bot.account, feedback, [port])]
            else:
                name_list: List[str] = [name.strip() for name in arg_str.split("/")]  # 类似.init del A/B/C 这样的用法
                name_list_valid, feedback = self.find_valid_entities(name_list,init_data)
            # 删除
            if name_list_valid:
                name_list_deleted: List[str] = []
                for v_name in name_list_valid:
                    # 删除生命值信息
                    index = -1
                    for i, entity in enumerate(init_data.entities):
                        if entity.name == v_name or entity.compatible_name == v_name:
                            index = i
                            if index == init_data.turn-1:
                                turn_skipped = True
                            break
                    if not init_data.entities[index].owner:
                        try:
                            from module.character.dnd5e import DC_CHAR_HP
                            self.bot.data_manager.delete_data(DC_CHAR_HP, [meta.group_id, entity.name])
                        except (ImportError, DataManagerError):  # 没有设置生命值信息
                            pass
                    # 删除先攻信息
                    try:
                        name_list_deleted.append(str(entity.name))
                        init_data.del_entity(v_name)
                    except InitiativeError as e:
                        feedback += self.format_loc(LOC_INIT_ERROR, error_info=e.info) + "\n"
                if name_list_deleted:
                    if arg_str == "":
                        feedback += self.format_loc(LOC_INIT_INFO_DEL_THIS_TURN, entity=name_list_deleted[0])
                    else:
                        feedback += self.format_loc(LOC_INIT_INFO_DEL, entity_list="、".join(name_list_deleted))
                    # 检测是否因此更改了回合，是的话提示一下回合变化
                    if not init_data.first_turn and init_data.turns_in_round > 0 and turn_skipped:
                        if init_data.turn > init_data.turns_in_round:
                            init_data.round += 1
                            init_data.turn = 1
                        feedback += "\n" + self.format_loc(LOC_BR_ROUND_SHOW,round=str(init_data.round),turn=str(init_data.turn),turn_name=init_data.entities[init_data.turn-1].name)
                feedback = feedback.strip()
            return [BotSendMsgCommand(self.bot.account, feedback, [port])]

    def get_help(self, keyword: str, meta: MessageMetaData) -> str:
        if keyword == "init" or keyword == "先攻":
            help_str = "显示先攻列表：.init ([可选指令]) [可选指令]:clr 清空先攻列表 del 删除指定先攻条目 fst 稍微提前先攻条目 swap 交互先攻条目\n" \
                       "del指令支持部分匹配\n" \
                       "hp信息也会在先攻列表上显示\n" \
                       "示例:\n" \
                       ".先攻 //查看先攻列表\n" \
                       ".先攻清除 //清空先攻列表\n" \
                       ".先攻删除地精 //在先攻列表中删除地精.init del 地精a/地精b/地精c //在先攻列表中删除地精abc\n"\
                       "如需查看投掷先攻相关的指令请输入.help 投掷先攻\n"\
                       "如需查看回合与轮次相关的指令请输入.help 战斗轮"
            return help_str
        if keyword == "ri" or keyword == "投掷先攻":
            help_str = "投掷先攻：.ri([优劣势][加值]) ([名称][/(投骰表达式#)名称/...])\n" \
                       "示例:\n" \
                       ".ri优势+1 //让自己加入先攻列表\n" \
                       ".ri20 地精 //将地精以固定先攻20加入先攻列表\n" \
                       ".ri+2 地精/灵活地精+1/笨拙地精-1 //将3个地精分别加入先攻列表\n" \
                       ".ri-2 2#食人魔僵尸/1d4#兽人僵尸 //将2个食人魔僵尸(a,b)以相同的先攻加入先攻列表,\n" \
                       " 将1d4个兽人僵尸(a~d)以相同的先攻加入先攻列表\n"\
                       "如需查看先攻表格相关的指令请输入.help先攻\n"\
                       "如需查看回合与轮次相关的指令请输入.help 战斗轮"
            return help_str
        return ""

    def get_description(self) -> str:
        return ".ri 投掷先攻 .init 操作先攻列表"
    
    def find_valid_entities(self,name_list: List[str],init_data: InitList) -> Tuple[List[str],str]:
        # O(N*M)暴力搜索寻找匹配对象
        global_list = [entity.compatible_name for index, entity in enumerate(init_data.entities)]
        result_list: List[str] = []
        feedback: str = ""
        for name in name_list:
            match_num = sum([e_name == name for e_name in global_list])  
            if match_num == 1:  # 正好有一个同名条目
                result_list.append(name)
            elif match_num == 0:  # 没有同名条目, 进入模糊搜索
                possible_res: List[str] = match_substring(name, global_list)
                if len(possible_res) == 0:  # 还是没有结果, 提示用户
                    feedback += self.format_loc(LOC_INIT_ENTITY_NOT_FOUND,name=name) + "\n"
                elif len(possible_res) > 1:  # 多个可能的结果, 提示用户
                    possible_name = []
                    for res in possible_res:
                        possible_name += [entity.name for entity in init_data.find_entity(res)]
                    feedback += self.format_loc(LOC_INIT_ENTITY_VAGUE, name_list="\n".join(possible_name)) + "\n"
                elif len(possible_res) == 1:
                    result_list.append(possible_res[0])
            else: #if match_num > 1:  # 多于一个同名条目, 按设计是不可能出现的, 需要排查原因
                feedback += self.format_loc(LOC_INIT_ERROR, error_info=f"列表中存在同名条目{name}, 请联系开发者") + "\n"
        return (result_list,feedback)

    def add_initiative_entities(self, result_dict: Dict[str, Tuple[int, str]], owner_id: str, group_id: str) -> str:
        """

        Args:
            result_dict: 需要加入先攻列表的信息, key为先攻条目名称, val为二元组, val[0]代表先攻数值, val[1]代表掷骰表达式结果
            owner_id: 为空代表无主的NPC, 不为空代表PC账号
            group_id: 目标群号

        Returns:
            feedback: 操作执行成功或失败的提示
        """
        # 获取先攻列表
        init_data: InitList = self.bot.data_manager.get_data(DC_INIT, [group_id], default_gen=InitList, get_ref=True)

        # 针对 .ri 3#地精 这种用法简化一下输出(会产生3次一样的roll_res)
        final_result_dict: Dict[str, Tuple[List[str], int]] = {}
        for name, roll_res in result_dict.items():
            if roll_res[1] not in final_result_dict:
                final_result_dict[roll_res[1]] = ([], roll_res[0])
            final_result_dict[roll_res[1]][0].append(name)
        repeatted : bool = False
        feedback = ""
        same_warn: Dict[int,List[str]] = {}
        feedback_list = []
        for roll_res_str, (name_list, roll_val) in final_result_dict.items():
            is_valid = True
            for name in name_list:
                try:
                    for entity in init_data.entities:
                        if entity.name == name or entity.compatible_name == name:  # 检查有没有同名条目, 有则提示重复
                            repeatted = True
                        elif entity.init == roll_val:  # 检查有没有同值, 有则提示相同，让DM确定先后
                            if roll_val not in same_warn.keys(): # 若存在相同的，则增加一段相同提示
                                same_warn[roll_val] = [name,entity.name]
                            elif entity.name not in same_warn[roll_val]:
                                same_warn[roll_val].append(entity.name)
                    init_data.add_entity(name, owner_id, roll_val)
                except InitiativeError as e:
                    is_valid = False
                    feedback_list.append(self.format_loc(LOC_INIT_ERROR, error_info=e.info))
            if is_valid:
                feedback_list.append(self.format_loc(LOC_INIT_ROLL, name=", ".join(name_list), init_result=roll_res_str))
        if repeatted :
            feedback += self.format_loc(LOC_INIT_ENTITY_REPEAT)
        feedback += "\n".join(feedback_list)
        if len(same_warn) > 0:
            same_warn_feedback = "\n".join([self.format_loc(LOC_INIT_ENTITY_SAME_LIST, entity_list =" / ".join(entities)) for entities in same_warn.values()])
            feedback += "\n" + self.format_loc(LOC_INIT_ENTITY_SAME) + "\n" + same_warn_feedback
        return feedback
