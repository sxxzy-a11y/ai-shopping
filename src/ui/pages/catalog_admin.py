"""商品维护页：商品 / 分类 / 品牌三个分块（变更 §8–§10）。

三块合在一页是有意的：它们维护的是同一件事的三层——商品的字段、
商品所属分类的元数据、商品品牌的元数据。分成三个页面，管理员改一件商品
时要来回跳。

**参数用「一行一个 `键: 值`」的文本域编辑**，不引第三方表格组件：
项目零新增依赖，而 `st.data_editor` 的可编辑表格在 AppTest 下不好断言。
文本域还能顺手把「键不认识」「取值越界」的错误位置说清楚——
校验与错误文案都在 `src/catalog_admin.py`，这里只负责渲染。
"""

from __future__ import annotations

import streamlit as st

from src import catalog_admin, catalog_meta, comparison, config
from src.auth import require_admin
from src.errors import ZhigouError, to_user_message
from src.ui import components, state

_KEY_FLASH = "zg_catalog_flash"

_NEW_PREFIX = "zg_cat_new_"


def _viewer():
    return state.current_user()


def _flash(message: str, tone: str) -> None:
    st.session_state[_KEY_FLASH] = (message, tone)


def _render_flash() -> None:
    pending = st.session_state.pop(_KEY_FLASH, None)
    if pending:
        components.show_notice(pending[0], pending[1])


def _apply(action, success: str) -> None:
    """执行一次写操作，记下结果并重跑（与用户管理页同一套反馈机制）。"""
    try:
        action()
    except ZhigouError as exc:
        _flash(to_user_message(exc), "stop")
    else:
        _flash(success, "ok")
    st.rerun()


# --------------------------------------------------------------------------
# 页面
# --------------------------------------------------------------------------


def render(catalog=None) -> None:
    viewer = _viewer()
    require_admin(viewer)

    components.page_header(
        "商品维护",
        "维护商品信息、图片、详情与参数，以及分类与品牌的元数据。"
        "**界面录入的商品一律标为未核验**——是谁填的不等于核实过。",
    )
    _render_flash()

    tab_product, tab_category, tab_brand = st.tabs(["商品", "分类", "品牌"])
    with tab_product:
        _render_products(viewer, catalog)
    with tab_category:
        _render_categories(viewer)
    with tab_brand:
        _render_brands(viewer, catalog)


# --------------------------------------------------------------------------
# 商品块
# --------------------------------------------------------------------------


def _specs_to_text(specs: dict) -> str:
    return "\n".join(f"{key}: {value}" for key, value in (specs or {}).items())


def _text_to_specs(text: str) -> dict:
    """把「一行一个 `键: 值`」解析成参数字典。

    值尽量转成数字：`ram_gb: 16` 该是数字 16，不是字符串 "16"——
    评分要拿它比大小。转不动就原样留着（`cpu: 酷睿 i7` 这类就是这么用的）。
    """
    specs: dict[str, object] = {}
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if not key:
            continue
        specs[key] = _coerce_number(value)
    return specs


def _coerce_number(value: str):
    text = value.strip()
    if not text:
        return ""
    try:
        number = float(text)
    except ValueError:
        return text
    return int(number) if number.is_integer() else number


