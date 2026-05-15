# guancli CLI 使用说明

> 来源：`/Users/jian.yang/Downloads/guancli使用说明.pdf`
>
> 本文件由 PDF 转换并整理为 Markdown，只保留 guancli CLI 的安装、认证、命令、参数、工作流和排查说明；已排除官方附加注册能力相关内容。

## CLI 使用要点

- `guancli` 用于连接观远 BI，调用 BI API，查询 ETL、数据集、页面、卡片、表单、任务、指标、ChatBI 等真实资源和数据。
- 不知道资源 ID 时，先用 `tree` 或 `search` 定位，再用 `get` 查看详情，最后按需用 `preview` 查看数据。
- 默认优先用于查询、分析、预览和排查；涉及表单写入、批量更新或删除时，先确认环境、资源 ID、目标行和字段变更。
- 输出过长时使用 `--brief`；接口异常、字段不完整或结构不清楚时使用 `--raw`。
- 脚本处理优先使用 `-f json`；给业务人员阅读优先使用默认表格或 `-f csv`。

---

## 1. 适用场景与能力边界

### 1.1. 适用场景

guancli 适合以下场景:

- 快速查看 BI 系统中的 ETL 、数据集、页面、卡片等资源。
- 根据关键字搜索资源,并进一步获取详情、字段结构、血缘关系或卡片配置。
- 从页面反查卡片,从卡片反查数据集,从数据集反查上下游资源。
- 预览数据集、卡片、ETL 节点或指标数据,支持筛选、排序、列选择和多种输出格式。
- 查询、插入、更新、删除表单填报数据。
- 查询运行中或历史任务,辅助定位 ETL 、同步、计算等任务失败原因。
- 使用 ChatBI 主题问数或洞察分析。
- 通过通用 fetch 命令调用当前 BI 环境的开放或内部 API。
- 快速创建 SuperApp 模板项目。
### 1.2. 使用边界

当前 guancli 更适合查询、分析和排查。 已支持但需要谨慎使用的能力:

- 大规模批量写入或删除表单数据。
- 在生产环境直接执行未经确认的写操作。
- 自动化脚本中连续调用写操作。
- 对大数据量资源执行预览、导出或高频查询。
当前不支持的场景:

- 直接修改 ETL。
- 通过 guancli 创建或修改卡片、页面、数据源等复杂 BI 资源。
- 管理员级后台操作。
另外, guancli 可以辅助预览、查询和导出部分结果,但不建议将当前试用版本直接作为正式数据导出、报表分发、审计留痕或审批流程的替代方案。 如遇到命令返回异常、字段不完整、输出格式与预期不一致等情况,可优先使用 --raw 查看接口原始返回,并将命令、资源 ID、报错信息和当前环境说明反馈给观远支持团队。

## 2. CLI 命令行工具概览

### 2.1. CLI 负责连接 BI 并获取数据

CLI 是实际执行命令的工具,例如:

```bash
guancli ds get <ds_id>
guancli card preview <cd_id> --limit 20
guancli task history --status Failed
```

它会基于当前登录用户权限调用 BI API,并把结果输出到终端。

## 3. 安装与运行方式

### 3.1. 安装前准备

guancli 通过 npm 包发布。安装前请先确认本机已经安装 Node.js 和 npm。 检查 Node.js:

```bash
node -v
```

检查 npm:

```bash
npm -v
```

如果以上命令无法执行,说明当前电脑还没有安装 Node.js,或 Node.js 没有正确加入系统 PATH。请先安装 Node.js,再重新打开终端执行检查命令。 建议使用较新的 Node.js LTS 版本。安装完成后,如果终端仍提示找不到 node 或 npm,通常需要 关闭当前终端窗口并重新打开。

### 3.2. npm 全局安装

推荐使用 npm 全局安装:

```bash
npm install -g @guandata/guancli
```

安装完成后,验证命令是否可用:

```bash
guancli version
```

如果希望确认命令安装到了哪里,可以执行:

```bash
npm list -g @guandata/guancli
```

如果安装成功但执行 guancli version 提示找不到命令,通常是 npm 全局命令目录没有加入系统 PATH。可先查看 npm 全局命令目录:

```bash
npm prefix -g
```

Windows 下,全局命令通常位于类似下面的位置:

```text
%AppData%\npm
```

macOS / Linux 下,全局命令通常位于 npm 全局 prefix 对应的 bin 目录。将该目录加入 PATH 后,重新打开终端再执行:

```bash
guancli version
```

### 3.3. 升级 guancli

如果后续需要更新到最新版本,可再次执行全局安装命令:

```bash
npm install -g @guandata/guancli
```

然后查看当前版本:

```bash
guancli version
```

### 3.4. 卸载 guancli

如果需要卸载:

```bash
npm uninstall -g @guandata/guancli
```

卸载后可验证命令是否仍存在:

```bash
guancli version
```

