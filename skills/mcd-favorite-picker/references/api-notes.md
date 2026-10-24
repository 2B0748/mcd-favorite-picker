# 麦当劳 MCP 接口备忘（v1.1 实测版）

端点 `https://mcp.mcd.cn`，Streamable HTTP，鉴权 `Authorization: Bearer <token>`，限流 600 次/分钟。
下列结构全部来自 2026-10-24 的真实调用，不是文档抄录。

## 统一信封（大部分工具）

```json
{ "success": true, "code": 200, "message": "请求成功", "datetime": "...", "traceId": "...", "data": {...} }
```

`result.content[0].text` 是 **markdown 说明 + `## Original Response` + JSON**，必须切段再解析。

**但不是所有工具都这样**——见下面的「返回形态分类」，这是最容易翻车的地方。

---

## 返回形态分类（重要）

| 形态 | 工具 | 解析方式 |
|---|---|---|
| JSON 信封 | `order-list` `query-meals` `query-meal-detail` `calculate-price` `query-nearby-stores` `query-store-coupons` `query-my-account` | 切 `## Original Response` 后 `json.loads` |
| **纯 markdown（无 JSON）** | `available-coupons` `query-my-coupons` | 正则解析标题/价格/有效期 |
| **字符串里塞 CSV** | `list-nutrition-foods` | `data` 是字符串，首行是列名声明 |

---

## order-list

无参数。`data.list[]`：`orderId` / `createTime`(`yyyy-MM-dd HH:mm:ss`) / `storeCode` / `storeName` / `orderStatus` /
`realTotalAmount`（**元**，字符串如 `"22.9"`）/ `orderProductList[]`。

`orderProductList[]` = `{productCode, productName, quantity, comboItemList[]}`，
`comboItemList[]` = `{productCode, name, quantity}` —— **套餐壳名在 `productName`，真身在这里**。

返回条数不等于全部历史，结论里要如实说明样本量。

## query-nearby-stores

必填 `beType`(1|5) + `searchType`(1=收藏店, 2=按位置)。

**坑**：用户没有收藏门店时不会返回空数组，而是直接失败：

```
{"success":false,"code":600050,"message":"收藏餐厅列表为空，请您提供城市+关键词进行搜索"}
```

所以 `searchType=1` 失败要立刻退到 `searchType=2` + `city` + `keyword`，不要把 600050 当致命错误。
关键词用商圈/地标名（`万达` 这类过粗的关键词可能返回 600014 查不到地址）。

## query-meals ← 菜单

必填 `storeCode` / `orderType` / `beType`。返回：

```
data.categories[] = { name, meals: [ { code, tags[] } ] }   ← 只有 code，没有名字
data.meals = { "<code>": { name, image, currentPrice, originalPrice, canWithOrder } }
data.frequent = { code, tags } | null                        ← 「常点餐品」
```

- **名称和价格在 `data.meals` 这个映射表里，必须用 `categories[].meals[].code` 去 join**。
- `currentPrice` / `originalPrice` 是**元**的字符串（如 `"38"`）。
- `data.frequent` 是服务端给的常点餐品，但**历史订单少时为 `null`**，不能依赖。
- **菜单里没有早餐分类**：非早餐时段调用，14 个分类全是正餐（人气热卖 / 精选单人餐 / 鸡肉汉堡卷 / 巨无霸牛鱼肉堡 / 麦咖啡 / 饮品 …）。早餐品只在供早时段出现——所以「能不能买到早餐」由菜单决定，不能靠时间猜。

实测样本：某门店 14 个分类、122 个餐品。

## query-meal-detail

必填 `storeCode` / `orderType` / `beType` / `code`。用来拿套餐构成（可换配的子项）、特制选项。

## calculate-price ← 算价

必填 `storeCode` / `orderType` / `beType`，`items[]`。

**items 里商品编码的字段名是 `productCode`，不是 `code`。**

传错字段名**不会报错**，而是返回 `price: 0`、`productList: []`、`success: true`。
这是本接口最阴的坑——必须校验 `productList` 非空，否则会把 0 元当成真实价格展示。

