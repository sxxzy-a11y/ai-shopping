"""领域异常与面向用户的中文文案映射。

设计要点：业务模块只抛领域异常，界面在边界处调用 to_user_message()
取中文提示。这样「不向用户暴露堆栈」这件事只需在一个地方保证，
文案也只在一个地方维护。
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# 异常类型
# --------------------------------------------------------------------------


class ZhigouError(Exception):
    """本项目所有领域异常的基类。

    子类通过类属性声明默认中文文案；实例可以覆盖。
    额外上下文放在 self.detail 里，供日志使用，不进界面。
    """

    default_message: str = "处理请求时发生问题，请稍后重试。"

    def __init__(self, message: str | None = None, *, detail: str | None = None) -> None:
        self.detail = detail
        super().__init__(message or self.default_message)

    @property
    def user_message(self) -> str:
        """给普通用户看的中文文案。"""
        return str(self)


# --- 数据层 -----------------------------------------------------------------


class DataFileMissing(ZhigouError):
    """种子数据文件缺失。商品数据已改存数据库，这个错误现在只在
    「库为空、且没有种子文件可导入」时出现。"""

    default_message = (
        "商品库为空，且找不到种子数据文件 data/products.json，无法初始化商品数据。"
    )


class DataFileInvalid(ZhigouError):
    default_message = "商品数据解析失败，请检查数据内容是否合法。"


class EmptyCatalog(ZhigouError):
    default_message = "当前没有可用于分析的商品数据，请先向商品库中补充商品。"


class FieldValidationError(ZhigouError):
    default_message = "商品数据字段不完整，部分商品已按信息不完整处理。"


# --- 输入层 -----------------------------------------------------------------


class EmptyDemand(ZhigouError):
    default_message = "请先描述你的购买需求，或至少选择商品类型。"


class InvalidBudget(ZhigouError):
    default_message = "预算必须填写为大于 0 的数字，例如 3000。"


class DemandParseError(ZhigouError):
    default_message = "无法理解这段需求描述，请换一种说法或使用下方的结构化选项。"


class TooFewForComparison(ZhigouError):
    default_message = "请至少选择 2 件商品进行比较。"


class TooManyForComparison(ZhigouError):
    default_message = "选择的商品数量过多，请减少后再比较。"


class MixedCategoryComparison(ZhigouError):
    default_message = "一次只能比较同一类别的商品，请先移除其他类别的商品。"


# --- 大模型层 ---------------------------------------------------------------


class AINotConfigured(ZhigouError):
    default_message = "未配置大模型 API 密钥，已切换到本地演示模式。"


class UpstreamTimeout(ZhigouError):
    default_message = "AI 服务响应超时，已切换到本地规则模式完成本次分析。"


class UpstreamAuthError(ZhigouError):
    default_message = "AI 服务鉴权失败，密钥可能无效或已过期，已切换到本地规则模式。"


class UpstreamUnavailable(ZhigouError):
    default_message = "AI 服务暂时不可用，已切换到本地规则模式完成本次分析。"


class UpstreamResponseError(ZhigouError):
    default_message = "AI 返回的内容无法解析，已回退到本地规则模式。"


# --- 存储与导出 -------------------------------------------------------------


class HistoryReadError(ZhigouError):
    default_message = "历史记录读取失败，可能是本地数据库文件损坏。当前仍可进行新的分析。"


class HistoryWriteError(ZhigouError):
    default_message = "本次分析记录保存失败，结果仍可在当前页面查看。"


class ProductStoreReadError(ZhigouError):
    """商品库读取失败。与历史记录读取失败分开——两者可独立恢复。"""

    default_message = "商品数据读取失败，可能是本地数据库文件损坏。"


class ProductStoreWriteError(ZhigouError):
    default_message = "商品数据写入失败，本次变更未生效。"


class ExportError(ZhigouError):
    default_message = "导出失败，请检查目标位置是否可写后重试。"


# --- 账号与鉴权 -------------------------------------------------------------


class InvalidUsername(ZhigouError):
    """用户名不合规。具体长度要求由 `src/auth.py` 的常量拼进文案，
    避免「规则改了一处、提示还写着旧数字」。"""

    default_message = "用户名不合规，请换一个。"


class WeakPassword(ZhigouError):
    default_message = "密码强度不足，请换一个更长的密码。"


class UsernameTaken(ZhigouError):
    default_message = "该用户名已被占用，请换一个。"


class InvalidCredentials(ZhigouError):
    """用户名不存在或密码错误。

    **刻意不区分这两种情况**：文案只有一句，调用方也无法把原因透出去。
    能分开说，就等于提供了一个枚举「哪些用户名存在」的地方。
    """

    default_message = "用户名或密码不正确。"


class AccountDisabled(InvalidCredentials):
    """账号已停用。

    文案**故意与 `InvalidCredentials` 完全相同**（继承而非复制，两者永远同步）：
    「这个账号存在但被停用了」同样是不该告诉访问者的信息。
    真实原因写进 `detail`，那只进日志。
    """


class PermissionDenied(ZhigouError):
    """越权。**这不是界面层的提示文案，是守卫抛出的异常**——
    普通用户直接调用管理员操作时必须拿到它（design D3）。"""

    default_message = "当前账号没有执行该操作的权限。"


class InvalidImageUrl(ZhigouError):
    """图片地址不合规。空值是允许的——「没有图片」是一种如实的状态。"""

    default_message = "图片地址必须以 http:// 或 https:// 开头。"


class InvalidSpec(ZhigouError):
    """商品参数不合规：键不属于该分类，或取值超出既有档位/区间。"""

    default_message = "商品参数不合规，请检查参数名与取值。"


class ProductValidationFailed(ZhigouError):
    """写入前的整体校验没通过。`detail` 里带着逐条问题，界面会列出来。"""

    default_message = "商品数据校验未通过，本次修改没有写入。"


class LastAdminProtected(ZhigouError):
    """会动到「最后一个可用管理员」的操作被拒绝。

    与 `PermissionDenied` 分开：那是「你没有权限」，这是「谁来做都不行」。
    两者对用户是两句不同的话，混用会让人以为自己权限不够。
    """

    default_message = "系统必须至少保留一个可用的管理员账号，该操作已被拒绝。"


# --------------------------------------------------------------------------
# 文案映射
# --------------------------------------------------------------------------

#: 兜底文案，用于**非领域异常**（意料之外的 TypeError 之类）。
#:
#: 这里原本还有一张 `_MESSAGE_BY_TYPE`（异常类 → 文案）的映射表，但全项目
#: 没有一处读它——`to_user_message()` 取的是实例上的 `user_message`，
#: 那才是能带上本次上下文的那一份。留着它是**陷阱**：新增异常类的人会去
#: 那张表里登记一行，以为起了作用，实际什么也没发生。已删除。
FALLBACK_MESSAGE = "操作未能完成，请稍后重试。若问题持续，请查看调试日志。"


def to_user_message(error: BaseException) -> str:
    """把任意异常转成可以安全展示给用户的中文文案。

    非领域异常（例如意料之外的 TypeError）一律返回兜底文案，
    绝不把原始报错内容透出去——原始信息只应进日志。
    """
    if isinstance(error, ZhigouError):
        return error.user_message
    return FALLBACK_MESSAGE
