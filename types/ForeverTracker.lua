---@meta

-- The tracker contract's classes, declared once here for core's own UI/Tracker*.lua files.

---@class ForeverTrackerSettings
---@field attached boolean the column follows the native quest tracker
---@field locked? boolean the Lock switch, which suppresses the grip's drag
---@field scale? number the player's tracker scale, 0.5 to 2; the host reads a missing one as 1
---@field backdropOpacity? number the optional backdrop's opacity, 0 (off) to 1
---@field x? number the detached position, from UIParent's top left corner
---@field y? number
---@field migrated? boolean the one-time copy from a consumer's old tracker settings is done

-- A Forever addon's old tracker table, offered once with its first attached section so its saved scale, lock and
-- position carry over into ForeverCoreDB.
---@class ForeverTrackerLegacySettings
---@field attached? boolean
---@field locked? boolean
---@field scale? number
---@field backdropOpacity? number
---@field x? number
---@field y? number

---@class ForeverTrackerGrip
---@field Show fun(value: boolean) shows or hides the grip, which the host keeps hidden while attached
---@field SetLabel fun(value: boolean) redraws the label from the switch, without waiting for a hover

---@class ForeverTrackerShowSetting
---@field get fun(): boolean whether the section is currently shown
---@field set fun(shown: boolean) the addon's own switch, which hides the section as its settings checkbox does
---@field where string the place the player turns it back on, in the addon's own words
---@field safeCall? fun(label: string, fn: function, ...: any): boolean, any the addon's SafeCall for its own getter and setter

---@class ForeverTrackerHostAPI
---@field Attach fun(module: ForeverTrackerModule, show?: ForeverTrackerShowSetting, contract?: ForeverTrackerMenuContract) the section's optional show switch and declarative menu
---@field HandleBlockHeaderClick fun(module: ForeverTrackerModule, block: any, button: string): boolean forwards a block title click into the declarative contract
---@field IsAttached fun(module: Frame?): boolean
---@field GetSettings fun(): ForeverTrackerSettings
---@field GetScale fun(): number
---@field SetScale fun(value: number)
---@field GetBackdropOpacity fun(): number
---@field SetBackdropOpacity fun(value: number)
---@field IsLocked fun(): boolean
---@field SetLocked fun(value: boolean)
---@field IsAttachedToQuestTracker fun(): boolean
---@field SetAttached fun(value: boolean)
---@field OnAttachmentChanged fun(callback: fun(attached: boolean))
---@field OnNativeSizeChanged? fun(callback: fun()) runs a callback when the client's own objective tracker changes size, which is how ObjectiveTrackerManager adds its modules
---@field SavePosition fun(x: number, y: number)
---@field Debug fun(): string the tracker stack's anchors, heights and in-combat state, for an addon's debug command

---@class ForeverTrackerTarget
---@field kind "section"|"block"
---@field id? any
---@field block? any
---@field module ForeverTrackerModule

---@class ForeverTrackerMenuBuilder
---@field Title fun(self: ForeverTrackerMenuBuilder, text: string)
---@field Primary fun(self: ForeverTrackerMenuBuilder, text: string, fn: fun())
---@field Action fun(self: ForeverTrackerMenuBuilder, text: string, fn: fun(), opts?: { combat?: boolean }): any
---@field Open fun(self: ForeverTrackerMenuBuilder, text: string, fn: fun(): boolean?, string?): any invokes a callback that may return false and a visible refusal reason
---@field End fun(self: ForeverTrackerMenuBuilder, text: string, fn: fun()): any
---@field Submenu fun(self: ForeverTrackerMenuBuilder, text: string): ForeverMenuDescription

---@class ForeverTrackerMenuContract
---@field menu fun(target: ForeverTrackerTarget, menu: ForeverTrackerMenuBuilder)
---@field click? fun(target: ForeverTrackerTarget, button: string): boolean?, string? returns false and a reason when the action cannot run
---@field clickHint? fun(target: ForeverTrackerTarget): string? the localized action name shown in the block tooltip

---@class ForeverTrackerOrderAPI
---@field Sort fun(modules: ForeverTrackerModule[]) orders the shared column's sections in place

