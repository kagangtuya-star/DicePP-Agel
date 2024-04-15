import abc


class RequestData(metaclass=abc.ABCMeta):
    """请求信息"""
    pass


class FriendRequestData(RequestData):
    """加好友请求"""

    def __init__(self, user_id, comment):
        self.user_id: str = user_id
        self.comment: str = comment


class JoinGroupRequestData(RequestData):
    """其他人的加群请求（骰娘为管理员限定）"""

    def __init__(self, user_id, group_id):
        self.user_id: str = user_id
        self.group_id: str = group_id
        self.comment: str = "无" # 已废弃参数


class InviteGroupRequestData(RequestData):
    """邀请骰娘加群请求"""

    def __init__(self, user_id, group_id):
        self.user_id: str = user_id
        self.group_id: str = group_id
        self.comment: str = "无" # 已废弃参数
