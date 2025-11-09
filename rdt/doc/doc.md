# Reliable Data Transport (RDT) Protocol

The procedures you will write are for the sending entity and the receiving
entity. Only unidirectional transfer of data from the sender to the receiver is required. Of
course, the receiver will have to send packets to the sender to acknowledge (positively or
negatively) receipt of data. Your routines are to be implemented in the form of
the procedures described below. These procedures will be called by (and will
call) procedures that I have written which simulate a network environment. The
overall structure of the simulated environment is shown below.

<object data="diagram.pdf" type="application/pdf" width="700px" height="700px">
    <embed src="diagram.pdf">
        This browser does not support PDFs. Please download the PDF to view it: <a href="diagram.pdf">Download PDF</a>.</p>
    </embed>
</object>

The unit of data passed between the upper layers and your protocols is a
*message*, which is simply a 20-byte string. Your sending entity will thus
receive data in 20-byte chunks from layer5; your receiving entity should deliver
20-byte chunks of correctly received data to layer5 at the receiving side. You
will not have to worry about the encoding of this string, just use it as you
would normally use a string.

The unit of data passed between your routines and the network layer is a
*packet*, which is declared as:

```
class Pkt:
    seqnum (int)
    checksum (int)
    payload (str)
```

Your routines will fill in the payload field from the message data passed down
from layer5. The other packet fields will be used by your protocols to ensure
reliable delivery, as we've seen in class.

The routines you will write are detailed below. As noted above, such procedures
in real-life would be part of the operating system, and would be called by other
procedures in the operating system.

- **`rdt_send(msg)`**, where `msg` is a 20-byte string, containing data to be
  sent to the receiver. This routine will be called whenever the upper layer at
  the sending side has a message to send. It is the job of your protocol to
  ensure that the data in such a message is delivered in order, and correctly,
  to the receiving side upper layer. **Also, since this protocol is a
  stop-and-wait protocol, you should only send a message if there is currently
  no other message in transit. Just ignore the incoming message if that is the
  case and return `False` (this is why we use a large frequency), otherwise,
  return True.**
- **`rdt_rcv(pkt)`**, where `pkt` is an object of type `Pkt`. This routine will
  be called on the sender when a packet from the receiver arrives, and on the
  receiver when a packet from the sender arrives.
- **`timer_interrupt()`**. This routine will be called when the sender's timer
  expires (thus generating a timer interrupt). You'll probably want to use this
  routine to control the retransmission of packets. See `start_timer()` and
  `stop_timer()` below for how the timer is started and stopped.

## Implementation Structure

To accurately simulate the separation between the sender and the receiver, you must implement your logic in two separate classes:

-   **`RDTSender`**: This class will handle the logic for the sending entity. Its constructor will be `__init__(self, udt, timer)`. It must implement the following methods:
    -   `rdt_send(msg)`
    -   `rdt_rcv(pkt)`
    -   `timer_interrupt()`

-   **`RDTReceiver`**: This class will handle the logic for the receiving entity. Its constructor will be `__init__(self, udt, app_layer)`. It must implement the following method:
    -   `rdt_rcv(packet)`

The simulator will create a separate instance of each class. This structure enforces the real-world constraint that the sender and receiver cannot directly share state, as they would be running on different machines.

## The Simulator

### Interface

Instead of calling simulator functions directly, your `RDTSender` and `RDTReceiver` classes will be provided with objects that represent the interfaces to the other layers of the network stack.

-   Your `RDTSender` will be initialized with two objects:
    -   An instance of a `UDT` (Unreliable Data Transfer) class.
    -   An instance of a `Timer` class.

-   Your `RDTReceiver` will be initialized with two objects:
    -   An instance of a `UDT` class.
    -   An instance of an `AppLayer` (Application Layer) class.

These objects provide the following methods for you to call:

-   **`udt.send(packet)`**: Sends a `packet` into the underlying unreliable network. Both the sender and receiver will use this to send packets.
-   **`app_layer.deliver_data(message)`**: Delivers a `message` string up to the application layer. This should only be called by the receiver.
-   **`timer.start(increment)`**: Starts a timer that will generate a `timer_interrupt()` event after `increment` time units (a `float`). To give you an idea of the appropriate `increment` value, a packet takes an average of 5 time units to arrive.
-   **`timer.stop()`**: Stops the currently running timer.

### Environment

