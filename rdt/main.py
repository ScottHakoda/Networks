import argparse
import asyncio
import logging
import re
import sys
import threading
from collections import deque

import rdt
import simulator
from tui import TuiApp


# --- TUI Setup ---

class TuiLogHandler(logging.Handler):
    def __init__(self, queue):
        super().__init__()
        self.queue = queue

    def emit(self, record):
        msg = self.format(record)
        self.queue.append({"type": "LOG", "data": msg})

class TuiVisualizer:
    def __init__(self, queue):
        self.queue = queue
        self.log_to_pane = True

    async def log_event(self, event_type, host=None, data=None):
        event = {"type": event_type, "host": host, "data": str(data)}

        if event_type in ["PKT_LOST", "PKT_CORRUPT"]:
            net_event = {"type": "NET_EVENT", "data": f"{event_type}: {data}"}
            self.queue.append(net_event)
            # The TUI will pause between this event and the next (clear) one
            self.queue.append({"type": "NET_EVENT", "data": ""})  # Clear network
        else:
            self.queue.append(event)

# --- Standard Logger ---

class ColorFormatter(logging.Formatter):
    grey = "\x1b[90m"
    green = "\x1b[32m"
    yellow = "\x1b[33m"
    red = "\x1b[31m"
    blue = "\x1b[34m"
    cyan = "\x1b[36m"
    reset = "\x1b[0m"

    def format(self, record):
        # get the full message as formatted by the parent
        msg = super().format(record)

        # color timestamp
        msg = re.sub(r'(\[.*?\])', self.grey + r'\1' + self.reset, msg, 1)
        # color host
        msg = re.sub(r'(@ Sender|@ Receiver|@ Network)', self.yellow + r'\1' + self.reset, msg)
        # color event types
        msg = re.sub(r'(L5->L4|L3->L4|L4->L5)', self.green + r'\1' + self.reset, msg)
        # color student rdt events
        msg = re.sub(r'(RDT_SEND|RDT_RECV)', self.blue + r'\1' + self.reset, msg)
        # color negative events
        msg = re.sub(r'(PKT_LOST|PKT_CORRUPT|TIMEOUT)', self.red + r'\1' + self.reset, msg)
        # color payloads
        msg = re.sub(r"('.*?')", self.cyan + r"\1" + self.reset, msg)

        return msg

parser = argparse.ArgumentParser(description='Stop-and-wait protocol simulator')
parser.add_argument('-n', '--nmsgs', default=20, type=int, help="number of messages to simulate")
parser.add_argument('-f', '--freq', default=1000, type=float, help="average time between messages from sender's layer5 [>0.0]")
parser.add_argument('-l', '--lossprob', default=0.0, type=float, help="packet loss probability [0.0,1.0), 0 means no loss")
parser.add_argument('-c', '--corruptprob', default=0.0, type=float, help="packet corruption probability [0.0,1.0), 0 means no corruption")
parser.add_argument('-p', '--pause', type=float, help="the time in seconds to wait between events, controls simulator speed. Defaults to 2s for GUI/TUI, 1s for terminal.")
parser.add_argument('-v', '--verbose', action='count', default=3, help="how chatty is the simulator, the log level")
parser.add_argument('--tui', action='store_true', help="Enable Textual User Interface mode")
parser.add_argument('--no-gui', dest='gui', action='store_false', help="Disable GUI and run in terminal-only mode.")

args = parser.parse_args()

if args.pause is None:
    if args.gui or args.tui:
        args.pause = 2.0
    else:
        args.pause = 1.0

level=50-args.verbose*10
if level < 0:
    level = 0

# create logger
logger = logging.getLogger()
logger.setLevel(level)

if args.tui:
    event_queue = deque()
    tui_handler = TuiLogHandler(event_queue)
    tui_handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(tui_handler)
    visualizer = TuiVisualizer(event_queue)
elif args.gui:
    import gui # lazy import
    event_queue = deque()
    visualizer = gui.GuiVisualizer(event_queue)
    # create console handler and set level to debug
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(ColorFormatter('%(message)s'))
    logger.addHandler(ch)
else:
    # create console handler and set level to debug
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(ColorFormatter('%(message)s'))
    logger.addHandler(ch)
    visualizer = None


if args.lossprob >= 1.0:
    print("Invalid packet loss probability")
    sys.exit(1)

if args.corruptprob >= 1.0:
    print("Invalid packet corruption probability")
    sys.exit(1)

sim = simulator.Simulator(args.nmsgs, args.freq, args.lossprob, args.corruptprob, args.pause, visualizer)

if args.tui:
    def run_simulation():
        sim.run(rdt.RDTSender, rdt.RDTReceiver)

    sim_thread = threading.Thread(target=run_simulation, daemon=True)
    sim_thread.start()

    app = TuiApp(event_queue, pause=args.pause)
    app.run()
elif args.gui:
    def run_simulation():
        sim.run(rdt.RDTSender, rdt.RDTReceiver)

    sim_thread = threading.Thread(target=run_simulation, daemon=True)
    sim_thread.start()

    import gui # lazy import
    app = gui.GuiApp(event_queue, pause=args.pause, animation_network_steps=visualizer.animation_network_steps, visualizer=visualizer)
    app.run()
else:
    print("Running simulator with the following parameters:\n")
    print(f'\tverbose     = {args.verbose}')
    print(sim.get_params())
    print('\n','*'*10,'GO','*'*10,'\n')

    sim.run(rdt.RDTSender, rdt.RDTReceiver)
