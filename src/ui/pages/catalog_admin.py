"""商品维护页：概览 / 商品 / 分类 / 品牌。

三块合在一页是有意的：它们维护的是同一件事的三层——商品的字段、
商品所属分类的元数据、品牌的元数据。分成多个页面，管理员改一件商品
时要来回跳。

**参数用「一行一个 `键: 值`」的文本域编辑**，不引第三方表格组件：
项目依赖以必要为限，而 `st.data_editor` 的可编辑表格在 AppTest 下不好断言。
文本域还能顺手把「键不认识」「取值越界」的错误位置说清楚——
校验与错误文案都在 `src/catalog_admin.py`，这里只负责渲染。
"""

from __future__ import annotations

import streamlit as st

from src import catalog_admin, catalog_meta, comparison, config
from src.auth import require_admin
from src.errors import ZhigouError, to_user_message
from src.ui import components, state
from src.ui.theme import chip

_FLASH_KEY = "zg_catalog_flash"

_NEW_PREFIX = "zg_cat_new_"
_BRAND_KEY = "zg_cat_f_brand"
_CATEGORY_KEY = "zg_cat_f_category"
_STATUS_KEY = "zg_cat_f_status"
_QUERY_KEY = "zg_cat_f_query"

_ALL = "全部"


def _viewer():
    return state.current_user()


def _flash(message: str, tone: str) -> None:
    st.session_state[_FLASH_KEY] = (message, tone)


def _render_flash() -> None:
    pending = st.session_state.pop(_FLASH_KEY, None)
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
        "界面录入的商品一律标为未核验——是谁填的不等于核实过。",
    )
    _render_flash()

    try:
        records = catalog_admin.list_products()
    except ZhigouError as exc:
        components.show_notice(to_user_message(exc), "stop")
        return

    tab_category, tab_brand, tab_product, tab_detail = st.tabs(
        ["分类", "品牌", "商品管理", "详情与参数"]
    )
    with tab_category:
        _render_categories(viewer)
    with tab_brand:
        _render_brands(viewer, catalog)
    with tab_product:
        _render_products(viewer, records)
    with tab_detail:
        _render_product_details(viewer)


# --------------------------------------------------------------------------
# 商品块
# --------------------------------------------------------------------------


def _render_overview(records: list[dict]) -> None:
    total = len(records)
    active = sum(1 for r in records if r.get("is_active", True))
    inactive = total - active
    unverified = sum(
        1
        for r in records
        if r.get("data_status") != config.STATUS_VERIFIED
    )
    components.stat_row(
        [
            ("tag", str(total), "件商品"),
            ("check", str(active), "启用"),
            ("pause", str(inactive), "停用"),
            ("info", str(unverified), "未核验"),
        ]
    )


def _render_filters(records: list[dict]) -> dict:
    """筛选栏。返回当前筛选条件。"""
    categories = sorted({str(r.get("category")) for r in records})
    category_label = st.selectbox(
        "分类",
        options=[_ALL, *categories],
        format_func=lambda value: _ALL if value == _ALL else config.category_label(value),
        key=_CATEGORY_KEY,
    )

    scoped = (
        [r for r in records if str(r.get("category")) == category_label]
        if category_label != _ALL
        else records
    )
    brands = sorted({str(r.get("brand")) for r in scoped if r.get("brand")})
    # 分类切换后，先前选中的品牌可能不在选项里——清掉它，别让控件报错
    if st.session_state.get(_BRAND_KEY) not in ([_ALL, *brands]):
        st.session_state.pop(_BRAND_KEY, None)

    col_brand, col_status, col_query = st.columns([1.2, 1, 1.8])
    with col_brand:
        brand = st.selectbox("品牌", options=[_ALL, *brands], key=_BRAND_KEY)
    with col_status:
        status = st.selectbox("状态", options=[_ALL, "启用", "停用"], key=_STATUS_KEY)
    with col_query:
        query = st.text_input("搜索", key=_QUERY_KEY, placeholder="名称 / 型号 / ID")

    return {
        "category": category_label,
        "brand": brand,
        "status": status,
        "query": query.strip().lower(),
    }


