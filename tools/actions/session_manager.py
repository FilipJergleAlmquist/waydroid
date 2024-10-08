# Copyright 2021 Erfan Abdi
# SPDX-License-Identifier: GPL-3.0-or-later
import logging
import os
import time
import signal
import sys
import shutil
import tools.config
import tools.helpers.ipc
from tools import services
import dbus
import dbus.service
import dbus.exceptions
from gi.repository import GLib
import copy

class DbusSessionManager(dbus.service.Object):
    def __init__(self, looper, bus, object_path, args):
        self.args = args
        self.looper = looper
        dbus.service.Object.__init__(self, bus, object_path)

    @dbus.service.method("id.waydro.SessionManager", in_signature='i', out_signature='')
    def Stop(self, session_id):
        self.args.session_id = session_id
        do_stop(self.args, self.looper)
        stop_container(session_id, quit_session=False)

def service(args, looper):
    dbus_obj = DbusSessionManager(looper, dbus.SessionBus(), '/SessionManager', args)
    looper.run()

def start(args, unlocked_cb=None, background=True):
    logging.info("starting sessions")
    try:
        name = dbus.service.BusName("id.waydro.Session", dbus.SessionBus(), do_not_queue=True)
    except dbus.exceptions.NameExistsException:
        logging.error("Session is already running")
        if unlocked_cb:
            unlocked_cb()
        return
    
    mainloop = GLib.MainLoop()

    for i in range(args.num_sessions):
        args.session_id = i

        logging.info(f"starting session {i}")
        session = copy.copy(tools.config.session_defaults(args))

        # TODO: also support WAYLAND_SOCKET?
        wayland_display = session["wayland_display"]
        if wayland_display == "None" or not wayland_display:
            logging.warning('WAYLAND_DISPLAY is not set, defaulting to "wayland-0"')
            wayland_display = session["wayland_display"] = "wayland-0"

        if os.path.isabs(wayland_display):
            wayland_socket_path = wayland_display
        else:
            xdg_runtime_dir = session["xdg_runtime_dir"]
            if xdg_runtime_dir == "None" or not xdg_runtime_dir:
                logging.error(f"XDG_RUNTIME_DIR is not set; please don't start a Waydroid session with 'sudo'!")
                sys.exit(1)
            wayland_socket_path = os.path.join(xdg_runtime_dir, wayland_display)
        if not os.path.exists(wayland_socket_path):
            logging.error(f"Wayland socket '{wayland_socket_path}' doesn't exist; are you running a Wayland compositor?")
            sys.exit(1)

        waydroid_data = session["waydroid_data"]
        if not os.path.isdir(waydroid_data):
            os.makedirs(waydroid_data)

        dpi = tools.helpers.props.host_get(args, "ro.sf.lcd_density")
        if dpi == "":
            dpi = os.getenv("GRID_UNIT_PX")
            if dpi is not None:
                dpi = str(int(dpi) * 20)
            else:
                dpi = "0"
        session["lcd_density"] = dpi

        session["background_start"] = "true" if background else "false"

        local_args = copy.copy(args)

        # GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGUSR1, sigusr_handler, None)
        try:
            tools.helpers.ipc.DBusContainerService().Start(args.session_id, session)
        except dbus.DBusException as e:
            logging.debug(e)
            if e.get_dbus_name().startswith("org.freedesktop.DBus.Python"):
                logging.error(e.get_dbus_message().splitlines()[-1])
            else:
                logging.error("WayDroid container is not listening")
            sys.exit(0)

        # services.user_manager.start(args, session, unlocked_cb)
        # services.clipboard_manager.start(args)


    def sigint_handler(data):
        # do_stop(local_args, mainloop)
        for i in range(args.num_sessions):
            session_id = i
            stop_container(session_id, quit_session=False)
        mainloop.quit()

    # def sigusr_handler(data):
    #     do_stop(local_args, mainloop)

    GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGINT, sigint_handler, None)
    GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGTERM, sigint_handler, None)

    service(args, mainloop)

def do_stop(args, looper):
    services.user_manager.stop(args)
    services.clipboard_manager.stop(args)
    looper.quit()

def stop(args):
    try:
        tools.helpers.ipc.DBusSessionService().Stop()
    except dbus.DBusException:
        stop_container(args.session_id, quit_session=True)

def stop_container(session_id, quit_session):
    try:
        tools.helpers.ipc.DBusContainerService().Stop(session_id, quit_session)
    except dbus.DBusException:
        pass
