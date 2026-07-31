# Items 列表搜索、排序与分页联动 —— 技术方案

| 项目 | 内容 |
| --- | --- |
| 文档日期 | 2026-07-30 |
| 状态 | 已对齐方案，待实施 |
| 影响范围 | 后端 `app/api/routes/items.py` + 测试；前端 `routes/_layout/items.tsx`、`components/Items/`、`hooks/`、自动生成的 SDK |
| 不影响 | 数据库结构 / 业务字段 / 用户权限模型 / 已有的 Items CRUD 语义 |

---

## 1. 背景与目标

当前 Items 列表页存在以下限制：

- 后端 `GET /api/v1/items/` 仅接受 `skip/limit`，**排序硬编码为 `created_at desc`**，**无标题搜索能力**。
- 前端 [items.tsx](frontend/src/routes/_layout/items.tsx) 一次性请求最多 100 条，复用通用 [DataTable.tsx](frontend/src/components/Common/DataTable.tsx) 在**客户端切片分页**。
- 前端使用 `useSuspenseQuery`，请求时整块切到 `Suspense` fallback，**翻页/搜索会出现整页闪烁、输入框失焦**。

本次目标是引入一套**服务端搜索 / 排序 / 分页**机制，并保证交互流畅：

1. 标题模糊搜索（不区分大小写，**输入防抖**）。
2. 全局范围检索：在当前用户权限可见的全量数据上执行（超管看全部，普通用户看自己创建的）。
3. 按 `created_at` 升降序切换。
4. 平滑过渡，无整页闪烁、输入框不失焦。
5. 改变搜索词 / 排序 / 每页条数时自动回到第 1 页。
6. 默认每页 10 条，支持 `[10, 20, 50, 100]` 梯度；底部分页工具栏极简：`Rows per page` + `Total N items` + `Page X of Y` + 首末页/上下页按钮。
7. 空状态明确区分"暂无数据"与"无搜索结果"。
8. 不修改现有权限与业务逻辑、不动数据库表结构。

---

## 2. 已对齐的关键决策

| 编号 | 决策点 | 选定方案 | 理由 |
| --- | --- | --- | --- |
| D1 | URL 同步策略 | **全部不入 URL，纯组件 state** | URL 最简洁；交互完全无跳转闪烁 |
| D2 | 表格组件归属 | **新建 `ItemsTable` 专用组件**，不动 `DataTable` | 遵循 SRP / YAGNI；避免污染通用组件 |
| D3 | 排序范围 | **仅 `created_at`**，后端用 `Literal["asc","desc"]` 校验 | 与需求字面一致；未来扩展可平滑加字段 |
| D4 | UI 文案语言 | **保持英文**，与现有 UI 文案一致 | 全局中文指令针对对话回复，不强制 UI 文案 |
| D5 | 防抖机制 | **采用 300ms 防抖**（独立 `useDebounce` hook） | 通用、可复用、与现有 hooks 目录风格一致 |

---

## 3. 非目标

- 不引入 URL query 参数同步（D1）。
- 不替换或重构通用 `DataTable`（D2）。
- 不扩展排序字段（如 `title`、`description`）（D3）。
- 不改动数据库 schema，不新增 Alembic 迁移。
- 不替换鉴权 / 权限模型。
- 不引入新的状态管理库或路由库。

---

## 4. 整体架构

```
┌────────────────────────── 前端 ──────────────────────────┐
│ routes/_layout/items.tsx                                  │
│   └─ <ItemsTable />  (新建, 接管全部交互态)               │
│                                                            │
│ components/Items/ItemsTable.tsx   ← 服务端分页/搜索/排序   │
│   ├─ 搜索框 (useDebounce 300ms)                           │
│   ├─ 排序切换按钮                                          │
│   ├─ Table (复用 ui/table)                                │
│   ├─ 空状态: "暂无数据" / "无搜索结果"                     │
│   └─ 分页工具栏 (pageSize / Total / Page X of Y / 4 按钮) │
│                                                            │
│ components/Items/columns.tsx      ← 新增 created_at 列     │
│ hooks/useDebounce.ts             ← 新建                   │
└────────────────────────────────────────────────────────────┘
                          │ HTTPS
                          ▼
┌────────────────────────── 后端 ──────────────────────────┐
│ GET /api/v1/items/?title=&order=asc|desc&skip=&limit=     │
│   ├─ 权限过滤 (保留: 超管全量 / 普通用户 owner_id)         │
│   ├─ title 模糊匹配 (ILIKE, 不区分大小写)                  │
│   ├─ order 按 created_at 升降序                            │
│   └─ 返回 { data: ItemPublic[], count }                    │
│                                                            │
│   query 参数: title?, order (asc|desc, 默认 desc),         │
│              skip (>=0), limit (1..100, 默认 10)           │
└────────────────────────────────────────────────────────────┘
```

