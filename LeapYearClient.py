from __future__ import annotations
import os
import asyncio
import typing
import shutil

import bsdiff4

import Utils

from NetUtils import NetworkItem, ClientStatus
from MultiServer import mark_raw
from CommonClient import CommonContext, server_loop, \
    gui_enabled, ClientCommandProcessor, logger, get_base_parser
from Utils import async_start

class LeapYearCommandProcessor(ClientCommandProcessor):
    def __init__(self, ctx):
        super().__init__(ctx)

    def _cmd_resync(self):
        """Manually trigger a resync."""
        if isinstance(self.ctx, LeapYearContext):
            self.output("Syncing items.")
            self.ctx.syncing = True

    def patch_game(self):
        with open(Utils.user_path("Leap Year", "data.win"), "rb") as f:
            patchedFile = bsdiff4.patch(f.read(), "patch.bsdiff")
        with open(Utils.user_path("Leap Year", "data.win"), "wb") as f:
            f.write(patchedFile)
            f.close()

    def _cmd_patch(self):
        """Patch the game. Only use this command if /auto_patch fails."""
        if isinstance(self.ctx, LeapYearContext):
            os.makedirs(name=Utils.user_path("Leap Year"), exist_ok=True)
            self.ctx.patch_game()
            self.output("Patched.")

    def _cmd_savepath(self, directory: str):
        """Redirect to proper save data folder. This is necessary for Linux users to use before connecting."""
        if isinstance(self.ctx, LeapYearContext):
            self.ctx.save_game_folder = directory
            self.output("Changed to the following directory: " + self.ctx.save_game_folder)

    @mark_raw
    def _cmd_auto_patch(self, steaminstall: typing.Optional[str] = None):
        """Patch the game automatically."""
        if isinstance(self.ctx, LeapYearContext):
            os.makedirs(name=Utils.user_path("Leap Year"), exist_ok=True)
            tempInstall = steaminstall
            if not os.path.isfile(os.path.join(tempInstall, "data.win")):
                tempInstall = None
            if tempInstall is None:
                tempInstall = "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Leap Year"
                if not os.path.exists(tempInstall):
                    tempInstall = "C:\\Program Files\\Steam\\steamapps\\common\\Leap Year"
            elif not os.path.exists(tempInstall):
                tempInstall = "C:\\Program Files (x86)\\Steam\\steamapps\\common\\Leap Year"
                if not os.path.exists(tempInstall):
                    tempInstall = "C:\\Program Files\\Steam\\steamapps\\common\\Leap Year"
            if not os.path.exists(tempInstall) or not os.path.exists(tempInstall) or not os.path.isfile(os.path.join(tempInstall, "data.win")):
                self.output("ERROR: Cannot find Leap Year. Please rerun the command with the correct folder."
                            " command. \"/auto_patch (Steam directory)\".")
            else:
                for file_name in os.listdir(tempInstall):
                    if file_name != "steam_api.dll":
                        shutil.copy(os.path.join(tempInstall, file_name),
                               Utils.user_path("Leap Year", file_name))
                self.ctx.patch_game()
                self.output("Patching successful!")


class LeapYearContext(CommonContext):
    tags = {"AP", "Online"}
    game = "Leap Year"
    command_processor = LeapYearCommandProcessor
    items_handling = 0b111

    save_game_folder = os.path.expandvars(r"%localappdata%/Leap_Year")

    def __init__(self, server_address, password):
        super().__init__(server_address, password)
        self.finished_game = False
        self.syncing = False

    async def server_auth(self, password_requested: bool = False):
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    def clear_game_files(self):
        if not os.path.exists(self.save_game_folder):
            return
        self.finished_game = False
        for root, dirs, files in os.walk(self.save_game_folder):
            for file in files:
                if file.endswith((".item", ".victory", ".check")):
                    os.remove(os.path.join(root, file))

    async def connect(self, address: typing.Optional[str] = None):
        self.clear_game_files()
        await super().connect(address)

    async def disconnect(self, allow_autoreconnect: bool = False):
        self.clear_game_files()
        await super().disconnect(allow_autoreconnect)

    async def connection_closed(self):
        self.clear_game_files()
        await super().connection_closed()

    async def shutdown(self):
        self.clear_game_files()
        await super().shutdown()

    def on_package(self, cmd: str, args: dict):
        if cmd == "Connected":
            self.game = self.slot_info[self.slot].game
        async_start(process_leapyear_cmd(self, cmd, args))

    def run_gui(self):
        from kvui import GameManager
        class LYManager(GameManager):
            logging_pairs = [("Client", "Archipelago")]
            base_title = "Archipelago Leap Year Client"
        self.ui = LYManager(self)
        self.ui_task = asyncio.create_task(self.ui.async_run(), name="UI")

