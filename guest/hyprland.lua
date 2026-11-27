-- Hornero QA session (test image only, never shipped).
--
-- Hyprland 0.57+ reads ~/.config/hypr/hyprland.lua before any hyprlang
-- hyprland.conf, and HorneroOS/config ships only the Lua entrypoint. This
-- file replaces the product entrypoint in the QA image and loads the
-- product's own fragments, so scenarios drive the real binds, rules,
-- geometry and Signal border colours. Only determinism is overridden: fixed
-- outputs, no animations, no idle daemons, no autostart beyond the shell.
-- Runtime changes go through `hyprctl eval '<lua>'` (`hyprctl keyword`
-- answers "unknown request" with exit status 0 on a Lua config).
-- luacheck: globals hl hornero_helpers

local here = os.getenv("HOME") .. "/.config/hypr/hyprland.lua.d/"

dofile(here .. "environment.lua")
dofile(here .. "input.lua")
dofile(here .. "layout.lua")
hornero_helpers = dofile(here .. "helpers.lua")
dofile(here .. "keybindings.lua")
dofile(here .. "window-rules.lua")
dofile(here .. "smart-colors.lua")
dofile(here .. "static.lua")

-- Outputs: use QEMU's preferred mode per head; extra heads stack to the right.
hl.monitor({ output = "Virtual-1", mode = "preferred", position = "0x0", scale = 1 })
hl.monitor({ output = "Virtual-2", mode = "preferred", position = "auto", scale = 1 })
hl.monitor({ output = "", mode = "preferred", position = "auto", scale = 1 })

-- QEMU has no NVIDIA VA-API: point libva at the virtio driver.
hl.env("LIBVA_DRIVER_NAME", "virtio_gpu")

hl.config({
	animations = { enabled = false },
	misc = {
		disable_hyprland_logo = true,
		disable_splash_rendering = true,
		force_default_wallpaper = 0,
	},
	cursor = {
		no_hardware_cursors = true,
		-- Hide an idle pointer so captures show the product, not a cursor
		-- parked wherever QEMU's tablet left it. Pointer journeys still see it move.
		inactive_timeout = 1,
	},
	ecosystem = {
		no_update_news = true,
		no_donation_nag = true,
	},
})

hl.on("hyprland.start", function()
	hl.exec_cmd("$HOME/.local/bin/qa-shell.sh")
end)
