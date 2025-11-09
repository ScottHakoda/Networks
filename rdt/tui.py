import logging
from collections import deque

import rdt
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer, Static, RichLog
from rich.panel import Panel
from rich.console import Group
from rich.text import Text
from rich.table import Table


RDT_LOGO = """
[b]
        ✦          *
     *  ██████╗ ██████╗ ████████╗  ✨
        ██╔══██╗██╔══██╗╚══██╔══╝   ✧
   .    ██████╔╝██║  ██║   ██║
        ██╔══██╗██║  ██║   ██║    *
  ✧     ██║  ██║██████╔╝   ██║
        ╚═╝  ╚═╝  ╚═══╝    ╚═╝   .
   ✨          .          ✦
[/b]
"""


def _get_pkt_repr(pkt):
    """Manually construct a string representation of a Pkt for comparison."""
    if isinstance(pkt, rdt.Pkt):
        # Use getters to build a consistent representation
        return f"Pkt(seq={pkt.get_seqnum()}, payload='{pkt.get_payload()}', checksum={pkt.get_checksum()})"
    return str(pkt) # Fallback for non-Pkt objects


def _format_pkt_for_tui(pkt):
    if not isinstance(pkt, rdt.Pkt):
        return f"[bright_black]Pkt([red]invalid:{str(pkt)}[/red])[/bright_black]"
    payload_str = pkt.get_payload() or ""
    if payload_str:
        payload_formatted = f"[magenta]'{payload_str}'[/magenta]"
    else:
        payload_formatted = "''"
    return f"[bright_black]Pkt(seq={pkt.get_seqnum()}, payload={payload_formatted}, checksum={pkt.get_checksum()})[/bright_black]"


# --- Widgets ---

class LayerWidget(Container):
    """A widget to display a single layer in a host."""
    def __init__(self, layer_name: str, **kwargs):
        super().__init__(**kwargs)
        self.layer_name = layer_name
        self.content_area = Static(classes="layer-content")

    def compose(self) -> ComposeResult:
        yield Static(f"[b]{self.layer_name}[/b]", classes="title")
        yield self.content_area

    def update_content(self, content: str):
        self.content_area.update(Panel(content or " ", expand=True))

class HostWidget(Container):
    """A widget representing a host (Sender or Receiver)."""
    def __init__(self, name: str, **kwargs):
        super().__init__(**kwargs)
        self.host_name = name
        self.l5 = LayerWidget("Application (L5)")
        self.l4 = LayerWidget("Transport (L4) (RDT)")
        self.l3 = LayerWidget("Network (L3)")

    def compose(self) -> ComposeResult:
        yield Static(f"[b]{self.host_name}[/b]", classes="title")
        yield self.l5
        yield self.l4
        yield self.l3

