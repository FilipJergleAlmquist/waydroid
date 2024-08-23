# Copyright 2021 Oliver Smith
# SPDX-License-Identifier: GPL-3.0-or-later
import os
import pwd

#
# Exported functions
#
from tools.config.load import load, load_channels
from tools.config.save import save
import logging

#
# Exported variables (internal configuration)
#
version = "1.4.3"
tools_src = os.path.normpath(os.path.realpath(__file__) + "/../../..")

# Keys saved in the config file (mostly what we ask in 'waydroid init')
config_keys = ["arch",
               "images_path",
               "vendor_type",
               "system_datetime",
               "vendor_datetime",
               "suspend_action",
               "mount_overlays",
               "auto_adb"]

# Config file/commandline default values
# $WORK gets replaced with the actual value for args.work (which may be
# overridden on the commandline)
_defaults = {
    "arch": "arm64",
    "work": "/var/lib/waydroid",
    "vendor_type": "MAINLINE",
    "system_datetime": "0",
    "vendor_datetime": "0",
    "preinstalled_images_paths": [
        "/etc/waydroid-extra/images",
        "/usr/share/waydroid-extra/images",
    ],
    "suspend_action": "freeze",
    "mount_overlays": "True",
    "auto_adb": "True",
    "container_xdg_runtime_dir": "/run/xdg",
    "container_wayland_display": "wayland-0",
}
_defaults["images_path"] = _defaults["work"] + "/images"
_defaults["rootfs"] = _defaults["work"] + "/rootfs"
_defaults["overlay"] = _defaults["work"] + "/overlay"
_defaults["overlay_rw"] = _defaults["work"] + "/overlay_rw"
_defaults["overlay_work"] = _defaults["work"] + "/overlay_work"
_defaults["data"] = _defaults["work"] + "/data"
_defaults["lxc"] = _defaults["work"] + "/lxc"
_defaults["host_perms"] = _defaults["work"] + "/host-permissions"
_defaults["container_pulse_runtime_path"] = _defaults["container_xdg_runtime_dir"] + "/pulse"

def defaults(args, key):
    if key in ["work", "rootfs", "overlay", "overlay_rw", "overlay_work", "data", "lxc"]:
        session_default = _defaults[key].replace('/waydroid', f'/waydroid/session_{args.session_id}')
        logging.info(f"Session default {key} => {session_default}")
        return session_default
    return _defaults[key]

_session_defaults = {
    "user_name": pwd.getpwuid(os.getuid()).pw_name,
    "user_id": str(os.getuid()),
    "group_id": str(os.getgid()),
    "host_user": os.path.expanduser("~"),
    "pid": str(os.getpid()),
    "xdg_data_home": str(os.environ.get('XDG_DATA_HOME', os.path.expanduser("~") + "/.local/share")),
    "xdg_runtime_dir": str(os.environ.get('XDG_RUNTIME_DIR')),
    "wayland_display": str(os.environ.get('WAYLAND_DISPLAY')),
    "pulse_runtime_path": str(os.environ.get('PULSE_RUNTIME_PATH')),
    "state": "STOPPED",
    "lcd_density": "0",
    "background_start": "true"
}
_session_defaults["waydroid_data"] = _session_defaults["xdg_data_home"] + \
    "/waydroid/data"
if _session_defaults["pulse_runtime_path"] == "None":
    _session_defaults["pulse_runtime_path"] = _session_defaults["xdg_runtime_dir"] + "/pulse"

def session_defaults(args, key=None):
    if key is None:
        session_copy = _session_defaults.copy()
        session_copy["waydroid_data"] = session_defaults(args, "waydroid_data")
        return session_copy
    if key == "waydroid_data":
        return _session_defaults[key].replace('waydroid/', f'waydroid/session_{args.session_id}')
    return _session_defaults[key]

channels_defaults = {
    "config_path": "/usr/share/waydroid-extra/channels.cfg",
    "system_channel": "https://ota.waydro.id/system",
    "vendor_channel": "https://ota.waydro.id/vendor",
    "rom_type": "lineage",
    "system_type": "VANILLA"
}
channels_config_keys = ["system_channel",
                        "vendor_channel",
                        "rom_type",
                        "system_type"]
