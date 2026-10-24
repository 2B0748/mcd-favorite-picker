# AGENTS.md

给**任意** AI Agent 的接入说明（Codex、Cursor、Cline、Aider、Zed、WorkBuddy、Claude Code…）。
本文件是跨 Agent 的事实标准入口；Skill 本体在 [`skills/mcd-favorite-picker/SKILL.md`](skills/mcd-favorite-picker/SKILL.md)。

## 这个项目做什么

读麦当劳历史订单 → 算出常点 → 按当前时段推荐 → 比较「单点 / 套餐 / 用券 / 自组」哪种最省。
数据全部来自麦当劳官方 MCP（`https://mcp.mcd.cn`，35 个工具），本地只做统计与金额比较。

## 你有三种接入方式，按能力选

### 1. 你支持远程 MCP

配好连接器后直接调工具，按 SKILL.md 的六步流程走。

```json
{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn",
      "headers": { "Authorization": "Bearer ${MCD_MCP_TOKEN}" }
    }
  }
}
```

工具名前缀各单位不同（`mcp__mcd-mcp__order-list` / `mcd-mcp:order-list` / 裸名），按你的客户端对应。

### 2. 你只能执行命令（不支持 MCP）

一条命令出结果，无需任何 MCP 集成：

```bash
python skills/mcd-favorite-picker/scripts/run_recommend.py \
    --target 板烧 --city 芜湖 --keyword 步行街 --card
```

已知道门店编码时用 `--store <storeCode>` 跳过搜索。输出 `今日推荐.md` + `prefs.json`（+ 可选画像卡）。

### 3. 你需要精确控制某一次调用

```bash
python skills/mcd-favorite-picker/scripts/mcp_client.py tools
python skills/mcd-favorite-picker/scripts/mcp_client.py call query-meals \
    --args '{"storeCode":"3450024","orderType":1,"beType":1}' --out meals.json
```

## 环境契约

| 项 | 值 |
|---|---|
| Python | ≥ 3.10，**仅标准库**，无需 pip install |
| Token | 环境变量 `MCD_MCP_TOKEN`，或 `~/.mcd_mcp_token`，或 `--token-file` |
| 网络 | 需要。价格与菜单不可离线伪造 |
| 写操作 | **禁止自动执行** `create-order` / `cancel-order` / `auto-bind-coupons` / `draw-lottery` / `mall-create-order` / `party-order-create` |

## 你必须遵守的约束

1. **不编价格。** 任何金额必须来自本次工具返回或脚本输出。没有数据就说没有。
2. **不猜门店。** 用户没给城市/门店就用 `--city` + `--keyword` 搜，搜不到要问。
3. **不假设有早餐。** 非供早时段菜单里没有早餐分类，先查菜单再推荐。
4. **不隐瞒样本不足。** 订单 < 5 单必须标注「参考性有限」，0 单转冷启动。
5. **不下单。** 停在方案建议，除非用户逐单明确确认。

## 四个会直接坑到你的接口事实

| 事实 | 后果 |
|---|---|
| `calculate-price` 的 items 字段是 **`productCode`** 不是 `code` | 传错**不报错**，返回 `price: 0` + `success: true`，会展示假价格。必须校验 `productList` 非空 |
| `query-meals` 的名称与价格在 **`data.meals[code]` 映射表**，不在 `categories[].meals[]` | 只读分类树会拿不到名字 |
| `query-my-coupons` / `available-coupons` 是**纯 markdown**，无 JSON 信封 | 通用 JSON 解析器会挂 |
| 无收藏门店时 `query-nearby-stores` 返回 **`success:false, code:600050`** | 这不是致命错误，要退到 city + keyword |

金额单位：`query-meals.currentPrice` 和 `order-list.realTotalAmount` 是**元**；`calculate-price` 的 `price` / `discount` 是**分**。

完整字段与 35 个工具清单见 [`skills/mcd-favorite-picker/references/api-notes.md`](skills/mcd-favorite-picker/references/api-notes.md)。

## 验证

```bash
python skills/mcd-favorite-picker/tests/run_tests.py
```

8 项离线回归，不需要 Token、不联网。改任何脚本后先跑这个。

## 术语

- **套餐**：菜单里名字带「套」或「件」的餐品，`comboItemList` 非空。
- **自组**：把汉堡、薯条、饮料按单品拼起来，用来和套餐比价。
- **活动价**：`currentPrice < originalPrice`。实测出现过四件套比三件套便宜。
- **券可用性**：日期区间 + 星期限制 + 每日时段 + 渠道，四维全过才算可用。
