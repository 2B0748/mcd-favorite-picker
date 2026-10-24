---
name: mcd-favorite-picker
version: "1.2.0"
description: 读取麦当劳历史订单算出最常买的汉堡/小食/套餐，按当前时段（早餐/午餐/下午茶/晚餐/夜宵）推荐，并顺带算出「单点 vs 套餐 vs 用券 vs 自组」哪种最省钱，可生成可分享的口味画像卡。触发场景：麦当劳今天吃什么、帮我按我的口味推荐、我常点的是什么、怎么点最便宜、查我的麦当劳订单、麦门人格。通用 Skill：支持 MCP 的客户端直接调工具，不支持 MCP 的 Agent 走 scripts/run_recommend.py 一条命令跑完。
agent_created: true
license: MIT
---

# 麦当劳口味推荐（mcd-favorite-picker）

把「你过去真实买过什么」变成「现在该点什么、怎么点最省」。

两条铁律：
1. **偏好必须来自订单数据**，不靠印象编。
2. **推荐必须能被当前菜单验证**，卖不了的东西不推。

---

## 两种运行方式（先选一条）

| 你的 Agent 情况 | 走哪条 | 需要什么 |
|---|---|---|
| 客户端支持远程 MCP（WorkBuddy / Claude Code / Cursor / Cherry Studio / Cline…） | **A. 直接调工具**，按下面的六步流程走 | 配好 `mcd-mcp` 连接器 |
| 不支持 MCP，只能执行命令（Codex、Aider、各类终端 Agent、CI） | **B. 一条命令跑完**：`python scripts/run_recommend.py --target 板烧 --city 芜湖 --keyword 步行街` | 只需 Token |

B 的输出是完整 markdown 报告（偏好 + 比价 + 券），逻辑与 A 完全一致——A 是让模型按步骤调工具，B 是脚本替模型调。**能用 A 就用 A**：模型能追问、能换店、能解释；B 适合无 MCP 环境或批量跑。

---

## 配置 Token 与连接器

Token 到 `https://open.mcd.cn/mcp` 登录 → 控制台 → 激活。

**方式 A（MCP 连接器）**：

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

各客户端位置不同：WorkBuddy 在【连接器 → 自定义连接器】；Claude Code 用 `claude mcp add` 或 `~/.claude.json`；Cursor 在 `~/.cursor/mcp.json`；Cherry Studio 在【设置 → MCP 服务器】。保存后记得在列表里**信任/启用**，否则工具不会挂上来。

工具名前缀因客户端而异（WorkBuddy 为 `mcp__mcd-mcp__order-list`，有的客户端为 `mcd-mcp:order-list`）。**下文一律只写裸工具名**，按你客户端的实际前缀对应。

**方式 B（命令行）**：Token 放环境变量 `MCD_MCP_TOKEN`，或写入 `~/.mcd_mcp_token`，或 `--token-file` 指定。

```bash
python scripts/mcp_client.py tools                  # 连通性自检，应显示 35 tools
python scripts/run_recommend.py --store 3450024 --target 板烧 --card
python scripts/run_recommend.py --city 芜湖 --keyword 步行街 --target 板烧
```

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

覆盖：0/1/5/20 单、跨时段、prefs 去重累积、活动价识别、券的星期与日期校验、MCP 客户端解析，共 10 项。
改动任何脚本后先跑这个。

## 文件

| 文件 | 作用 |
|---|---|
| `references/api-notes.md` | 35 个工具的真实字段、信封格式、beType/beCode 铁律 |
| `scripts/run_recommend.py` | **方式 B 入口**：一条命令跑完订单→偏好→门店→菜单→券→比价→报告 |
| `scripts/mcp_client.py` | 零依赖 MCP 客户端（纯标准库），给不支持 MCP 的 Agent 用，也可单独调任意工具 |
| `scripts/analyze_orders.py` | 订单 → 偏好统计 + prefs.json 增量累积 |
| `scripts/best_deal.py` | 券可用性解析 + 四类方案比价 |
| `scripts/make_card.py` | prefs.json → 可分享画像卡（HTML/PNG） |
| `tests/` | fixture 生成与回归测试 |

## 给模型的操作提示

- **不要凭记忆报价格**。所有金额必须来自本次工具返回或脚本输出。
- **不要假设菜单里有早餐**。非供早时段没有早餐分类，先看菜单再说。
- 用户没给城市/门店时先问一句，别猜。
- 报错先看是不是 405（地址错）或 401（Token 错），这两种占绝大多数。
- 结论里必须带上**次数**和**日期**（「买过 4 次，最近 8/15」），这是可信度的来源。
