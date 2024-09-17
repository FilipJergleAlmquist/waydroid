# Copyright 2021 Erfan Abdi
# SPDX-License-Identifier: GPL-3.0-or-later
from shutil import which
import logging
import os
import time
import glob
import signal
import sys
import uuid
import tools.config
from tools import helpers
from tools import services
import dbus
import dbus.service
import dbus.exceptions
from gi.repository import GLib

class DbusContainerManager(dbus.service.Object):
    def __init__(self, looper, bus, object_path, args):
        self.args = args
        self.looper = looper
        self.sessions = {}
        dbus.service.Object.__init__(self, bus, object_path)

    @dbus.service.method("id.waydro.ContainerManager", in_signature='ia{ss}', out_signature='i', sender_keyword="sender", connection_keyword="conn")
    def Start(self, session_id, session, sender, conn):
        self.args.session_id = session_id

        dbus_info = dbus.Interface(conn.get_object("org.freedesktop.DBus", "/org/freedesktop/DBus/Bus", False), "org.freedesktop.DBus")
        uid = dbus_info.GetConnectionUnixUser(sender)
        if str(uid) not in ["0", session["user_id"]]:
            raise RuntimeError("Cannot start a session on behalf of another user")
        pid = dbus_info.GetConnectionUnixProcessID(sender)
        if str(uid) != "0" and str(pid) != session["pid"]:
            raise RuntimeError("Invalid session pid")
        
        if session_id in self.sessions:
            raise RuntimeError(f"Already tracking a session {session_id}")
        
        self.sessions[session_id] = do_start(self.args, session)
        return self.args.container_pid

    @dbus.service.method("id.waydro.ContainerManager", in_signature='ib', out_signature='')
    def Stop(self, session_id, quit_session):
        self.args.session_id = session_id
        self.args.session = self.sessions.pop(session_id)
        stop(self.args, quit_session)

    @dbus.service.method("id.waydro.ContainerManager", in_signature='b', out_signature='')
    def StopAll(self, quit_session):
        logging.info("Stopping all containers")
        for session_id in list(self.sessions.keys()):
            logging.info(f"Stopping session {session_id}")
            self.args.session_id = session_id   
            self.args.session = self.sessions.pop(session_id)
            stop(self.args, quit_session)

    @dbus.service.method("id.waydro.ContainerManager", in_signature='i', out_signature='')
    def Freeze(self, session_id):
        self.args.session_id = session_id
        self.args.session = self.sessions[session_id]
        freeze(self.args)

    @dbus.service.method("id.waydro.ContainerManager", in_signature='i', out_signature='')
    def Unfreeze(self, session_id):
        self.args.session_id = session_id
        self.args.session = self.sessions[session_id]
        unfreeze(self.args)

    @dbus.service.method("id.waydro.ContainerManager", in_signature='i', out_signature='a{ss}')
    def GetSession(self, session_id):
        self.args.session_id = session_id
        try:
            session = self.sessions[session_id]
            # session = self.args.session
            session["state"] = helpers.lxc.status(self.args)
            logging.info(f"retreived session {session_id}, {session}")
            return session
        # except AttributeError:
            return {}
        except KeyError:
            new_session = {}
            self.sessions[session_id] = new_session
            logging.info(f"created new session {session_id}, {session}")
            return new_session

def service(args, looper):
    dbus_obj = DbusContainerManager(looper, dbus.SystemBus(), '/ContainerManager', args)
    def sigint_handler(data):
        logging.info("Caught termination signal")
        dbus_obj.StopAll(True)
        looper.quit()

    GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGINT, sigint_handler, None)
    GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGTERM, sigint_handler, None)
    looper.run()

def set_permissions(args, perm_list=None, mode="777"):
    def chmod(path, mode):
        if os.path.exists(path):
            command = ["chmod", mode, "-R", path]
            tools.helpers.run.user(args, command, check=False)

        # Nodes list
    if not perm_list:
        perm_list = [
            "/dev/ashmem",

            # sw_sync for HWC
            "/dev/sw_sync",
            "/sys/kernel/debug/sync/sw_sync",

            # Media
            "/dev/Vcodec",
            "/dev/MTK_SMI",
            "/dev/mdp_sync",
            "/dev/mtk_cmdq",

            # Graphics
            "/dev/dri",
            "/dev/graphics",
            "/dev/pvr_sync",
            "/dev/ion",
        ]

        # Framebuffers
        perm_list.extend(glob.glob("/dev/fb*"))
        # Videos
        perm_list.extend(glob.glob("/dev/video*"))

    for path in perm_list:
        chmod(path, mode)