---

## 5. 后端方案

### 5.1 API 契约

`GET /api/v1/items/`

| 参数 | 类型 | 默认 | 校验 | 说明 |
| --- | --- | --- | --- | --- |
| `title` | string \| null | null | 最大 255 字符 | 标题模糊匹配（ILIKE `%title%`，不区分大小写） |
| `order` | enum | `"desc"` | `Literal["asc", "desc"]` | `created_at` 升/降序 |
| `skip` | int | 0 | ≥ 0 | 跳过条数 |
| `limit` | int | 10 | 1 ≤ x ≤ 100 | 每页条数上限 |

响应保持不变：`ItemsPublic = { data: ItemPublic[], count: int }`。

### 5.2 实现要点（[items.py](backend/app/api/routes/items.py)）

- **抽取 `_apply_item_filters(statement, *, current_user, title)`** 统一拼接 `where` 条件，超管 / 普通用户 / 搜索共用，避免重复（DRY）。
- **count 与 data 复用同一过滤基语句**：`count_stmt = select(func.count()).select_from(base.subquery())`，避免 where 条件在两处维护漂移。
- **排序分支收敛到一行**：`col(Item.created_at).desc() if order == "desc" else col(Item.created_at).asc()`。
- **参数校验**：`limit: int = Query(default=10, ge=1, le=100)`；`order` 用 `Literal` 自动 422。
- 权限分支**完全保留**：仅是"普通用户额外加一个 `owner_id` 过滤"，搜索/排序在两种身份下行为一致。

### 5.3 实现草案（仅示意，实施时以最终代码为准）

```python
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from sqlmodel import col, func, select
from sqlalchemy.sql import Select

from app.api.deps import CurrentUser, SessionDep
from app.models import Item, ItemCreate, ItemPublic, ItemsPublic, ItemUpdate, Message

router = APIRouter(prefix="/items", tags=["items"])


def _apply_item_filters(
    statement: Select, *, current_user: CurrentUser, title: str | None
) -> Select:
    if title:
        statement = statement.where(col(Item.title).ilike(f"%{title}%"))
    if not current_user.is_superuser:
        statement = statement.where(Item.owner_id == current_user.id)
    return statement


@router.get("/", response_model=ItemsPublic)
def read_items(
    session: SessionDep,
    current_user: CurrentUser,
    title: str | None = None,
    order: Literal["asc", "desc"] = "desc",
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
) -> Any:
    base = _apply_item_filters(
        select(Item), current_user=current_user, title=title
    )

    count = session.exec(select(func.count()).select_from(base.subquery())).one()

    rows_statement = (
        base.order_by(col(Item.created_at).desc() if order == "desc"
                      else col(Item.created_at).asc())
        .offset(skip)
        .limit(limit)
    )
    items = session.exec(rows_statement).all()

    return ItemsPublic(
        data=[ItemPublic.model_validate(item) for item in items], count=count
    )


# 其余端点 (read_item/create_item/update_item/delete_item) 不变
```

### 5.4 测试用例（[test_items.py](backend/tests/api/routes/test_items.py)）

新增以下用例（沿用现有 `create_random_item` + `get_superuser_token_headers` fixture）：

| 用例 | 验证点 |
| --- | --- |
| `test_read_items_title_filter` | 构造 title 分别为 `"Alpha"` / `"Beta"` 的两条，搜索 `title=alp` 仅返回 Alpha |
| `test_read_items_pagination` | 至少 3 条数据下，`limit=1&skip=0` 与 `limit=1&skip=1` 返回不同 item 且 `count` 反映全量 |
| `test_read_items_default_limit` | 不传 limit 时返回 ≤10 条 |
| `test_read_items_sort_order_asc_desc` | 按已知 `created_at` 构造数据，验证 `order=asc` / `desc` 的返回顺序 |
| `test_read_items_invalid_order` | `order=invalid` → 422 |
| `test_read_items_invalid_limit` | `limit=0` 与 `limit=999` → 422 |
| `test_read_items_title_filter_normal_user` | 普通用户搜索，结果集严格被 `owner_id` 过滤（不会搜到他人数据） |

