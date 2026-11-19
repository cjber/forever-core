-- Machine translated (2026-10-22); corrections welcome: https://github.com/cjber/forever-core/issues/new?template=translation.yml
local _, ns = ...
if GetLocale() ~= "koKR" then
	return
end
local L = ns.L

L["%s (%s)"] = "%s (%s)"
L["%s and %s"] = "%s 및 %s"
L["%s, %s and %s"] = "%s, %s 및 %s"
L["%s, %s, %s and %d more"] = "%s, %s, %s 및 %d명 더"
L["+%d more"] = "+%d개 더"
L["%d contributions"] = "기여 %d건" -- mt
L[", "] = ", "
L["%s (last %d):"] = "%s (최근 %d개):"
L["%s: no lines yet."] = "%s: 아직 줄이 없습니다."
L["All addons"] = "모든 애드온"
L["Bug"] = "오류"
L["Bug: "] = "오류: "
L["Close"] = "닫기"
L["Copy issue link"] = "이슈 링크 복사"
L["Copy report"] = "보고서 복사"
L["Debug log is already on and pinned for this character."] =
	"이 캐릭터에 대해 디버그 기록이 이미 켜져 있고 고정되어 있습니다."
L["Debug log is off and unpinned."] = "디버그 기록이 꺼져 있고 고정이 해제되었습니다."
L["Debug log is off for this session; it is still pinned."] =
	"이 세션 동안 디버그 기록이 꺼져 있지만 여전히 고정되어 있습니다."
L["Debug log is off."] = "디버그 기록이 꺼져 있습니다."
L["Debug log is on and pinned for this character."] =
	"이 캐릭터에 대해 디버그 기록이 켜져 있고 고정되어 있습니다."
L["Debug log is on for this session."] = "이 세션 동안 디버그 기록이 켜져 있습니다."
L["Feature request"] = "기능 요청"
L["Feature request: "] = "기능 요청: "
L["ForeverCore"] = "ForeverCore"
L["Forever addons"] = "Forever 애드온"
L["Hide this section"] = "Hide this section"
L["Inspired by"] = "영감을 준"
L["Lock the tracker"] = "추적기 잠금"
L["No addon has attached its log yet."] = "아직 기록을 첨부한 애드온이 없습니다."
L["No one is listed yet."] = "아직 등록된 사람이 없습니다."
L["On"] = "켬"
L["Players"] = "플레이어"
L["Report a bug or request a feature"] = "오류 보고 또는 기능 요청"
L["Thanks"] = "감사합니다"
L["Thanks to %s"] = "%s 님께 감사드립니다"
L["The link is selected. Press Ctrl+C (Cmd+C on a Mac), then paste into a browser; GitHub opens a filled-in issue."] =
	"링크가 선택되었습니다. Ctrl+C(Mac은 Cmd+C)를 눌러 복사한 후 브라우저에 붙여 넣으십시오. GitHub에 내용이 채워진 이슈가 열립니다."
L["The players who helped each Forever addon."] = "각 Forever 애드온을 도와주신 플레이어들입니다."
L["The text is selected. Press Ctrl+C (Cmd+C on a Mac) to copy it, then paste it into your bug report."] =
	"텍스트가 선택되었습니다. Ctrl+C(Mac은 Cmd+C)를 눌러 복사한 후 오류 보고에 붙여 넣으십시오."
L["Title"] = "제목"
L["Tracker background"] = "추적기 배경"
L["Tracker position"] = "추적기 위치"
L["Under the quest tracker"] = "퀘스트 추적기 아래"
L["Left of the quest tracker"] = "퀘스트 추적기 왼쪽"
L["Attach to quest tracker"] = "퀘스트 추적기에 붙이기" -- mt
L["The shared Forever tracker sits under the quest tracker when this is on, and left of it when it is off. Every Forever addon shows this same setting."] =
	"켜면 공용 Forever 추적기가 퀘스트 추적기 아래에, 끄면 왼쪽에 놓입니다. 모든 Forever 애드온에 같은 설정이 있습니다." -- mt
L["Tracker"] = "추적기"
L["Click to %s"] = "%s하려면 클릭"
L["Right-click for options"] = "우클릭하여 옵션 보기"
L["Unavailable in combat"] = "전투 중에는 사용할 수 없음"
L["Usage: /forever debug, /forever debug on, /forever debug off, /forever debug pin, /forever debug show"] =
	"사용법: /forever debug, /forever debug on, /forever debug off, /forever debug pin, /forever debug show"
L["What happened, or what you would like"] = "무슨 일이 있었는지 또는 원하는 기능"

