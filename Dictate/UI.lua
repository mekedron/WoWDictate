local addonName, ns = ...
local L = ns.L

local BACKDROP = {
	bgFile = "Interface\\Tooltips\\UI-Tooltip-Background",
	edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
	tile = true, tileSize = 16, edgeSize = 14,
	insets = { left = 3, right = 3, top = 3, bottom = 3 },
}

function ns.ApplyBackdrop(frame, alpha)
	frame:SetBackdrop(BACKDROP)
	frame:SetBackdropColor(0.05, 0.05, 0.08, alpha or 0.92)
	frame:SetBackdropBorderColor(0.4, 0.4, 0.45, 1)
end

local function colorize(target)
	if not target then
		return L.DEFAULT
	end
	local c = target.color
	return ("|cff%02x%02x%02x%s|r"):format(c[1] * 255, c[2] * 255, c[3] * 255, target.label)
end
ns.Colorize = colorize

---------------------------------------------------------------------------
-- HUD: recording / recognizing / short messages
---------------------------------------------------------------------------

local HUD = CreateFrame("Frame", "DictateHUD", UIParent, "BackdropTemplate")
ns.HUD = HUD
HUD:SetFrameStrata("FULLSCREEN_DIALOG")
HUD:SetSize(220, 30)
HUD:SetPoint("BOTTOM", UIParent, "BOTTOM", 0, 230)
ns.ApplyBackdrop(HUD, 0.85)
HUD:Hide()

HUD.dot = HUD:CreateTexture(nil, "OVERLAY")
HUD.dot:SetSize(12, 12)
HUD.dot:SetPoint("LEFT", 10, 0)
HUD.dot:SetTexture("Interface\\COMMON\\Indicator-Red")
HUD.dot:SetTexCoord(0.15, 0.85, 0.15, 0.85)

HUD.text = ns.CreateText(HUD, "OVERLAY", "GameFontHighlight")
HUD.text:SetPoint("LEFT", HUD.dot, "RIGHT", 8, 0)

HUD:SetScript("OnUpdate", function(self, elapsed)
	if self.recording then
		self.phase = (self.phase or 0) + elapsed * 4
		self.dot:SetAlpha(0.55 + 0.45 * math.sin(self.phase))
	end
	if self.hideAt and GetTime() >= self.hideAt then
		self.hideAt = nil
		self:Hide()
	end
end)

local function layout(self, text, showDot)
	self.text:SetText(text)
	self.dot:SetShown(showDot)
	self.text:ClearAllPoints()
	if showDot then
		self.text:SetPoint("LEFT", self.dot, "RIGHT", 8, 0)
	else
		self.text:SetPoint("LEFT", 12, 0)
	end
	self:SetWidth(math.max(140, self.text:GetStringWidth() + (showDot and 42 or 24)))
	self:Show()
end

function HUD:ShowRecording(target, radial)
	self.recording, self.hideAt = true, nil
	self.radial = radial
	layout(self, L.RECORDING .. ": " .. colorize(target), true)
end

function HUD:SetTarget(target, cancel)
	if self.recording then
		local label = cancel and ("|cffff5555" .. L.CANCEL .. "|r") or colorize(target)
		layout(self, L.RECORDING .. ": " .. label, true)
	end
end

function HUD:ShowStatus(text)
	self.recording, self.hideAt = false, nil
	self.dot:SetAlpha(1)
	layout(self, text, false)
end

function HUD:Flash(text, kind, target)
	self.recording = false
	if kind == "error" then
		text = "|cffff7070" .. text .. "|r"
	end
	layout(self, text, false)
	self.hideAt = GetTime() + (kind == "error" and 4 or 1.5)
end

local hide = HUD.Hide
function HUD:Hide()
	self.recording, self.hideAt = false, nil
	hide(self)
end

---------------------------------------------------------------------------
-- Confirmation window
---------------------------------------------------------------------------

local Popup = CreateFrame("Frame", "DictatePopup", UIParent, "BackdropTemplate")
ns.Popup = Popup
Popup:SetFrameStrata("DIALOG")
Popup:SetSize(520, 92)
Popup:SetPoint("BOTTOM", UIParent, "BOTTOM", 0, 280)
Popup:SetClampedToScreen(true)
Popup:SetMovable(true)
Popup:EnableMouse(true)
Popup:RegisterForDrag("LeftButton")
Popup:SetScript("OnDragStart", Popup.StartMoving)
Popup:SetScript("OnDragStop", function(self)
	self:StopMovingOrSizing()
	local point, _, relPoint, x, y = self:GetPoint()
	ns.db.popupPos = { point, relPoint, x, y }
end)
ns.ApplyBackdrop(Popup)
Popup:Hide()

Popup.channel = CreateFrame("Button", nil, Popup)
Popup.channel:SetPoint("TOPLEFT", 12, -9)
Popup.channel:SetSize(200, 18)
Popup.channel:RegisterForClicks("LeftButtonUp", "RightButtonUp")
Popup.channel.text = ns.CreateText(Popup.channel, "OVERLAY", "GameFontNormal")
Popup.channel.text:SetPoint("LEFT")
Popup.channel:SetScript("OnClick", function(_, button)
	Popup:CycleChannel(button == "RightButton" and -1 or 1)
end)

