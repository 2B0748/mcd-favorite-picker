# MCP 集成说明

本 Skill 依赖麦当劳官方远程 MCP：`https://mcp.mcd.cn`，协议 Streamable HTTP，鉴权 `Authorization: Bearer <token>`。
Token 在 [open.mcd.cn/mcp](https://open.mcd.cn/mcp) 申请，限流 600 次/分钟，超限返回 429。

以下字段与行为均来自 2026-10-24 的真实调用，不是照文档抄的。

## 本 Skill 用到的工具

| 工具 | 必填参数 | 用途 | 返回形态 |
|---|---|---|---|
| `order-list` | 无 | 历史餐饮订单 | JSON 信封 |
| `query-nearby-stores` | `beType`, `searchType` | 找门店（先收藏店，再按城市+关键词） | JSON 信封 |
| `query-meals` | `storeCode`, `orderType`, `beType` | 当前门店在售餐品与价格 | JSON 信封 |
| `query-meal-detail` | `storeCode`, `orderType`, `beType`, `code` | 套餐构成与换配 | JSON 信封 |
| `calculate-price` | `storeCode`, `orderType`, `beType`, `items` | 整单官方核价 | JSON 信封 |
| `query-store-coupons` | `orderType`, `beType`, `storeCode` | 该门店可用券 | JSON 信封 |
| `query-my-coupons` | 无 | 卡包全量券 | **纯 markdown** |
| `available-coupons` | 无 | 可领取券 | **纯 markdown** |
| `list-nutrition-foods` | 无 | 160 条餐品营养 | **字符串内 CSV** |

只读为主。`create-order` / `cancel-order` / `auto-bind-coupons` / `draw-lottery` / `mall-create-order` / `party-order-create` 属写操作，本 Skill 不自动调用。

## 返回形态不止一种

大部分工具的 `result.content[0].text` 是「字段说明 markdown + `## Original Response` + JSON」，需要切段再解析。但有两个例外会直接让通用解析器崩掉：

- `query-my-coupons`、`available-coupons`：**纯 markdown**，没有 JSON 信封。
- `list-nutrition-foods`：`data` 是**字符串**，内容是一段 CSV：

```
[160]{productName,nutritionDescription,energyKj,energyKcal,protein,fat,carbohydrate,sodium,calcium}:
  中薯条,null,1210,289,4,12,38,165,18
```

## 六个必须知道的字段事实

1. **`calculate-price` 的 items 字段是 `productCode`，不是 `code`。**
   传错**不报错**，返回 `price: 0`、`productList: []`、`success: true`。必须先校验 `productList` 非空。
2. **`query-meals` 的名称和价格不在分类树里。**
   `data.categories[].meals[]` 只有 `code` 和 `tags`；名称与价格在 `data.meals[code]` 映射表里，必须 join。
3. **单位不统一。** `query-meals.currentPrice` 与 `order-list.realTotalAmount` 是**元**；`calculate-price` 的 `price` / `discount` 是**分**。
4. **非供早时段的菜单没有早餐分类。** 实测 12:55 拉到的 14 个分类全是正餐，所以「能不能买到早餐」必须看菜单，不能靠时间猜。
5. **没有收藏门店时 `query-nearby-stores` 会失败而不是返回空数组。**
   `{"success":false,"code":600050}` → 立刻退到 `searchType=2` + `city` + `keyword`。
6. **券的有效期是复合条件。**
   `2026-10-26 10:30-2026-10-30 23:59 周一、二、三、四、五 10:30-23:59`
   同时含日期区间、星期限制、每日时段窗口。只看「有没有券」会推荐用不了的券。

## 两个易漏的业务点

**活动价**：`currentPrice < originalPrice` 就是促销。实测同一门店板烧四件套 `28 / 60`，比三件套 `38.50` 还便宜。不比较原价就会漏掉最省的选择。

**下架品**：历史订单里的品名可能已退市。实测在售品名相似度 0.9–1.0，下架品最高只有 0.286。阈值取 0.85 直接采用、0.5–0.85 给候选、低于 0.5 判定下架，改按「品类 + 风味」给替代。

## 参数规则

| beType | 场景 | orderType | beCode |
|---|---|---|---|
| 1 | 到店自取 | 1 | **不传**（传了报错） |
| 5 | 得来速 | 1 | 必传 |
| 2 | 麦乐送 | 2 | 必传 |
| 6 | 企业团餐 | 2 | 必传 |

本仓库只实测了到店自取（`beType=1`）链路；其余三种场景的参数规则来自官方字段说明，未做联调验证。

## 错误码

| 现象 | 原因 |
|---|---|
| 401 | Token 无效/过期，或缺 `Bearer ` 前缀（含空格） |
| 405 | URL 用了 `open.mcd.cn/mcp`（那是网页控制台），应为 `mcp.mcd.cn` |
| 429 | 超过 600 次/分钟 |
| 600050 | 无收藏门店 |
| 600014 | 城市 + 关键词搜不到，换更具体的地标 |

## 业务价值

省钱这件事，用户自己算不清：套餐价、单点价、券价、活动和原价交织在一起，还得判断券当天能不能用。这部分完全可以用确定性代码算清楚，不需要模型猜。

本 Skill 的分工是：模型负责理解意图、选择门店、把话说人话；脚本负责整数分级的金额比较、券的可用性判定、名称匹配与降级。模型不参与算钱，只负责解释算出来的结果。
