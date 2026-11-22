local addonName, ns = ...

-- Localization. Each Locales/<locale>.lua file registers one WoW client locale
-- (enUS, ruRU, deDE, ...). The addon follows the game language unless the
-- player picks another one in the settings; missing keys fall back to English.

ns.locales = {} -- code -> { name = ..., strings = { ... } }
ns.localeOrder = {}

-- Client locales that share a translation.
local ALIASES = { enGB = "enUS", esMX = "esES", ptPT = "ptBR" }

function ns.RegisterLocale(code, name, strings)
	if not ns.locales[code] then
		table.insert(ns.localeOrder, code)
	end
	ns.locales[code] = { name = name, strings = strings }
end

local function resolve(code)
	code = ALIASES[code] or code
	return ns.locales[code] and code or "enUS"
end

-- setting: "auto" or a locale code. Saved values "en"/"ru" from early versions
-- are understood as enUS/ruRU.
function ns.DetectLanguage(setting)
	if setting == "en" then
		return "enUS"
	elseif setting == "ru" then
		return "ruRU"
	elseif setting and setting ~= "auto" then
		return resolve(setting)
	end
	return resolve(GetLocale())
end

ns.L = setmetatable({}, {
	__index = function(_, key)
		local current = ns.locales[ns.lang or "enUS"]
		local value = current and current.strings[key]
		if value == nil then
			value = ns.locales.enUS and ns.locales.enUS.strings[key]
		end
		return value or key
	end,
})

-- Key binding texts are read by the game when the Key Bindings window opens.
function ns.ApplyBindingNames()
	BINDING_CATEGORY_DICTATE = "Dictate"
	for _, action in ipairs({ "RADIAL", "QUICK", "REPLY", "SEND", "CANCEL" }) do
		_G["BINDING_NAME_DICTATE_" .. action] = ns.L["BINDING_" .. action]
	end
end