如果仍能执行,说明电脑上可能还有其他位置安装过 guancli,需要检查当前终端的 PATH 或其他 Node.js/npm 环境。

### 3.5. 使用 npx 临时运行

也可以不做全局安装,直接通过 npx 运行:

```bash
npx @guandata/guancli auth login
```

npx 会临时下载并执行 npm 包中的命令。它适合临时试用、快速验证或不希望污染全局环境的场景。经常使用时,仍建议使用全局安装,避免每次运行都依赖临时下载和网络环境。

## 5. 登录与多环境管理

使用 guancli 前，需要先配置 BI 系统地址和认证信息。登录成功后，后续 CLI 命令会自动复用当前认证信息。

### 5.1. 交互式登录

```bash
guancli auth login
```

按提示输入:

1. 环境名称:默认 default,也可以填写 prod 、 test 、 staging 等。
2. BI 系统 URL:例如 https://bi.example.com。
3. 登录方式:选择用户名密码登录或直接输入 Token。
4. Domain:如果系统配置了默认域,可留空让工具自动探测。
5. Login ID:登录账号,通常为邮箱或用户名。
6. Password:账号密码。
登录成功后,Token 会保存到本机配置文件中,后续命令会自动复用。

### 5.2. 非交互式登录

适合脚本或自动化场景:

```bash
guancli auth login \
--profile prod \
--url https://bi.example.com \
--domain demo \
--login-id user@example.com \
--password your_password \
--default
```

如果希望保存密码,并在 401 或 Token 失效时自动重新登录,可增加:

```bash
--save-password
```

示例:

```bash
guancli auth login \
--profile prod \
--url https://bi.example.com \
--domain demo \
--login-id user@example.com \
--password your_password \
--save-password \
--default
```

--save-password 会把密码保存到本机配置文件中。请仅在受信任的电脑或服务器上使用。

### 5.3. 使用已有 Token 登录

执行:

```bash
guancli auth login
```

登录方式选择 2. 直接输入 Token,然后粘贴已有 Auth Token。Token 方式适合临时使用,但如果 Token 过期,通常需要重新执行 auth login。

### 5.4. 查看认证状态

```bash
guancli auth status
guancli auth whoami
```

查看指定环境:

```bash
guancli auth status --profile prod
```

### 5.5. 多环境管理

guancli 支持在一台电脑上保存多个 BI 环境配置,例如测试环境、生产环境、客户 A 环境、客户 B 环境。 查看所有环境:

```bash
guancli auth list
```

切换默认环境:

```bash
guancli auth use prod
```

删除环境配置:

```bash
guancli auth remove staging
```

临时指定环境,不切换默认环境:

```bash
guancli --profile prod ds tree
guancli --profile test etl search 销售
```

也可以使用环境变量:

```bash
set GUANCLI_PROFILE=prod
guancli ds treemacOS / Linux:
```

```bash
export GUANCLI_PROFILE=prod
guancli ds tree
```

### 5.6. 修改已有环境

修改 URL 、Domain、账号等信息:

```bash
guancli auth modify prod --url https://new-bi.example.com
guancli auth modify prod --domain demo
guancli auth modify prod --login-id user@example.com
```

修改密码并立即重新登录:

```bash
guancli auth modify prod --password new_password --relogin
```

修改密码并保存:

```bash
guancli auth modify prod --password new_password --save-password --relogin
```

### 5.7. 探测默认 Domain

如果登录页面没有显示 Domain 输入框,可执行:

```bash
guancli auth detect-domain --url https://bi.example.com
```

如果已经配置过环境,也可以直接:

```bash
guancli auth detect-domain
```

### 5.8. 配置文件位置

认证信息保存在系统标准配置目录下的 guancli/config.json 中。 常见位置:

- Windows: %AppData%\guancli\config.json
- macOS: ~/Library/Application Support/guancli/config.json
- Linux: ~/.config/guancli/config.json
配置文件大致结构如下: JS O N 1 { 2 "profiles": { 3 "default": { 4 "name": "default", 5 "base_url": "https://bi.example.com", 6 "domain": "demo", 7 "login_id": "user@example.com", 8 "auth_method": "password", 9 "token": "...", 10 "is_default": true 11 } 12 }, 13 "token_refresh_interval_seconds": 600 14 }

## 6. 使用建议

- 第一次使用先执行 guancli auth status 和 guancli auth whoami,确认环境和账号
正确。

- 当前版本仍在内部验证中,建议先在测试环境或非关键资源上完成试用,再逐步用于正式业务场
景。

- 不知道资源 ID 时,先用 tree 或 search 定位,再用 get 查看详情。
- 需要排查数据口径时,优先查看 ds get 、 card get 、 page get 和 etl get。
- 需要脚本化处理时,优先使用 -f json。
- 需要给业务人员查看结果时,优先使用默认表格或 -f csv。
- 写表单数据前,先用 form schema 确认字段名和类型,再用 form query -f json 获取
完整 rowId。

