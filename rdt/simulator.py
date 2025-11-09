import asyncio
import heapq
import logging
import random
import string
import threading
import time

import rdt

sim_logger = logging.getLogger(__name__)

# possible events:
TIMER_INTERRUPT = 0
FROM_LAYER5 = 1
FROM_LAYER3 = 2
GUI_ANIMATE = 3
NETWORK_EFFECT = 4

# helpful consts
A = 0
B = 1
ENTITIES = {A: "Sender", B: "Receiver"}
EVENTS = {TIMER_INTERRUPT: "TIMER_INTERRUPT", FROM_LAYER5: "FROM_LAYER5", FROM_LAYER3: "FROM_LAYER3", GUI_ANIMATE: "GUI_ANIMATE", NETWORK_EFFECT: "NETWORK_EFFECT"}

class Event:

    def __init__(self):
        self.time = None    # event time
        self.type = None    # event type code
        self.entity = None  # entity where event occurs
        self.pkt = None     # packet (if any) assoc w/ this event
        self.cancelled = False

    def __lt__(self, other):
        return self.time < other.time

    def __str__(self):
        s = "Event("
        s += "entity=" + ENTITIES[self.entity]
        s += ", time={:.03f}".format(self.time if self.time else -1)
        s += ", type=" + EVENTS[self.type]
        if self.pkt is not None:
            # Use getters to avoid calling student's __str__
            if self.type == GUI_ANIMATE:
                pkt_data = self.pkt['pkt']
                pos = self.pkt['pos']
                s += f", anim_pkt=Pkt(seq={pkt_data.get_seqnum()}), pos={pos}"
            elif self.type == NETWORK_EFFECT:
                pkt_data = self.pkt['packet']
                s += f", net_effect_pkt=Pkt(seq={pkt_data.get_seqnum()})"
            elif isinstance(self.pkt, rdt.Pkt):
                s += f", packet=Pkt(seq={self.pkt.get_seqnum()})"
            else:
                s += f", packet=INVALID({str(self.pkt)})"
        return s + ")"

