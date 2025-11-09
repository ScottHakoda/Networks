import ast
import io
import random
import string
import unittest
import unittest.mock

import asttest
import rdt
import simulator

class TestRDT(asttest.ASTTest):

    def setUp(self):
        super().setUp('rdt.py')
        self.msgs = 50
        self.expected = []
        for i in range(self.msgs-1):
            self.expected.append(string.ascii_lowercase[i%26])
        self.freq = 1000
        self.lossprob = 0
        self.corruptprob = 0
        self.pause = 0
        self._simulations = 1
        self.min_rcvd = self.msgs * .96
        self.msg = ("Your protocol did not transport the messages with a high "
                "enough success rate{}.\n\n")
        self.report = "Got: {}\nExpected at least: {}\n\nSimulator parameters:\n\n{}"


    def simulate(self):
        sim = simulator.Simulator(self.msgs, self.freq, self.lossprob,
                self.corruptprob, self.pause)
        sim.run(rdt.RDTSender, rdt.RDTReceiver)
        return sim

    def simulations(self):
        results = []
        worst = None
        for i in range(self._simulations):
            sim = self.simulate()
            results.append(len(sim.received))
            if not worst or len(sim.received) < len(worst):
                worst = sim.received
        return sim, sum(results)/len(results), worst

    def test_rdt_structure(self):
        # Find RDTSender class
        sender_class_node = next((c for c in self.find_all(ast.ClassDef) if c.name == 'RDTSender'), None)
        self.assertIsNotNone(sender_class_node, "Could not find the `RDTSender` class. Do not rename it.")

        # Check RDTSender methods
        sender_methods = {'rdt_send': 2, 'rdt_rcv': 2, 'timer_interrupt': 1}
        for method_name, nargs in sender_methods.items():
            method_node = next((n for n in sender_class_node.body if isinstance(n, ast.FunctionDef) and n.name == method_name), None)
            self.assertIsNotNone(method_node, f"Method `{method_name}` not found in `RDTSender`.")
            self.assertEqual(len(method_node.args.args), nargs,
                             f"Method `{method_name}` in `RDTSender` should have {nargs} argument(s).")

        # Find RDTReceiver class
        receiver_class_node = next((c for c in self.find_all(ast.ClassDef) if c.name == 'RDTReceiver'), None)
        self.assertIsNotNone(receiver_class_node, "Could not find the `RDTReceiver` class. Do not rename it.")

        # Check RDTReceiver methods
        receiver_methods = {'rdt_rcv': 2}
        for method_name, nargs in receiver_methods.items():
            method_node = next((n for n in receiver_class_node.body if isinstance(n, ast.FunctionDef) and n.name == method_name), None)
            self.assertIsNotNone(method_node, f"Method `{method_name}` not found in `RDTReceiver`.")
            self.assertEqual(len(method_node.args.args), nargs,
                             f"Method `{method_name}` in `RDTReceiver` should have {nargs} argument(s).")

        # Check for forbidden calls in sender
        rdt_send_node = next((n for n in sender_class_node.body if isinstance(n, ast.FunctionDef) and n.name == 'rdt_send'), None)
        if rdt_send_node:
            for call in self.find_all(ast.Call, rdt_send_node):
                if isinstance(call.func, ast.Attribute) and call.func.attr == "deliver_data":
                    self.fail("The sender's `rdt_send` method should not call `deliver_data()`. That's for the receiver.")

    @unittest.mock.patch('sys.stderr', new_callable=io.StringIO)
    @unittest.mock.patch('sys.stdout', new_callable=io.StringIO)
    def test_unreliable_channels(self, stdout, stderr):
        scenarios = {
            "reliable_channel": {"loss": 0, "corrupt": 0, "desc": ", even under perfect conditions"},
            "bit_errors":       {"loss": 0, "corrupt": 0.2, "desc": " when dealing with bit errors"},
            "loss":             {"loss": 0.1, "corrupt": 0, "desc": " when dealing with packet loss"},
            "both":             {"loss": 0.1, "corrupt": 0.2, "desc": " when sending over an unreliable channel"},
        }

        for name, params in scenarios.items():
            with self.subTest(name):
                # Must reset probabilities since setUp() is not called between subtests
                self.lossprob = params["loss"]
                self.corruptprob = params["corrupt"]

                sim, avg, worst = self.simulations()
                self.assertGreaterEqual(avg, self.min_rcvd,
                        self.msg.format(params["desc"]) +
                        self.report.format(len(worst), self.min_rcvd, sim.get_params()))