> 注意：`create_random_item` 当前用随机字符串生成 title，新测试需要可控 title，可在用例内直接走 `crud.create_item` 或在 `tests/utils/item.py` 增加 `create_item_with_title(db, title)` 辅助函数。

---

## 6. 前端方案

### 6.1 状态模型（`ItemsTable` 内部 state，**不入 URL**）

| 状态 | 类型 | 初值 | 触发的副作用 |
| --- | --- | --- | --- |
| `q` | string | `""` | 仅控制输入框显示；不直接触发请求 |
| `debouncedQ` | string | `""` | 由 `useDebounce(q, 300)` 派生；变化时触发请求 + 重置 page |
| `page` | number | `1` | 1-based，变化时触发请求 |
| `pageSize` | number | `10` | 变化时重置 page=1 |
| `order` | `"asc" \| "desc"` | `"desc"` | 变化时重置 page=1 |

### 6.2 数据获取

- 用 `useQuery` + `placeholderData: keepPreviousData` 取代 `useSuspenseQuery`：
  - 翻页 / 搜索时**保留上一次的数据**渲染，避免整块 Suspense fallback（解决闪烁与失焦）。
  - 通过 `isFetching` 在数据更新中加 `opacity-60 pointer-events-none` 半透明遮罩，给用户视觉反馈。
  - **首屏**（无 `data`）用 `<Skeleton>` 占位，避免空表格闪烁。
- queryKey 设计（前缀失效兼容现有 mutation）：

  ```ts
  queryKey: ["items", { debouncedQ, page, pageSize, order }]
  ```

  - `AddItem` / `EditItem` 现有的 `invalidateQueries({ queryKey: ["items"] })` 仍然命中（前缀匹配）。
  - `DeleteItem` 现有的 `invalidateQueries()`（全失效）仍生效。
  - **不需要改动 mutation 组件**。

- queryFn 草案：

  ```ts
  queryFn: () =>
    ItemsService.readItems({
      skip: (page - 1) * pageSize,
      limit: pageSize,
      title: debouncedQ.trim() || undefined,
      order,
    }),
  ```

### 6.3 联动重置页码

```ts
useEffect(() => {
  setPage(1)
}, [debouncedQ, pageSize, order])
```

- `q` 不进依赖，避免输入过程中跳页。
- `debouncedQ` 进依赖，仅在防抖落地后跳一次。

### 6.4 新增 hook：`useDebounce`

[frontend/src/hooks/useDebounce.ts](frontend/src/hooks/useDebounce.ts)

```ts
import { useEffect, useState } from "react"

export function useDebounce<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}
```

- 与现有 `hooks/useCopyToClipboard.ts`、`hooks/useMobile.ts` 风格一致。
- 通用、可在其他场景复用。

### 6.5 新组件：`ItemsTable`

[frontend/src/components/Items/ItemsTable.tsx](frontend/src/components/Items/ItemsTable.tsx)

- 顶部工具栏：左侧 `Input`（带 `Search` 图标）+ 右侧排序切换 `Button`（图标 + 文案 `Newest` / `Oldest`）。
- 表格主体：基于 [ui/table](frontend/src/components/ui/table.tsx) 手写渲染，沿用 [columns.tsx](frontend/src/components/Items/columns.tsx) 的列定义。
- 空状态：
  - 无搜索词且无数据：`You don't have any items yet` + `Add a new item to get started`（沿用现有文案）。
  - 有搜索词且无数据：`No items match "{debouncedQ}"` + 建议改用其他关键字。
- 分页工具栏（**始终显示**，即使只有 1 页）：
  - 左侧：`Rows per page` + `Select([10, 20, 50, 100])` + `Total {count} items`。
  - 右侧：`Page {page} of {totalPages}` + 四个按钮 `⏮ ◀ ▶ ⏭`，按钮在越界时 `disabled`。
  - `totalPages = max(1, ceil(count / pageSize))`。
