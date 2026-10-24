---
name: mcd-favorite-picker
version: "1.1.0"
description: 读取麦当劳历史订单算出最常买的汉堡/小食/套餐，按当前时段（早餐/午餐/下午茶/晚餐/夜宵）推荐，并顺带算出「单点 vs 套餐 vs 用券 vs 自组」哪种最省钱，可生成可分享的口味画像卡。触发场景：麦当劳今天吃什么、帮我按我的口味推荐、我常点的是什么、怎么点最便宜、查我的麦当劳订单、麦门人格。依赖已接入的麦当劳官方 MCP（连接器名 mcd-mcp）。
agent_created: true
---

# 麦当劳口味推荐（mcd-favorite-picker）

把「你过去真实买过什么」变成「现在该点什么、怎么点最省」。

两条铁律：
1. **偏好必须来自订单数据**，不靠印象编。
2. **推荐必须能被当前菜单验证**，卖不了的东西不推。

---

## 前置检查

需要连接器 `mcd-mcp`（麦当劳官方 MCP，35 个工具）。若工具列表里没有 `mcp__mcd-mcp__*`，让用户去【连接器 → 自定义连接器 → 配置 MCP】填：

```json
{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn",
      "headers": { "Authorization": "Bearer YOUR_MCP_TOKEN" }
    }
  }
}
```

Token 在 `https://open.mcd.cn/mcp` 登录 → 控制台 → 激活。保存后要到列表里点「信任」并启用。

⚠ **URL 必须是 `https://mcp.mcd.cn`**，不是 `https://open.mcd.cn/mcp`（后者是网页控制台，405）；`Bearer ` 前缀连空格不能少（否则 401）。

---

## 执行流程

### 第 1 步 · 定位时间与时段

本地时间可用就用本地；需要和服务器对齐时调 `now-time-info`。

| 时段 | 时间窗 | 推荐什么 | 券的坑 |
|---|---|---|---|
| 早餐 | 05:00–10:29 | 麦满分、粥、油条、薯饼、豆浆、蛋堡 | 多数券 **10:30 起**才可用 |
| 午餐 | 10:30–13:59 | 汉堡 / 套餐（主力） | — |
| 下午茶 | 14:00–16:59 | 小食 + 饮品 / 甜品 | — |
| 晚餐 | 17:00–21:59 | 汉堡 / 套餐，可给更丰富组合 | — |
| 夜宵 | 22:00–04:59 | 单品为主，提醒部分门店已打烊 | — |

**早餐收档预警**：若当前在 10:00–10:29，主动提示「还有 N 分钟早餐收档」。

**能不能买到早餐，以菜单里有没有早餐分类为准**，不要靠时间猜——非供早时段的菜单里根本没有早餐品。

### 第 2 步 · 拉历史订单并累积偏好

调 `order-list`（无参数）。把返回原文存成文件，然后：

```bash
python scripts/analyze_orders.py <订单原文.txt> --prefs prefs.json --out 报告.txt --now "YYYY-MM-DD HH:MM"
```

- `prefs.json` 会按 `orderId` 去重后**增量累积**。**每次都要带上 `--prefs`**，否则样本永远只有接口这次给的几单。
- 只查已有快照：`--show-prefs prefs.json`。
- `order-list` 只含餐饮订单；商城单在 `mall-order-list`，本 Skill 默认不掺。

### 第 3 步 · 读偏好结论

脚本输出会给出四组排序（最常买套餐 / 最爱汉堡 / 最爱小食 / 最爱饮品甜品）、时段分布、近 7 天重复项、从未点过的品类。

按样本量决定说话方式：

| 样本 | 态度 |
|---|---|
| ≥ 5 单 | 正常输出，可给「你的老三样」组合 |
| 1–4 单 | 照常推荐，但必须写明「样本仅 N 单，参考性有限」 |
| 0 单 | 不要编历史，转冷启动（见下） |

- **重复抑制**：近 7 天吃过的同款要降权，并明说「你 X 号刚吃过」。
- **负向偏好**：`从未点过的品类` 在样本 < 8 单时只能当弱提示（「你好像没点过甜品」），不得断言「你不吃」。
- **时段缺样本**：从没在早上买过，就别把正餐偏好套到早餐上，直接按早餐菜单推经典款并说明。

**冷启动**（0 单或某时段无数据）：跳过历史，直接走第 4–5 步，按「菜单结构 + 活动价 + 券 + 时段」推荐，并说明这是冷启动推荐。

### 第 4 步 · 定位门店与菜单

1. `query-nearby-stores`：先试 `beType=1, searchType=1`（收藏店）。
   **用户没收藏门店时会返回 `success:false, code:600050`，这不是错误**，立刻退到 `searchType=2` + `city` + `keyword`。城市/位置用户没给就先问一句。
2. `query-meals`：`storeCode` + `orderType=1` + `beType=1`，**到店自取不要传 `beCode`**。
3. 返回里 `data.categories[].meals[].code` 只有编码，**名称与价格在 `data.meals[code]` 映射表里**，必须 join 后另存成 `menu.json` 供第 5 步用。