def _apply_filters(records: list[dict], filters: dict) -> list[dict]:
    result = records
    if filters["category"] != _ALL:
        result = [r for r in result if str(r.get("category")) == filters["category"]]
    if filters["brand"] != _ALL:
        result = [r for r in result if str(r.get("brand")) == filters["brand"]]
    if filters["status"] == "启用":
        result = [r for r in result if r.get("is_active", True)]
    elif filters["status"] == "停用":
        result = [r for r in result if not r.get("is_active", True)]
    if filters["query"]:
        needle = filters["query"]
        result = [
            r
            for r in result
            if needle in str(r.get("name", "")).lower()
            or needle in str(r.get("model", "")).lower()
            or needle in str(r.get("id", "")).lower()
        ]
    return result


def _render_products(viewer, records: list[dict]) -> None:
    _render_overview(records)

    filters = _render_filters(records)
    filtered = _apply_filters(records, filters)

    with st.expander("＋ 新增商品", expanded=False):
        _render_new_product_form(viewer)

    st.write("")
    components.section_title("商品列表", len(filtered))
    components.caption(
        "停用的商品不再出现在搜索与推荐中，但历史记录里已有的引用仍可读——"
        "停用不等于删除。界面新增或修改的商品一律保持「未核验」。"
    )

    if not filtered:
        components.empty_state("没有符合条件的商品。换个筛选条件试试。")
        return

    for record in filtered:
        _render_product_row(viewer, record)


def _render_new_product_form(viewer) -> None:
    components.caption(
        "新商品的来源会自动记为「管理员界面录入 · 未核验」；"
        "参数名必须是该分类既有的参数，取值要在既有区间内。"
    )

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
        "specs": catalog_admin.text_to_specs(specs),
        "use_cases": catalog_admin.lines_to_list(use_cases),
        "pros": catalog_admin.lines_to_list(pros),
        "cons": catalog_admin.lines_to_list(cons),
    }
    _apply(
        lambda: catalog_admin.create_product(viewer, record),
        f"已新增商品「{record['name'] or record['id']}」，标为未核验。",
    )


def _render_product_row(viewer, record) -> None:
    product_id = str(record.get("id"))
    active = bool(record.get("is_active", True))
    verified = record.get("data_status") == config.STATUS_VERIFIED
    price = record.get("price")

    chips = " ".join(
        [
            chip("启用", "ok") if active else chip("停用", "neutral"),
            chip("已核验", "ok") if verified else chip("未核验", "warn"),
        ]
    )
    price_text = "未知" if price is None else f"¥{price}"

    with st.expander(
        f"{record.get('name') or product_id} · {config.category_label(str(record.get('category')))}"
        f" · {price_text} · {active and '启用' or '停用'}"
    ):
        st.markdown(chips, unsafe_allow_html=True)
        entered = record.get("entered_by") or "非界面录入"
        st.markdown(
            components.facts(
                [
                    ("商品 ID", product_id),
                    ("品牌 / 型号", f"{record.get('brand') or '未填'} · {record.get('model') or '未填'}"),
                    ("参考价", price_text),
                    ("录入者", entered),
                    ("来源说明", record.get("data_source") or "（无）"),
                ]
            ),
            unsafe_allow_html=True,
        )

        _render_edit_form(viewer, record)

        st.write("")
        label = "停用" if active else "启用"
        if st.button(label, key=f"zg_cat_active_{product_id}"):
            _apply(
                lambda: catalog_admin.set_active(viewer, product_id, not active),
                f"已{label}「{record.get('name') or product_id}」。",
            )


def _render_edit_form(viewer, record) -> None:
    product_id = str(record.get("id"))
    category = str(record.get("category"))

    with st.form(f"zg_cat_edit_{product_id}"):
        col_a, col_b = st.columns(2)
        with col_a:
            name = st.text_input("名称", value=record.get("name") or "", key=f"zg_cat_name_{product_id}")
            brand = st.text_input("品牌", value=record.get("brand") or "", key=f"zg_cat_brand_{product_id}")
            price = st.number_input(
                "参考价（元）",
                value=float(record.get("price") or 0.0),
                step=100.0,
                key=f"zg_cat_price_{product_id}",
            )
        with col_b:
            model = st.text_input("型号", value=record.get("model") or "", key=f"zg_cat_model_{product_id}")
            image_url = st.text_input(
                "图片地址", value=record.get("image_url") or "", key=f"zg_cat_image_{product_id}"
            )
            source_url = st.text_input(
                "来源链接", value=record.get("source_url") or "", key=f"zg_cat_source_{product_id}"
            )

        components.caption(
            "参数、适用场景、亮点与不足在「详情与参数」中维护——"
            "它们同时是检索依据，集中在一处编辑可以避免两处失同步。"
        )

        saved = st.form_submit_button("保存修改")

    if not saved:
        return

    changes = {
        "name": name.strip(),
        "brand": brand.strip(),
        "model": model.strip(),
        "price": float(price) if price else None,
        "image_url": image_url,
        "source_url": source_url,
    }
    _apply(
        lambda: catalog_admin.update_product(viewer, product_id, changes),
        f"已保存「{record.get('name') or product_id}」的修改。",
    )


