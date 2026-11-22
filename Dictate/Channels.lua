local addonName, ns = ...
local L = ns.L

local Channels = {}
ns.Channels = Channels

-- Chat messages are limited to 255 bytes; Cyrillic letters take two.
local MAX_BYTES = 255

-- A target is { key, chatType, target, label, color }.
local function make(key, chatType, label, target, colorType)
	local info = ChatTypeInfo[colorType or chatType] or ChatTypeInfo.SAY
	return {
		key = key,
		chatType = chatType,
		target = target,
		label = label,
		color = { info.r or 1, info.g or 1, info.b or 1 },
	}
end

local builders = {
	SAY = function() return make("SAY", "SAY", L.CH_SAY) end,
	YELL = function() return make("YELL", "YELL", L.CH_YELL) end,
	PARTY = function()
		if IsInGroup(LE_PARTY_CATEGORY_HOME) then
			return make("PARTY", "PARTY", L.CH_PARTY)
		end
	end,
	RAID = function()
		if IsInRaid(LE_PARTY_CATEGORY_HOME) then
			return make("RAID", "RAID", L.CH_RAID)
		end
	end,
	RAID_WARNING = function()
		if IsInRaid() and (UnitIsGroupLeader("player") or UnitIsGroupAssistant("player")) then
			return make("RAID_WARNING", "RAID_WARNING", L.CH_RAID_WARNING)
		end
	end,
	INSTANCE_CHAT = function()
		if LE_PARTY_CATEGORY_INSTANCE and IsInGroup(LE_PARTY_CATEGORY_INSTANCE) then
			return make("INSTANCE_CHAT", "INSTANCE_CHAT", L.CH_INSTANCE_CHAT)
		end
	end,
	GUILD = function()
		if IsInGuild() then
			return make("GUILD", "GUILD", L.CH_GUILD)
		end
	end,
	OFFICER = function()
		if IsInGuild() and C_GuildInfo and C_GuildInfo.IsGuildOfficer and C_GuildInfo.IsGuildOfficer() then
			return make("OFFICER", "OFFICER", L.CH_OFFICER)
		end
	end,
	REPLY = function()
		return Channels.Reply()
	end,
	TARGET = function()
		if UnitExists("target") and UnitIsPlayer("target") and not UnitIsUnit("target", "player")
			and UnitFactionGroup("target") == UnitFactionGroup("player") then
			local name = GetUnitName("target", true)
			if name then
				return make("TARGET", "WHISPER", L.TARGET:format(Ambiguate(name, "short")), name)
			end
		end
	end,
}

-- Menu order, clockwise from the top.
Channels.ORDER = {
	"RAID", "PARTY", "INSTANCE_CHAT", "RAID_WARNING", "SAY", "YELL",
	"REPLY", "TARGET", "OFFICER", "GUILD",
}
Channels.ALL = {
	"SAY", "YELL", "PARTY", "RAID", "RAID_WARNING", "INSTANCE_CHAT",
	"GUILD", "OFFICER", "REPLY", "TARGET", "PUBLIC",
}

function Channels.Reply()
	local name, chatType = ChatFrameUtil.GetLastTellTarget()
	if not name then
		return nil
	end
	chatType = chatType or "WHISPER"
	local display = chatType == "BN_WHISPER" and name or Ambiguate(name, "short")
	return make("REPLY", chatType, L.REPLY:format(display), name, chatType)
end

function Channels.Get(key)
	local build = builders[key]
	return build and build()
end

local function publicChannels()
	local list = {}
	local data = { GetChannelList() }
	for i = 1, #data, 3 do
		local id, name, disabled = data[i], data[i + 1], data[i + 2]
		if id and name and not disabled then
			local t = make("CHANNEL" .. id, "CHANNEL", ("%d. %s"):format(id, name), id, "CHANNEL" .. id)
			table.insert(list, t)
		end
	end
	return list
end

-- Channels the player can talk in right now and wants in the menu.
function Channels.Available()
	local list = {}
	for _, key in ipairs(Channels.ORDER) do
		if ns.db.menu[key] then
			local t = Channels.Get(key)
			if t then
				table.insert(list, t)
			end
		end
	end
	if ns.db.menu.PUBLIC then
		for _, t in ipairs(publicChannels()) do
			table.insert(list, t)
		end
	end
	return list
end

local function smart()
	return Channels.Get("INSTANCE_CHAT") or Channels.Get("RAID") or Channels.Get("PARTY") or Channels.Get("SAY")
end

function Channels.Default()
	local choice = ns.db.defaultChannel
	if choice == "last" then
		local last = ns.db.lastChannel and Channels.Get(ns.db.lastChannel)
		return last or smart()
	elseif choice ~= "smart" then
		local t = Channels.Get(choice)
		if t then
			return t
		end
	end
	return smart()
end