`items[]` 支持 `{ productCode, quantity, couponId?, couponCode?, roundList?, modification? }`，
即**算价时可直接带券**，这正是比价功能的实现基础。

返回（全部**单位分**）：

| 字段 | 含义 |
|---|---|
| `price` / `originalPrice` | 现价 / 原价 |
| `discount` | 优惠金额 |
| `productList[].subtotal` | 单品小计，可用于校验入参是否被识别 |
| `takeWayList[]` | 取餐方式（`eat-in` 堂食 / `take-in-store` 外带） |
| `enjoyed` / `enjoyable` | 已享受 / 可享受的优惠（`realDiscount` 是**元**） |

**实测比价样例（同一门店，2026-10-24）：**

| 方案 | 组成 | 价格 |
|---|---|---|
| 单点 | 板烧鸡腿堡 ¥24 | ¥24.00 |
| 套餐 | 板烧鸡腿堡三件套 | **¥38.50** |
| 自组 | 板烧 ¥24 + 中薯条 ¥14.50 + 雪碧小杯 ¥10 | ¥48.50 |

套餐比自组省 **¥10.00**——这类差价就是省钱引擎要输出的东西。

## available-coupons / query-my-coupons ← 券

**返回纯 markdown，没有 JSON 信封。**

`query-my-coupons` 的结构：

```
共 3 张可用优惠券 | 第 1/1 页 | 每页 50 条

## 1024“码”力翻倍
- **优惠**: ¥20.48 (用券价格)
- **有效期**: 2026-10-24 00:00-2026-10-30 23:59 10:30-23:59
- **领取时间**: 今日收到
- **标签**: 到店专用
```

**关键**：`有效期` 里除了日期区间，还带 **时段窗口**（`10:30-23:59`）和**星期限制**（`周一、二、三、四、五`）。
早餐时段那些 `10:30 起` 的券**不能用**。判定可用性必须同时看日期、星期、时段、渠道四个维度。

`available-coupons` 是「可领取」列表，券名里直接带价格（`11.9元麦辣鸡腿堡`、`19.9元王牌炸鸡任选2`），状态字段是 `可领取` / `已领取`。

## query-store-coupons

必填 `orderType` / `beType` / `storeCode`。**是 JSON 信封**，`data[]`：

`{ title, couponId, couponCode, tradeDateTime, products: [ { productName, productCode } ] }`

`data: []` 表示该门店当前无可用券（正常情况，不是错误）。这里拿到的 `couponId`/`couponCode` 可以直接透传给 `calculate-price`。

## list-nutrition-foods

无参数。`data` 是**字符串**，格式：

```
[160]{productName,nutritionDescription,energyKj,energyKcal,protein,fat,carbohydrate,sodium,calcium}:
  猪柳麦满分,null,1288,308,16,16,24,781,213
  中薯条,null,1210,289,4,12,38,165,18
```

首行 `[N]{列名}:` 声明行数与列序，之后每行 CSV。`energyKcal` 是千卡，`protein`/`fat`/`carbohydrate` 克，`sodium`/`calcium` 毫克。
共 160 条常见餐品，可用于给推荐组合算热量与「低卡替代」。

## 其余工具速查

`query-my-account`（积分余额）、`query-promotions`、`campaign-calendar`（活动日历）、
`query-order`（`orderId` 单笔）、`mall-*`（积分商城）、`party-*`（企业团餐）、
`draw-lottery` / `query-my-prizes`（抽奖与奖品）、`delivery-*`（外送）、`auto-bind-coupons`（领券，写）。

## 排查对照

| 症状 | 原因 |
|---|---|
| 401 | Token 无效/过期，或缺 `Bearer ` 前缀 |
| 405 | URL 用了 `open.mcd.cn/mcp` |
| 429 | 超 600 次/分钟 |
| `price: 0` 但 success | items 用了 `code` 而非 `productCode` |
| `code: 600050` | 无收藏门店，改用 city + keyword 搜索 |
| `code: 600014` | 城市+关键词搜不到，换更具体的地标 |
| 查菜单/算价报错 | 到店自取误传 `beCode`，或缺 `storeCode` |
| 价格差 100 倍 | `calculate-price` 是分，`query-meals.currentPrice` 是元 |
