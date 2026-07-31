# Items 列表 · 搜索 / 排序 / 分页 功能说明

| 项目 | 内容 |
| --- | --- |
| 文档版本 | v1.0 |
| 更新日期 | 2026-07-31 |
| 适用模块 | 后端 `GET /api/v1/items/`、前端 `/items` 页面 |
| 关联方案 | [items-search-pagination-plan.md](../../items-search-pagination-plan.md) |

---

## 1. 功能定位

为 Items 列表提供**服务端搜索、排序与分页**能力，替代旧版「一次性拉取 + 客户端切片分页」的实现，同时保证翻页 / 搜索过程中的交互流畅性（无整页闪烁、输入框不失焦）。

### 1.1 用户价值

| 角色 | 价值 |
| --- | --- |
| 普通用户 | 在自己的数据中快速按标题检索；按创建时间正/反序浏览；翻页流畅 |
| 超级管理员 | 在全量数据中检索；可控分页大小；不会因为数据量增长导致首屏变慢 |
| 二次开发者 | 标准化的 query 参数契约，便于扩展更多过滤/排序字段 |

---

## 2. 功能清单

### F1 · 标题模糊搜索

- **范围**：标题字段（`Item.title`），不区分大小写（PostgreSQL `ILIKE`）。
- **触发**：搜索框输入后 **300ms 防抖**触发请求（避免每次按键都打后端）。
- **作用域**：
  - 普通用户：仅在自己创建的 Item 中匹配。
  - 超级管理员：在全量 Item 中匹配。
- **示例**：搜索 `probe` 可命中 `AlphaProbe`、`BetaProbe`、`PROBE-XYZ`。

### F2 · 创建时间排序

- **字段**：`created_at`。
- **方向**：`desc`（默认：最新优先）/ `asc`（最旧优先）。
- **入口**：列表右上角切换按钮，文案与图标同步变化（`Newest ↓` / `Oldest ↑`）。

### F3 · 服务端分页

- **每页条数**：默认 `10`，可选 `[10, 20, 50, 100]`。
- **导航**：首末页 + 上一页 / 下一页 共 4 个按钮，越界自动 disabled。
- **信息展示**：
  - 左侧：`Rows per page` 选择器 + `Total N items` 总数。
  - 右侧：`Page X of Y` 当前/总页数。
- **始终展示**：即便只有 1 页，工具栏仍显示（让用户感知总数）。

### F4 · 联动重置

- 改变 **搜索词 / 排序方向 / 每页条数** 时，自动回到第 1 页。
- 翻页（page）变化不重置其他状态。

### F5 · 空状态区分

| 场景 | 文案 |
| --- | --- |
| 无数据 + 未搜索 | `You don't have any items yet` / `Add a new item to get started.` |
| 无数据 + 有搜索词 | `No items match "{keyword}"` / `Try a different keyword.` |
| 首次加载中 | Skeleton 骨架屏占位（避免空表格闪烁） |
| 加载错误 | 红色错误提示 + 错误信息 |

### F6 · 加载视觉反馈

- 数据切换中：表格主体 `opacity-60 + pointer-events-none`，半透明遮罩 + 过渡动画。
- **不卸载表格、不清空输入框**，输入框始终保有焦点。

---

## 3. API 契约

### 3.1 端点

`GET /api/v1/items/`

### 3.2 Query 参数

| 参数 | 类型 | 必填 | 默认 | 校验 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `title` | string | 否 | `null` | `max_length=255` | 标题模糊匹配（ILIKE `%title%`） |
| `order` | enum | 否 | `desc` | `Literal["asc", "desc"]`，非法值 422 | `created_at` 排序方向 |
| `skip` | int | 否 | `0` | `>= 0` | 跳过条数（用于分页偏移） |
| `limit` | int | 否 | `10` | `1 <= x <= 100`，越界 422 | 每页条数上限 |

### 3.3 响应体（未变更）

```json
{
  "data": [
    { "id": "uuid", "title": "...", "description": "...", "owner_id": "uuid", "created_at": "..." }
  ],
  "count": 123
}
```

### 3.4 鉴权与权限

- 需要 Bearer Token（JWT）。
- **权限模型保持不变**：
  - 普通用户：仅可见自己创建的 Item（`owner_id = current_user.id`）。
  - 超级管理员：可见全量 Item。
- 搜索条件 **叠加** 在权限过滤之上，不会突破权限边界。

---

## 4. 交互与 UI

### 4.1 页面布局

```
┌──────────────────────────────────────────────────────────┐
│ Items                              [ + Add Item ]        │
│ Create and manage your items                             │
├──────────────────────────────────────────────────────────┤
│ 🔍 [Search by title...]           [ ↓ Newest ]           │
├──────────────────────────────────────────────────────────┤
│ ID    Title        Description     Created At     Actions│
│ ──────────────────────────────────────────────────────── │
│ ...                                                      │
├──────────────────────────────────────────────────────────┤
│ Total 123 items  Rows per page [10▾]   Page 1 of 13     │
│                                          ⏮ ◀ ▶ ⏭        │
└──────────────────────────────────────────────────────────┘
```

### 4.2 列定义