- 删除表单数据、批量更新数据前,建议先导出一份查询结果用于留档。

## 7. 建议试用路径

### 7.1. 第一阶段:确认安装和认证

```bash
guancli version
guancli auth login
guancli auth status
guancli auth whoami
```

目标是确认当前电脑可以正常执行 CLI,并且已连接到正确 BI 环境。

### 7.2. 第二阶段:只读查询和资源理解

```bash
guancli ds tree
guancli page tree
guancli etl tree
guancli ds search 销售
guancli page search 看板
```

目标是验证目录、搜索和详情查看是否能帮助理解当前 BI 项目。

### 7.3. 第三阶段:数据预览和问题排查

```bash
guancli ds get <ds_id> --brief
guancli ds preview <ds_id> --limit 20
guancli page get <page_id>
guancli card preview <cd_id> --limit 20
guancli task history --status Failed
```

目标是验证能否定位数据来源、预览数据、排查页面或任务问题。

### 7.4. 第四阶段:谨慎验证写操作

如需验证表单写操作,建议先使用测试表单或少量数据:

```bash
guancli form list
guancli form schema <fmId>
guancli form query <fmId> -f json
```

在确认 fmId 、字段名和 rowId 后,再执行:

```bash
guancli form add <fmId> --set "字段=值"
guancli form update <fmId> <rowId> --set "字段=新值 "
```

删除操作应最后验证,并保留操作前查询结果:

```bash
guancli form delete <fmId> <rowId>
```

## 8. 推荐 CLI 工作方式

### 8.1. 查询和排查顺序

排查 BI 资源或数据问题时，建议按以下顺序执行：

1. 先确认环境和登录状态。
2. 根据资源类型搜索或列目录。
3. 获取资源详情。
4. 预览必要数据。
5. 如有异常，使用 `--raw` 查看原始返回。
6. 记录执行过的命令、资源 ID、关键输出和下一步建议。

```bash
guancli auth status
guancli auth whoami
guancli ds search 销售汇总
guancli ds get <ds_id> --brief
guancli ds preview <ds_id> --limit 20
```

### 8.2. 涉及写操作时的建议

表单 CRUD 是当前 guancli 中少数写操作能力。执行写操作前建议先确认：

- 当前 profile 和 BI 地址。
- 表单 `fmId`。
- 字段名称和字段类型。
- 目标 `rowId`。
- 即将写入、更新或删除的内容。

建议先查询并导出目标数据，再执行新增、更新或删除命令。删除和批量更新应优先在测试环境或少量数据上验证。

## 9. 常用工作流示例

### 9.1. 分析 BI 资源

可使用 CLI 完成以下操作:

- 搜索某个 ETL 、数据集、页面或卡片。
- 查看 ETL 节点、SQL 、输入输出和血缘。
- 查看数据集字段结构、字段类型、维度、度量、计算字段和血缘。
- 查看页面中有哪些卡片、筛选器和交互配置。
- 查看卡片的数据集来源、图表配置和预览数据。
典型命令:

```bash
guancli page search 销售经营看板
guancli page get <page_id>
guancli card get <cd_id>
guancli ds get <ds_id>
```

### 9.2. 按名称查找数据集并预览数据

```bash
guancli ds search 销售
guancli ds get <ds_id>
guancli ds preview <ds_id> --limit 20
```

带筛选、排序和行数限制的示例:

```bash
guancli ds preview <ds_id> \
--filter "日期 toMonth EQ 2026-01" \
--filter "城市 EQ 上海 " \
--sort-desc 销售额 \
--limit 20
```

### 9.3. 从页面找到卡片,再查看卡片数据

```bash
guancli page search 经营看板
guancli page get <page_id>
guancli card get <cd_id>
guancli card preview <cd_id> --limit 20
```

### 9.4. 排查 ETL 和数据口径

典型命令:

```bash
guancli ds search 销售汇总
guancli ds get <ds_id> --assoc
guancli etl get <etl_id>
```

如果要排查失败任务:

```bash
guancli task history --status Failed --task-types ETL_COMBINED
guancli task get <task_id>
guancli task detail <task_id>
```

### 9.5. 查询和维护表单填报数据

典型命令:

```bash
guancli form list 客户回访
guancli form schema <fmId>
guancli form query <fmId> --filter "状态 EQ 待处理 " -f json
guancli form update <fmId> <rowId> --set "状态=已处理 "
```

建议:涉及写入、更新、删除表单数据时，先确认即将操作的 `fmId`、`rowId` 和字段变更内容，再执行。

### 9.6. 使用 ChatBI 问数和洞察

典型命令:

```bash
guancli chatbi list-theme
guancli chatbi query --theme-name "经营主题 " --message "最近 30 天营业收入是多少? "
```

洞察分析:

```bash
guancli chatbi insight \
--theme-name "经营主题 " \
--message "分析最近 30 天营业收入变化原因 "
```

### 9.7. 查询指标和指标归因

