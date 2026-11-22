local addonName, ns = ...
local L = ns.L

local category

local function options(pairsList)
	return function()
		local container = Settings.CreateControlTextContainer()
		for _, pair in ipairs(pairsList) do
			container:Add(pair[1], pair[2])
		end
		return container:GetData()
	end
end

local function header(layout, text)
	if layout and CreateSettingsListSectionHeaderInitializer then
		layout:AddInitializer(CreateSettingsListSectionHeaderInitializer(text))
	end
end

function ns.InitOptions()
	if not Settings or not Settings.RegisterVerticalLayoutCategory then
		return
	end
	local db = ns.db
	category = Settings.RegisterVerticalLayoutCategory("Dictate")
	local layout = SettingsPanel and SettingsPanel.GetLayout and SettingsPanel:GetLayout(category)

	local function setting(key, tbl, varType, name, default)
		return Settings.RegisterAddOnSetting(category, "DICTATE_" .. key, key, tbl or db, varType, name, default)
	end

	header(layout, L.OPT_DELIVERY)

	local mode = setting("mode", nil, Settings.VarType.String, L.OPT_MODE, "popup")
	Settings.CreateDropdown(category, mode, options({
		{ "popup", L.MODE_POPUP },
		{ "chatbox", L.MODE_CHATBOX },
		{ "auto", L.MODE_AUTO },
	}), L.OPT_MODE_TIP)

	local focus = setting("popupFocus", nil, Settings.VarType.Boolean, L.OPT_POPUP_FOCUS, true)
	Settings.CreateCheckbox(category, focus, L.OPT_POPUP_FOCUS_TIP)

	local countdown = setting("countdown", nil, Settings.VarType.Number, L.OPT_COUNTDOWN, 0)
	local sliderOptions = Settings.CreateSliderOptions(0, 10, 1)
	sliderOptions:SetLabelFormatter(MinimalSliderWithSteppersMixin.Label.Right, function(value)
		return value == 0 and L.OPT_OFF or L.OPT_SECONDS:format(value)
	end)
	Settings.CreateSlider(category, countdown, sliderOptions, L.OPT_COUNTDOWN_TIP)

	header(layout, L.OPT_CHANNELS)

	local default = setting("defaultChannel", nil, Settings.VarType.String, L.OPT_DEFAULT, "smart")
	Settings.CreateDropdown(category, default, options({
		{ "smart", L.DEF_SMART },
		{ "last", L.DEF_LAST },
		{ "SAY", L.CH_SAY },
		{ "PARTY", L.CH_PARTY },
		{ "RAID", L.CH_RAID },
		{ "INSTANCE_CHAT", L.CH_INSTANCE_CHAT },
		{ "GUILD", L.CH_GUILD },
	}), L.OPT_DEFAULT_TIP)

	local center = setting("center", nil, Settings.VarType.String, L.OPT_CENTER, "default")
	Settings.CreateDropdown(category, center, options({
		{ "default", L.OPT_CENTER_DEFAULT },
		{ "cancel", L.OPT_CENTER_CANCEL },
	}))

	local prefixes = setting("voicePrefixes", nil, Settings.VarType.Boolean, L.OPT_PREFIXES, true)
	Settings.CreateCheckbox(category, prefixes, L.OPT_PREFIXES_TIP)

	header(layout, L.OPT_MENU)
	for _, key in ipairs(ns.Channels.ALL) do
		local s = setting(key, db.menu, Settings.VarType.Boolean, L["CH_" .. key], ns.defaults.menu[key] == true)
		Settings.CreateCheckbox(category, s)
	end

	header(layout, L.OPT_OTHER)

	local sounds = setting("sounds", nil, Settings.VarType.Boolean, L.OPT_SOUNDS, true)
	Settings.CreateCheckbox(category, sounds)

	if db.lang == "en" or db.lang == "ru" then
		db.lang = ns.DetectLanguage(db.lang)
	end
	local languages = { { "auto", L.LANG_AUTO } }
	for _, code in ipairs(ns.localeOrder) do
		table.insert(languages, { code, ns.locales[code].name })
	end
	local lang = setting("lang", nil, Settings.VarType.String, L.OPT_LANG, "auto")
	Settings.CreateDropdown(category, lang, options(languages), L.OPT_LANG_TIP)
	lang:SetValueChangedCallback(function(_, value)
		ns.lang = ns.DetectLanguage(value)
		ns.ApplyBindingNames()
		ns.Print(L.LANG_RELOAD)
	end)

	Settings.RegisterAddOnCategory(category)
end

function ns.OpenOptions()
	if category then
		Settings.OpenToCategory(category:GetID())
	end
end