- 加载中：`isFetching && !isFirstLoad` 时给表格主体加 `opacity-60 pointer-events-none transition-opacity`，**不卸载表格、不清空输入框**。

### 6.6 columns 调整（[columns.tsx](frontend/src/components/Items/columns.tsx)）

- 在 `Description` 列后新增 `created_at` 列，让排序方向可见。
- 用 `Intl.DateTimeFormat` 格式化（保留时区信息），无 `created_at` 时返回 `null`。

### 6.7 路由页面调整（[_layout/items.tsx](frontend/src/routes/_layout/items.tsx)）

- 删除旧的 `getItemsQueryOptions` 与 `ItemsTableContent`、`ItemsTable` 局部实现。
- 直接渲染 `<ItemsTable />`，并保留外层 `<AddItem />` 头部按钮。
- 不再需要 `Suspense` fallback `PendingItems`（首屏改由 `ItemsTable` 内部 Skeleton 处理）。

### 6.8 SDK 重新生成

后端 API 改完后，在仓库根执行：

```bash
bash ./scripts/generate-client.sh
# 等价于 cd frontend && bun run generate-client
```

生成后 `ItemsService.readItems` 会自动多出 `title`、`order` 参数；`ItemsReadItemsData` / `ItemsReadItemsResponse` 类型同步更新。**禁止手工编辑 `client/` 下的生成文件**。

---

## 7. 文件改动清单

### 后端
| 文件 | 操作 |
| --- | --- |
| [backend/app/api/routes/items.py](backend/app/api/routes/items.py) | 修改 `read_items`：新增 `title`、`order` 参数；抽取 `_apply_item_filters` |
| [backend/tests/api/routes/test_items.py](backend/tests/api/routes/test_items.py) | 新增 7 个测试用例 |
| [backend/tests/utils/item.py](backend/tests/utils/item.py) | 可选：增加 `create_item_with_title(db, title)` 辅助 |

### 前端
| 文件 | 操作 |
| --- | --- |
| [frontend/src/hooks/useDebounce.ts](frontend/src/hooks/useDebounce.ts) | 新建 |
| [frontend/src/components/Items/ItemsTable.tsx](frontend/src/components/Items/ItemsTable.tsx) | 新建（核心组件） |
| [frontend/src/components/Items/columns.tsx](frontend/src/components/Items/columns.tsx) | 新增 `created_at` 列 |
| [frontend/src/routes/_layout/items.tsx](frontend/src/routes/_layout/items.tsx) | 替换内部表格为新 `ItemsTable` |
| [frontend/src/client/](frontend/src/client/) | 由 `generate-client` 自动重新生成 |

### 不变
- [DataTable.tsx](frontend/src/components/Common/DataTable.tsx)：保持不动（D2）。
- [AddItem.tsx](frontend/src/components/Items/AddItem.tsx) / [EditItem.tsx](frontend/src/components/Items/EditItem.tsx) / [DeleteItem.tsx](frontend/src/components/Items/DeleteItem.tsx)：缓存失效策略天然兼容，无需改动。
- 数据库 / Alembic / 权限模型：不动。

---

## 8. 关键技术点说明

### 8.1 为什么改 `useSuspenseQuery` → `useQuery + keepPreviousData`

`useSuspenseQuery` 在每次请求前会让组件挂起，触发上层 `Suspense` fallback（整页 `PendingItems`）—— 这是**整页闪烁、输入框失焦**的根因。改为 `useQuery` 后：

- 组件不再挂起，输入框 / 按钮 / 选择器全程可交互。
- `keepPreviousData` 让翻页时旧数据继续显示，请求完成后无缝替换。
- 用 `isFetching` 在切换瞬间加半透明遮罩提供视觉反馈，避免"看上去卡住"的错觉。

### 8.2 为什么 queryKey 用对象而非扁平数组

```ts
["items", { debouncedQ, page, pageSize, order }]
```

- 对象键值明确、可读、扩展性好（未来加 `sortBy` 不破坏位置参数）。
- 前缀 `["items"]` 与现有 mutation 的 `invalidateQueries({ queryKey: ["items"] })` 完全兼容。

### 8.3 为什么 `limit` 上限设为 100

防止恶意 / 误用造成超大查询；同时满足需求中最大每页 100 条。后端用 `Query(le=100)` 强制，前端 select 也只暴露到 100。

### 8.4 为什么分页工具栏始终显示（即使只有 1 页）

