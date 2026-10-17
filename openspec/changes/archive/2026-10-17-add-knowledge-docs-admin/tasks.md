## 1. 后端

- [ ] 1.1 `Document` 增加 `source_path`，`load_documents` 填充
- [ ] 1.2 `src/knowledge/admin.py`：`create_document`（校验、front-matter、slug 去重）
- [ ] 1.3 `src/knowledge/admin.py`：`delete_document`（仅文件型、找不到报错）
- [ ] 1.4 单测：新增可被加载、同分类拒绝、slug 去重、删除生效、商品级拒绝

## 2. 界面

- [ ] 2.1 商品知识库：新增资料表单（标题/类型/分类/来源/正文）
- [ ] 2.2 商品知识库：删除资料（二次确认，仅文件型）
- [ ] 2.3 提示：新增/删除后关键词索引自动更新；语义检索需重新生成向量
- [ ] 2.4 界面测试：管理员新增与删除、普通用户不可见

## 3. 收尾

- [ ] 3.1 `pytest` 全绿；`openspec validate` 通过
- [ ] 3.2 浏览器实测