Popup.hint = ns.CreateText(Popup, "OVERLAY", "GameFontDisableSmall")
Popup.hint:SetPoint("TOPRIGHT", -12, -12)

Popup.box = CreateFrame("Frame", nil, Popup, "BackdropTemplate")
Popup.box:SetPoint("TOPLEFT", 8, -30)
Popup.box:SetPoint("TOPRIGHT", -8, -30)
Popup.box:SetHeight(26)
ns.ApplyBackdrop(Popup.box, 1)
Popup.box:SetBackdropColor(0, 0, 0, 1)

local edit = CreateFrame("EditBox", "DictatePopupEdit", Popup.box)
Popup.edit = edit
edit:SetPoint("TOPLEFT", 8, -4)
edit:SetPoint("BOTTOMRIGHT", -8, 4)
edit:SetAutoFocus(false)
edit:SetMaxLetters(0)
edit:SetFontObject(ns.Font("ChatFontNormal"))
edit:SetTextInsets(0, 0, 0, 0)

Popup.info = ns.CreateText(Popup, "OVERLAY", "GameFontDisableSmall")
Popup.info:SetPoint("BOTTOMLEFT", 12, 12)

Popup.send = CreateFrame("Button", nil, Popup, "UIPanelButtonTemplate")
Popup.send:SetSize(110, 22)
Popup.send:SetPoint("BOTTOMRIGHT", -10, 8)
Popup.send:SetScript("OnClick", function() Popup:Send() end)

Popup.cancel = CreateFrame("Button", nil, Popup, "UIPanelButtonTemplate")
Popup.cancel:SetSize(90, 22)
Popup.cancel:SetPoint("RIGHT", Popup.send, "LEFT", -6, 0)
Popup.cancel:SetScript("OnClick", function() Popup:Close() end)

function Popup:UpdateInfo()
	local text = self.edit:GetText()
	local parts = #ns.Channels.Split(text)
	local info = ("%d/255"):format(#text)
	if parts > 1 then
		info = info .. ", " .. L.PARTS:format(parts)
	end
	if self.countdownEnd then
		info = info .. "   |cffffd100" .. L.COUNTDOWN:format(math.ceil(self.countdownEnd - GetTime())) .. "|r"
	end
	self.info:SetText(info)
end

function Popup:SetTarget(target)
	self.target = target
	self.channel.text:SetText(colorize(target))
	self.channel:SetWidth(self.channel.text:GetStringWidth() + 4)
	if self.countdownEnd and ns.IsRestricted(target) then
		self.countdownEnd = nil
	end
	self:UpdateInfo()
end

function Popup:CycleChannel(step)
	if self.target then
		self:SetTarget(ns.Channels.Next(self.target, step))
	end
end

function Popup:Open(target, text)
	if ns.db.popupPos then
		local p = ns.db.popupPos
		self:ClearAllPoints()
		self:SetPoint(p[1], UIParent, p[2], p[3], p[4])
	end
	self.send:SetText(L.SEND)
	self.cancel:SetText(L.CANCEL)
	self.hint:SetText(ns.db.popupFocus and L.POPUP_HINT or L.POPUP_HINT_NOFOCUS)
	self.countdownEnd = nil
	if ns.db.countdown > 0 and not ns.IsRestricted(target) then
		self.countdownEnd = GetTime() + ns.db.countdown
	end
	self.edit:SetText(text)
	self.edit:SetCursorPosition(#text)
	self:SetTarget(target)
	self:Show()
	if ns.db.popupFocus then
		self.edit:SetFocus()
	end
end

function Popup:Send()
	local text = strtrim(self.edit:GetText() or "")
	if text ~= "" and self.target then
		ns.Channels.Send(self.target, text)
		ns.PlaySound("sent")
	end
	self:Close()
end

function Popup:Close()
	self.countdownEnd = nil
	self.edit:ClearFocus()
	self:Hide()
end

function Popup:HandleBinding(action)
	if not self:IsShown() then
		return
	end
	if action == "SEND" then
		self:Send()
	else
		self:Close()
	end
end

Popup:SetScript("OnUpdate", function(self)
	if self.countdownEnd then
		if GetTime() >= self.countdownEnd then
			self.countdownEnd = nil
			self:Send()
		else
			self:UpdateInfo()
		end
	end
end)

edit:SetScript("OnEnterPressed", function() Popup:Send() end)
edit:SetScript("OnEscapePressed", function() Popup:Close() end)
edit:SetScript("OnTabPressed", function() Popup:CycleChannel(IsShiftKeyDown() and -1 or 1) end)
edit:SetScript("OnTextChanged", function(_, userInput)
	if userInput then
		Popup.countdownEnd = nil
	end
	Popup:UpdateInfo()
end)
edit:SetScript("OnMouseDown", function(self) self:SetFocus() end)
ns.HookInputLine(edit)
