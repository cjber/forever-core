-- Translated by moshoutegong; lines ending -- mt are machine translated. Corrections welcome: https://github.com/cjber/forever-core/issues/new?template=translation.yml
local _, ns = ...
if GetLocale() ~= "zhCN" then
	return
end
local L = ns.L

L["%s (%s)"] = "%s（%s）"
L["%s and %s"] = "%s 和 %s"
L["%s, %s and %s"] = "%s、%s 和 %s"
L["%s, %s, %s and %d more"] = "%s、%s、%s 以及另外 %d 位"
L["+%d more"] = "还有 %d 个"
L[", "] = "、"
L["%d contributions"] = "%d 项贡献"
L["%d yd"] = "%d 码"
L["%s (last %d):"] = "%s（最近 %d 条）："
L["%s: no lines yet."] = "%s：暂无日志。"
L["Adds a macro window with every macro in one list, a mono editor with live checks, and history."] =
	"在同一窗口列出所有宏，提供等宽字体编辑器、实时检查和编辑历史。"
L["All addons"] = "所有插件"
L["Attach to quest tracker"] = "停靠到任务追踪栏"
L["Bug"] = "错误报告"
L["Bug: "] = "错误报告："
L["Close"] = "关闭"
L["Copy issue link"] = "复制反馈链接"
L["Copy link"] = "复制链接"
L["Copy report"] = "复制报告"
L["Copy the address, then open it in your browser."] = "复制该地址，然后在浏览器中打开。"
L["Debug log is already on and pinned for this character."] = "该角色的调试日志已经开启并固定。"
L["Debug log is off and unpinned."] = "调试日志已关闭并取消固定。"
L["Debug log is off for this session; it is still pinned."] =
	"本次会话已关闭调试日志，但仍保持固定。"
L["Debug log is off."] = "调试日志已关闭。"
L["Debug log is on and pinned for this character."] = "该角色的调试日志已开启并固定。"
L["Debug log is on for this session."] = "本次会话已开启调试日志。"
L["Don't suggest this again"] = "不再推荐"
L["Drag to move"] = "拖动以移动"
L["Feature request"] = "功能建议"
L["Feature request: "] = "功能建议："
L["ForeverCore"] = "ForeverCore"
L["Forever addons"] = "Forever 插件"
L["Forever quest list"] = "Forever 任务列表"
L["Forever tracker"] = "Forever 追踪栏"
L["Hide this section"] = "隐藏此分区"
L["Inspired by"] = "灵感来自"
L["Installed, turned off"] = "已安装，已禁用"
L["Keeps a cosmetic journal of the creatures you kill, zone by zone."] =
	"按区域记录你击杀过的生物，供浏览收藏。"
L["Lists your commission turn-ins, the materials in your bags and the next NPC to visit."] =
	"列出要交付的委托、背包里的材料和下一位要拜访的 NPC。"
L["Lists your tracked quests in the Forever column, ready to turn in first, then this zone, then the rest by zone, nearest first. The game's own objective tracker is hidden while this is on."] =
	"在 Forever 追踪栏中列出已追踪的任务：先列出可交付的任务，再列出当前区域的任务，其余任务按区域由近到远排列。启用后会隐藏游戏自带的目标追踪栏。"
L["Lock the tracker"] = "锁定追踪栏"
L["No addon has attached its log yet."] = "还没有插件附加日志。"
L["No one is listed yet."] = "还没有列出任何人。"
L["Not installed"] = "未安装"
L["On"] = "开启"
L["Open"] = "打开"
L["Picks quests for your level and plans them into one journey."] =
	"推荐适合你等级的任务，并规划成一条路线。"
L["Plans the cheapest route to your next profession rank."] = "规划升到下一专业等级最省钱的路线。"
L["Plans the quickest way anywhere and guides you there, with live boat and zeppelin times."] =
	"规划到目的地的最快路线并提供导航，显示船只和飞艇的实时班次。"
L["Players"] = "玩家"
L["Quest automation, rare alerts and merchant handling for the default UI."] =
	"为游戏原生界面提供任务自动处理、稀有生物提醒和商人交易辅助。"
L["Ready to turn in"] = "可交付"
L["Report a bug or request a feature"] = "报告错误或提交功能建议"
L["Show a quiet line where one of my other Forever addons would help. Only for addons you don't have."] =
	"适当时显示一行提示，推荐尚未安装的其他 Forever 插件。"
L["Shows the Legacy challenges you can advance in each zone."] =
	"显示每个地区中你可以推进的传承挑战。"