async def process_leapyear_cmd(ctx: LeapYearContext, cmd: str, args: dict):
    if cmd == "Connected":
        if not os.path.exists(ctx.save_game_folder):
            os.makedirs(ctx.save_game_folder)

        slot_data = args.get("slot_data", {})
        config_path = os.path.join(ctx.save_game_folder, "ap_config.txt")
        with open(config_path, "w") as f:
            f.write(f"days_needed={slot_data.get('days_needed', 18)}\n")
            f.write(f"location_of_29={slot_data.get('location_of_29', 'gate')}\n")
            f.write(f"shards_needed={slot_data.get('shards_needed', 3)}\n")

    elif cmd == "ReceivedItems":
        start_index = args["index"]
        if start_index == 0:
            ctx.items_received = []
        elif start_index != len(ctx.items_received):
            sync_msg = [{"cmd": "Sync"}]
            if ctx.locations_checked:
                sync_msg.append({"cmd": "LocationChecks", "locations": list(ctx.locations_checked)})
            await ctx.send_msgs(sync_msg)

        if start_index == len(ctx.items_received):
            for item in args["items"]:
                network_item = NetworkItem(*item)

                filename = f"{network_item.location}PLR{network_item.player}.item"
                filepath = os.path.join(ctx.save_game_folder, filename)

                with open(filepath, "w") as f:
                    f.write(str(network_item.item))

                ctx.items_received.append(network_item)
        ctx.watcher_event.set()

async def game_watcher(ctx: LeapYearContext):
    """Watches the save directory for files created by GameMaker."""
    while not ctx.exit_event.is_set():
        path = ctx.save_game_folder

        if not os.path.exists(path):
            await asyncio.sleep(0.5)
            continue

        if ctx.syncing:
            for root, dirs, files in os.walk(path):
                for file in files:
                    if file.endswith(".item"):
                        os.remove(os.path.join(root, file))
            sync_msg = [{"cmd": "Sync"}]
            if ctx.locations_checked:
                sync_msg.append({"cmd": "LocationChecks", "locations": list(ctx.locations_checked)})
            await ctx.send_msgs(sync_msg)
            ctx.syncing = False

        sending_checks = []
        victory = False

        for root, dirs, files in os.walk(path):
            for file in files:

                if file == "check.spot":
                    try:
                        with open(os.path.join(root, file), "r") as f:
                            lines = f.readlines()
                        for line in lines:
                            loc_id = int(line.strip())
                            sending_checks.append(loc_id)
                    finally:
                        await ctx.send_msgs([{"cmd": "LocationChecks", "locations": sending_checks}])
                        os.remove(os.path.join(root, file))

                elif file == "victory.txt":
                    victory = True

        ctx.locations_checked = sending_checks

        if not ctx.finished_game and victory:
            await ctx.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
            ctx.finished_game = True

        await asyncio.sleep(0.1)

def main():
    Utils.init_logging("LeapYearClient", exception_logger="Client")

    async def _main():
        ctx = LeapYearContext(None, None)
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="server loop")
        asyncio.create_task(game_watcher(ctx), name="LeapYearProgressionWatcher")

        if gui_enabled:
            ctx.run_gui()
        ctx.run_cli()

        await ctx.exit_event.wait()
        await ctx.shutdown()

    import colorama
    colorama.just_fix_windows_console()
    asyncio.run(_main())
    colorama.deinit()

if __name__ == "__main__":
    parser = get_base_parser(description="Leap Year Archipelago Client")
    args = parser.parse_args()
    main()