A call to `udt.send(packet)` sends packets into the medium (i.e., into the
network layer). Your `rdt_rcv()` procedures are called when a packet is to be
delivered from the medium to your protocol layer.

The medium is capable of corrupting and losing packets. It will not reorder
packets. The simulator is configured via command-line arguments:

- **`--nmsgs` (`-n`)**: The number of messages to simulate. My simulator (and your
  routines) will stop as soon as this number of messages have been passed down
  from layer 5, regardless of whether or not all of the messages have been
  correctly delivered. Thus, you need **not** worry about undelivered or
  unACK'ed messages still in your sender when the simulator stops. Note that if
  you set this value to 1, your program will terminate immediately, before the
  message is delivered to the other side. Thus, this value should always be
  greater than 1. I recommend using a value of N+1. So for example, 11 to send
  (and hopefully receive) 10 packets.
- **`--freq` (`-f`)**: The average time between messages from sender's layer5. You can set
  this value to any non-zero, positive value. Note that the smaller the value
  you choose, the faster events will occur in the simulator. I would recommend a
  really high number at first, even as high as 1000.
- **`--lossprob` (`-l`)**: The probability of packet loss. A value of 0.1 would mean that
  one in ten packets (on average) are lost.
- **`--corruptprob` (`-c`)**: The probability of bit errors. A value of 0.2 would mean that
  one in five packets (on average) are corrupted. Note that the contents of
  payload, sequence, or checksum fields can be corrupted. Your checksum should
  thus include the data and sequence fields.
- **`--verbose` (`-v`)**: The level of chattiness. Use multiple times for more detail (e.g., `-vvv`). The program uses
  Python's `logging` package. Various log messages are already set up for either
  the `debug` or `warning` levels. You might find it useful to add your own log
  messages for the `info` log level. You should also keep in mind that *real*
  protocols do not have underlying networks that provide such nice information
  about what is going to happen to their packets!
- **`--pause` (`-p`)**: The time (in seconds) to pause between events, controlling the simulation speed. Defaults to 2s for GUI/TUI, and 1s for terminal.
- **`--no-gui`**: Run the simulator in the terminal with log output only, instead of the default graphical interface.
- **`--tui`**: Use a terminal-based user interface instead of the graphical one.

### Graphical User Interface (GUI)

By default, the simulator runs with a graphical user interface (GUI) that visualizes the operation of your RDT protocol.

The GUI shows the state of the sender and receiver, including the data at each layer (Application, Transport, and Network). It also visualizes packets in transit across the network. Lost and corrupted packets are colored red for easy identification.

The playback controls at the top allow you to:
- **Pause and Resume** the simulation.
- **Step Forward** and **Step Back** through events when paused.
- Adjust the **simulation speed** with a slider.

The GUI is a powerful tool for debugging your implementation. You can run the simulator in a terminal-only mode using the `--no-gui` flag.

## Helpful Hints

- **Checksumming.** You can use whatever approach for checksumming you want
  (implement it as a method on the `Pkt` class). Remember that the sequence
  number field can also be corrupted. I suggest a TCP-like checksum,
  which consists of the sum of the (integer) sequence field value added to a
  character-by-character sum of the payload field of the packet. I recommend
  using the Python builtin function
  [`ord()`](https://docs.python.org/3/library/functions.html#ord) for this.
- Note that any shared "state" among your routines needs to be in the form of a
  data attribute on your class. Note also that any information that your
  procedures need to save from one invocation to the next must also be
  similarly maintained. For example, your routines will need to keep a copy of a
  packet for possible retransmission. It would probably be a good idea for such
  a data structure to also be saved as an attribute of your class. Note,
  however, that if one of your data attributes is used by your sender side, that
  variable should **NOT** be accessed by the receiving side entity, since in
  real life, communicating entities connected only by a communication channel
  can not share state by some other means.
- There is an attribute on the simulator object called `t` that you can access from
  within your code to help you out with your diagnostics msgs.
- **START SIMPLE.** First design and implement your procedures for the case
  of no loss and no corruption (set the probabilities of loss and corruption
  to zero), and get them working first. Then handle the case of one of these
  probabilities being non-zero, and then finally both being non-zero.
- **Debugging.** Use the logs excessively. You can control the log verbosity with the `-v` flag.
  The simulator's GUI is also an excellent debugging tool. It allows you to
  pause, step through events, and adjust the simulation speed on the fly.
  Slowing down the execution, either with the GUI's speed slider or the `--pause`
  command-line argument, is very helpful.
