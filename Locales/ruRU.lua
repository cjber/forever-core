-- Machine translated (2026-10-22); corrections welcome: https://github.com/cjber/forever-core/issues/new?template=translation.yml
local _, ns = ...
if GetLocale() ~= "ruRU" then
	return
end
local L = ns.L

L["%s (%s)"] = "%s (%s)"
L["%s and %s"] = "%s и %s"
L["%s, %s and %s"] = "%s, %s и %s"
L["%s, %s, %s and %d more"] = "%s, %s, %s и ещё %d"
L["+%d more"] = "+%d ещё"
L["%d contributions"] = "вкладов: %d" -- mt
L[", "] = ", "
L["%s (last %d):"] = "%s (последние %d):"
L["%s: no lines yet."] = "%s: строк пока нет."
L["All addons"] = "Все аддоны"
L["Bug"] = "Ошибка"
L["Bug: "] = "Ошибка: "
L["Close"] = "Закрыть"
L["Copy issue link"] = "Скопировать ссылку на issue"
L["Copy report"] = "Скопировать отчет"
L["Debug log is already on and pinned for this character."] =
	"Журнал отладки уже включён и закреплён для этого персонажа."
L["Debug log is off and unpinned."] = "Журнал отладки выключен, закрепление снято."
L["Debug log is off for this session; it is still pinned."] =
	"Журнал отладки выключен для этого сеанса; закрепление сохранено."
L["Debug log is off."] = "Журнал отладки выключен."
L["Debug log is on and pinned for this character."] =
	"Журнал отладки включён и закреплён для этого персонажа."
L["Debug log is on for this session."] = "Журнал отладки включён для этого сеанса."
L["Feature request"] = "Предложение функции"
L["Feature request: "] = "Предложение функции: "
L["ForeverCore"] = "ForeverCore"
L["Forever addons"] = "Модификации Forever"
L["Hide this section"] = "Hide this section"
L["Inspired by"] = "Вдохновили"
L["Lock the tracker"] = "Закрепить трекер"
L["No addon has attached its log yet."] =
	"Ни один аддон ещё не подключил свой журнал."
L["No one is listed yet."] = "Пока никого нет в списке."
L["On"] = "Вкл."
L["Players"] = "Игроки"
L["Report a bug or request a feature"] = "Сообщить об ошибке или предложить функцию"
L["Thanks"] = "Спасибо"
L["Thanks to %s"] = "Спасибо %s"
L["The link is selected. Press Ctrl+C (Cmd+C on a Mac), then paste into a browser; GitHub opens a filled-in issue."] =
	"Ссылка выделена. Нажмите Ctrl+C (Cmd+C на Mac) и вставьте ее в браузер; GitHub откроет заполненную задачу."
L["The players who helped each Forever addon."] =
	"Игроки, которые помогли каждому аддону Forever."
L["The text is selected. Press Ctrl+C (Cmd+C on a Mac) to copy it, then paste it into your bug report."] =
	"Текст выделен. Нажмите Ctrl+C (Cmd+C на Mac), чтобы скопировать его, затем вставьте в сообщение об ошибке."
L["Title"] = "Заголовок"
L["Tracker background"] = "Фон отслеживания"
L["Tracker position"] = "Положение отслеживания"
L["Under the quest tracker"] = "Под списком заданий"
L["Left of the quest tracker"] = "Слева от списка заданий"
L["Attach to quest tracker"] = "Прикрепить к списку заданий" -- mt
L["The shared Forever tracker sits under the quest tracker when this is on, and left of it when it is off. Every Forever addon shows this same setting."] =
	"Когда включено, общий трекер Forever стоит под списком заданий, а когда выключено, слева от него. Эта настройка одна для всех аддонов Forever." -- mt
L["Tracker"] = "Отслеживание"
L["Click to %s"] = "Нажмите, чтобы %s"
L["Right-click for options"] =
	"Щёлкните правой кнопкой мыши для просмотра параметров"
L["Unavailable in combat"] = "Недоступно в бою"
L["Usage: /forever debug, /forever debug on, /forever debug off, /forever debug pin, /forever debug show"] =
	"Использование: /forever debug, /forever debug on, /forever debug off, /forever debug pin, /forever debug show"
L["What happened, or what you would like"] =
	"Что произошло или что вы хотели бы видеть"

L["1 ms"] = "1 мс"
L["5 ms"] = "5 мс"
L["10 ms"] = "10 мс"
L["50 ms"] = "50 мс"
L["100 ms"] = "100 мс"
L["Addon"] = "Аддон"
L["Application"] = "Приложение"
L["Last"] = "Последняя"
L["Memory KB"] = "Память КБ"
L["Memory: not available on this client."] = "Память: недоступна в этом клиенте."
L["Peak"] = "Пик"
L["Recent"] = "Недавняя"
L["Session"] = "Сессия"
L["Performance (read when this window opened):"] =
	"Производительность (прочитано при открытии окна):"
