local addonName, ns = ...
local L = ns.L

-- Radial channel menu: opens around the cursor while the key is held; the
-- direction of the cursor picks a channel, the center is the default channel
-- (or cancel), and pulling far outside the ring cancels.
local DEAD_ZONE = 28
local CANCEL_DISTANCE = 140 -- beyond the ring
local PILL_W, PILL_H = 132, 26

local Radial = CreateFrame("Frame", "DictateRadial", UIParent)
ns.Radial = Radial
Radial:SetFrameStrata("FULLSCREEN_DIALOG")
Radial:SetSize(1, 1)
Radial:Hide()
Radial.pills = {}

local center = CreateFrame("Frame", nil, Radial, "BackdropTemplate")
center:SetSize(112, 40)
center:SetPoint("CENTER")
ns.ApplyBackdrop(center, 0.9)
center.text = ns.CreateText(center, "OVERLAY", "GameFontHighlightSmall")
center.text:SetPoint("CENTER")
center.text:SetWidth(104)
Radial.center = center

local function pill(index)
	local p = Radial.pills[index]
	if not p then
		p = CreateFrame("Frame", nil, Radial, "BackdropTemplate")
		p:SetSize(PILL_W, PILL_H)
		ns.ApplyBackdrop(p, 0.85)
		p.text = ns.CreateText(p, "OVERLAY", "GameFontHighlight")
		p.text:SetPoint("CENTER")
		p.text:SetWidth(PILL_W - 10)
		p.text:SetWordWrap(false)
		Radial.pills[index] = p
	end
	return p
end

local function highlight(frame, on, color)
	if on then
		frame:SetBackdropBorderColor(color[1], color[2], color[3], 1)
		frame:SetBackdropColor(color[1] * 0.35, color[2] * 0.35, color[3] * 0.35, 0.95)
		frame:SetScale(1.12)
	else
		frame:SetBackdropBorderColor(0.4, 0.4, 0.45, 1)
		frame:SetBackdropColor(0.05, 0.05, 0.08, 0.85)
		frame:SetScale(1)
	end
end

local function cursor()
	local x, y = GetCursorPosition()
	local scale = UIParent:GetEffectiveScale()
	return x / scale, y / scale
end

function Radial:Open()
	self.targets = ns.Channels.Available()
	self.default = ns.Channels.Default()
	local n = #self.targets
	self.radius = math.max(95, n * 19)
	local x, y = cursor()
	self.cx, self.cy = x, y
	self:ClearAllPoints()
	self:SetPoint("CENTER", UIParent, "BOTTOMLEFT", x, y)
	for i, p in ipairs(self.pills) do
		p:SetShown(i <= n)
	end
	for i, target in ipairs(self.targets) do
		-- Clockwise from the top.
		local angle = math.rad(90 - (i - 1) * 360 / n)
		local p = pill(i)
		p:ClearAllPoints()
		p:SetPoint("CENTER", self, "CENTER", math.cos(angle) * self.radius, math.sin(angle) * self.radius)
		p.text:SetText(ns.Colorize(target))
		p.angle = angle
		highlight(p, false)
		p:Show()
	end
	self.selection, self.cancel = nil, false
	self:Update()
	self:Show()
end

function Radial:Update()
	local x, y = cursor()
	local dx, dy = x - self.cx, y - self.cy
	local dist = math.sqrt(dx * dx + dy * dy)
	local selection, cancel = nil, false
	if dist > self.radius + CANCEL_DISTANCE then
		cancel = true
	elseif dist > DEAD_ZONE and #self.targets > 0 then
		local angle = math.atan2(dy, dx)
		local best, bestDiff = nil, math.huge
		for i, p in ipairs(self.pills) do
			if i > #self.targets then
				break
			end
			local diff = math.abs((angle - p.angle + math.pi) % (2 * math.pi) - math.pi)
			if diff < bestDiff then
				best, bestDiff = i, diff
			end
		end
		selection = best
	elseif ns.db.center == "cancel" then
		cancel = true
	end
	if selection ~= self.selection or cancel ~= self.cancel or not self.drawn then
		self.selection, self.cancel, self.drawn = selection, cancel, true
		for i, p in ipairs(self.pills) do
			if i <= #self.targets then
				highlight(p, i == selection, self.targets[i].color)
			end
		end
		local centerCancel = ns.db.center == "cancel"
		if cancel then
			center.text:SetText("|cffff5555" .. L.CANCEL .. "|r")
		elseif centerCancel then
			center.text:SetText("|cff999999" .. L.CANCEL .. "|r")
		else
			center.text:SetText(ns.Colorize(self.default) .. "\n|cff999999" .. L.AUTO .. "|r")
		end
		highlight(center, not selection, cancel and { 1, 0.3, 0.3 } or { 0.8, 0.8, 0.8 })
		ns.HUD:SetTarget(selection and self.targets[selection] or (not centerCancel and self.default) or nil, cancel)
	end
end

Radial:SetScript("OnUpdate", Radial.Update)

-- Returns the chosen target (nil = default) and whether the dictation is cancelled.
function Radial:Close()
	if not self:IsShown() then
		return nil, false
	end
	self:Update()
	self:Hide()
	self.drawn = false
	if self.cancel then
		return nil, true
	end
	return self.selection and self.targets[self.selection] or nil, false
end