### 第 5 步 · 比价（本 Skill 的核心增值）

```bash
# 先解析券包，算出每张券此刻能不能用
python scripts/best_deal.py coupons <query-my-coupons 原文.txt> --now "..." --out coupons.json

# 再对目标品生成并比较方案
python scripts/best_deal.py deal --menu menu.json --target 板烧 \
        --coupons coupons.json --nutrition <营养原文.txt> --now "..." --out deal.txt
```

会输出：单点 / 套餐 / 用券 / 自组 四类方案、原价与活动价、热量，以及两条结论——「只要主品多少钱」「想吃一套多少钱、比单点多多少」。

**两个必须人工复核的点**：

1. **活动价**：`currentPrice < originalPrice` 就是促销。实测遇到过「四件套 ¥28（原价 ¥60）比三件套 ¥38.50 还便宜」——这种一定要主动指出来，是省钱引擎最有价值的输出。
2. **券的可用性**：`有效期` 里可能同时有日期区间、星期限制（`周一、二、三`）、时段窗口（`10:30-23:59`）。四维都要过，否则会推荐用不了的券。脚本已实现，但**结论里要说清为什么不可用**（「这张要 10-26 才开始」）。

需要精确总价（含券后）时才调 `calculate-price`，`items[]` 的字段是 **`productCode`**，
并且**必须校验 `productList` 非空**——传错字段名会静默返回 0 元且 `success:true`。

### 第 6 步 · 输出

结构控制在 15 行内：

```
【现在 12:54 · 午餐】按你过去 N 单的口味：

主推：板烧鸡腿堡四件套 ¥28.00（活动价，原价 ¥60.00）
      只比单点汉堡多 ¥4.00，就多出小食和饮品
备选：板烧鸡腿堡三件套 ¥38.50 —— 同样「堡+薯+饮」比自组省 ¥10.00
热量：主品约 391 kcal；套餐含小食饮品，需按构成另算
提示：11.9 元麦辣鸡腿堡券要 10-26 才开始，今天用不了
```

- 每个推荐带**出现次数**，这是可信度来源。
- 价格用实时菜单/算价，别拿历史订单金额冒充当前价。
- 结尾可问「要我把这单加进购物车吗」，但**不下单**。

### 可选 · 口味画像卡

```bash
python scripts/make_card.py prefs.json --out 麦门口味画像.html --png 麦门口味画像.png
```

产出可分享卡片（人格名 + 订单数 + 累计消费 + 客单价 + 最常点 + 时段分布）。
样本 < 5 单时卡面会自动标注「人格为暂定」。`--png` 需要本机有 Edge，没有就只出 HTML。

---

## 硬性边界

- **只读为主**。`create-order` / `party-order-create` / `delivery-*` / `mall-create-order` / `cancel-order` / `auto-bind-coupons` / `draw-lottery` 是写操作，必须用户明确要求 + 逐单二次确认。
- **订单数据是隐私**。只用于本次分析，不写进会提交到仓库的文件，回复里不展示完整 `orderId`、门店地址。
- **不展示 Token**。
- 限流 600 次/分钟，串行调用；429 退避重试一次。
- 卖不了的东西不推；匹配不上就说「原款已不在售」并按品类+风味给替代。

---

## 常见坑（实测）

| 现象 | 原因 | 处理 |
|---|---|---|
| `json.loads` 报错 | 返回被 markdown 包裹 | 切 `## Original Response` 段 |
| `price: 0` 但 success | items 用了 `code` 而非 `productCode` | 改字段名并校验 `productList` 非空 |
| 价格差 100 倍 | `calculate-price` 是分，`query-meals.currentPrice` 是元 | 分开处理 |
| 菜单查不到名字 | 名称在 `data.meals` 映射里 | 用 code join |
| `code: 600050` | 无收藏门店 | 改用 city + keyword |
| 401 / 405 | 缺 `Bearer ` / 用了 `open.mcd.cn/mcp` | 见前置检查 |
| 券解析出空 | `query-my-coupons` 是纯 markdown，无 JSON | 用 `best_deal.py coupons` 解析 |
| 历史品名匹配不上 | 已下架 | 实测相似度：在售品 0.9–1.0，下架品 ≤0.29；低于 0.5 判定下架 |

## 自测

```bash
python tests/run_tests.py
```

覆盖：0/1/5/20 单、跨时段、prefs 去重累积、活动价识别、券的星期与日期校验。
改动任何脚本后先跑这个。

## 文件

| 文件 | 作用 |
|---|---|
| `references/api-notes.md` | 35 个工具的真实字段、信封格式、beType/beCode 铁律 |
| `scripts/analyze_orders.py` | 订单 → 偏好统计 + prefs.json 增量累积 |
| `scripts/best_deal.py` | 券可用性解析 + 四类方案比价 |
| `scripts/make_card.py` | prefs.json → 可分享画像卡（HTML/PNG） |
| `tests/` | fixture 生成与回归测试 |