# --------------------------------------------------------------------------
# 分类块
# --------------------------------------------------------------------------


def _render_categories(viewer) -> None:
    components.show_notice(
        "分类可以在下方新增；新增时先使用默认评分权重（预算 25% / 需求 35% / "
        "性能 20% / 性价比 20%），参数档位与知识指南可以后续补充。"
        "**停用不等于删除**——停用后该分类的商品不再出现在搜索与推荐中，数据仍在，"
        "随时可以恢复。",
        "info",
    )

    try:
        entries = catalog_meta.category_entries()
    except ZhigouError as exc:
        components.show_notice(to_user_message(exc), "stop")
        return

    _render_new_category_form(viewer)

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

    _render_new_brand_form(viewer)

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

# --------------------------------------------------------------------------
# 详情与参数
# --------------------------------------------------------------------------

_DETAIL_PREFIX = "zg_cat_detail_"


def _render_product_details(viewer) -> None:
    """按商品维护参数、适用场景、亮点与不足（原知识库页的编辑器）。"""
    try:
        records = catalog_admin.list_products()
    except ZhigouError as exc:
        components.show_notice(to_user_message(exc), "stop")
        return

    if not records:
        components.empty_state("商品库里还没有商品。")
        return

    components.caption(
        "维护商品的参数与展示内容。这些字段既用于商品卡片与比较表，"
        "也会被合成进知识库参与检索——保存后到「知识库管理」重新生成向量即可生效。"
    )

    query = st.text_input(
        "搜索商品", key=f"{_DETAIL_PREFIX}q", placeholder="名称 / 型号 / ID"
    ).strip().lower()
    scoped = [
        record
        for record in records
        if not query
        or query in str(record.get("name", "")).lower()
        or query in str(record.get("model", "")).lower()
        or query in str(record.get("id", "")).lower()
    ]
    if not scoped:
        components.empty_state("没有匹配的商品。")
        return

    options = {
        f"{record.get('name') or record.get('id')} · {record.get('id')}"
        f"（{config.category_label(str(record.get('category')))}）": record
        for record in scoped
    }
    pick = st.selectbox("选择商品", options=list(options), key=f"{_DETAIL_PREFIX}pick")
    record = options[pick]
    product_id = str(record.get("id"))
    category = str(record.get("category"))
    known = comparison.param_keys(category)

    st.markdown(
        components.facts(
            [
                ("商品 ID", product_id),
                ("品牌 / 型号", f"{record.get('brand') or '未填'} · {record.get('model') or '未填'}"),
                ("分类", config.category_label(category)),
                (
                    "参考价",
                    "未知" if record.get("price") is None else f"¥{record.get('price')}",
                ),
                ("核验状态", "已核验" if record.get("data_status") == config.STATUS_VERIFIED else "未核验"),
            ]
        ),
        unsafe_allow_html=True,
    )
    st.write("")

    with st.form(f"zg_cat_detail_{product_id}"):
        specs = st.text_area(
            "参数",
            value=catalog_admin.specs_to_text(record.get("specs") or {}),
            key=f"{_DETAIL_PREFIX}specs_{product_id}",
            height=150,
            help=f"一行一个「参数名: 取值」。该分类既有的参数："
            f"{'、'.join(known) or '（未登记）'}",
        )
        use_cases = st.text_area(
            "适用场景",
            value="\n".join(record.get("use_cases") or []),
            key=f"{_DETAIL_PREFIX}use_{product_id}",
            height=90,
            help="一行一个",
        )
        pros = st.text_area(
            "亮点",
            value="\n".join(record.get("pros") or []),
            key=f"{_DETAIL_PREFIX}pros_{product_id}",
            height=90,
            help="一行一个",
        )
        cons = st.text_area(
            "不足",
            value="\n".join(record.get("cons") or []),
            key=f"{_DETAIL_PREFIX}cons_{product_id}",
            height=90,
            help="一行一个",
        )
        saved = st.form_submit_button("保存详情", type="primary")

    if not saved:
        return

    changes = {
        "specs": catalog_admin.text_to_specs(specs),
        "use_cases": catalog_admin.lines_to_list(use_cases),
        "pros": catalog_admin.lines_to_list(pros),
        "cons": catalog_admin.lines_to_list(cons),
    }
    try:
        catalog_admin.update_product(viewer, product_id, changes)
    except ZhigouError as exc:
        _flash(f"保存失败：{to_user_message(exc)}", "stop")
    else:
        hint = _sync_knowledge_vectors()
        _flash(
            f"已保存「{record.get('name') or product_id}」的详情与参数。{hint}",
            "ok",
        )
    st.rerun()