典型命令:

```bash
guancli metric search 销售额
guancli metric get <metric_id>
guancli metric query <metric_id> --dim 渠道 --limit 20
```

指标归因示例:

```bash
guancli metric_attribution search 销售
guancli metric_attribution get <metric_tree_id>
guancli metric_attribution query <metric_tree_id> --target dim --dim 渠道
```

### 9.8. 调用通用 API

对于 CLI 尚未封装成专用命令的接口,可以通过 fetch 调用:

```bash
guancli fetch GET /api/health
guancli fetch POST /api/example '{"name":"test"}'
```

这适合支持团队或实施人员做接口级排查。

## 10. 全局参数、输出格式与筛选语法

### 10.1. 全局参数

大部分命令都支持以下全局参数:

**参数 说明**

--profile <name> 使用指定环境配置 --raw 输出后端原始 JSON,不做解析和格式化 --brief 轻量输出,省略较长的 Malloy、血缘、公式等内容 --format, -f 指定输出格式 --verbose, -v 输出更详细的日志 示例:

```bash
guancli ds preview <ds_id> -f table
guancli ds preview <ds_id> -f csv
guancli ds preview <ds_id> -f json
guancli ds get <ds_id> --brief
guancli ds get <ds_id> --raw
```

### 10.2. 输出格式

**格式 说明**

auto 默认格式,终端友好的表格或文本,内容较多时 自动精简 table 对齐表格,不自动截断 csv CSV 格式,便于导出到 Excel expanded 类 PostgreSQL 的竖排格式,适合查看宽表 json JSON 行记录或结构化对象,适合脚本处理 -f json 常用于脚本处理和获取完整 ID。例如:

```bash
guancli form query <fmId> -f json
```

这会以 JSON 形式输出表单数据,适合获取完整 rowId,避免默认表格展示时较长 ID 被截断。

### 10.3. 通用筛选语法

筛选条件格式:

```text
"列名 操作符 值"
```

示例:

```bash
guancli ds preview <ds_id> --filter "城市 EQ 上海 "
guancli ds preview <ds_id> --filter "年龄 GT 18"
guancli ds preview <ds_id> --filter "渠道 IN 线上,门店 "
guancli ds preview <ds_id> --filter "销售额 BT 1000,5000"
guancli ds preview <ds_id> --filter "备注 IS_NULL"
```

多个条件默认使用 AND:

```bash
guancli ds preview <ds_id> \
--filter "城市 EQ 上海 " \
--filter "销售额 GT 1000"
```

改为 OR:

```bash
guancli ds preview <ds_id> \
--filter "城市 EQ 上海 " \
--filter "城市 EQ 北京 " \
--combine-type OR
```

支持的操作符:

**操作符 含义**

EQ 等于 NE 不等于 LT 小于 LE 小于等于 GT 大于 GE 大于等于 BT between,两个值用英文逗号分隔 IN 多值匹配,多个值用英文逗号分隔 IS_NULL 为空 NOT_NULL 不为空 CONTAINS 包含 NOT_CONTAINS 不包含 STARTSWITH 以指定内容开头 NOT_STARTSWITH 不以指定内容开头 ENDSWITH 以指定内容结尾 NOT_ENDSWITH 不以指定内容结尾

### 10.4. 日期粒度筛选

日期或时间字段支持按年、季度、月、日筛选:

```bash
guancli ds preview <ds_id> --filter "日期 toYear EQ 2026"
guancli ds preview <ds_id> --filter "日期 toQuarter IN 2026-Q1,2026-Q2"
guancli ds preview <ds_id> --filter "日期 toMonth EQ 2026-01"
guancli ds preview <ds_id> --filter "日期 toDate EQ 2026-01-15"
```

**粒度 修饰符 值格式 示例**

年 toYear YYYY 2026 季度 toQuarter YYYY-QN 2026-Q1 月 toMonth YYYY-MM 2026-01 日 toDate YYYY-MM-DD 2026-01-15

### 10.5. 排序和列选择

升序:

```bash
guancli ds preview <ds_id> --sort-asc 日期
```

降序:

```bash
guancli ds preview <ds_id> --sort-desc 销售额
```

只显示指定列:

```bash
guancli ds preview <ds_id> --columns "日期,城市,销售额 "
```

组合使用:

```bash
guancli ds preview <ds_id> \
--filter "城市 EQ 上海 " \
--sort-desc 销售额 \
--columns "城市,门店,销售额 " \
--limit 20
```

## 11. CLI 命令详细说明

### 11.1. ETL 操作

ETL 命令用于查看 ETL 目录、搜索 ETL 、获取 ETL 详情,以及预览 ETL 节点数据。 查看 ETL 目录树:

```bash
guancli etl tree
```

搜索 ETL:

```bash
guancli etl search 销售
guancli etl search 销售 --dir-id <dir_id>
```

获取 ETL 详情:

```bash
guancli etl get <resource_id>
guancli etl get <resource_id> --brief
guancli etl get <resource_id> --raw
```

详情通常包括:

- ETL 基本信息。
- 节点列表。
- 节点 SQL 或等价逻辑。
- 输入、输出数据集。
- 资源血缘关系。
预览 ETL 节点数据:

```bash
guancli etl preview <etl_id> <node_id>
guancli etl preview <etl_id> <node_id> --limit 20
guancli etl preview <etl_id> <node_id> --filter "城市 EQ 上海 "
guancli etl preview <etl_id> <node_id> --sort-desc 销售额
guancli etl preview <etl_id> <node_id> --columns "城市,销售额,订单数 "
guancli etl preview <etl_id> <node_id> --timeout 180
```

### 11.2. 数据集操作

查看数据集目录树:

```bash
guancli ds tree
```

搜索数据集:

```bash
guancli ds search 销售
guancli ds search 销售 --dir-id <dir_id>
guancli ds search --id <ds_id>
guancli ds search 销售 --id <ds_id>
guancli ds search --id <ds_id> --limit 30 --offset 0
```

查看数据集详情:

```bash
guancli ds get <ds_id>
guancli ds get <ds_id> --brief
guancli ds get <ds_id> --assoc
guancli ds get <ds_id> --raw
```

详情通常包括:

- 数据集名称、I D、类型等基本信息。
- 字段结构。
- 维度、度量、计算字段。
- Malloy source 定义。
- 血缘关系。
预览数据集数据:

```bash
guancli ds preview <ds_id>
guancli ds preview <ds_id> --limit 20
guancli ds preview <ds_id> --limit 1000
guancli ds preview <ds_id> -f table
guancli ds preview <ds_id> -f csv
guancli ds preview <ds_id> -f json
guancli ds preview <ds_id> -f expanded
```

数据集预览的行数规则:

- <ds_id> 指数据集 ID,即 dsId,不是卡片 ID。
- 不指定 --limit 时,CLI 默认向接口请求 50 行。
- 可通过 --limit <行数 > 指定希望返回的行数,例如 --limit 1000。
- 当前接口最大支持返回 60, 000 行;超过接口上限时,会以 BI 后端返回的限制或错误信息为准。
- 默认 auto 输出格式在行数较多时会精简展示;如果需要确认实际返回行数,建议查看输出摘要
中的“返回行”,或使用 -f json / -f table。

### 11.3. 页面操作

页面命令用于查看 BI 页面或仪表板的目录、搜索页面、获取页面详情。

```bash
guancli page tree
guancli page search 经营看板
guancli page search 经营看板 --dir-id <dir_id>
guancli page get <page_id>
```

页面详情通常包括:

- 页面基本信息。
- 页面内卡片列表。
- 卡片 ID,即 cdId。
- 卡片类型。
- 筛选器配置。
- 交互联动配置。
- 使用的数据集和血缘信息。
从页面详情中拿到 cdId 后,可继续执行:

```bash
guancli card get <cd_id>
guancli card preview <cd_id>
```

### 11.4. 卡片操作

查看卡片元信息:

```bash
guancli card get <cd_id>
guancli card get <cd_id> --raw
```

卡片元信息通常包括:

- 卡片所在页面。
- 卡片类型。
- 关联数据集。
- 图表配置。
- 维度、度量、筛选器等配置。
预览卡片数据:

```bash
guancli card preview <cd_id>
guancli card preview <cd_id> --limit 20
guancli card preview <cd_id> --limit 1000
guancli card preview <cd_id> -f table
guancli card preview <cd_id> -f json
guancli card preview <cd_id> -f expanded
```

卡片预览的行数规则:

- 不指定 --limit 时,默认返回 50 行。
- 可通过 --limit <行数 > 指定希望返回的行数,例如 --limit 20 或 --limit 1000。
- 当前最多返回 1,000 行;即使指定更大 的 --limit,实际返回行数也不会超过该上限。
卡片筛选:

```bash
guancli card preview <cd_id> --filter "城市 EQ 上海 "
guancli card preview <cd_id> --filter "年龄 GT 18" --filter "渠道 IN 线上,门 店"
guancli card preview <cd_id> --filter "日期 toMonth EQ 2026-01"
```

排序、列选择和数值精度:

```bash
guancli card preview <cd_id> --sort-desc 销售额
guancli card preview <cd_id> --columns "城市,销售额 "
guancli card preview <cd_id> --precision 4
guancli card preview <cd_id> --precision -1
```

卡片排序在 CLI 端对已返回数据执行,可能受 --limit 影响。需要完整排序时建议适当增大 --limit。

### 11.5. 表单填报操作

表单命令支持查询表单结构、查询数据、插入数据、更新数据和删除数据。操作字段时使用“字段名 称”,CLI 内部会映射为字段 ID。 列出表单:

```bash
guancli form list
guancli form list 客户
guancli form list --tree
```

查看表单结构:

```bash
guancli form schema <fmId>
guancli form schema <fmId> -f json
```

结构中通常包括:

- 字段 ID。
- 字段名称。
- 字段类型。
- 是否必填。
- 是否可编辑。
- 选项值。
- 子表字段对应的 subFmId。
查询表单数据:

```bash
guancli form query <fmId>
guancli form query <fmId> --limit 100 --offset 0
guancli form query <fmId> --filter "姓名 EQ 张三 "
guancli form query <fmId> --filter "状态 CONTAINS 待处理 "
guancli form query <fmId> --sort-asc 创建时间
guancli form query <fmId> --sort-desc 金额
guancli form query <fmId> --columns "姓名,状态,金额 "
```

建议获取完整 rowId 时使用 JSON 或竖排格式:

```bash
guancli form query <fmId> -f json
guancli form query <fmId> -f expandedrowId 是更新和删除表单行时必须使用的行 ID。默认表格输出中较长的 rowId 可能被截断。
```

插入表单数据:

```bash
guancli form add <fmId> --data '{"姓名 ":"张三 ","金额 ":42}'
guancli form add <fmId> --set "姓名=张三 " --set "金额=42"
```

批量插入:

```bash
echo '[{"姓名 ":"张三 "},{"姓名 ":"李四 "}]' | guancli form add <fmId> --stdin
```

更新表单数据:

```bash
guancli form update <fmId> <rowId> --set "状态=已处理 "
guancli form update <fmId> <rowId> --data '{"状态 ":"已处理 ","金额 ":99}'
```

删除表单数据:

```bash
guancli form delete <fmId> <rowId>
guancli form delete <fmId> <rowId1> <rowId2>
guancli form delete <fmId> --all --yes
```

删除操作不可轻易恢复,请先确认表单和 r ow Id。 子表操作:

```bash
guancli form schema <mainFmId>
guancli form schema <subFmId>
guancli form query <subFmId>
guancli form add <subFmId> --parent-row <mainRowId> --set "明细字段=值"
guancli form update <subFmId> <subId> --set "明细字段=新值 "
guancli form delete <subFmId> <subId>
```

子表插入会读取并保留已有子表行后再提交,适合低并发维护场景,不建议多个用户同时对同一主表行 做子表写入。

### 11.6. 任务排查

任务命令用于查看运行中任务、历史任务、任务详情和任务日志明细。 查看运行中任务:

```bash
guancli task running
```

查询历史任务:

```bash
guancli task history
guancli task history --status Failed
guancli task history --task-types ETL_COMBINED
guancli task history --object-name-like 销售
guancli task history --user-name-like 张三
```

按时间范围筛选:

```bash
guancli task history \
--start-time "2026-03-30 10:00:00" \
--end-time "2026-03-30 12:00:00"
```

组合示例:

```bash
guancli task history \
--status Failed \
--task-types ETL_COMBINED \
--object-name-like 销售
```

查看任务概要和详细日志:

```bash
guancli task get <task_id>
guancli task detail <task_id>
guancli task detail <task_id> --offset 0 --limit 200
```

### 11.7. 指标操作

指标命令用于搜索指标、查看指标口径、查询指标数据和查看指标目录。

```bash
guancli metric tree
guancli metric search 销售额
guancli metric search 销售额 --dir-id <topic_id>
guancli metric get <metric_id>
guancli metric get <metric_id> --brief
```

指标详情通常包括:

- 指标名称、I D、状态、类型。
- 业务口径。
- 计算逻辑。
- 数据来源。
- 可用维度。
- 时间维度。
- 默认筛选。
- 管理信息和血缘引用。
查询指标数据:

```bash
guancli metric query <metric_id>
guancli metric query <metric_id> --dim 日期 --dim 渠道
guancli metric query <metric_id> --limit 20
guancli metric query <metric_id> --filter "渠道 EQ 线上 "
guancli metric query <metric_id> --sort-desc 销售额
guancli metric query <metric_id> --columns "日期,渠道,销售额 "
guancli metric query <metric_id> --precision 4
```

### 11.8. 指标归因操作

指标归因命令用于搜索指标树、查看指标树详情,并基于指标树做指标拆解或维度归因。 命令名为:

```bash
guancli metric_attribution ...
```

查看指标树目录、搜索和详情:

```bash
guancli metric_attribution tree
guancli metric_attribution search 销售
guancli metric_attribution get <metric_tree_id>
```

执行指标拆解:

```bash
guancli metric_attribution query <metric_tree_id> --target index
guancli metric_attribution query <metric_tree_id> --target index --limit 5
```

执行单维度归因:

```bash
guancli metric_attribution query <metric_tree_id> --target dim --dim 渠道
guancli metric_attribution query <metric_tree_id> \
--target dim \
--dim 城市 \
--limit 10
```

执行多维度扫描:

```bash
guancli metric_attribution query <metric_tree_id> --target scan
guancli metric_attribution query <metric_tree_id> \
--target scan \
--scan-dim 渠道 \
--scan-dim 城市
```