class Simulator:

    def __init__(self, n_sim_msgs, msg_freq, loss_prob, corrupt_prob, pause, visualizer=None):
        self.n_sim_msgs = n_sim_msgs        # number of msgs to simulate
        self.msg_freq = msg_freq            # avg msg send rate (lambda_) TODO: is it really?
        self.loss_prob = loss_prob          # probability msgs will be lost
        self.corrupt_prob = corrupt_prob    # probability msgs will be corrupted
        self.pause = pause                  # time to wait between events
        self.visualizer = visualizer

        self.events = []    # the event log
        self.sent = []      # the msgs sent
        self.received = []  # the msgs received

        self.timer_A = None
        self.timer_B = None

        self.msg_count = 0        # number of messages from 5 to 4 so far
        self.tolayer3_count = 0   # number sent into layer 3
        self.lost_count = 0       # number lost in media
        self.corrupt_count = 0    # number corrupted by media
        self.t = 0.0              # time

    def get_params(self):
        return (f'\tnmsgs       = {self.n_sim_msgs}\n' +
                f'\tfreq        = {self.msg_freq}\n' +
                f'\tlossprob    = {self.loss_prob}\n' +
                f'\tcorruptprob = {self.corrupt_prob}\n' +
                f'\tpause       = {self.pause}\n')

    def _format_pkt_log(self, pkt):
        if not isinstance(pkt, rdt.Pkt):
            return f"[bright_black]Pkt([red]invalid:{str(pkt)}[/red])[/bright_black]"
        payload_str = pkt.get_payload() or ""
        if payload_str:
            payload_formatted = f"[magenta]'{payload_str}'[/magenta]"
        else:
            payload_formatted = "''"
        return f"[bright_black]Pkt(seq={pkt.get_seqnum()}, payload={payload_formatted}, checksum={pkt.get_checksum()})[/bright_black]"

    def _format_pkt_console(self, pkt):
        if not isinstance(pkt, rdt.Pkt):
            return f"Pkt(invalid:{str(pkt)})"
        payload_str = pkt.get_payload() or ""
        return f"Pkt(seq={pkt.get_seqnum()}, payload='{payload_str}', checksum={pkt.get_checksum()})"

    def generate_next_arrival(self):
        sim_logger.debug(f"[{self.t:8.2f}] GEN_NEXT_ARR: creating new arrival")

        # time x is from an exponential distribution with average self.msg_freq
        x = random.expovariate(1.0/self.msg_freq)

        newevent = Event()
        newevent.time = self.t+x
        newevent.type = FROM_LAYER5
        newevent.entity = A
        self.insert_event(newevent)

    def insert_event(self, event):
        """insert event into event list according to its time"""
        sim_logger.debug(f"[{self.t:8.2f}] INSERT_EVENT: time is {self.t:.03f}")
        sim_logger.debug(f"[{self.t:8.2f}] INSERT_EVENT: future time will be {event.time:.03f}")
        heapq.heappush(self.events, event)

    def get_next_event(self):
        # get next event to simulate, removing from event list
        while self.events:
            event = heapq.heappop(self.events)
            if not event.cancelled:
                self.t = event.time # update time to next event time
                sim_logger.debug(f"[{self.t:8.2f}] NEXT_EVENT: {event}")
                return event
        return None # No more valid events

    def print_events(self):
        print("-"*15)
        for event in self.events:
            print(event)
        print("-"*15)

    def check_end(self):
        return len(self.events) == 0 or self.n_sim_msgs == self.msg_count

    def stop_timer(self, AorB):
        """AorB: is A or B trying to stop the timer"""
        sim_logger.debug(f"[{self.t:8.2f}] STOP_TIMER: for {ENTITIES[AorB]}")

        timer_to_stop = None
        if AorB == A:
            timer_to_stop = self.timer_A
            self.timer_A = None
        else:
            timer_to_stop = self.timer_B
            self.timer_B = None

        if timer_to_stop:
            timer_to_stop.cancelled = True
        else:
            sim_logger.warning("unable to cancel your timer. It wasn't running.")

    def start_timer(self, AorB, increment):
        """AorB: A or B is trying to start timer"""
        sim_logger.debug(f"[{self.t:8.2f}] START_TIMER: for {ENTITIES[AorB]} duration {increment}")

        active_timer = self.timer_A if AorB == A else self.timer_B
        if active_timer:
            sim_logger.warning("attempt to start a timer that is already started")
            return

        # create future event for when timer goes off
        newevent = Event()
        newevent.time = self.t + increment
        newevent.type = TIMER_INTERRUPT
        newevent.entity = AorB

        if AorB == A:
            self.timer_A = newevent
        else:
            self.timer_B = newevent

        self.insert_event(newevent)

    def tolayer3(self, AorB, packet):
        """AorB: A or B is sending a packet"""
        self.tolayer3_count += 1

        # make a copy of the packet student just gave me since they may decide
        # to do something with the packet after we return back to them
        mypkt = rdt.Pkt()
        mypkt.set_seqnum(packet.get_seqnum())
        mypkt.set_payload(packet.get_payload())
        mypkt.set_checksum(packet.get_checksum())
        sim_logger.debug(f"[{self.t:8.2f}] TOLAYER3: seq: {mypkt.get_seqnum()} check: {mypkt.get_checksum()} {mypkt.get_payload()}")

        # create future event for arrival of packet at the other side
        arrival_event = Event()
        arrival_event.type = FROM_LAYER3    # packet will pop out from layer3
        arrival_event.entity = (AorB+1) % 2 # event occurs at other entity
        arrival_event.pkt = mypkt           # save my copy of packet
        # finally, compute the arrival time of packet at the other end.
        # medium can not reorder, so make sure packet arrives between 1 and 10
        # time units after the latest arrival time of packets
        # currently in the medium on their way to the destination
        last_time = self.t

        for event in self.events:
            if event.type == FROM_LAYER3 and event.entity == arrival_event.entity:
                last_time = event.time

        if self.visualizer:
            # For GUI mode, transit time is deterministic and based on animation settings
            # to provide a consistent visual speed.
            animation_network_steps = self.visualizer.animation_network_steps
            # Each animation step will visually take pause/2 seconds.
            step_interval = self.visualizer.get_pause() / 2.0
            total_duration = step_interval * (animation_network_steps + 1)
            arrival_event.time = last_time + total_duration

            # Schedule the animation events using the step_interval calculated above.
            if AorB == A: # Sender -> Receiver
                for i in range(1, animation_network_steps + 1):
                    anim_event = Event()
                    anim_event.time = self.t + i * step_interval
                    anim_event.type = GUI_ANIMATE
                    anim_event.entity = AorB
                    anim_event.pkt = {'pkt': mypkt, 'pos': i}
                    self.insert_event(anim_event)
            else: # Receiver -> Sender
                for i in range(1, animation_network_steps + 1):
                    anim_event = Event()
                    anim_event.time = self.t + i * step_interval
                    anim_event.type = GUI_ANIMATE
                    anim_event.entity = AorB
                    pos = animation_network_steps - i
                    anim_event.pkt = {'pkt': mypkt, 'pos': pos}
                    self.insert_event(anim_event)
        else:
            # For non-visual modes, use random transit time.
            arrival_event.time = last_time + random.uniform(0.5, 5)

        # Schedule a network effect event to happen mid-transit
        network_effect_event = Event()
        transit_duration = arrival_event.time - self.t
        network_effect_event.time = self.t + transit_duration / 2.0
        network_effect_event.type = NETWORK_EFFECT
        network_effect_event.entity = AorB
        network_effect_event.pkt = {'packet': mypkt, 'arrival_event': arrival_event}
        self.insert_event(network_effect_event)

        if self.visualizer:
            asyncio.run(self.visualizer.log_event("PKT_FROM_RDT", host=ENTITIES[AorB], data=mypkt))
            asyncio.run(self.visualizer.log_event("L4_L3", host=ENTITIES[AorB], data=mypkt))
            asyncio.run(self.visualizer.log_event("L3_NET", host=ENTITIES[AorB], data=mypkt))
        sim_logger.debug(f"[{self.t:8.2f}] TOLAYER3: scheduling arrival on other side: {arrival_event}")
        self.insert_event(arrival_event)

    def tolayer5(self, AorB, msg):
        sim_logger.info(f"[{self.t:8.2f}]   L4->L5       @ {ENTITIES[AorB]:<9}: delivered data: '{msg}'")
        if self.visualizer:
            if getattr(self.visualizer, 'log_to_pane', False):
                self.visualizer.queue.append({"type": "LOG", "data": f"[green][{self.t:8.2f}][/green]   [cyan]L4->L5       [/cyan] @ [blue]{ENTITIES[AorB]:<9}[/blue]: [bright_black]delivered data: [/bright_black][magenta]'{msg}'[/magenta]\n"})
            asyncio.run(self.visualizer.log_event("L4_L5", host=ENTITIES[AorB], data=msg))
        self.received.append(msg[-1])

    def run(self, sender_class, receiver_class):
        # Instantiate the RDT entities, giving them the correct abstractions
        udt_A = UDT(self, A)
        timer_A = Timer(self, A)
        sender = sender_class(udt_A, timer_A)

        udt_B = UDT(self, B)
        app_layer_B = AppLayer(self, B)
        receiver = receiver_class(udt_B, app_layer_B)

        self.generate_next_arrival()     # initialize event list

        if self.visualizer:
            all_msgs_chars = "".join([string.ascii_lowercase[i%26] for i in range(self.n_sim_msgs)])
            asyncio.run(self.visualizer.log_event("APP_INIT", host=ENTITIES[A], data=all_msgs_chars))
            asyncio.run(self.visualizer.log_event("APP_INIT", host=ENTITIES[B], data=""))

        while not self.check_end():
            if not self.visualizer:
                time.sleep(self.pause)
                sim_logger.info("")
            else:
                # When stepping, is_paused is true, but should_step will be true for one event.
                is_stepping_now = self.visualizer.should_step()
                if self.visualizer.is_paused() and not is_stepping_now:
                    time.sleep(0.1) # Polling for state change
                    continue

                # If running continuously, apply pause between events.
                # If stepping, don't pause. "ignore time"
                if not self.visualizer.is_paused():
                    time.sleep(self.visualizer.get_pause())

            event = self.get_next_event()
            if not event: # All remaining events were cancelled
                break

            if event.type == FROM_LAYER5:
                # fill in msg to give with string of same letter
                msg2give = string.ascii_lowercase[self.msg_count%26]

                if event.entity == A:
                    # Log the L5->L4 transition first for correct event ordering in GUI.
                    sim_logger.info(f"[{self.t:8.2f}]   L5->L4       @ {ENTITIES[A]:<9}: sending data: '{msg2give}'")
                    if self.visualizer:
                        if getattr(self.visualizer, 'log_to_pane', False):
                            self.visualizer.queue.append({"type": "LOG", "data": f"[green][{self.t:8.2f}][/green]   [cyan]L5->L4       [/cyan] @ [blue]{ENTITIES[A]:<9}[/blue]: [bright_black]sending data: [/bright_black][magenta]'{msg2give}'[/magenta]\n"})
                        asyncio.run(self.visualizer.log_event("DATA_FROM_APP", host=ENTITIES[A], data=msg2give[0]))
                        asyncio.run(self.visualizer.log_event("L5_L4", host=ENTITIES[A], data=msg2give))

                    # Try to send the message. If the sender is busy, rdt_send will return False.
                    if not sender.rdt_send(msg2give):
                        sim_logger.info(f"[{self.t:8.2f}]   L5->L4       @ {ENTITIES[A]:<9}: sender busy, will retry '{msg2give}'")
                        if self.visualizer:
                            # Revert GUI state since sender was busy
                            asyncio.run(self.visualizer.log_event("L4_L5_REJECT", host=ENTITIES[A], data=msg2give))

                        # The sender is busy, so we'll reschedule this message to be sent
                        # later. To avoid a busy-wait loop, we'll schedule it for after
                        # all current in-flight packets have arrived.
                        max_arrival_time = self.t
                        for e in self.events:
                            if e.type == FROM_LAYER3 and e.time > max_arrival_time:
                                max_arrival_time = e.time

                        event.time = max_arrival_time + 0.01
                        self.insert_event(event)
                        continue

                # If accepted, proceed with simulation as normal for this message.
                self.generate_next_arrival()   # set up future arrival
                self.sent.append(msg2give[-1])
                self.msg_count += 1

            elif event.type == FROM_LAYER3:
                pkt2give = event.pkt

                # deliver packet by calling the appropriate entity
                if self.visualizer:
                    if getattr(self.visualizer, 'log_to_pane', False):
                        if event.entity == A:
                            self.visualizer.queue.append({"type": "LOG", "data": f"[green][{self.t:8.2f}][/green]   [cyan]L3->L4       [/cyan] @ [blue]{ENTITIES[A]:<9}[/blue]: [bright_black]ack received: [/bright_black]{self._format_pkt_log(pkt2give)}\n"})
                        else:
                            self.visualizer.queue.append({"type": "LOG", "data": f"[green][{self.t:8.2f}][/green]   [cyan]L3->L4       [/cyan] @ [blue]{ENTITIES[B]:<9}[/blue]: [bright_black]data received: [/bright_black]{self._format_pkt_log(pkt2give)}\n"})
                    asyncio.run(self.visualizer.log_event("NET_L3", host=ENTITIES[event.entity], data=pkt2give))
                    asyncio.run(self.visualizer.log_event("L3_L4", host=ENTITIES[event.entity], data=pkt2give))

                if event.entity == A:
                    sim_logger.info(f"[{self.t:8.2f}]   L3->L4       @ {ENTITIES[A]:<9}: ack received: {self._format_pkt_console(pkt2give)}")
                    sender.rdt_rcv(pkt2give)
                else:
                    sim_logger.info(f"[{self.t:8.2f}]   L3->L4       @ {ENTITIES[B]:<9}: data received: {self._format_pkt_console(pkt2give)}")
                    receiver.rdt_rcv(pkt2give)

            elif event.type == TIMER_INTERRUPT:
                if event.entity == A:
                    self.timer_A = None
                    sim_logger.info(f"[{self.t:8.2f}]   TIMEOUT      @ {ENTITIES[A]:<9}: timer interrupt")
                    if self.visualizer:
                         # no async here, it's a direct log
                         if getattr(self.visualizer, 'log_to_pane', False):
                             self.visualizer.queue.append({"type": "LOG", "data": f"[green][{self.t:8.2f}][/green]   [red]TIMEOUT      [/red] @ [blue]{ENTITIES[A]:<9}[/blue]: [bright_black]timer interrupt[/bright_black]\n"})
                         asyncio.run(self.visualizer.log_event("TIMEOUT", host=ENTITIES[A]))
                    sender.timer_interrupt()
            elif event.type == NETWORK_EFFECT:
                arrival_event = event.pkt['arrival_event']
                packet = event.pkt['packet']

                # simulate losses:
                if random.random() < self.loss_prob:
                    self.lost_count += 1
                    arrival_event.cancelled = True
                    sim_logger.warning(f"[{self.t:8.2f}]   PKT_LOST     @ Network  : {self._format_pkt_console(packet)}")
                    if self.visualizer:
                        if getattr(self.visualizer, 'log_to_pane', False):
                            self.visualizer.queue.append({"type": "LOG", "data": f"[green][{self.t:8.2f}][/green]   [yellow]PKT_LOST     [/yellow] @ [blue]Network[/blue]  : {self._format_pkt_log(packet)}\n"})
                        # The host is where it was sent FROM. The event's entity is where it was sent from.
                        asyncio.run(self.visualizer.log_event("PKT_LOST", host=ENTITIES[event.entity], data=packet))
                    continue # Use continue to skip corruption check if lost.

                # simulate corruption:
                if random.random() < self.corrupt_prob:
                    self.corrupt_count += 1
                    # this will modify the packet within the arrival_event
                    pkt_to_corrupt = arrival_event.pkt
                    x = random.random()
                    if x < 0.75 and len(pkt_to_corrupt.get_payload()) > 0:
                        payload = pkt_to_corrupt.get_payload()
                        pos = random.randint(0, len(payload)-1)
                        # select a random character from the alphabet
                        char = random.choice(string.ascii_letters)
                        new_payload = payload[:pos] + char + payload[pos+1:]
                        pkt_to_corrupt.set_payload(new_payload)
                    elif x < 0.875:
                        pkt_to_corrupt.set_seqnum(999999)
                    else:
                        checksum = pkt_to_corrupt.get_checksum()
                        pkt_to_corrupt.set_checksum(1 if checksum is None else checksum + 1)
                    sim_logger.warning(f"[{self.t:8.2f}]   PKT_CORRUPT  @ Network  : {self._format_pkt_console(pkt_to_corrupt)}")
                    if self.visualizer:
                        if getattr(self.visualizer, 'log_to_pane', False):
                            self.visualizer.queue.append({"type": "LOG", "data": f"[green][{self.t:8.2f}][/green]   [yellow]PKT_CORRUPT  [/yellow] @ [blue]Network[/blue]  : {self._format_pkt_log(pkt_to_corrupt)}\n"})
                        asyncio.run(self.visualizer.log_event("PKT_CORRUPT", host="Network", data=pkt_to_corrupt))
            elif event.type == GUI_ANIMATE:
                if self.visualizer:
                    asyncio.run(self.visualizer.log_event("GUI_ANIMATE", host=ENTITIES[event.entity], data=event.pkt))
            else:
                sim_logger.critical("INTERNAL PANIC: unknown event type")

            if self.visualizer and 'is_stepping_now' in locals() and is_stepping_now:
                self.visualizer.did_step()

        sim_logger.info(f"\nSimulator terminated at time {self.t:.03f} after "
              f"sending {self.msg_count}/{self.n_sim_msgs} msgs from layer 5.")
        sim_logger.info(f"STATS: {self.tolayer3_count} packets sent, {self.lost_count} lost, {self.corrupt_count} corrupted.")
        sim_logger.info(f"Sent    : {self.sent}")
        sim_logger.info(f"Received: {self.received}")


class UDT:
    """Unreliable Data Transfer channel."""
    def __init__(self, simulator, entity):
        self.simulator = simulator
        self.entity = entity

    def send(self, packet):
        """Send a packet over the channel."""
        self.simulator.tolayer3(self.entity, packet)


class AppLayer:
    """Application Layer interface."""
    def __init__(self, simulator, entity):
        self.simulator = simulator
        self.entity = entity

    def deliver_data(self, message):
        """Deliver data to the application layer."""
        self.simulator.tolayer5(self.entity, message)


class Timer:
    """Timer helper."""
    def __init__(self, simulator, entity):
        self.simulator = simulator
        self.entity = entity

    def start(self, increment):
        """Start the timer with a given duration."""
        self.simulator.start_timer(self.entity, increment)

    def stop(self):
        """Stop the timer."""
        self.simulator.stop_timer(self.entity)