L["Performance: not available on this client."] =
	"Производительность: недоступна в этом клиенте."
L["Performance: the client's add-on profiler is off."] =
	"Производительность: профилировщик аддонов клиента выключен."
L["%d more rows not shown."] = "Не показано строк: %d."
L["Debug capture is on: /forever debug off stops it."] =
	"Запись отладки включена: /forever debug off её выключает."
L["Debug capture is on. Attach the files in the client's Logs folder to your report. Turn it off with /forever debug off."] =
	"Запись отладки включена. Приложите к отчёту файлы из папки Logs клиента. Отключите её командой /forever debug off."
L["Debug capture is on. The client's logs are in its Logs folder; turn it off with /forever debug off."] =
	"Запись отладки включена. Журналы клиента находятся в папке Logs; отключите её командой /forever debug off."
L["Debug capture is off and the client's settings are back; the debug log is off and unpinned."] =
	"Запись отладки выключена, настройки клиента восстановлены; журнал отладки выключен и откреплён."
L["Debug capture could not start because ForeverCore has not finished loading."] =
	"Не удалось запустить запись отладки: ForeverCore ещё не загрузился."
L["%s: the installed ForeverCore is another addon (%s). Remove it and install ForeverCore from CurseForge."] =
	"%s: установленный ForeverCore является другим аддоном (%s). Удалите его и установите ForeverCore с CurseForge." -- mt
L["%s needs ForeverCore. Install it from CurseForge, or choose Reinstall on ForeverCore in the CurseForge app."] =
	"%s требует ForeverCore. Установите его с CurseForge или выберите «Переустановить» для ForeverCore в приложении CurseForge." -- mt
L["%s: ForeverCore is turned off. Enable it in the AddOns list to fix this."] =
	"%s: ForeverCore отключён. Включите его в списке аддонов, чтобы исправить это." -- mt
L["Quests"] = "Задания"

L["ForeverCore startup report"] = "Отчёт о запуске ForeverCore" -- mt
L["Core: %s; API %s"] = "Core: %s; API %s" -- mt
L["Runtime: %s copy %s"] = "Среда: %s, копия %s" -- mt
L["Runtime error: %s"] = "Ошибка среды: %s" -- mt
L["Standalone runtime"] = "Самостоятельная среда" -- mt
L["Core copies:"] = "Копии Core:" -- mt
L["Rejected"] = "Отклонена" -- mt
L["Sealed"] = "Завершена" -- mt
L["Unsealed"] = "Не завершена" -- mt
L["%s: build %s, %s"] = "%s: сборка %s, %s" -- mt
L['No installed Forever addon named "%s".'] =
	'Установленный аддон Forever с именем "%s" не найден.' -- mt
L["No installed Forever addons found."] = "Установленные аддоны Forever не найдены." -- mt
L["Enable ForeverCore or a Forever addon in AddOns if /fcore is unavailable, then /reload and read Lua errors."] =
	"Если команды /fcore нет, откройте AddOns, включите ForeverCore или аддон Forever и прочитайте первую ошибку Lua после /reload." -- mt
L["Installed Forever addons:"] = "Установленные аддоны Forever:" -- mt
L["Registered"] = "Зарегистрирован" -- mt
L["Loaded but not registered"] = "Загружен, но не зарегистрирован" -- mt
L["Not loaded"] = "Не загружен" -- mt
L["Load: %s; enabled: %s; core pin: %s"] = "Загружен: %s; включён: %s; версия Core: %s" -- mt
L["Requires: %s; optional: %s"] = "Требуется: %s; необязательно: %s" -- mt
L["Loadable: %s; reason: %s"] = "Можно загрузить: %s; причина: %s" -- mt
L["First error: %s"] = "Первая ошибка: %s" -- mt
L["No error captured. Use /console scriptErrors 1, then /reload and read the first error naming %s."] =
	"Ошибки не записаны. Включите ошибки Lua командой /console scriptErrors 1, выполните /reload и прочитайте первую ошибку с упоминанием %s." -- mt
L["Callback error: %s"] = "Ошибка обратного вызова: %s" -- mt
L["Login error: %s"] = "Ошибка входа: %s" -- mt
L["Warning: %s"] = "Предупреждение: %s" -- mt
L["Copy %s: %s"] = "Копия %s: %s" -- mt

L["Drag to move the tabs."] = "Перетащите, чтобы переместить вкладки."
L["Reset tab position"] = "Сбросить положение вкладок"