-- Same channel next in the menu order (Tab in the confirmation window).
function Channels.Next(current, step)
	local list = Channels.Available()
	if #list == 0 then
		return current
	end
	for i, t in ipairs(list) do
		if t.key == current.key then
			return list[(i - 1 + (step or 1)) % #list + 1]
		end
	end
	return list[1]
end

---------------------------------------------------------------------------
-- Voice prefixes: "рейд, ..." / "guild: ..."
---------------------------------------------------------------------------

-- string.lower only knows ASCII; lower-case Cyrillic by hand (UTF-8).
function Channels.Lower(text)
	text = text:lower()
	text = text:gsub("\208([\144-\159])", function(c) -- А..П
		return "\208" .. string.char(c:byte() + 32)
	end)
	text = text:gsub("\208([\160-\175])", function(c) -- Р..Я
		return "\209" .. string.char(c:byte() - 32)
	end)
	return (text:gsub("\208\129", "\209\145")) -- Ё
end

function Channels.UpperFirst(text)
	local b1, b2 = text:byte(1, 2)
	if b1 == 208 and b2 and b2 >= 176 and b2 <= 191 then -- а..п
		return "\208" .. string.char(b2 - 32) .. text:sub(3)
	elseif b1 == 209 and b2 and b2 >= 128 and b2 <= 143 then -- р..я
		return "\208" .. string.char(b2 + 32) .. text:sub(3)
	elseif b1 == 209 and b2 == 145 then -- ё
		return "\208\129" .. text:sub(3)
	end
	return (text:gsub("^%l", string.upper))
end

local PREFIXES = {
	RAID_WARNING = { "объявление", "рейд варнинг", "рейдварнинг", "raid warning" },
	RAID = { "в рейд", "рейду", "рейд", "raid" },
	PARTY = { "в группу", "группе", "группа", "в пати", "пати", "party", "group" },
	INSTANCE_CHAT = { "в подземелье", "подземелье", "инстанс", "instance" },
	OFFICER = { "офицерам", "офицеры", "officers", "officer" },
	GUILD = { "в гильдию", "гильдии", "гильдия", "в ги", "ги", "guild" },
	YELL = { "крикни", "кричи", "крик", "yell" },
	SAY = { "скажи", "сказать", "say" },
	REPLY = { "ответь", "ответ", "reply" },
}
local prefixList
local function buildPrefixList()
	prefixList = {}
	for key, words in pairs(PREFIXES) do
		for _, word in ipairs(words) do
			table.insert(prefixList, { word = word, key = key })
		end
	end
	table.sort(prefixList, function(a, b) return #a.word > #b.word end)
end

-- Returns target, rest of text when the text starts with a channel word
-- followed by punctuation or a space.
function Channels.ParsePrefix(text)
	if not prefixList then
		buildPrefixList()
	end
	local lower = Channels.Lower(text)
	for _, p in ipairs(prefixList) do
		if lower:sub(1, #p.word) == p.word then
			local rest = text:sub(#p.word + 1)
			local sep = rest:match("^[%s,:;%.!%-]+") or rest:match("^\226\128[\147\148][%s]*")
			if sep or rest == "" then
				local target = Channels.Get(p.key)
				if target then
					rest = rest:sub(#(sep or "") + 1)
					rest = Channels.UpperFirst(rest)
					return target, rest
				end
			end
		end
	end
	return nil
end

---------------------------------------------------------------------------
-- Sending
---------------------------------------------------------------------------

-- Split into chat-sized parts at spaces, never inside a UTF-8 character.
function Channels.Split(text, limit)
	limit = limit or MAX_BYTES
	local parts = {}
	while #text > limit do
		local cut = limit
		while cut > 1 and text:byte(cut + 1) and text:byte(cut + 1) >= 128 and text:byte(cut + 1) < 192 do
			cut = cut - 1
		end
		local space = text:sub(1, cut):match(".*()%s")
		if space and space > limit / 2 then
			cut = space - 1
		end
		table.insert(parts, (text:sub(1, cut):gsub("%s+$", "")))
		text = text:sub(cut + 1):gsub("^%s+", "")
	end
	if text ~= "" then
		table.insert(parts, text)
	end
	return parts
end

local SLASH = {
	SAY = "/s", YELL = "/y", PARTY = "/p", RAID = "/raid", RAID_WARNING = "/rw",
	INSTANCE_CHAT = "/i", GUILD = "/g", OFFICER = "/o",
}

function Channels.Slash(target)
	if target.chatType == "WHISPER" or target.chatType == "BN_WHISPER" then
		return "/w " .. target.target
	elseif target.chatType == "CHANNEL" then
		return "/" .. target.target
	end
	return SLASH[target.chatType] or "/s"
end

local sendChat = (C_ChatInfo and C_ChatInfo.SendChatMessage) or SendChatMessage

function Channels.Send(target, text)
	ns.db.lastChannel = target.key
	for _, part in ipairs(Channels.Split(text)) do
		if target.chatType == "BN_WHISPER" then
			local id = BNet_GetBNetIDAccount and BNet_GetBNetIDAccount(target.target)
			if id then
				C_BattleNet.SendWhisper(id, part)
			end
		else
			sendChat(part, target.chatType, nil, target.target)
		end
	end
	if target.chatType == "WHISPER" or target.chatType == "BN_WHISPER" then
		ChatFrameUtil.SetLastToldTarget(target.target, target.chatType)
	end
end