L["Suggest my other Forever addons"] = "推荐其他 Forever 插件"
L["Thanks"] = "感谢"
L["Thanks to %s"] = "感谢 %s"
L["The Forever addons are free, with nothing locked behind them. If they help, you can buy me a coffee."] =
	"Forever 插件全部免费，没有任何付费才能使用的内容。如果它们对你有帮助，可以请我喝杯咖啡。"
L["The link is selected. Press Ctrl+C (Cmd+C on a Mac), then paste into a browser; GitHub opens a filled-in issue."] =
	"链接已选中。按 Ctrl+C（Mac 上为 Cmd+C）复制，然后粘贴到浏览器中；GitHub 会打开一个已填写的问题。"
L["The players who helped each Forever addon."] = "帮助过每个 Forever 插件的玩家。"
L["The text is selected. Press Ctrl+C (Cmd+C on a Mac) to copy it, then paste it into your bug report."] =
	"文本已选中。按 Ctrl+C（Mac 上为 Cmd+C）复制，然后粘贴到你的错误报告中。"
L["The tracker is locked. Turn off Lock the tracker to move it."] =
	"追踪栏已锁定。关闭“锁定追踪栏”即可移动它。"
L["This addon"] = "本插件"
L["Title"] = "标题"
L["Tracker background"] = "追踪栏背景"
L["Tracker"] = "追踪栏"
L["Click to %s"] = "点击 %s"
L["Right-click for options"] = "右键查看选项"
L["Unavailable in combat"] = "战斗中不可用"
L["Usage: /forever debug, /forever debug on, /forever debug off, /forever debug pin, /forever debug show"] =
	"用法：/forever debug、/forever debug on、/forever debug off、/forever debug pin、/forever debug show"
L["Turn off the Forever quest list (use the game's tracker)"] =
	"Turn off the Forever quest list (use the game's tracker)"
L["Use the game's tracker"] = "Use the game's tracker"
L["Keep this list"] = "Keep this list"
L["This is the Forever quest list, shown in place of the game's quest tracker. To switch it off later, right-click the Quests header, or untick Forever quest list in Options > AddOns > ForeverCore."] =
	"This is the Forever quest list, shown in place of the game's quest tracker. To switch it off later, right-click the Quests header, or untick Forever quest list in Options > AddOns > ForeverCore."
L["What happened, or what you would like"] = "请描述遇到的问题或希望增加的功能"
L.MINIMAP_UNAVAILABLE = "小地图不可用，已跳过自定义按钮。"
L["MENU_BACK"] = "返回"

L["1 ms"] = "1 毫秒"
L["5 ms"] = "5 毫秒"
L["10 ms"] = "10 毫秒"
L["50 ms"] = "50 毫秒"
L["100 ms"] = "100 毫秒"
L["Addon"] = "插件"
L["Application"] = "客户端"
L["Last"] = "最近一次"
L["Memory KB"] = "内存（KB）"
L["Memory: not available on this client."] = "当前客户端无法读取内存占用。"
L["Peak"] = "峰值"
L["Recent"] = "近期"
L["Session"] = "会话"
L["Performance (read when this window opened):"] = "性能（打开此窗口时读取）："
L["Performance: not available on this client."] = "当前客户端无法读取性能数据。"
L["Performance: the client's add-on profiler is off."] = "性能：客户端的插件性能分析器已关闭。"
L["%d more rows not shown."] = "另有 %d 行未显示。"
L["Debug capture is on: /forever debug off stops it."] = "调试记录已开启：/forever debug off 可将其关闭。"
L["Debug capture is on. Attach the files in the client's Logs folder to your report. Turn it off with /forever debug off."] =
	"调试捕获已开启。请将客户端 Logs 文件夹中的文件附在报告中。使用 /forever debug off 关闭。"
L["Debug capture is on. The client's logs are in its Logs folder; turn it off with /forever debug off."] =
	"调试捕获已开启。客户端日志位于其 Logs 文件夹中；使用 /forever debug off 关闭。"
L["Debug capture is off and the client's settings are back; the debug log is off and unpinned."] =
	"调试捕获已关闭，客户端设置已恢复；调试日志已关闭并取消固定。"
L["Debug capture could not start because ForeverCore has not finished loading."] =
	"无法启动调试捕获，因为 ForeverCore 尚未完成加载。"
L["%s: the installed ForeverCore is another addon (%s). Remove it and install ForeverCore from CurseForge."] =
	"%s：已安装的 ForeverCore 是另一个插件（%s）。请移除它，并从 CurseForge 安装 ForeverCore。"