def _lines_to_list(text: str) -> list[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def _render_products(viewer, catalog) -> None:
    _render_new_product_form(viewer)

    st.divider()
    components.section_title("商品列表")

    try:
        records = catalog_admin.list_products()
    except ZhigouError as exc:
        components.show_notice(to_user_message(exc), "stop")
        return

    components.caption(
        f"共 {len(records)} 件商品。下架的商品不再出现在搜索与推荐中，"
        "但历史记录里已有的引用仍可读——下架不等于删除。"
    )
    components.show_notice(
        "**界面录入不等于核验。** 这里新增或修改的商品一律保持「未核验」，"
        "录入者的身份不构成核验，也不会把既有的来源说明改写成「界面录入」。",
        "warn",
    )

    for record in records:
        _render_product_row(viewer, record)


def _render_new_product_form(viewer) -> None:
    components.section_title("新增商品")

    with st.form("zg_catalog_new_product"):
        col_a, col_b = st.columns(2)
        with col_a:
            product_id = st.text_input("商品 ID", key=f"{_NEW_PREFIX}id")
            name = st.text_input("名称", key=f"{_NEW_PREFIX}name")
            brand = st.text_input("品牌", key=f"{_NEW_PREFIX}brand")
            model = st.text_input("型号", key=f"{_NEW_PREFIX}model")
        with col_b:
            category = st.selectbox(
                "分类",
                options=list(config.CATEGORY_LABELS),
                format_func=config.category_label,
                key=f"{_NEW_PREFIX}category",
            )
            price = st.number_input(
                "参考价（元）", min_value=0.0, step=100.0, key=f"{_NEW_PREFIX}price"
            )
            image_url = st.text_input(
                "图片地址", key=f"{_NEW_PREFIX}image", help="http:// 或 https:// 开头，可留空"
            )
            source_url = st.text_input("来源链接", key=f"{_NEW_PREFIX}source")

        specs = st.text_area(
            "参数",
            key=f"{_NEW_PREFIX}specs",
            help="一行一个「参数名: 取值」。参数名必须是该分类既有的参数。",
            placeholder="cpu_tier: 3\nram_gb: 16\nweight_kg: 1.4",
        )
        use_cases = st.text_area("适用场景", key=f"{_NEW_PREFIX}use_cases", help="一行一个")
        pros = st.text_area("亮点", key=f"{_NEW_PREFIX}pros", help="一行一个")
        cons = st.text_area("不足", key=f"{_NEW_PREFIX}cons", help="一行一个")

        submitted = st.form_submit_button("新增", type="primary")

    if not submitted:
        return

    record = {
        "id": product_id.strip(),
        "name": name.strip(),
        "brand": brand.strip(),
        "category": category,
        "model": model.strip(),
        "price": float(price) if price else None,
        "image_url": image_url,
        "source_url": source_url,
        "specs": _text_to_specs(specs),
        "use_cases": _lines_to_list(use_cases),
        "pros": _lines_to_list(pros),
        "cons": _lines_to_list(cons),
    }
    _apply(
        lambda: catalog_admin.create_product(viewer, record),
        f"已新增商品「{record['name'] or record['id']}」，标为未核验。",
    )


def _render_product_row(viewer, record) -> None:
    product_id = str(record.get("id"))
    active_label = "在售" if record.get("is_active", True) else "**已下架**"
    verified = "已核验" if record.get("data_status") == config.STATUS_VERIFIED else "未核验"

    with st.expander(
        f"{record.get('name') or product_id} · {config.category_label(str(record.get('category')))}"
        f" · {active_label} · {verified}"
    ):
        entered = record.get("entered_by") or "非界面录入"
        components.caption(
            f"ID {product_id} · 品牌 {record.get('brand') or '未填'}"
            f" · 参考价 {record.get('price') if record.get('price') is not None else '未知'}"
            f" · 录入者 {entered}"
        )
        components.caption(f"来源说明：{record.get('data_source') or '（无）'}")

        _render_edit_form(viewer, record)

        st.write("")
        label = "下架" if record.get("is_active", True) else "上架"
        if st.button(label, key=f"zg_cat_active_{product_id}"):
            _apply(
                lambda: catalog_admin.set_active(
                    viewer, product_id, not record.get("is_active", True)
                ),
                f"已{label}「{record.get('name') or product_id}」。",
            )


def _render_edit_form(viewer, record) -> None:
    product_id = str(record.get("id"))
    category = str(record.get("category"))
    known = comparison.param_keys(category)

    with st.form(f"zg_cat_edit_{product_id}"):
        col_a, col_b = st.columns(2)
        with col_a:
            name = st.text_input("名称", value=record.get("name") or "", key=f"zg_cat_name_{product_id}")
            brand = st.text_input("品牌", value=record.get("brand") or "", key=f"zg_cat_brand_{product_id}")
        with col_b:
            model = st.text_input("型号", value=record.get("model") or "", key=f"zg_cat_model_{product_id}")
            image_url = st.text_input(
                "图片地址", value=record.get("image_url") or "", key=f"zg_cat_image_{product_id}"
            )

        specs = st.text_area(
            "参数",
            value=_specs_to_text(record.get("specs") or {}),
            key=f"zg_cat_specs_{product_id}",
            help=f"该分类既有的参数：{'、'.join(known) or '（未登记）'}",
        )
        use_cases = st.text_area(
            "适用场景",
            value="\n".join(record.get("use_cases") or []),
            key=f"zg_cat_use_{product_id}",
        )
        pros = st.text_area("亮点", value="\n".join(record.get("pros") or []), key=f"zg_cat_pros_{product_id}")
        cons = st.text_area("不足", value="\n".join(record.get("cons") or []), key=f"zg_cat_cons_{product_id}")

        saved = st.form_submit_button("保存修改")

    if not saved:
        return

    changes = {
        "name": name.strip(),
        "brand": brand.strip(),
        "model": model.strip(),
        "image_url": image_url,
        "specs": _text_to_specs(specs),
        "use_cases": _lines_to_list(use_cases),
        "pros": _lines_to_list(pros),
        "cons": _lines_to_list(cons),
    }
    _apply(
        lambda: catalog_admin.update_product(viewer, product_id, changes),
        f"已保存「{record.get('name') or product_id}」的修改。",
    )


# --------------------------------------------------------------------------
# 分类块
# --------------------------------------------------------------------------


def _render_categories(viewer) -> None:
    components.section_title("分类")
    components.show_notice(
        "分类的**键集合不可增删**：新增一个分类要同时配评分权重、参数档位"
        "与知识指南，那是改代码与语料的工作量。这里能改的是展示名、排序与启用状态。"
        "**停用不等于删除**——停用后该分类的商品不再出现在搜索与推荐中，数据仍在，"
        "随时可以恢复。",
        "info",
    )

    try:
        entries = catalog_meta.category_entries()
    except ZhigouError as exc:
        components.show_notice(to_user_message(exc), "stop")
        return

    for entry in entries:
        state_label = "启用" if entry.is_active else "**已停用**"
        with st.expander(f"{entry.label}（{entry.key}） · {state_label}"):
            if entry.custom_label:
                components.caption("展示名已被修改。")

            with st.form(f"zg_cat_meta_{entry.key}"):
                label = st.text_input(
                    "展示名",
                    value=entry.label,
                    key=f"zg_cat_label_{entry.key}",
                    help=f"留空或与默认一致则回到默认名「{config.CATEGORY_LABELS[entry.key]}」",
                )
                order = st.number_input(
                    "排序", value=int(entry.sort_order), step=1, key=f"zg_cat_order_{entry.key}"
                )
                active = st.checkbox("启用", value=entry.is_active, key=f"zg_cat_enabled_{entry.key}")
                # 标签带上前缀而不是统一叫「保存」：一页里三个分块的保存按钮
                # 都叫「保存」时，界面测试按标签取只能拿到第一个。
                saved = st.form_submit_button("保存分类")

            if saved:
                display = "" if label.strip() == config.CATEGORY_LABELS[entry.key] else label.strip()
                _apply(
                    lambda: catalog_meta.set_category_meta(
                        viewer,
                        entry.key,
                        display_label=display,
                        sort_order=int(order),
                        is_active=active,
                    ),
                    f"已保存分类「{entry.label}」的元数据。",
                )


# --------------------------------------------------------------------------
# 品牌块
# --------------------------------------------------------------------------


def _render_brands(viewer, catalog) -> None:
    components.section_title("品牌")
    components.show_notice(
        "品牌字典**随商品库自动同步**：商品里出现的品牌一定会在这里。"
        "字典里登记一个商品库里没有的品牌，**不会**让需求解析认识它——"
        "解析仍以商品数据为准。停用品牌同样只是不再出现在搜索与推荐里，"
        "数据没有删。",
        "info",
    )

    try:
        entries = catalog_meta.brand_entries(catalog.products if catalog else None)
    except ZhigouError as exc:
        components.show_notice(to_user_message(exc), "stop")
        return

    if not entries:
        components.empty_state("商品库里还没有品牌。")
        return

    for entry in entries:
        state_label = "启用" if entry.is_active else "**已停用**"
        with st.expander(f"{entry.display_name} · {entry.product_count} 件 · {state_label}"):
            if entry.product_count == 0:
                components.caption("字典里有这个品牌，但商品库里没有它的商品——不会被解析器认识。")

            with st.form(f"zg_brand_meta_{entry.brand_name}"):
                display = st.text_input(
                    "展示名", value=entry.display_name, key=f"zg_brand_name_{entry.brand_name}"
                )
                order = st.number_input(
                    "排序", value=int(entry.sort_order), step=1, key=f"zg_brand_order_{entry.brand_name}"
                )
                active = st.checkbox("启用", value=entry.is_active, key=f"zg_brand_enabled_{entry.brand_name}")
                saved = st.form_submit_button("保存品牌")

            if saved:
                _apply(
                    lambda: catalog_meta.set_brand_meta(
                        viewer,
                        entry.brand_name,
                        display_name=display.strip() or entry.brand_name,
                        sort_order=int(order),
                        is_active=active,
                    ),
                    f"已保存品牌「{entry.display_name}」的元数据。",
                )