def start(args):
    try:
        name = dbus.service.BusName("id.waydro.Container", dbus.SystemBus(), do_not_queue=True)
    except dbus.exceptions.NameExistsException:
        logging.error("Container service is already running")
        return

    status = helpers.lxc.status(args)
    if status == "STOPPED":
        # Load binder and ashmem drivers
        cfg = tools.config.load(args)
        if cfg["waydroid"]["vendor_type"] == "MAINLINE":
            if helpers.drivers.probeBinderDriver(args) != 0:
                logging.error("Failed to load Binder driver")
            helpers.drivers.probeAshmemDriver(args)
        helpers.drivers.loadBinderNodes(args)
        binderfs_path = tools.config.defaults(args, "binderfs")
        set_permissions(args, [
            binderfs_path + args.BINDER_DRIVER,
            binderfs_path + args.VNDBINDER_DRIVER,
            binderfs_path + args.HWBINDER_DRIVER
        ], "666")

        mainloop = GLib.MainLoop()
        service(args, mainloop)
    else:
        logging.error("WayDroid container is {}".format(status))

def do_start(args, session):
    # if "session" in args:
    #     raise RuntimeError("Already tracking a session")

    status = helpers.lxc.status(args)
    if status == "STOPPED":
        # Load binder and ashmem drivers
        cfg = tools.config.load(args)
        if cfg["waydroid"]["vendor_type"] == "MAINLINE":
            if helpers.drivers.probeBinderDriver(args) != 0:
                logging.error("Failed to load Binder driver")
            helpers.drivers.probeAshmemDriver(args)
        helpers.drivers.loadBinderNodes(args)
        binderfs_path = tools.config.defaults(args, "binderfs")
        set_permissions(args, [
            binderfs_path + args.BINDER_DRIVER,
            binderfs_path + args.VNDBINDER_DRIVER,
            binderfs_path + args.HWBINDER_DRIVER
        ], "666")


    # Networking
    command = [tools.config.tools_src +
               "/data/scripts/waydroid-net.sh", "start", "--sid", str(args.session_id)]
    # if args.session_id == 0:
    tools.helpers.run.user(args, command)

    # Create session-specific LXC config file
    helpers.lxc.generate_session_lxc_config(args, session)
    # Backwards compatibility
    with open(tools.config.defaults(args, "lxc") + "/waydroid/config") as f:
        if "config_session" not in f.read():
            helpers.mount.bind(args, session["waydroid_data"],
                               tools.config.defaults(args, "data"))

    # Mount rootfs
    cfg = tools.config.load(args)
    helpers.images.mount_rootfs(args, cfg["waydroid"]["images_path"], session)
    helpers.protocol.set_aidl_version(args)
    container_process = helpers.lxc.start(args)

    args.session = session
    args.container_pid = container_process.pid

    return session

def stop(args, quit_session=True):
    try:
        services.hardware_manager.stop(args)
        status = helpers.lxc.status(args)
        if status != "STOPPED":
            helpers.lxc.stop(args)
            while helpers.lxc.status(args) != "STOPPED":
                pass

        # Networking
        command = [tools.config.tools_src +
                   "/data/scripts/waydroid-net.sh", "stop", "--sid", str(args.session_id)]
        tools.helpers.run.user(args, command, check=False)

        # Umount rootfs
        helpers.images.umount_rootfs(args)

        # Backwards compatibility
        try:
            helpers.mount.umount_all(args, tools.config.defaults(args, "data"))
        except:
            pass

        if "session" in args:
            # if quit_session:
            #     try:
            #         os.kill(int(args.session["pid"]), signal.SIGTERM)
            #     except:
            #         pass
            del args.session
    except:
        pass

def restart(args):
    status = helpers.lxc.status(args)
    if status == "RUNNING":
        helpers.lxc.stop(args)
        helpers.lxc.start(args)
    else:
        logging.error("WayDroid container is {}".format(status))

def freeze(args):
    status = helpers.lxc.status(args)
    if status == "RUNNING":
        helpers.lxc.freeze(args)
        while helpers.lxc.status(args) == "RUNNING":
            pass
    else:
        logging.error("WayDroid container is {}".format(status))

def unfreeze(args):
    status = helpers.lxc.status(args)
    if status == "FROZEN":
        helpers.lxc.unfreeze(args)
        while helpers.lxc.status(args) == "FROZEN":
            pass
