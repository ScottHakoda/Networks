import copy
import logging
import os
import tkinter as tk
from tkinter import scrolledtext

import rdt # for isinstance check


def get_payload_color(payload):
    """Get a consistent color for a given payload character."""
    if not payload:
        return "black"
    return "red"


# This is analogous to TuiVisualizer
class GuiVisualizer:
    def __init__(self, queue):
        self.queue = queue
        self.animation_network_steps = 2
        self.is_paused = lambda: False # Start un-paused; GuiApp will override.
        self.get_pause = lambda: 1.0 # Default, GuiApp will override
        # For stepping logic
        self._should_step = lambda: False
        self._did_step = lambda: None

    def should_step(self):
        return self._should_step()

    def did_step(self):
        self._did_step()

    async def log_event(self, event_type, host=None, data=None):
        event = {"type": event_type, "host": host, "data": data}
        self.queue.append(event)


def _get_pkt_repr(pkt):
    """Manually construct a string representation of a Pkt for comparison."""
    if isinstance(pkt, rdt.Pkt):
        # Use getters to build a consistent representation
        return f"Pkt(seq={pkt.get_seqnum()}, payload='{pkt.get_payload()}', checksum={pkt.get_checksum()})"
    return str(pkt) # Fallback for non-Pkt objects

class GuiApp(tk.Tk):
    def _draw_key_value(self, canvas, x, y, key, value, key_color="black", value_color="blue", font_size=10):
        # Draw key
        key_id = canvas.create_text(x, y, text=key, anchor='nw', font=("Courier", font_size), fill=key_color)
        key_bbox = canvas.bbox(key_id)

        # Draw value next to key
        if key_bbox:
            canvas.create_text(key_bbox[2], y, text=value, anchor='nw', font=("Courier", font_size, "bold"), fill=value_color)

    def _draw_packet_on_canvas(self, canvas, data, draw_box=True):
        canvas.delete("all")
        if not data:
            return

        padding = 10

        if draw_box:
            # Bounding box for the packet/data
            canvas.create_rectangle(
                padding, padding,
                canvas.winfo_width() - padding, canvas.winfo_height() - padding,
                outline="black", fill="#fffde7" # light yellow
            )

        y_pos = padding + 5
        x_pos = padding + 5
        if isinstance(data, rdt.Pkt):
            seqnum = data.get_seqnum()
            payload = data.get_payload()
            checksum = data.get_checksum()

            self._draw_key_value(canvas, x_pos, y_pos, "seq: ", str(seqnum), value_color="#4169E1") # royal blue
            y_pos += 20
            payload_color = get_payload_color(payload)
            self._draw_key_value(canvas, x_pos, y_pos, "payload: ", f"'{payload}'", value_color=payload_color)
            y_pos += 20
            self._draw_key_value(canvas, x_pos, y_pos, "checksum: ", str(checksum), value_color="#228B22") # forest green
        else: # It's a string message
            payload_color = get_payload_color(data)
            self._draw_key_value(canvas, x_pos, y_pos, "data: ", f"'{data}'", value_color=payload_color)

    def _draw_network_packet(self, x, y, pkt_info):
        canvas = self.network_canvas
        packet_data = pkt_info['data']
        box_width = 180
        box_height = 70
        padding = 5

        fill_color = "#e3f2fd"  # light blue
        if pkt_info.get('lost') or pkt_info.get('corrupt'):
            fill_color = "#ffcdd2" # light red

        canvas.create_rectangle(
            x, y, x + box_width, y + box_height,
            outline="black", fill=fill_color
        )

        y_pos_text = y + padding
        x_pos_text = x + padding
        if isinstance(packet_data, rdt.Pkt):
            seqnum = packet_data.get_seqnum()
            payload = packet_data.get_payload()
            checksum = packet_data.get_checksum()

            self._draw_key_value(canvas, x_pos_text, y_pos_text, "seq: ", str(seqnum), value_color="#4169E1")
            y_pos_text += 20
            payload_color = get_payload_color(payload)
            self._draw_key_value(canvas, x_pos_text, y_pos_text, "payload: ", f"'{payload}'", value_color=payload_color)
            y_pos_text += 20
            self._draw_key_value(canvas, x_pos_text, y_pos_text, "checksum: ", str(checksum), value_color="#228B22")
        else:
            pkt_str = _get_pkt_repr(packet_data)
            canvas.create_text(x + padding, y_pos_text, text=pkt_str, anchor='nw', font=("Courier", 10), width=box_width - 2*padding)


    def __init__(self, event_queue, pause=0.5, animation_network_steps=3, visualizer=None):
        super().__init__()
        self.event_queue = event_queue
        self.pause_value = tk.DoubleVar(value=pause)
        self.visualizer = visualizer
        if visualizer:
            visualizer.is_paused = lambda: self.is_paused
            visualizer.get_pause = self.pause_value.get
            visualizer.is_stepping = False
            visualizer._should_step = lambda: visualizer.is_stepping
            visualizer._did_step = lambda: setattr(visualizer, 'is_stepping', False)
        self.animation_network_steps = animation_network_steps

        self.title("RDT Simulator")
        self.geometry("1200x800")
        self.bind('<Escape>', lambda e: self.destroy())

        # Playback control state
        self.is_paused = False
        self.event_history = []
        self.current_event_index = -1

        # Data models for UI state
        self.sender_layers = {"L5": {"all": "", "next_idx": -1}, "L4": "", "L3": ""}
        self.receiver_layers = {"L5": "", "L4": "", "L3": ""}
        self.network_packets = []
        self.network_event_msg = ""
        self.corrupted_packet_repr = None

        # Store initial state for replay
        self.initial_sender_layers = copy.deepcopy(self.sender_layers)
        self.initial_receiver_layers = copy.deepcopy(self.receiver_layers)

        self._create_widgets()
        self.process_event_queue()

    def _create_widgets(self):
        # Configure grid layout for the main window
        self.grid_rowconfigure(0, weight=2) # Top row for hosts and logo
        self.grid_rowconfigure(1, weight=3) # Bottom row for network
        self.grid_columnconfigure(0, weight=1)

        # Top frame for hosts and logo
        top_frame = tk.Frame(self)
        top_frame.grid(row=0, column=0, sticky="nsew", pady=10)
        top_frame.grid_columnconfigure(0, weight=1) # Sender column
        top_frame.grid_columnconfigure(1, weight=0) # Logo column (no expand)
        top_frame.grid_columnconfigure(2, weight=1) # Receiver column
        top_frame.grid_rowconfigure(0, weight=1)

        # Host widgets
        self.sender_frame = self._create_host_widget(top_frame, "Sender")
        self.sender_frame.grid(row=0, column=0, sticky="nsew", padx=10)

        # Logo and controls in the middle column
        middle_column_frame = tk.Frame(top_frame)
        middle_column_frame.grid(row=0, column=1, sticky="ns", padx=10)
        middle_column_frame.grid_rowconfigure(0, weight=0) # Logo should not expand
        middle_column_frame.grid_rowconfigure(1, weight=0) # Controls should not expand

        logo_container = tk.Frame(middle_column_frame)
        logo_container.grid(row=0, column=0, sticky="n")

        try:
            # Path is relative to the script location
            logo_path = os.path.join(os.path.dirname(__file__), 'doc', 'logo.gif')
            logo_img = tk.PhotoImage(file=logo_path)
            # Scale the image down by a factor of 3 to better fit the window
            self.logo_photo = logo_img.subsample(3, 3)

            logo_label = tk.Label(logo_container, image=self.logo_photo)
            logo_label.pack(side=tk.TOP, pady=10)
        except tk.TclError as e:
            # Fallback or error message if logo loading fails
            tk.Label(logo_container, text="RDT Simulator", font=("Helvetica", 24, "bold")).pack(side=tk.TOP, pady=10)
            print(f"Could not load logo: {e}")

        # Controls container
        controls_container = tk.Frame(middle_column_frame)
        controls_container.grid(row=1, column=0, sticky="n")

        button_frame = tk.Frame(controls_container)
        button_frame.pack(side=tk.TOP, pady=(10, 0))

        self.step_back_button = tk.Button(button_frame, text="< Step Back", command=self._step_back, state=tk.DISABLED)
        self.step_back_button.pack(side=tk.LEFT, padx=5)

        self.pause_button = tk.Button(button_frame, text="Pause", command=self._toggle_pause, width=12)
        self.pause_button.pack(side=tk.LEFT, padx=5)

        self.step_forward_button = tk.Button(button_frame, text="Step Forward >", command=self._step_forward, state=tk.DISABLED)
        self.step_forward_button.pack(side=tk.LEFT, padx=5)

        # Slider for simulation speed
        speed_slider_frame = tk.Frame(controls_container)
        speed_slider_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(5,0))

        tk.Label(speed_slider_frame, text="Fast").pack(side=tk.LEFT)
        speed_slider = tk.Scale(speed_slider_frame, from_=0.1, to=4.0, resolution=0.1, orient=tk.HORIZONTAL, variable=self.pause_value, showvalue=0)
        speed_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        tk.Label(speed_slider_frame, text="Slow").pack(side=tk.LEFT)

        self.receiver_frame = self._create_host_widget(top_frame, "Receiver")
        self.receiver_frame.grid(row=0, column=2, sticky="nsew", padx=10)

        # Network widget in its own row at the bottom
        self.network_frame = self._create_network_widget(self)
        self.network_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

    def _create_host_widget(self, parent, name):
        frame = tk.LabelFrame(parent, text=name, padx=10, pady=10)
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_rowconfigure(2, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        l5_frame = tk.LabelFrame(frame, text="Application (L5)", padx=5, pady=2)
        l5_frame.grid(row=0, column=0, sticky="nsew", pady=2)
        l5_frame.pack_propagate(False)
        l5_content = tk.Canvas(l5_frame, highlightthickness=0)
        l5_content.pack(fill=tk.BOTH, expand=True)

        l4_frame = tk.LabelFrame(frame, text="Transport (L4) (RDT)", padx=5, pady=2)
        l4_frame.grid(row=1, column=0, sticky="nsew", pady=2)
        l4_frame.pack_propagate(False)
        l4_content = tk.Canvas(l4_frame, highlightthickness=0)
        l4_content.pack(fill=tk.BOTH, expand=True)

        l3_frame = tk.LabelFrame(frame, text="Network (L3)", padx=5, pady=2)
        l3_frame.grid(row=2, column=0, sticky="nsew", pady=2)
        l3_frame.pack_propagate(False)
        l3_content = tk.Canvas(l3_frame, highlightthickness=0)
        l3_content.pack(fill=tk.BOTH, expand=True)

        # store references to content labels
        if name == "Sender":
            self.sender_labels = {"L5": l5_content, "L4": l4_content, "L3": l3_content}
        else:
            self.receiver_labels = {"L5": l5_content, "L4": l4_content, "L3": l3_content}

        return frame

    def _create_network_widget(self, parent):
        frame = tk.LabelFrame(parent, text="Network", padx=10, pady=10)
        self.network_canvas = tk.Canvas(frame, bg="white")
        self.network_canvas.pack(fill=tk.BOTH, expand=True)
        return frame

    def _redraw_network(self):
        self.network_canvas.delete("all")
        width = self.network_canvas.winfo_width()
        height = self.network_canvas.winfo_height()

        if self.network_event_msg:
            self.network_canvas.create_text(width/2, height/2, text=self.network_event_msg, fill="red", font=("Helvetica", 16, "bold"))

        y_pos = 10
        box_width = 180
        box_height = 70
        for pkt_info in self.network_packets:
            packet_data = pkt_info['data']

            pos = pkt_info.get('pos', 0 if pkt_info['side'] == 'left' else self.animation_network_steps)

            # Calculate x_pos based on position steps
            x_start = 20
            x_end = width - 20 - box_width
            if self.animation_network_steps > 0:
                x_pos = x_start + (x_end - x_start) * (pos / self.animation_network_steps)
            else:
                x_pos = x_start # fallback for no steps

            self._draw_network_packet(x_pos, y_pos, pkt_info)
            y_pos += box_height + 10 # so packets don't overlap

    def _draw_sender_l5_canvas(self, canvas, data):
        canvas.delete("all")
        text_to_draw = data.get("all", "")
        if not text_to_draw:
            return

        padding = 10
        font_size = 12
        font_family = "Courier"

        # Draw each character with its color
        x_offset = padding
        for i, char in enumerate(text_to_draw):
            color = get_payload_color(char)
            char_id = canvas.create_text(x_offset, padding, text=char, anchor='nw', font=(font_family, font_size, "bold"), fill=color)
            bbox = canvas.bbox(char_id)
            if bbox:
                x_offset = bbox[2] + 2 # Move to the end of the last character, with a small gap

        next_idx = data.get("next_idx", -1)
        if next_idx == 0:
            char_to_box = text_to_draw[0]
            # Use a dummy item to get the bounding box for the first character
            dummy_id = canvas.create_text(padding, padding, text=char_to_box, anchor='nw', font=(font_family, font_size, "bold"))
            bbox = canvas.bbox(dummy_id)
            canvas.delete(dummy_id)
            if bbox:
                x0, y0, x1, y1 = bbox
                canvas.create_rectangle(x0 - 2, y0 - 2, x1 + 2, y1 + 2, outline="red", width=1.5)

    def _draw_receiver_l5_canvas(self, canvas, data):
        canvas.delete("all")
        if not data:
            return

        padding = 10
        font_size = 12
        font_family = "Courier"

        x_offset = padding
        for char in data:
            color = get_payload_color(char)
            char_id = canvas.create_text(x_offset, padding, text=char, anchor='nw', font=(font_family, font_size, "bold"), fill=color)
            bbox = canvas.bbox(char_id)
            if bbox:
                x_offset = bbox[2] + 2 # with a small gap

    def process_event_queue(self):
        if not self.is_paused:
            if self.event_queue:
                event = self.event_queue.popleft()
                self.event_history.append(event)
                self.current_event_index += 1
                self.handle_event(event)

        # Dynamically adjust polling interval based on slider
        poll_interval_ms = max(25, int(self.pause_value.get() * 1000 / 4))
        self.after(poll_interval_ms, self.process_event_queue)

    def _toggle_pause(self):
        # This button is only enabled when at the live edge of history
        self.is_paused = not self.is_paused
        self.pause_button.config(text="Resume" if self.is_paused else "Pause")

        # Stepping buttons should be disabled when not paused
        state = tk.NORMAL if self.is_paused else tk.DISABLED
        self.step_forward_button.config(state=state)
        self.step_back_button.config(state=state)

    def _wait_for_step_event(self):
        if self.event_queue:
            # Event(s) arrived. Process one.
            event = self.event_queue.popleft()
            self.event_history.append(event)
            self.current_event_index += 1
            self.handle_event(event)
            # Re-enable buttons
            self.step_forward_button.config(state=tk.NORMAL)
            self.step_back_button.config(state=tk.NORMAL)
        else:
            # Simulator hasn't produced an event yet. Check again.
            self.after(50, self._wait_for_step_event)

    def _step_forward(self):
        # This button is only enabled when paused
        if self.current_event_index < len(self.event_history) - 1:
            # Replaying history: get next event from history
            self.current_event_index += 1
            event = self.event_history[self.current_event_index]
            self.handle_event(event)
        elif self.event_queue: # At live edge, and there are events to process
            event = self.event_queue.popleft()
            self.event_history.append(event)
            self.current_event_index += 1
            self.handle_event(event)
        else:
            # Live edge and queue is empty: signal simulator to run one step.
            if self.visualizer and not self.visualizer.is_stepping: # prevent multiple requests
                self.visualizer.is_stepping = True
                # Disable buttons while we wait for the simulator
                self.step_forward_button.config(state=tk.DISABLED)
                self.step_back_button.config(state=tk.DISABLED)
                # Poll for the result
                self.after(50, self._wait_for_step_event)

        # After stepping, if we are at the live edge, enable the pause button
        if self.current_event_index == len(self.event_history) - 1:
            self.pause_button.config(state=tk.NORMAL)

    def _step_back(self):
        # This button is only enabled when paused
        if self.current_event_index >= 0:
            self.current_event_index -= 1
            self._replay_from_start()
            # Since we stepped back, we are in history, so disable pause button
            self.pause_button.config(state=tk.DISABLED)

    def _replay_from_start(self):
        # Reset state to the very beginning
        self.sender_layers = copy.deepcopy(self.initial_sender_layers)
        self.receiver_layers = copy.deepcopy(self.initial_receiver_layers)
        self.network_packets = []
        self.network_event_msg = ""
        self.corrupted_packet_repr = None

        # Replay all events from history up to the current index
        for i in range(self.current_event_index + 1):
            self.handle_event(self.event_history[i])

        # If we've stepped back to before any events, we need to explicitly redraw the empty state
        if self.current_event_index == -1:
            self._draw_sender_l5_canvas(self.sender_labels["L5"], self.sender_layers["L5"])
            self._draw_packet_on_canvas(self.sender_labels["L4"], self.sender_layers["L4"], draw_box=isinstance(self.sender_layers["L4"], rdt.Pkt))
            self._draw_packet_on_canvas(self.sender_labels["L3"], self.sender_layers["L3"])

            self._draw_receiver_l5_canvas(self.receiver_labels["L5"], self.receiver_layers["L5"])
            self._draw_packet_on_canvas(self.receiver_labels["L4"], self.receiver_layers["L4"])
            self._draw_packet_on_canvas(self.receiver_labels["L3"], self.receiver_layers["L3"])

            self._redraw_network()

    def handle_event(self, event):
        event_type = event.get("type")
        host = event.get("host")
        data = event.get("data", "")

        widget_layers = self.sender_layers if host == "Sender" else self.receiver_layers

        if event_type == "APP_INIT":
            if host == "Sender":
                self.sender_layers["L5"]["all"] = data
            else: # Receiver
                self.receiver_layers["L5"] = data
        elif event_type == "DATA_FROM_APP":
            if host == "Sender":
                self.sender_layers["L5"]["next_idx"] = 0
        elif event_type == "L5_L4":
            if host == "Sender":
                self.sender_layers["L4"] = data
                if self.sender_layers["L5"]["all"]:
                    self.sender_layers["L5"]["all"] = self.sender_layers["L5"]["all"][1:]
                self.sender_layers["L5"]["next_idx"] = -1
        elif event_type == "PKT_FROM_RDT":
            widget_layers["L4"] = data
        elif event_type == "L4_L3":
            widget_layers["L4"] = ""
            widget_layers["L3"] = data
        elif event_type == "L3_NET":
            # A new network event clears any 'lost' packet displays.
            self.network_packets = [p for p in self.network_packets if not p.get('lost')]
            widget_layers["L3"] = ""
            pos = 0 if host == "Sender" else self.animation_network_steps
            packet = {"data": data, "side": "left" if host == "Sender" else "right", "pos": pos}
            if self.corrupted_packet_repr and self.corrupted_packet_repr == _get_pkt_repr(data):
                packet['corrupt'] = True
                self.corrupted_packet_repr = None # One-time use
            self.network_packets.append(packet)
            self.network_event_msg = ""
        elif event_type == "GUI_ANIMATE":
            pkt_to_animate_repr = _get_pkt_repr(data['pkt'])
            new_pos = data['pos']
            for p in self.network_packets:
                if _get_pkt_repr(p['data']) == pkt_to_animate_repr:
                    p['pos'] = new_pos
                    break
        elif event_type == "NET_L3":
            # A new network event clears any 'lost' packet displays.
            self.network_packets = [p for p in self.network_packets if not p.get('lost')]
            pkt_repr = _get_pkt_repr(data)
            # Remove packet from network view and update arrival layer
            self.network_packets = [p for p in self.network_packets if _get_pkt_repr(p['data']) != pkt_repr]
            widget_layers["L3"] = data
            self.network_event_msg = ""
        elif event_type == "L3_L4":
            widget_layers["L3"] = ""
            widget_layers["L4"] = data
        elif event_type == "L4_L5":
            if host == "Receiver":
                self.receiver_layers["L4"] = ""
                if data:
                    self.receiver_layers["L5"] += data[0]
        elif event_type == "L4_L5_REJECT":
            if host == "Sender":
                self.sender_layers["L4"] = ""
                if data:
                    self.sender_layers["L5"]["all"] = data[0] + self.sender_layers["L5"]["all"]
                self.sender_layers["L5"]["next_idx"] = -1
        elif event_type == "TIMEOUT":
            # RDT has decided to resend, so clear the lost packet display
            self.network_packets = [p for p in self.network_packets if not p.get('lost')]
            self.network_event_msg = "TIMEOUT"
        elif event_type == "PKT_LOST":
            # Remove the original packet from network view, and add a 'lost' marker in its place.
            pkt_repr = _get_pkt_repr(data)
            self.network_packets = [p for p in self.network_packets if _get_pkt_repr(p['data']) != pkt_repr]

            pos = self.animation_network_steps // 2
            packet = {"data": data, "side": "left" if host == "Sender" else "right", "pos": pos, "lost": True}
            self.network_packets.append(packet)
            self.network_event_msg = "PKT_LOST"
        elif event_type == "PKT_CORRUPT":
            self.network_event_msg = "PKT_CORRUPT"
            self.corrupted_packet_repr = _get_pkt_repr(data)

        # Update canvases and redraw network
        self._draw_sender_l5_canvas(self.sender_labels["L5"], self.sender_layers["L5"])
        self._draw_packet_on_canvas(self.sender_labels["L4"], self.sender_layers["L4"], draw_box=isinstance(self.sender_layers["L4"], rdt.Pkt))
        self._draw_packet_on_canvas(self.sender_labels["L3"], self.sender_layers["L3"])

        self._draw_receiver_l5_canvas(self.receiver_labels["L5"], self.receiver_layers["L5"])
        self._draw_packet_on_canvas(self.receiver_labels["L4"], self.receiver_layers["L4"])
        self._draw_packet_on_canvas(self.receiver_labels["L3"], self.receiver_layers["L3"])

        self._redraw_network()

    def run(self):
        self.mainloop()
