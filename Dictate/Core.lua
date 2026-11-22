local addonName, ns = ...
local L = ns.L

ns.lang = ns.DetectLanguage("auto")
ns.ApplyBindingNames()

-- Seconds without an answer from the companion before we give up on a dictation.
local COMPANION_TIMEOUT = 10
-- Seconds the hidden receive box keeps the keyboard while waiting for a paste
-- pushed by the companion on its own (receive key).
local RECEIVE_WINDOW = 2
-- Seconds it keeps the keyboard after a dictation key is released.
local DICTATION_WINDOW = 10
-- Holds shorter than this are taps, not dictations (the companion uses 300 ms,
-- ours is lower so that we never ignore a message the companion does send).
local MIN_HOLD = 0.25
local HISTORY_SIZE = 30

local defaults = {
	lang = "auto",
	mode = "popup", -- popup | chatbox | auto
	popupFocus = true,
	countdown = 0,
	voicePrefixes = true,
	center = "default", -- default | cancel
	defaultChannel = "smart", -- smart | last | SAY | PARTY | RAID | GUILD | ...
	menu = {
		SAY = true, YELL = false, PARTY = true, RAID = true, RAID_WARNING = true,
		INSTANCE_CHAT = true, GUILD = true, OFFICER = true, REPLY = true, TARGET = true,
		PUBLIC = false,
	},
	sounds = true,
	receiveKey = "CTRL-SHIFT-F12",
	history = {},
}

ns.defaults = defaults

local function applyDefaults(db, src)
	for k, v in pairs(src) do
		if db[k] == nil then
			db[k] = type(v) == "table" and CopyTable(v) or v
		elseif type(v) == "table" and type(db[k]) == "table" and k ~= "history" then
			applyDefaults(db[k], v)
		end
	end
end

function ns.Print(fmt, ...)
	local msg = select("#", ...) > 0 and fmt:format(...) or fmt
	DEFAULT_CHAT_FRAME:AddMessage("|cff66ccffDictate:|r " .. msg)
end

-- Blizzard font objects switch between the Latin and Cyrillic font by the first
-- letters of a string, so mixed text shows boxes. The Cyrillic Friz Quadrata
-- contains both alphabets; all addon text uses copies of fonts set to it.
local CYRILLIC_FONT = "Fonts\\FRIZQT___CYR.TTF"
local fontCache = {}

function ns.Font(base)
	if not fontCache[base] then
		local source = _G[base] or GameFontNormal
		local font = CreateFont("Dictate_" .. base)
		font:CopyFontObject(source)
		local _, size, flags = source:GetFont()
		font:SetFont(CYRILLIC_FONT, size or 12, flags or "")
		fontCache[base] = font
	end
	return fontCache[base]
end

function ns.CreateText(parent, layer, base)
	local fs = parent:CreateFontString(nil, layer or "OVERLAY")
	fs:SetFontObject(ns.Font(base or "GameFontHighlight"))
	return fs
end

function ns.Debug(fmt, ...)
	if ns.db and ns.db.debug then
		ns.Print("|cff999999[debug]|r " .. fmt, ...)
	end
end

function ns.PlaySound(kind)
	if not ns.db.sounds or not SOUNDKIT then
		return
	end
	local sounds = {
		start = SOUNDKIT.IG_MAINMENU_OPTION_CHECKBOX_ON,
		stop = SOUNDKIT.IG_MAINMENU_OPTION_CHECKBOX_OFF,
		sent = SOUNDKIT.TELL_MESSAGE,
		error = SOUNDKIT.IG_QUEST_LOG_ABANDON_QUEST,
	}
	if sounds[kind] then
		PlaySound(sounds[kind])
	end
end

---------------------------------------------------------------------------
-- Protocol: the companion pastes "##WD#<kind>#<payload>#WD##" (docs/protocol.md)
---------------------------------------------------------------------------

local MARK_START, MARK_END = "##WD#", "#WD##"