排除维度:

```bash
guancli metric_attribution query <metric_tree_id> \
--target scan \
--exclude-dim 门店 \
--group-limit 3
```

时间对比和筛选:

```bash
guancli metric_attribution query <metric_tree_id> \
--target dim \
--dim 渠道 \
--period 2026-04-01 \
--last-period 2026-03-01
guancli metric_attribution query <metric_tree_id> \
--target dim \
--dim 渠道 \
--filter "区域 EQ 华东 "
```

使用原始时间对比 JSON:

```bash
guancli metric_attribution query <metric_tree_id> \
--target dim \
--dim 渠道 \
--time-comparison-json '{"advType":"...","advValue":{}}'
```

### 11.9. ChatBI 问数与洞察

ChatBI 命令复用当前 guancli 登录环境,不需要单独配置 ChatBI URL 或额外 Token。 查看可用主题:

```bash
guancli chatbi list-theme
guancli chatbi list-theme --insight
```

主题问数:

```bash
guancli chatbi query \
--theme-name "经营主题 " \
--message "最近 30 天营业收入是多少? "
```

按主题 ID:

```bash
guancli chatbi query \
--theme-id <theme_id> \
--message "最近 30 天营业收入是多少? "
```

继续同一会话:

```bash
guancli chatbi query \
--theme-name "经营主题 " \
--session-id <session_id> \
--message "按城市拆分一下 "
```

添加外部上下文:

```bash
guancli chatbi query \
--theme-name "经营主题 " \
--message "分析本月收入 " \
--external-context "重点关注华东区域 "
```

洞察分析:

```bash
guancli chatbi insight \
--theme-name "经营主题 " \
--message "分析最近 30 天营业收入变化原因 "
```

指定智能体模式:

```bash
guancli chatbi insight \
--theme-id <theme_id> \
--message "分析最近 30 天营业收入变化原因 " \
--agent-mode single_agent
```

指定分析专家:

```bash
guancli chatbi insight \
--theme-name "经营主题 " \
--analysis-expert-id <expert_id> \
--message "分析收入波动原因 "
```

调整轮询间隔和超时:

```bash
guancli chatbi insight \
--theme-name "经营主题 " \
--message "分析最近 30 天营业收入变化原因 " \
--poll-interval-ms 2000 \
--timeout-ms 300000
```

### 11.10. 通用 API 调用

fetch 命令用于调用当前 BI 环境下的接口。它会自动带上当前 p rofile 的认证信息。 G ET 请求:

```bash
guancli fetch GET /api/health
```

POST 请求:

```bash
guancli fetch POST /api/example '{"name":"test"}'
```

从 stdin 读取请求体:

```bash
type body.json | guancli fetch POST /api/example --stdinmacOS / Linux:
```

```bash
cat body.json | guancli fetch POST /api/example --stdin
```

上传文件:

```bash
guancli fetch POST /api/upload --upload file=C:\path\to\data.csv
```

多个文件或字段:

```bash
guancli fetch POST /api/upload \
--upload file=C:\path\to\data.csv \
--field name=test \
--field type=csv
```

附加请求头:

```bash
guancli fetch GET /api/example --header "X-Trace-Id=demo"
```

### 11.11. SuperApp 项目创建

guancli app create 用于快速创建 SuperApp 模板项目。

```bash
guancli app create --name my-app --path ~/workspace
```

参数:

**参数 说明**

--name 项目名称 --path 项目所在目录 创建过程中会尝试:

- 下载模板项目。
- 创建项目目录。
- 复制 .env.template 为 .env。
- 更新 package.json 中的项目名称。
- 初始化 G it 仓库。
- 如存在 setup.sh,执行初始化脚本。
- 如不存在 setup.sh,尝试执行 npm install 并启动开发服务。
- 从 8000 到 8009 检测可用端口。

## 12. 输出、导出与脚本处理建议

### 12.1. 给人阅读

默认使用:

```bash
guancli ds preview <ds_id>
```

宽表建议:

```bash
guancli ds preview <ds_id> -f expanded
```

### 12.2. 导出给 Excel

```bash
guancli ds preview <ds_id> -f csv > data.csv
```

Windows PowerShell 如遇到编码问题, 可优先使用 JSON 输出,或使用支持 UTF-8 的终端。

### 12.3. 给脚本处理

```bash
guancli ds preview <ds_id> -f json
guancli card preview <cd_id> -f json
guancli form query <fmId> -f json
```

### 12.4. 排查接口问题

```bash
guancli ds get <ds_id> --raw
guancli card get <cd_id> --raw
guancli fetch GET /api/health --raw
```

## 13. 常见问题排查

### 13.1. 提示未登录或认证失败

先查看状态:

```bash
guancli auth status
```

重新登录:

```bash
guancli auth login
```

如果使用多环境,确认当前环境:

```bash
guancli auth list
guancli auth use <profile_name>
```

### 13.2. Token 过期

如果使用用户名密码登录,并保存了密码,工具会尝试自动重新登录。 如果使用 Token 登录,或没有保存密码,需要重新执行:

```bash
guancli auth login
```

### 13.3. 找不到资源

建议按以下顺序排查:

1. 确认当前 profile 是否连接到正确 BI 环境。
2. 用 tree 查看目录中是否存在该资源。
3. 用 search 搜索关键字。
4. 确认当前账号是否有权限访问该资源。
5. 如果知道 ID,优先使用 get <id> 或对应的 --id 精确查询。
### 13.4. 预览数据为空

可能原因:

- 数据集或卡片本身没有数据。
- 筛选条件过严。
- 字段名填写不正确。
- 当前账号没有数据权限。
- 卡片配置依赖页面筛选器,直接预览时上下文不同。
建议:

```bash
guancli ds get <ds_id>
guancli ds preview <ds_id> --limit 20 --raw
guancli card get <cd_id>
guancli card preview <cd_id> --raw
```

### 13.5. 筛选条件报错

检查格式是否为:

```text
"字段名 操作符 值"
```

常见错误:

- 操作符拼写错误。
- IN 或 BT 的多个值没有使用英文逗号。
- 字段名与实际字段不一致。
- 日期粒度值格式不正确。
### 13.6. 表单更新或删除失败

确认使用的是完整 rowId:

```bash
guancli form query <fmId> -f json
```

如果是子表,更新和删除时应使用 subId,不是主表 rowId。

### 13.7. ChatBI 没有返回结果

建议: 1.先执行 guancli chatbi list-theme 确认主题存在。 2.确认主题名称完全一致,或改用 --theme-id。 3.增加超时时间:

```bash
guancli chatbi insight \
--theme-name "经营主题 " \
--message "分析收入变化原因 " \
--timeout-ms 600000
```

### 13.8. 命令输出太长

使用精简模式:

```bash
guancli ds get <ds_id> --brief
guancli etl get <etl_id> --brief
```

只查看指定列:

```bash
guancli ds preview <ds_id> --columns "日期,城市,销售额 "
```

限制行数:

```bash
guancli ds preview <ds_id> --limit 20
```

需要查看接口原始返回:

```bash
guancli ds get <ds_id> --raw
```

## 14. 命令速查

### 14.1. 认证

```bash
guancli auth login
guancli auth login --profile prod --url https://bi.example.com --domain demo --login-id user@example.com --password xxx
guancli auth list
guancli auth status
guancli auth whoami
guancli auth use prod
guancli auth remove prod
guancli auth modify prod --password xxx --relogin
guancli auth detect-domain --url https://bi.example.com
guancli version
```

### 14.2. ETL

```bash
guancli etl tree
guancli etl search 销售
guancli etl search 销售 --dir-id <dir_id>
guancli etl get <etl_id>
guancli etl preview <etl_id> <node_id>
```

### 14.3. 数据集

```bash
guancli ds tree
guancli ds search 销售
guancli ds search --id <ds_id>
guancli ds get <ds_id>
guancli ds get <ds_id> --brief
guancli ds get <ds_id> --assoc
guancli ds preview <ds_id> --limit 20
```

### 14.4. 页面和卡片

```bash
guancli page tree
guancli page search 看板
guancli page get <page_id>
guancli card get <cd_id>
guancli card preview <cd_id> --limit 20
```

### 14.5. 表单

```bash
guancli form list
guancli form schema <fmId>
guancli form query <fmId> -f json
guancli form add <fmId> --set "字段=值"
guancli form update <fmId> <rowId> --set "字段=新值 "
guancli form delete <fmId> <rowId>
```

### 14.6. 任务

```bash
guancli task running
guancli task history --status Failed
guancli task get <task_id>
guancli task detail <task_id>
```

### 14.7. 指标

```bash
guancli metric tree
guancli metric search 销售额
guancli metric get <metric_id>
guancli metric query <metric_id> --dim 日期 --limit 20
```

### 14.8. 指标归因

```bash
guancli metric_attribution tree
guancli metric_attribution search 销售
guancli metric_attribution get <metric_tree_id>
guancli metric_attribution query <metric_tree_id> --target index
guancli metric_attribution query <metric_tree_id> --target dim --dim 渠道
guancli metric_attribution query <metric_tree_id> --target scan
```

### 14.9. ChatBI

```bash
guancli chatbi list-theme
guancli chatbi list-theme --insight
guancli chatbi query --theme-name "经营主题 " --message "最近 30 天营业收入是多少? "
guancli chatbi insight --theme-name "经营主题 " --message "分析最近 30 天营业收入变化原因 "
```

### 14.10. 通用 API 和 SuperApp

```bash
guancli fetch GET /api/health
guancli fetch POST /api/example '{"name":"test"}'
guancli app create --name my-app --path ~/workspace
```
