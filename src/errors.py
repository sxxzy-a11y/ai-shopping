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


# --------------------------------------------------------------------------
# 文案映射
# --------------------------------------------------------------------------

#: 兜底文案，用于未登记的异常类型。
FALLBACK_MESSAGE = "操作未能完成，请稍后重试。若问题持续，请查看调试日志。"

_MESSAGE_BY_TYPE: dict[type[ZhigouError], str] = {
    cls: cls.default_message for cls in (
        DataFileMissing,
        DataFileInvalid,
        EmptyCatalog,
        FieldValidationError,
        EmptyDemand,
        InvalidBudget,
        DemandParseError,
        TooFewForComparison,
        TooManyForComparison,
        MixedCategoryComparison,
        AINotConfigured,
        UpstreamTimeout,
        UpstreamAuthError,
        UpstreamUnavailable,
        UpstreamResponseError,
        HistoryReadError,
        HistoryWriteError,
        ExportError,
    )
}


def to_user_message(error: BaseException) -> str:
    """把任意异常转成可以安全展示给用户的中文文案。

    非领域异常（例如意料之外的 TypeError）一律返回兜底文案，
    绝不把原始报错内容透出去——原始信息只应进日志。
    """
    if isinstance(error, ZhigouError):
        return error.user_message
    return FALLBACK_MESSAGE