L["%s needs ForeverCore. Install it from CurseForge, or choose Reinstall on ForeverCore in the CurseForge app."] =
	"%s 需要 ForeverCore。请从 CurseForge 安装它，或在 CurseForge 应用中选择 ForeverCore 的“重新安装”。"
L["%s: ForeverCore is turned off. Enable it in the AddOns list to fix this."] =
	"%s：ForeverCore 已关闭。请在插件列表中启用它。"
L["No Forever addon has recorded anything for this character yet."] =
	"还没有任何 Forever 插件为这个角色记录内容。"
L["The link is selected. Press Ctrl+C (Cmd+C on a Mac), then open it in a browser. Nothing is sent."] =
	"链接已选中。按 Ctrl+C（Mac 上为 Cmd+C），然后在浏览器中打开。不会发送任何内容。"
L["Your Forever profile"] = "你的 Forever 档案"
L["%s (%d)"] = "%s (%d)"
L["%s %d/%d"] = "%s %d/%d"
L["Abandon"] = "放弃"
L["Abandoning a quest is not available."] = "无法放弃任务。"
L["Collapse"] = "折叠"
L["Expand"] = "展开"
L["Focus"] = "重点追踪"
L["Stop focusing"] = "取消重点追踪"
L["Objectives"] = "目标"
L["Open Quest Details"] = "打开任务详情"
L["Hide Quest Details"] = "隐藏任务详情"
L["Open Quest Map"] = "打开任务地图"
L["Quest"] = "任务"
L["Quests"] = "任务"
L["Route with Shortest Path"] = "用 Shortest Path 规划路线"
L["Shortest Path is not loaded."] = "Shortest Path 未加载。"
L["Shortest Path could not plan this route."] = "Shortest Path 无法规划此路线。"
L["There is no map pin for this quest."] = "此任务没有地图标记。"
L["There is no quest link to share."] = "没有可分享的任务链接。"
L["The world map is not available."] = "世界地图不可用。"
L["The quest log is not available."] = "任务日志不可用。"
L["Untrack"] = "取消追踪"
L["Share Quest"] = "分享任务"
L["Share in Chat"] = "在聊天中分享"
L["fold this zone"] = "折叠此区域"
L["unfold this zone"] = "展开此区域"
L["focus this quest"] = "重点追踪此任务"

L["ForeverCore startup report"] = "ForeverCore 启动报告"
L["Core: %s; API %s"] = "核心版本：%s，API：%s"
L["Runtime: %s copy %s"] = "运行时：%s（副本 %s）"
L["Runtime error: %s"] = "运行时错误：%s"
L["Standalone runtime"] = "独立运行时"
L["Core copies:"] = "核心副本列表："
L["Rejected"] = "已拒绝"
L["Sealed"] = "已完整加载"
L["Unsealed"] = "加载不完整"
L["%s: build %s, %s"] = "%s：构建 %s，%s"
L['No installed Forever addon named "%s".'] = "没有名为“%s”的已安装 Forever 插件。"
L["No installed Forever addons found."] = "未找到已安装的 Forever 插件。"
L["Enable ForeverCore or a Forever addon in AddOns if /fcore is unavailable, then /reload and read Lua errors."] =
	"如果 /fcore 不是命令，请打开 AddOns，启用 ForeverCore 或任一 Forever 插件，然后在 /reload 后查看首个 Lua 错误。"
L["Installed Forever addons:"] = "已安装的 Forever 插件："
L["Registered"] = "已注册"
L["Loaded but not registered"] = "已加载但未注册"
L["Not loaded"] = "未加载"
L["Load: %s; enabled: %s; core pin: %s"] = "已加载：%s；已启用：%s；Core 版本：%s"
L["Requires: %s; optional: %s"] = "必需：%s；可选：%s"
L["Loadable: %s; reason: %s"] = "可加载：%s；原因：%s"
L["First error: %s"] = "首个错误：%s"
L["No error captured. Use /console scriptErrors 1, then /reload and read the first error naming %s."] =
	"未记录错误。请用 /console scriptErrors 1 启用 Lua 错误，再执行 /reload，查看首个提到 %s 的错误。"
L["Callback error: %s"] = "回调错误：%s"
L["Login error: %s"] = "登录错误：%s"
L["Copy %s: %s"] = "副本 %s：%s"

L.MINIMAP_DRAG_HINT = "拖动可沿小地图移动按钮。" -- mt