-- Returns kind, payload, text before the message, text after it.
function ns.ExtractMessage(text)
	local s = text:find(MARK_START, 1, true)
	if not s then
		return nil
	end
	local e = text:find(MARK_END, s + #MARK_START, true)
	if not e then
		return nil
	end
	local body = text:sub(s + #MARK_START, e - 1)
	local kind, payload = body:match("^([^#]*)#(.*)$")
	return kind or body, payload or "", text:sub(1, s - 1), text:sub(e + #MARK_END)
end

---------------------------------------------------------------------------
-- Dictation state
---------------------------------------------------------------------------

-- ns.pending: the dictation the player is holding or waiting for.
--   action  RADIAL | QUICK | REPLY
--   target  chosen channel (radial or reply), nil = default
--   cancel  drop the text when it arrives
ns.pending = nil

local function finishPending()
	ns.pending = nil
	if ns.timeoutTimer then
		ns.timeoutTimer:Cancel()
		ns.timeoutTimer = nil
	end
end

local function startTimeout()
	if ns.timeoutTimer then
		ns.timeoutTimer:Cancel()
	end
	local pending = ns.pending
	ns.timeoutTimer = C_Timer.NewTimer(COMPANION_TIMEOUT, function()
		ns.timeoutTimer = nil
		if ns.pending == pending then
			ns.pending = nil
			ns.CloseReceiveBox()
			ns.HUD:Flash(L.NO_COMPANION, "error")
		end
	end)
end

function Dictate_Binding(action, keystate)
	ns.Debug("binding %s %s", action, tostring(keystate))
	if action == "SEND" or action == "CANCEL" then
		ns.Popup:HandleBinding(action)
		return
	end
	if keystate == "down" then
		if ns.pending and not ns.pending.released then
			return -- key repeat
		end
		finishPending()
		local pending = { action = action, started = GetTime() }
		ns.pending = pending
		if action == "RADIAL" then
			ns.Radial:Open()
			ns.HUD:ShowRecording(nil, true)
		elseif action == "REPLY" then
			pending.target = ns.Channels.Reply()
			if not pending.target then
				ns.HUD:Flash(L.NO_REPLY, "error")
				pending.cancel = true
			else
				ns.HUD:ShowRecording(pending.target)
			end
		else
			ns.HUD:ShowRecording(ns.Channels.Default())
		end
		ns.PlaySound("start")
	else
		local pending = ns.pending
		if not pending or pending.released or pending.action ~= action then
			return
		end
		pending.released = GetTime()
		if action == "RADIAL" then
			local target, cancel = ns.Radial:Close()
			pending.target = target
			pending.cancel = pending.cancel or cancel
		end
		if pending.released - pending.started < MIN_HOLD then
			finishPending()
			ns.HUD:Hide()
			return
		end
		ns.PlaySound("stop")
		-- Take the keyboard now: the companion pastes the text as soon as it is
		-- recognized. A cancelled dictation still receives it, to drop it.
		ns.OpenReceiveBox(DICTATION_WINDOW)
		if pending.cancel then
			ns.HUD:Flash(L.CANCELLED)
		else
			ns.HUD:ShowStatus(L.TRANSCRIBING)
		end
		startTimeout()
	end
end

local function remember(text, target)
	table.insert(ns.db.history, 1, { text = text, channel = target.key, time = time() })
	while #ns.db.history > HISTORY_SIZE do
		table.remove(ns.db.history)
	end
end

function ns.HandleStatus(status)
	local pending = ns.pending
	finishPending()
	if pending and pending.cancel then
		ns.HUD:Hide()
	elseif status == "empty" then
		ns.HUD:Flash(L.NOTHING_HEARD)
	elseif status == "loading" then
		ns.HUD:Flash(L.LOADING, "error")
	elseif status:sub(1, 6) == "error:" then
		ns.HUD:Flash(L.ERROR:format(status:sub(7)), "error")
		ns.PlaySound("error")
	else
		ns.HUD:Hide()
	end
end

-- A finished dictation that is not typed into an open input line.
function ns.HandleText(text)
	local pending = ns.pending
	finishPending()
	if pending and pending.cancel then
		ns.HUD:Hide()
		return
	end
	local target = pending and pending.target
	if not target and ns.db.voicePrefixes then
		local prefixed, rest = ns.Channels.ParsePrefix(text)
		if prefixed then
			target, text = prefixed, rest
		end
	end
	target = target or ns.Channels.Default()
	if text == "" then
		ns.HUD:Flash(L.NOTHING_HEARD)
		return
	end
	remember(text, target)
	ns.Deliver(target, text)
end

---------------------------------------------------------------------------
-- Delivery
---------------------------------------------------------------------------

-- Chat types that need a key press or click outside instances.
local RESTRICTED = { SAY = true, YELL = true, CHANNEL = true }

function ns.IsRestricted(target)
	if C_ChatInfo and C_ChatInfo.InChatMessagingLockdown and C_ChatInfo.InChatMessagingLockdown() then
		return true
	end
	return RESTRICTED[target.chatType] and not IsInInstance()
end

function ns.Deliver(target, text)
	local mode = ns.db.mode
	if mode == "auto" and ns.IsRestricted(target) then
		mode = "chatbox"
		ns.HUD:Flash(L.BLOCKED_FALLBACK)
	end
	if mode == "chatbox" and #ns.Channels.Split(text) > 1 then
		mode = "popup"
	end
	if mode == "auto" then
		ns.Channels.Send(target, text)
		ns.HUD:Flash(L.SENT .. ": " .. target.label, nil, target)
		ns.PlaySound("sent")
	elseif mode == "chatbox" then
		ns.HUD:Hide()
		ChatFrameUtil.OpenChat(ns.Channels.Slash(target) .. " " .. text)
	else
		ns.HUD:Hide()
		ns.Popup:Open(target, text)
	end
end

---------------------------------------------------------------------------
-- Receiving: the companion presses the receive key, we focus a hidden box,
-- then it pastes the message there.
---------------------------------------------------------------------------

local receiveBox = CreateFrame("EditBox", "DictateReceiveBox", UIParent)
receiveBox:SetSize(1, 1)
receiveBox:SetPoint("TOPLEFT", UIParent, "BOTTOMLEFT", -50, -50)
receiveBox:SetAutoFocus(false)
receiveBox:SetMaxLetters(0)
receiveBox:SetFontObject(ns.Font("GameFontHighlight"))
receiveBox:SetAlpha(0)
receiveBox:Hide()

local receiveSession = 0

local function closeReceiveBox()
	receiveSession = receiveSession + 1
	receiveBox:ClearFocus()
	receiveBox:SetText("")
	receiveBox:Hide()
end
ns.CloseReceiveBox = closeReceiveBox

function ns.OpenReceiveBox(seconds)
	if receiveBox:HasFocus() then
		return
	end
	receiveSession = receiveSession + 1
	local session = receiveSession
	receiveBox:Show()
	receiveBox:SetText("")
	receiveBox:SetFocus()
	ns.Debug("waiting for the companion (%d s)", seconds)
	C_Timer.After(seconds, function()
		if session == receiveSession and receiveBox:HasFocus() then
			ns.Debug("receive box timed out")
			closeReceiveBox()
		end
	end)
end

receiveBox:SetScript("OnTextChanged", function(self)
	if self:GetText() ~= "" then
		ns.Debug("receive box got: %s", self:GetText():gsub("|", "||"))
	end
	local kind, payload = ns.ExtractMessage(self:GetText())
	if not kind then
		return
	end
	closeReceiveBox()
	if kind == "t" then
		ns.HandleText(payload)
	elseif kind == "s" then
		ns.HandleStatus(payload)
	end
end)
receiveBox:SetScript("OnEscapePressed", closeReceiveBox)
receiveBox:SetScript("OnEditFocusLost", function(self)
	self:SetText("")
	self:Hide()
end)

local receiveButton = CreateFrame("Button", "DictateReceiveButton", UIParent)
receiveButton:RegisterForClicks("AnyDown", "AnyUp")
receiveButton:SetScript("OnClick", function(_, _, down)
	ns.Debug("receive key (%s)", down and "down" or "up")
	ns.OpenReceiveBox(RECEIVE_WINDOW)
end)

-- When an input line already has the keyboard (chat or our popup), the receive
-- key does nothing and the paste lands there: replace the message with its text.
function ns.HookInputLine(editBox)
	if not editBox or editBox.dictateHooked then
		return
	end
	editBox.dictateHooked = true
	editBox:HookScript("OnTextChanged", function(self)
		local kind, payload, before, after = ns.ExtractMessage(self:GetText())
		if not kind then
			return
		end
		local pending = ns.pending
		finishPending()
		ns.HUD:Hide()
		if kind ~= "t" or (pending and pending.cancel) then
			payload = ""
		end
		local glue = (before ~= "" and not before:find("%s$") and payload ~= "") and " " or ""
		self:SetText(before .. glue .. payload .. after)
		self:SetCursorPosition(#before + #glue + #payload)
	end)
end

local bindingOwner = CreateFrame("Frame")

function ns.ApplyReceiveKey()
	if InCombatLockdown() then
		ns.needBindings = true
		return false
	end
	ClearOverrideBindings(bindingOwner)
	SetOverrideBindingClick(bindingOwner, true, ns.db.receiveKey, "DictateReceiveButton")
	return true
end

-- First run: put the channel menu on the middle mouse button if it is free.
local function bindDefaults()
	if ns.db.boundDefaults then
		return
	end
	if InCombatLockdown() then
		ns.needBindings = true
		return
	end
	ns.db.boundDefaults = true
	if GetBindingKey("DICTATE_RADIAL") or (GetBindingAction("BUTTON3") or "") ~= "" then
		return
	end
	if SetBinding("BUTTON3", "DICTATE_RADIAL") then
		SaveBindings(GetCurrentBindingSet())
		ns.Print(L.BOUND_DEFAULT)
	end
end

---------------------------------------------------------------------------
-- Slash commands and events
---------------------------------------------------------------------------

SLASH_DICTATE1 = "/dictate"
SLASH_DICTATE2 = "/dict"
SlashCmdList.DICTATE = function(msg)
	local cmd, rest = (msg or ""):match("^%s*(%S*)%s*(.-)%s*$")
	cmd = cmd:lower()
	if cmd == "test" and rest ~= "" then
		ns.HandleText(rest)
	elseif cmd == "receivekey" and rest ~= "" then
		ns.db.receiveKey = rest:upper()
		if ns.ApplyReceiveKey() then
			ns.Print(L.RECEIVE_KEY_SET, ns.db.receiveKey)
		else
			ns.Print(L.RECEIVE_KEY_COMBAT)
		end
	elseif cmd == "debug" then
		ns.db.debug = not ns.db.debug
		ns.Print("debug %s, receive key %s, bound to: %s", ns.db.debug and "on" or "off", ns.db.receiveKey,
			tostring(GetBindingAction(ns.db.receiveKey, true)))
	elseif cmd == "history" then
		if #ns.db.history == 0 then
			ns.Print(L.HISTORY_EMPTY)
		end
		for i = math.min(10, #ns.db.history), 1, -1 do
			local h = ns.db.history[i]
			ns.Print("%s [%s] %s", date("%H:%M", h.time), h.channel, h.text)
		end
	elseif cmd == "help" or cmd == "?" then
		for i, line in ipairs(L.HELP) do
			ns.Print(i == 3 and line:format(ns.db.receiveKey) or line)
		end
	else
		ns.OpenOptions()
	end
end

local events = CreateFrame("Frame")
events:RegisterEvent("ADDON_LOADED")
events:RegisterEvent("PLAYER_LOGIN")
events:RegisterEvent("PLAYER_REGEN_ENABLED")
events:RegisterEvent("ADDON_ACTION_BLOCKED")
events:RegisterEvent("ADDON_ACTION_FORBIDDEN")
events:SetScript("OnEvent", function(_, event, arg1, arg2)
	if (event == "ADDON_ACTION_BLOCKED" or event == "ADDON_ACTION_FORBIDDEN") and arg1 == addonName then
		-- Name the protected function the game refused, so the cause can be found.
		ns.Print("|cffff7070%s|r: %s (%s)", event, tostring(arg2), InCombatLockdown() and "in combat" or "out of combat")
		return
	end
	if event == "ADDON_LOADED" and arg1 == addonName then
		DictateDB = DictateDB or {}
		applyDefaults(DictateDB, defaults)
		ns.db = DictateDB
		ns.lang = ns.DetectLanguage(ns.db.lang)
		ns.ApplyBindingNames()
		ns.InitOptions()
	elseif event == "PLAYER_LOGIN" then
		ns.ApplyReceiveKey()
		bindDefaults()
		for i = 1, NUM_CHAT_WINDOWS or 10 do
			ns.HookInputLine(_G["ChatFrame" .. i .. "EditBox"])
		end
	elseif event == "PLAYER_REGEN_ENABLED" and ns.needBindings then
		ns.needBindings = false
		ns.ApplyReceiveKey()
		bindDefaults()
	end
end)