| 列 | 说明 |
| --- | --- |
| ID | UUID 简写，hover 显示复制按钮 |
| Title | 加粗显示 |
| Description | 截断显示，空值显示斜体 `No description` |
| Created At | `Intl.DateTimeFormat` 本地化格式（新增列） |
| Actions | 行级菜单（编辑 / 删除） |

### 4.3 键盘与可访问性

- 搜索框带 `aria-label="Search items by title"`。
- 排序按钮带 `aria-label` 描述当前方向。
- 分页按钮带 `sr-only` 文案，屏幕阅读器可识别。

---

## 5. 状态管理

### 5.1 前端组件状态（不入 URL）

| 状态 | 类型 | 初值 | 联动 |
| --- | --- | --- | --- |
| `q` | string | `""` | 控制输入框显示，不直接触发请求 |
| `debouncedQ` | string | `""` | 由 `useDebounce(q, 300)` 派生；变化触发请求 |
| `page` | number | `1` | 1-based |
| `pageSize` | number | `10` | 变化时重置 `page=1` |
| `order` | `"asc" \| "desc"` | `"desc"` | 变化时重置 `page=1` |

### 5.2 数据获取

- 使用 `@tanstack/react-query` 的 `useQuery` + `placeholderData: keepPreviousData`。
- queryKey：`["items", { debouncedQ, page, pageSize, order }]`，前缀匹配保证 `AddItem`/`EditItem`/`DeleteItem` mutation 的 `invalidateQueries` 仍然命中。

---

## 6. 边界与限制

| 限制 | 值 / 行为 | 原因 |
| --- | --- | --- |
| `limit` 上限 | 100 | 防止恶意放大查询消耗后端资源 |
| `title` 最大长度 | 255 | 与 `Item.title` 列长度对齐 |
| 搜索范围 | 当前用户权限可见的全量数据 | 权限边界不可突破 |
| 排序字段 | 仅 `created_at` | YAGNI；后续可平滑扩展 |
| URL 同步 | 不入 URL | 交互最简洁；浏览器地址栏不闪烁 |

---

## 7. 测试覆盖

后端测试（`backend/tests/api/routes/test_items.py`）：

| 测试用例 | 覆盖点 |
| --- | --- |
| `test_read_items_title_filter` | 大小写不敏感的标题模糊匹配 |
| `test_read_items_pagination` | skip/limit 切片正确性 + count 反映全量 |
| `test_read_items_default_limit` | 默认 limit=10 |
| `test_read_items_sort_order_asc_desc` | asc/desc 返回顺序相反 |
| `test_read_items_invalid_order` | 非法 order → 422 |
| `test_read_items_invalid_limit` | limit=0 / limit=999 → 422 |
| `test_read_items_title_filter_normal_user` | 普通用户搜索被 owner_id 严格过滤 |

---

## 8. 文件清单

### 后端

| 文件 | 变更 |
| --- | --- |
| [backend/app/api/routes/items.py](../../backend/app/api/routes/items.py) | `read_items` 新增 `title`/`order` 参数；抽取 `_apply_item_filters` |
| [backend/tests/api/routes/test_items.py](../../backend/tests/api/routes/test_items.py) | 新增 7 个搜索/排序/分页测试 |
| [backend/tests/utils/item.py](../../backend/tests/utils/item.py) | 新增 `create_item_with_title` 辅助函数 |

### 前端

| 文件 | 变更 |
| --- | --- |
| [frontend/src/hooks/useDebounce.ts](../../frontend/src/hooks/useDebounce.ts) | 新建通用防抖 hook |
| [frontend/src/components/Items/ItemsTable.tsx](../../frontend/src/components/Items/ItemsTable.tsx) | 新建专属表格组件 |
| [frontend/src/components/Items/columns.tsx](../../frontend/src/components/Items/columns.tsx) | 新增 `created_at` 列 |
| [frontend/src/routes/_layout/items.tsx](../../frontend/src/routes/_layout/items.tsx) | 替换内部表格为新 `ItemsTable` |
| [frontend/src/client/](../../frontend/src/client/) | 由 `generate-client` 自动重新生成 |

### 不变项

- 数据库 schema / Alembic 迁移：无变更。
- 鉴权与权限模型：无变更。
- 通用 `DataTable` 组件：未触碰（YAGNI，避免污染通用组件）。
- `AddItem` / `EditItem` / `DeleteItem` 组件：天然兼容，无需改动。

---

## 9. 设计原则映射

| 原则 | 体现 |
| --- | --- |
| **KISS** | 状态不进 URL；翻页/搜索/排序三件套用最小状态机表达 |
| **YAGNI** | 排序仅支持 `created_at`，不预留未来字段；不替换通用 `DataTable` |
| **DRY** | `_apply_item_filters` 统一过滤逻辑，count 与 list 共用基语句 |
| **SRP** | `ItemsTable` 单一职责；`useDebounce` 可复用 |
| **OCP** | queryKey 使用对象结构，扩展字段不破坏位置参数 |

---

## 10. 后续可扩展点（非本期范围）

- 排序字段扩展到 `title` / `description` / 自定义字段。
- URL query 同步（用于分享 / 书签 / 浏览器前进后退）。
- 大数据量下对 `title` 增加 `pg_trgm` 索引以加速 ILIKE。
- 列级排序指示器（点击表头切换）。