L["1 ms"] = "1 ms"
L["5 ms"] = "5 ms"
L["10 ms"] = "10 ms"
L["50 ms"] = "50 ms"
L["100 ms"] = "100 ms"
L["Addon"] = "애드온"
L["Application"] = "애플리케이션"
L["Last"] = "마지막"
L["Memory KB"] = "메모리 KB"
L["Memory: not available on this client."] = "메모리: 이 클라이언트에서는 사용할 수 없습니다."
L["Peak"] = "최대"
L["Recent"] = "최근"
L["Session"] = "세션"
L["Performance (read when this window opened):"] = "성능(이 창을 열 때 읽음):"
L["Performance: not available on this client."] = "성능: 이 클라이언트에서는 사용할 수 없습니다."
L["Performance: the client's add-on profiler is off."] =
	"성능: 클라이언트의 애드온 프로파일러가 꺼져 있습니다."
L["%d more rows not shown."] = "표시되지 않은 행 %d개."
L["Debug capture is on: /forever debug off stops it."] =
	"디버그 기록이 켜져 있습니다: /forever debug off로 끕니다."
L["Debug capture is on. Attach the files in the client's Logs folder to your report. Turn it off with /forever debug off."] =
	"디버그 캡처가 켜져 있습니다. 클라이언트의 Logs 폴더에 있는 파일을 보고서에 첨부하세요. /forever debug off로 끌 수 있습니다."
L["Debug capture is on. The client's logs are in its Logs folder; turn it off with /forever debug off."] =
	"디버그 캡처가 켜져 있습니다. 클라이언트의 로그는 Logs 폴더에 있습니다. /forever debug off로 끌 수 있습니다."
L["Debug capture is off and the client's settings are back; the debug log is off and unpinned."] =
	"디버그 캡처가 꺼졌고 클라이언트 설정이 복원되었습니다. 디버그 로그도 꺼졌고 고정이 해제되었습니다."
L["Debug capture could not start because ForeverCore has not finished loading."] =
	"ForeverCore 로드가 끝나지 않아 디버그 캡처를 시작할 수 없습니다."
L["%s: the installed ForeverCore is another addon (%s). Remove it and install ForeverCore from CurseForge."] =
	"%s: 설치된 ForeverCore는 다른 애드온입니다(%s). 해당 애드온을 제거하고 CurseForge에서 ForeverCore를 설치하세요." -- mt
L["%s needs ForeverCore. Install it from CurseForge, or choose Reinstall on ForeverCore in the CurseForge app."] =
	'%s에 ForeverCore가 필요합니다. CurseForge에서 설치하거나 CurseForge 앱에서 ForeverCore의 "다시 설치"를 선택하세요.' -- mt
L["%s: ForeverCore is turned off. Enable it in the AddOns list to fix this."] =
	"%s: ForeverCore가 꺼져 있습니다. 애드온 목록에서 ForeverCore를 활성화하세요." -- mt
L["Quests"] = "퀘스트"

L["ForeverCore startup report"] = "ForeverCore 시작 보고서" -- mt
L["Core: %s; API %s"] = "Core: %s; API %s" -- mt
L["Runtime: %s copy %s"] = "런타임: %s, 사본 %s" -- mt
L["Runtime error: %s"] = "런타임 오류: %s" -- mt
L["Standalone runtime"] = "독립 실행 런타임" -- mt
L["Core copies:"] = "Core 사본:" -- mt
L["Rejected"] = "거부됨" -- mt
L["Sealed"] = "완료됨" -- mt
L["Unsealed"] = "미완료" -- mt
L["%s: build %s, %s"] = "%s: 빌드 %s, %s" -- mt
L['No installed Forever addon named "%s".'] = '"%s" 이름의 설치된 Forever 애드온이 없습니다.' -- mt
L["No installed Forever addons found."] = "설치된 Forever 애드온을 찾을 수 없습니다." -- mt
L["Enable ForeverCore or a Forever addon in AddOns if /fcore is unavailable, then /reload and read Lua errors."] =
	"/fcore 명령이 없으면 AddOns를 열고 ForeverCore 또는 Forever 애드온을 활성화한 뒤 /reload 후 첫 Lua 오류를 확인하세요." -- mt
L["Installed Forever addons:"] = "설치된 Forever 애드온:" -- mt
L["Registered"] = "등록됨" -- mt
L["Loaded but not registered"] = "불러왔으나 등록되지 않음" -- mt
L["Not loaded"] = "불러오지 않음" -- mt
L["Load: %s; enabled: %s; core pin: %s"] = "불러옴: %s; 활성화: %s; Core 버전: %s" -- mt
L["Requires: %s; optional: %s"] = "필수: %s; 선택: %s" -- mt
L["Loadable: %s; reason: %s"] = "불러오기 가능: %s; 사유: %s" -- mt
L["First error: %s"] = "첫 오류: %s" -- mt
L["No error captured. Use /console scriptErrors 1, then /reload and read the first error naming %s."] =
	"기록된 오류가 없습니다. /console scriptErrors 1로 Lua 오류를 켜고 /reload 후 %s을(를) 언급하는 첫 오류를 확인하세요." -- mt
L["Callback error: %s"] = "콜백 오류: %s" -- mt
L["Login error: %s"] = "로그인 오류: %s" -- mt
L["Warning: %s"] = "경고: %s" -- mt
L["Copy %s: %s"] = "사본 %s: %s" -- mt