class NetworkWidget(Container):
    """A widget representing the network medium."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.content_area = Static(classes="network-content")

    def compose(self) -> ComposeResult:
        yield Static("[b]Network[/b]", classes="title")
        yield self.content_area

    def update_content(self, packets, event_msg=None):
        packet_renderable = None
        if packets:
            left_panels = [Panel(f"[bright_black]pkt: [/bright_black]{_format_pkt_for_tui(p['data'])} ->", expand=False) for p in packets if p['side'] == 'left']
            right_panels = [Panel(f"<- [bright_black]pkt: [/bright_black]{_format_pkt_for_tui(p['data'])}", expand=False) for p in packets if p['side'] == 'right']

            left_group = Group(*left_panels) if left_panels else ""
            right_group = Group(*right_panels) if right_panels else ""

            grid = Table.grid(expand=True)
            grid.add_column(justify="left")
            grid.add_column(justify="center", ratio=1)
            grid.add_column(justify="right")
            grid.add_row(left_group, "", right_group)
            packet_renderable = grid

        renderable_content = None
        if event_msg:
            event_renderable = Text(event_msg, justify="center")
            if packet_renderable:
                renderable_content = Group(packet_renderable, event_renderable)
            else:
                renderable_content = event_renderable
        elif packet_renderable:
            renderable_content = packet_renderable

        if renderable_content:
            self.content_area.update(renderable_content)
        else:
            self.content_area.update("")

class TuiApp(App):
    CSS_PATH = "tui.css"
    BINDINGS = [("d", "toggle_dark", "Toggle dark mode")]

    def __init__(self, event_queue, pause=0.5):
        super().__init__()
        self.event_queue = event_queue
        self.pause = pause
        self.dark = True
        self.sender = HostWidget("Sender", id="sender")
        self.network = NetworkWidget(id="network")
        self.receiver = HostWidget("Receiver", id="receiver")
        self.log_pane = RichLog(id="log_pane", max_lines=100, markup=True)
        self.network_packets = []

    def compose(self) -> ComposeResult:
        logo_container = Container(
            Static(RDT_LOGO, id="rdt_logo"),
            id="logo_container"
        )
        network_and_logo = Vertical(
            logo_container,
            self.network,
            id="network_view"
        )

        yield Header()
        yield Horizontal(
            self.sender,
            network_and_logo,
            self.receiver,
            id="main_view"
        )
        yield self.log_pane
        yield Footer()

    def on_mount(self) -> None:
        self.set_interval(self.pause, self.process_event_queue)

    def process_event_queue(self):
        if self.event_queue:
            event = self.event_queue.popleft()
            self.handle_event(event)

    def handle_event(self, event):
        event_type = event.get("type")
        host = event.get("host")
        data = event.get("data", "")

        if event_type == "DATA_FROM_APP":
            widget = self.sender if host == "Sender" else self.receiver
            widget.l5.update_content(f"[bright_black]data: [/bright_black][magenta]'{data}'[/magenta]")
        elif event_type == "L5_L4":
            widget = self.sender if host == "Sender" else self.receiver
            widget.l5.update_content("")
            widget.l4.update_content(f"[bright_black]data: [/bright_black][magenta]'{data}'[/magenta]")
        elif event_type == "PKT_FROM_RDT":
            widget = self.sender if host == "Sender" else self.receiver
            widget.l4.update_content(f"[bright_black]pkt: [/bright_black]{_format_pkt_for_tui(data)}")
        elif event_type == "L4_L3":
            widget = self.sender if host == "Sender" else self.receiver
            widget.l4.update_content("")
            widget.l3.update_content(f"[bright_black]pkt: [/bright_black]{_format_pkt_for_tui(data)}")
        elif event_type == "L3_NET":
            widget = self.sender if host == "Sender" else self.receiver
            widget.l3.update_content("")
            packet = {"data": data, "side": "left" if host == "Sender" else "right"}
            self.network_packets.append(packet)
            self.network.update_content(self.network_packets)
        elif event_type == "NET_L3":
            # Compare using manually constructed representation to avoid student's __str__ or __eq__
            pkt_repr = _get_pkt_repr(data)
            self.network_packets = [p for p in self.network_packets if _get_pkt_repr(p['data']) != pkt_repr]
            self.network.update_content(self.network_packets)
            widget = self.sender if host == "Sender" else self.receiver
            widget.l3.update_content(f"[bright_black]pkt: [/bright_black]{_format_pkt_for_tui(data)}")
        elif event_type == "L3_L4":
            widget = self.sender if host == "Sender" else self.receiver
            widget.l3.update_content("")
            widget.l4.update_content(f"[bright_black]pkt: [/bright_black]{_format_pkt_for_tui(data)}")
        elif event_type == "L4_L5":
            widget = self.sender if host == "Sender" else self.receiver
            widget.l4.update_content("")
            widget.l5.update_content(f"[bright_black]data: [/bright_black][magenta]'{data}'[/magenta]")
        elif event_type == "LOG":
             self.log_pane.write(data)
        elif event_type == "PKT_LOST":
            # Compare using manually constructed representation to avoid student's __str__ or __eq__
            pkt_repr = _get_pkt_repr(data)
            self.network_packets = [p for p in self.network_packets if _get_pkt_repr(p['data']) != pkt_repr]
            event_msg = f"[b yellow]PKT_LOST[/b]"
            self.network.update_content(self.network_packets, event_msg=event_msg)
        elif event_type == "PKT_CORRUPT":
            event_msg = f"[b yellow]PKT_CORRUPT[/b]"
            self.network.update_content(self.network_packets, event_msg=event_msg)


    def action_toggle_dark(self) -> None:
        self.dark = not self.dark