# --------------------------------------------------------------------------
# 新增分类 / 品牌
# --------------------------------------------------------------------------


def _render_new_category_form(viewer) -> None:
    with st.expander("＋ 新增分类", expanded=False):
        components.caption(
            "新增分类后即可在「商品管理」里录入该分类的商品。"
            "评分先使用默认权重（预算 25% / 需求 35% / 性能 20% / 性价比 20%），"
            "知识指南可以稍后在知识库管理里补。"
        )
        with st.form("zg_cat_new_category"):
            key = st.text_input(
                "分类键", key="zg_cat_newcat_key", help="小写字母开头，如 tablet"
            )
            label = st.text_input("展示名", key="zg_cat_newcat_label")
            order = st.number_input("排序", key="zg_cat_newcat_order", value=100, step=1)
            active = st.checkbox("启用", value=True, key="zg_cat_newcat_active")
            submitted = st.form_submit_button("新增分类", type="primary")

        if not submitted:
            return
        try:
            catalog_meta.set_category_meta(
                viewer,
                key.strip(),
                display_label=label.strip(),
                sort_order=int(order),
                is_active=active,
            )
        except ZhigouError as exc:
            _flash(f"新增分类失败：{to_user_message(exc)}", "stop")
        else:
            # 立即并入内存表：新增分类后不必重启就能在商品表单里选到
            config.CATEGORY_LABELS.setdefault(key.strip(), label.strip() or key.strip())
            _flash(f"已新增分类「{label.strip() or key.strip()}」。", "ok")
        st.rerun()


def _render_new_brand_form(viewer) -> None:
    with st.expander("＋ 新增品牌", expanded=False):
        components.caption(
            "品牌字典随商品自动同步；这里可以先把品牌登记进字典（没有商品时也能登记），"
            "录入商品时即可选用。"
        )
        with st.form("zg_cat_new_brand"):
            name = st.text_input("品牌名", key="zg_cat_newbrand_name")
            display = st.text_input("展示名", key="zg_cat_newbrand_display")
            order = st.number_input("排序", key="zg_cat_newbrand_order", value=100, step=1)
            active = st.checkbox("启用", value=True, key="zg_cat_newbrand_active")
            submitted = st.form_submit_button("新增品牌", type="primary")

        if not submitted:
            return
        try:
            catalog_meta.set_brand_meta(
                viewer,
                name.strip(),
                display_name=display.strip() or name.strip(),
                sort_order=int(order),
                is_active=active,
            )
        except ZhigouError as exc:
            _flash(f"新增品牌失败：{to_user_message(exc)}", "stop")
        else:
            _flash(f"已新增品牌「{display.strip() or name.strip()}」。", "ok")
        st.rerun()


def _sync_knowledge_vectors() -> str:
    """保存详情后把知识向量增量同步，确保检索也用上新内容。"""
    from src.knowledge import chunking, embeddings

    service = embeddings.get_service()
    if not service.configured:
        return "关键词检索已同步；向量服务未配置，语义检索不受影响。"
    try:
        slices = chunking.split_corpus(state.get_knowledge_index().documents)
        result = state.get_vector_store().build_index(slices, service=service)
    except Exception:  # noqa: BLE001 —— 同步失败不该阻断保存结果
        return "知识向量未同步，请到「知识库管理」重新生成。"
    if result.embedded:
        return f"知识向量已同步更新（{result.embedded} 个切片）。"
    return "知识内容无变化，无需更新向量。"