需求要求展示 `Total N items` + `Rows per page`。即便只有 1 页，这些信息仍有价值（让用户知道系统里的总数）。现有 `DataTable` 仅在 `pageCount > 1` 显示分页栏 —— 新组件去掉这一条件。

### 8.5 空状态文案

| 场景 | 文案 |
| --- | --- |
| 首次加载中 | `<Skeleton>` 占位 |
| 无数据 + 未搜索 | `You don't have any items yet` + `Add a new item to get started` |
| 无数据 + 有搜索词 | `No items match "{debouncedQ}"` + `Try a different keyword` |
| 加载错误 | `Failed to load items` + 重试按钮（可选，初版可用 toast） |

---

## 9. 验证步骤

### 9.1 后端

```bash
cd backend
uv sync
bash ./scripts/test.sh
# 或单跑：
pytest tests/api/routes/test_items.py -v
```

### 9.2 前端

```bash
cd frontend
bun install
bun run generate-client   # 后端 API 变更后
bun run lint
bun run build
bunx playwright test      # 现有 E2E
```

### 9.3 手动验证（启动全栈）

```bash
# 终端 1
docker compose up -d db
cd backend && fastapi dev app/main.py
# 终端 2
cd frontend && bun run dev
```

打开 http://localhost:5173，登录后进入 `/items`，依次验证：

- [ ] 搜索框输入文字，**300ms 后**才触发请求（防抖生效）。
- [ ] 搜索过程中输入框**不失焦**、表格轻微半透明后平滑更新。
- [ ] 排序按钮切换，列表按 `created_at` 升降序刷新。
- [ ] 切换 `Rows per page` 后回到第 1 页。
- [ ] 切换排序方向后回到第 1 页。
- [ ] 搜索到无结果时显示"无搜索结果"空状态。
- [ ] 普通用户登录时，搜索结果只在自己创建的数据中匹配（不能搜到他人数据）。
- [ ] 超级管理员登录时，可搜到全量数据。
- [ ] 翻页到末页后再切搜索词，回到第 1 页。
- [ ] 新增 / 编辑 / 删除 item 后，列表自动刷新到最新数据。
- [ ] 浏览器地址栏**没有**多余 query 参数（D1）。

---

## 10. 风险与回滚

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| `keepPreviousData` 在搜索词切换瞬间仍显示旧数据 | 体验：用户可能误以为没生效 | 用 `isFetching` 半透明遮罩 + 总数 `Total` 实时跟随新请求结果 |
| `limit` 被恶意请求放大 | 后端资源 | `Query(le=100)` 强制上限 |
| 后端 `ILIKE` 在大数据量下慢查询 | 性能 | `Item.title` 已有 `max_length=255`；当前模板数据规模可接受；未来如需可加 `pg_trgm` 索引（不在本次范围） |
| 前端 SDK 没有重新生成 | 类型 / 调用失败 | 流程强制包含 `bun run generate-client`；CI 校验 `client/sdk.gen.ts` 与 OpenAPI 一致 |
| 删除最后一条数据后停在空页 | 用户停在空 page | 删除后失效会重新拉取；如页码越界，下一轮 `totalPages` 收缩并自动 disable 末页按钮（必要时可在 `useEffect` 里 clamp） |

### 回滚

- 后端：还原 [items.py](backend/app/api/routes/items.py) 至 `read_items` 的旧签名（`skip/limit`）。
- 前端：还原 [_layout/items.tsx](frontend/src/routes/_layout/items.tsx)；删除新建的 `ItemsTable.tsx` 与 `useDebounce.ts`；重新跑 `generate-client`。
- 数据库 / 业务数据无任何持久化变更，无需回滚数据。

---

## 11. 实施顺序建议

1. 后端：改 `read_items` + 抽辅助函数。
2. 后端：补 7 个测试，`pytest` 全绿。
3. 前端：`bun run generate-client` 同步 SDK。
4. 前端：新建 `useDebounce` hook。
5. 前端：扩展 `columns.tsx` 的 `created_at` 列。
6. 前端：新建 `ItemsTable.tsx`。
7. 前端：改 [_layout/items.tsx](frontend/src/routes/_layout/items.tsx)。
8. 全栈：`bun run lint && bun run build && bunx playwright test`。
9. 手动验证清单逐项打勾。