-- Reopened here for the one field core's own host reads from the section it is handed.
---@class ForeverTrackerModule : Frame
---@field trackerClickHint? fun(target: ForeverTrackerTarget): string? the localized click action
---@field legacySettings? ForeverTrackerLegacySettings the addon's old tracker table, copied once by the host
---@field safeCall? fun(label: string, fn: function, ...: any): boolean, any the addon's SafeCall for its own menu entries
---@field CanUpdate? fun(self: ForeverTrackerModule): boolean whether a refresh may lay the section out now
---@field OnHeaderClick? fun(self: ForeverTrackerModule, button: string) a header click other than the host's right-click menu
---@field OnBlockHeaderEnter? fun(self: ForeverTrackerModule, block: any) a block header's hover
---@field OnBlockHeaderLeave? fun(self: ForeverTrackerModule, block: any)
---@field MarkDirty? fun(self: ForeverTrackerModule) asks the host for one layout on the next frame
---@field SetHeader? fun(self: ForeverTrackerModule, text: string) sets the section's header text
---@field lineTemplate? string the template its objective lines acquire
---@field GetExistingBlock? fun(self: ForeverTrackerModule, key: any): any a block already built, never a new one
---@field GetNextBlockAnchoring? fun(self: ForeverTrackerModule): number, number where the next block would anchor
---@field availableHeight? number the room this layout pass gave the section
---@field contentsHeight? number what the section drew in this pass
---@field trackerMaxHeight? number|"remaining" the section's own height cap
---@field trackerScrollable? boolean Blizzard's module model, so the shared scroll wrapper applies
---@field scrollFrame? ScrollFrame
---@field scrollBar? any
---@field scrollOffset? number
---@field scrollRange? number
---@field scrollContentsWidth? number the width the scroll child was last measured at
---@field trackerViewport? number
---@field trackerBody? number
---@field trackerOverflow? boolean
---@field trackerCap? number
---@field SetScrollFrozen? fun(self: ForeverTrackerModule, frozen: boolean)
---@field OnScrollChanged? fun(self: ForeverTrackerModule) the section's own refresh after a scroll or layout
---@field ContentsFrame? Frame Blizzard's module model holds its blocks here
---@field headerHeight? number Blizzard's module header height
---@field firstBlock? any the first block in the module's block chain
---@field Update? fun(self: ForeverTrackerModule, availableHeight: number, dirtyUpdate?: boolean)
---@field UpdateHeight? fun(self: ForeverTrackerModule)
---@field GetContentsHeight? fun(self: ForeverTrackerModule): number
---@field CanFitBlock? fun(self: ForeverTrackerModule, block: any): boolean
---@field BeginLayout? fun(self: ForeverTrackerModule)
---@field IsTruncated? fun(self: ForeverTrackerModule): boolean
---@field IsCollapsed? fun(self: ForeverTrackerModule): boolean
---@field baseUpdate? any the module's own Update before the shared wrapper
---@field baseUpdateHeight? any
---@field baseGetContentsHeight? any
---@field baseIsTruncated? any
---@field baseCanFitBlock? any
---@field baseBeginLayout? any

-- UI/TrackerSection.lua, the section plumbing every addon's tracker shares.
---@class ForeverTrackerSectionOptions
---@field order? number the section's place among the column's sections
---@field lineTemplate? string the template its objective lines acquire
---@field header? string the header text set after the mixin
---@field maxHeight? number|"remaining" the section's own height cap: a number of UI units (200 when omitted), or "remaining" for what the column's other sections leave
---@field show? ForeverTrackerShowSetting the section's own show switch, offered as Hide this section
---@field legacy? table|fun(): table? the saved table holding the addon's old tracker table
---@field legacyKey? string the key in `legacy` holding the old tracker table, cleared after it is offered
---@field safeCall? fun(label: string, fn: function, ...: any): boolean, any the addon's SafeCall for this section
---@field contract? ForeverTrackerMenuContract the declarative section menu and click behavior
---@field onUnattached? fun(module: ForeverTrackerModule) called when the section is still not attached after a few seconds

---@class ForeverTrackerTextRow
---@field key any the objective key the line was added under
---@field text string the new line text
---@field color? any the line's colour table, Normal when absent

---@class ForeverTrackerTextBlock
---@field key any the block key
---@field title? string the block header's new text
---@field rows? ForeverTrackerTextRow[]

---@class ForeverTrackerInteractiveSpec
---@field onClick? fun(line: Frame, button: string) a left click on the line
---@field tooltip? fun(line: Frame) draws the line's tooltip; the helper hides it on leave

---@class ForeverTrackerHeaderTooltip
---@field title string the tooltip's title
---@field lines? string[] normal lines under the title

---@class ForeverTrackerLineAPI
---@field SetInteractive fun(line: Frame, spec: ForeverTrackerInteractiveSpec)
---@field SetHeaderTooltip fun(module: ForeverTrackerModule, tip: ForeverTrackerHeaderTooltip|fun(block: any): ForeverTrackerHeaderTooltip?)

---@class ForeverTrackerSectionAPI
---@field Create fun(name: string, mixin?: table, opts?: ForeverTrackerSectionOptions): ForeverTrackerModule?
---@field UpdateText fun(module: ForeverTrackerModule, blocks: ForeverTrackerTextBlock[]): boolean
---@field Room fun(module: ForeverTrackerModule, block: any): number
---@field AddMore fun(block: any, key: any, count: integer): any

---@class ForeverTrackerLock
---@field Locked fun(): boolean reads the saved switch through the host
---@field Grip fun(host: Frame, source: ForeverTrackerHostAPI): ForeverTrackerGrip draws the grip on the column it drags

---@class ForeverTrackerNamespace
---@field NewMenuDescription fun(kind: ForeverMenuEntryKind, text?: string): ForeverMenuDescription
---@field TrackerHost? ForeverTrackerHostAPI
---@field TrackerSection? ForeverTrackerSectionAPI
---@field TrackerLine? ForeverTrackerLineAPI
---@field TrackerHostForeign? boolean true when a vendored host loaded first and core forwarded to it
---@field TrackerLock? ForeverTrackerLock
---@field TrackerOrder? ForeverTrackerOrderAPI
---@field TrackerQuestie? ForeverTrackerQuestie
---@field TrackerEllesmere? ForeverTrackerEllesmere
---@field TrackerEqot? ForeverTrackerEqot
---@field TrackerHostSettings? fun(): ForeverTrackerSettings
---@field AttachCoreDb? fun()
---@field MigrateTrackerSettings? fun()
---@field L table<string, string>
---@field SafeCall? fun(label: string, fn: function, ...: any): boolean, ...any
---@field SafeCallFor? fun(name: string): ForeverSafeCallContext
---@field LogFor? fun(name: string): ForeverDebugLogContext
---@field ReportFor? fun(name: string, spec?: ForeverReportSpec): ForeverReportModule
---@field MapCanvasFor? fun(name: string): ForeverCanvasAPI
---@field ReportLines? fun(): string[]
