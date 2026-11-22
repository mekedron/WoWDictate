#!/usr/bin/env bash
# Installs the Dictate addon and the wow-dictate companion on Linux and macOS.
# (Windows: install.ps1.)
#   ./install.sh                  addon + companion (starts with the session)
#   ./install.sh addon            addon only
#   ./install.sh companion        companion only
#   WOW_DIR=".../_forever_" ./install.sh     WoW folder if it is not found
#   FLAVOR=_retail_ ./install.sh             another client folder (default _forever_)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
FLAVOR="${FLAVOR:-_forever_}"
OS="$(uname -s)"

find_wow_dir() {
	if [ -n "${WOW_DIR:-}" ]; then
		echo "$WOW_DIR"
		return
	fi
	local candidates=()
	if [ "$OS" = Darwin ]; then
		candidates+=("/Applications/World of Warcraft" "$HOME/Applications/World of Warcraft")
	else
		# Common Wine prefixes: own folder, Lutris, Bottles, Steam (Proton) compatdata, ~/.wine.
		candidates+=("$HOME/Battle.net/Games/World of Warcraft" "$HOME/Games/World of Warcraft")
		local pf
		for pf in \
			"$HOME"/Games/*/drive_c/"Program Files (x86)" \
			"$HOME"/.local/share/bottles/bottles/*/drive_c/"Program Files (x86)" \
			"$HOME"/.local/share/Steam/steamapps/compatdata/*/pfx/drive_c/"Program Files (x86)" \
			"$HOME"/.wine/drive_c/"Program Files (x86)"; do
			[ -d "$pf/World of Warcraft" ] && candidates+=("$pf/World of Warcraft")
		done
	fi
	local base
	for base in "${candidates[@]}"; do
		if [ -d "$base/$FLAVOR" ]; then
			echo "$base/$FLAVOR"
			return
		fi
	done
	echo "World of Warcraft $FLAVOR folder not found; set WOW_DIR=/path/to/World of Warcraft/$FLAVOR" >&2
	exit 1
}

install_addon() {
	local dir
	dir="$(find_wow_dir)/Interface/AddOns/Dictate"
	mkdir -p "$dir"
	mkdir -p "$dir/Locales"
	cp "$ROOT"/Dictate/*.toc "$ROOT"/Dictate/*.lua "$ROOT"/Dictate/*.xml "$dir"/
	cp "$ROOT"/Dictate/Locales/*.lua "$dir/Locales"/
	echo "addon -> $dir"
}

ensure_uv() {
	if ! command -v uv >/dev/null; then
		echo "installing uv (https://docs.astral.sh/uv/)"
		curl -LsSf https://astral.sh/uv/install.sh | sh
		export PATH="$HOME/.local/bin:$PATH"
	fi
	command -v uv
}

install_linux_service() {
	local uv=$1
	if ! id -nG | grep -qw input; then
		echo "warning: add yourself to the 'input' group and log in again:" >&2
		echo "  sudo usermod -aG input $USER" >&2
	fi
	if [ ! -w /dev/uinput ]; then
		echo "warning: /dev/uinput is not writable; add a udev rule, e.g.:" >&2
		echo "  echo 'KERNEL==\"uinput\", GROUP=\"input\", MODE=\"0620\"' | sudo tee /etc/udev/rules.d/70-uinput.rules" >&2
	fi
	command -v xclip >/dev/null || echo "warning: install xclip (Debian/Ubuntu: sudo apt install xclip)" >&2
	local unit="$HOME/.config/systemd/user/wow-dictate.service"
	mkdir -p "$(dirname "$unit")"
	cat >"$unit" <<UNIT
[Unit]
Description=wow-dictate: voice-to-chat companion for the Dictate WoW addon
After=graphical-session.target pipewire.service
PartOf=graphical-session.target

[Service]
ExecStart=$uv run --project $ROOT/companion wow-dictate run
Restart=on-failure
RestartSec=3

[Install]
WantedBy=graphical-session.target
UNIT
	systemctl --user daemon-reload
	systemctl --user enable wow-dictate.service
	systemctl --user restart wow-dictate.service
	echo "companion -> systemd user service wow-dictate (journalctl --user -fu wow-dictate)"
}

install_macos_agent() {
	local uv=$1
	local plist="$HOME/Library/LaunchAgents/dev.wowdictate.plist"
	mkdir -p "$(dirname "$plist")"
	cat >"$plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>Label</key><string>dev.wowdictate</string>
	<key>ProgramArguments</key>
	<array>
		<string>$uv</string><string>run</string><string>--project</string><string>$ROOT/companion</string>
		<string>wow-dictate</string><string>run</string>
	</array>
	<key>RunAtLoad</key><true/>
	<key>KeepAlive</key><true/>
	<key>ProcessType</key><string>Interactive</string>
</dict>
</plist>
PLIST
	launchctl bootout "gui/$(id -u)/dev.wowdictate" 2>/dev/null || true
	launchctl bootstrap "gui/$(id -u)" "$plist"
	echo "companion -> LaunchAgent dev.wowdictate"
	echo "allow it in System Settings > Privacy & Security: Accessibility, Input Monitoring, Microphone"
}

install_companion() {
	local uv
	uv="$(ensure_uv)"
	uv sync --project "$ROOT/companion" -q
	local config
	config="$("$uv" run --project "$ROOT/companion" wow-dictate config)"
	if [ "$OS" = Darwin ]; then
		install_macos_agent "$uv"
	else
		install_linux_service "$uv"
	fi
	echo "config    -> $config"
	echo "check     -> uv run --project $ROOT/companion wow-dictate doctor"
}

case "${1:-all}" in
	addon) install_addon ;;
	companion) install_companion ;;
	all) install_addon; install_companion ;;
	*) echo "usage: $0 [addon|companion|all]" >&2; exit 1 ;;
esac
