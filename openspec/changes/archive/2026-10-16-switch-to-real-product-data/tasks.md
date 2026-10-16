## 1. 数据模型：图片字段

- [x] 1.1 `products` 表加 `image_url` 列（可空），并入 `_SCHEMA_PRODUCTS`
- [x] 1.2 `_migrate` 给老库补这一列（`ALTER TABLE ... ADD COLUMN`）
- [x] 1.3 `Product` 增加 `image_url` 字段（默认空串）+ `has_image` 派生属性
- [x] 1.4 `product_store` 的读写覆盖 `image_url`
- [x] 1.5 `ingest` 字段别名加 `image_url`（含「图片」「图片地址」等中文别名）
- [x] 1.6 `scripts/fetch_products.py` 的 CSV 模板加图片列

## 2. 品类收缩到电子产品

- [x] 2.1 `config.CATEGORY_LABELS` 收缩到 laptop / phone
      （键盘与耳机随后也一并退出，最终只剩两类）
- [x] 2.2 `config.SCORING_WEIGHTS` 同步收缩
- [x] 2.3 移除 `data/knowledge/category/` 下 7 份非电子品类指南
- [x] 2.4 `_CATEGORY_KEYWORDS` 收缩；退出的品类词挪进 `_UNSUPPORTED_CATEGORY_TERMS`，
      并按**长度从长到短**匹配（否则「婴儿车」会被「婴儿」截胡）
- [x] 2.5 检查硬编码的品类假设：`_HEADLINE_SPECS`、`SPEC_LABELS`、`_SPEC_RANGES`、
      `_PERFORMANCE_SPECS`、`_PARAM_ORDER`、`_PARAM_BOOL`、`_PARAM_TIER`、
      `DEFAULT_CATEGORY_MAP`、`_HARD_CONSTRAINT_CHECKS`、`_CONSTRAINT_TERMS`、
      `TIER_EXTRA_KEYS`、`_CATEGORY_NAMES`
- [x] 2.6 顺带清掉随品类消失的死代码：`_score_durability`、「耐用性」维度、
      `_keyboard_feature_score` 及其分支
- [x] 2.7 补交叉引用测试：`test_config.py` 新增一组「凡引用类别或参数处，目标必须真实存在」
      的不变式测试，钉住这类漂移

## 3. 数据集替换

- [x] 3.1 联网检索两类商品数据（品牌、型号、参考价、参数、来源链接、图片链接）
- [x] 3.2 每条标注 `data_source` 为「公开资料整理 · 参数经简化，价格非实时」
- [x] 3.3 每条 `data_status` 一律 `unverified`
- [x] 3.4 规格键名与 `config.SPEC_LABELS` 对齐
- [x] 3.5 `use_cases` 取值落在既有词表内
- [x] 3.6 用 `--mode replace` 导入商品库，核对条数与字段
- [x] 3.7 `data/products.json` 同步为同一份数据集（种子）
- [x] 3.8 112 条旧演示商品已随 replace 清除，库中只剩 20 条
- [x] 3.9 逐条核验：检索结果全部经对抗式核验，被推翻的剔除或按核验给的价修正
- [x] 3.10 新增 `scripts/check_links.py` 用于实测外链可用性；
      来源页已失效的商品**留空来源**而不是留一条打不开的链接

## 4. 界面：商品图片

- [x] 4.1 缩略图改为：有图显示图片，否则类别图标
- [x] 4.2 图标垫底 + 图片 `onerror` 自隐，回落不出现破图
- [x] 4.3 商品卡片、比较表、历史页收藏卡片统一走同一个 `_thumb()`
- [x] 4.4 单测 `tests/test_ui_components.py`（7 条）
- [x] 4.5 浏览器实测——已人工看过真实渲染效果

## 5. 数据表述全局清理

- [x] 5.1 全局检索「演示数据」「自行构造」，逐处处理
- [x] 5.2 `README.md` 的数据说明改成「真实品牌 + 整理参数」
- [x] 5.3 `docs/data-disclaimer.md` 重写
- [x] 5.4 首页与「项目说明」页的数据边界说明同步
- [x] 5.5 导出报告与评测报告里的固定文案同步
- [x] 5.6 `openspec/specs/` 相关需求相应调整
- [x] 5.7 验收：全局再检索一次，不存在两种互相矛盾的说法

## 6. 评测集重写

- [x] 6.1 39 条 → 41 条，引用旧商品 ID 的预期全部按新数据集重算
- [x] 6.2 已移除品类的 6 条改成新的「不支持的类别」场景，评测器补上对应分支
- [x] 6.3 重跑评测，41 条全部通过
- [x] 6.4 评测集升到 2.0 版，`note` 里注明不做跨版本比较

## 7. 测试与文档同步

- [x] 7.1 「来源说明含演示二字」的断言改为「有来源说明且未核验」
- [x] 7.2 数据规模与品类覆盖的断言改为从 `config` 推导
- [x] 7.3 依赖旧商品 ID 的夹具改为**从数据集现取**（`tests/test_comparison.py`、
      `test_recommender.py`、`test_ai_service.py`、`test_report_service.py`）
- [x] 7.4 知识库测试：品类指南覆盖断言按 2 类调整
- [x] 7.5 README / docs 里的商品数、品类数、测试数同步
- [x] 7.6 `docs/demo_script.md` 的示例商品换成新数据集里的真实型号

## 8. 验收

- [x] 8.1 商品库中只有两类电子产品，无旧演示数据残留（112 → 20）
- [x] 8.2 商品卡片能正常展示图片（单测覆盖渲染）
- [x] 8.3 图片链接失效时回落成类别图标，界面不破
- [x] 8.4 需求解析、筛选、评分、比较、报告在新数据集上全部可用
- [x] 8.5 全局检索确认「演示数据」的表述不存在矛盾
- [x] 8.6 评测报告重新生成，指标为实测值（41/41）
- [x] 8.7 断网、不配密钥跑一遍，本地演示模式功能完整（`test_app` / `test_acceptance` 覆盖）
- [x] 8.8 `pytest` 全绿，实测 **784** 条

## 9. 顺带修掉的缺陷

- [x] 9.1 `scripts/migrate_products.py` 原来会**无条件清空 `source_url`**——那是给
      「全部自造」那批写的。换成有真实来源的数据后再跑一次会把全部来源链接抹掉，
      且一路不报错。已改成「只补缺、不覆盖」，并加 `--mode replace`
- [x] 9.2 `_thumb` 只判空不判空白，`image_url="   "` 会渲染出一个指向当前页面的 `<img>`
- [x] 9.3 抗幻觉的数值容差只按 2% 相对值算，真实参数位数是杂的（1.36 千克写「约 1.4 千克」）
      会被判成编造而丢掉整条解读。已给**带小数点的断言**补上取整半径；
      **整数断言刻意不给**，否则「1TB」会变成 [0.5, 1.5] TB，足以吞掉 512GB
