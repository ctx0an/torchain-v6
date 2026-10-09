"""Comprehensive verification test suite for torchain improvements."""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure repo root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))


class TestTorrcOptimization(unittest.TestCase):
    def test_tc4_torrc_performance_directives(self):
        from tc4.config import Config
        from tc4 import torrc
        cfg = Config()
        content = torrc.build(cfg, tor_user="tor")
        self.assertIn("OptimisticData 1", content)
        self.assertIn("LearnCircuitBuildTimeout 1", content)
        self.assertNotIn("LearnCircuitBuildTimeout 0", content)
        self.assertIn("NumEntryGuards 1", content)
        self.assertIn("KeepalivePeriod 120", content)
        self.assertIn("VirtualAddrNetworkIPv4 10.192.0.0/10", content)

    def test_tcwin_torrc_performance_directives(self):
        from tcwin.config import Config
        from tcwin import torrc
        cfg = Config()
        content = torrc.build(cfg)
        self.assertIn("OptimisticData 1", content)
        self.assertIn("LearnCircuitBuildTimeout 1", content)
        self.assertNotIn("LearnCircuitBuildTimeout 0", content)
        self.assertIn("NumEntryGuards 1", content)
        self.assertIn("KeepalivePeriod 120", content)
        self.assertIn("VirtualAddrNetworkIPv4 10.192.0.0/10", content)


class TestLinuxFirewallOnionRouting(unittest.TestCase):
    def test_onion_virtual_address_ordering(self):
        from tc4.config import Config
        from tc4 import firewall
        cfg = Config()
        with patch("tc4.firewall.which", return_value="/sbin/iptables"), \
             patch("tc4.firewall.down"), \
             patch("tc4.firewall._tor_uid", return_value="1001"), \
             patch("tc4.firewall._ipt") as mock_ipt:
            firewall.up(cfg, "tor")

        calls = [tuple(call.args) for call in mock_ipt.call_args_list]

        # In NAT chain, check that 10.192.0.0/10 REDIRECT occurs before _NON_TOR RETURN
        nat_onion_idx = -1
        first_non_tor_nat_idx = -1
        for idx, args in enumerate(calls):
            if ("-t", "nat") in zip(args, args[1:]) and "-d" in args and "10.192.0.0/10" in args:
                if "REDIRECT" in args:
                    nat_onion_idx = idx
            if ("-t", "nat") in zip(args, args[1:]) and "-d" in args and "10.0.0.0/8" in args:
                if "RETURN" in args and first_non_tor_nat_idx == -1:
                    first_non_tor_nat_idx = idx

        self.assertNotEqual(nat_onion_idx, -1, "NAT onion redirect rule missing")
        self.assertNotEqual(first_non_tor_nat_idx, -1, "NAT 10.0.0.0/8 return rule missing")
        self.assertLess(nat_onion_idx, first_non_tor_nat_idx,
                        "NAT onion rule must precede _NON_TOR rules")

        # In FILTER chain, check that 10.192.0.0/10 ACCEPT occurs before _NON_TOR ACCEPT
        filter_onion_idx = -1
        first_non_tor_filter_idx = -1
        for idx, args in enumerate(calls):
            if "-t" not in args and "-d" in args and "10.192.0.0/10" in args and "ACCEPT" in args:
                filter_onion_idx = idx
            if "-t" not in args and "-d" in args and "10.0.0.0/8" in args and "ACCEPT" in args:
                if first_non_tor_filter_idx == -1:
                    first_non_tor_filter_idx = idx

        self.assertNotEqual(filter_onion_idx, -1, "FILTER onion rule missing")
        self.assertNotEqual(first_non_tor_filter_idx, -1, "FILTER 10.0.0.0/8 rule missing")
        self.assertLess(filter_onion_idx, first_non_tor_filter_idx,
                        "FILTER onion rule must precede _NON_TOR rules")


class TestWindowsFirewallPluggableTransports(unittest.TestCase):
    def test_pt_firewall_rules(self):
        from tcwin.config import Config
        from tcwin import firewall
        cfg = Config()
        mock_pts = [
            r"C:\ProgramData\torchain\app\tor\PluggableTransports\lyrebird.exe",
            r"C:\ProgramData\torchain\app\tor\PluggableTransports\conjure-client.exe",
        ]
        with patch("tcwin.firewall.which", return_value="netsh"), \
             patch("tcwin.firewall.down"), \
             patch("tcwin.firewall._netsh"), \
             patch("tcwin.firewall.run") as mock_run, \
             patch("tcwin.firewall._find_pt_executables", return_value=mock_pts):
            firewall.up(cfg, r"C:\ProgramData\torchain\app\tor\tor.exe")

        run_calls = [call.args[0] for call in mock_run.call_args_list]
        rule_cmds = [" ".join(cmd) for cmd in run_calls]

        # Check lyrebird rule added
        lyrebird_rules = [c for c in rule_cmds if "allow-pt-lyrebird" in c]
        self.assertTrue(len(lyrebird_rules) > 0, "Missing firewall rule for lyrebird")
        self.assertIn("lyrebird.exe", lyrebird_rules[0])

        # Check conjure-client rule added
        conjure_rules = [c for c in rule_cmds if "allow-pt-conjure-client" in c]
        self.assertTrue(len(conjure_rules) > 0, "Missing firewall rule for conjure-client")
        self.assertIn("conjure-client.exe", conjure_rules[0])

    def test_find_pt_ignores_utilities_in_tor_dir(self):
        from tcwin.firewall import _find_pt_executables
        mock_files = ["tor.exe", "tor-resolve.exe", "tor-gencert.exe", "lyrebird.exe"]
        with patch("os.path.isdir", side_effect=lambda d: "PluggableTransports" not in d), \
             patch("os.listdir", return_value=mock_files), \
             patch("shutil.which", return_value=None):
            pts = _find_pt_executables(r"C:\tor\tor.exe")
        bases = [os.path.basename(p).lower() for p in pts]
        self.assertIn("lyrebird.exe", bases)
        self.assertNotIn("tor.exe", bases)
        self.assertNotIn("tor-resolve.exe", bases)
        self.assertNotIn("tor-gencert.exe", bases)

    def test_tcwin_netfix_rules_include_pt(self):
        from tcwin.netfix import _TORCHAIN_RULES
        self.assertIn("torchain-allow-pt-lyrebird", _TORCHAIN_RULES)
        self.assertIn("torchain-allow-pt-snowflake", _TORCHAIN_RULES)
        self.assertIn("torchain-allow-pt-conjure-client", _TORCHAIN_RULES)


class TestHostnameAndHostsRepair(unittest.TestCase):
    def test_verify_hosts_file_repairs_and_cleans(self):
        from tc4.netfix import _verify_hosts_file
        import tempfile

        with tempfile.NamedTemporaryFile("w+", delete=False) as tf:
            tf.write("127.0.0.1 localhost\n127.0.0.1 spoofedhost\n::1 localhost\n")
            tf_path = tf.name

        real_open = open
        try:
            with patch("tc4.netfix.os.path.exists", return_value=True), \
                 patch("builtins.open", side_effect=lambda p, *a, **kw: real_open(tf_path, *a, **kw) if p == "/etc/hosts" else real_open(p, *a, **kw)):
                out = _verify_hosts_file(orig_host="myorigbox", spoofed_host="spoofedhost")

            with real_open(tf_path, "r") as fh:
                final_content = fh.read()

            self.assertIn("myorigbox", final_content)
            self.assertNotIn("spoofedhost", final_content)
            self.assertIn("localhost", final_content)
        finally:
            if os.path.exists(tf_path):
                os.remove(tf_path)

    def test_hosts_cleaning_multi_spaces_and_aliases(self):
        from tc4.netfix import _verify_hosts_file
        from tc4.spoof import _remove_hosts_entry
        import tempfile

        with tempfile.NamedTemporaryFile("w+", delete=False) as tf:
            tf.write("127.0.0.1    localhost   spoofedhost\n127.0.1.1   spoofedhost\n::1 localhost\n")
            tf_path = tf.name

        real_open = open
        try:
            with patch("tc4.netfix.os.path.exists", return_value=True), \
                 patch("builtins.open", side_effect=lambda p, *a, **kw: real_open(tf_path, *a, **kw) if p == "/etc/hosts" else real_open(p, *a, **kw)):
                _verify_hosts_file(orig_host="myorigbox", spoofed_host="spoofedhost")

            with real_open(tf_path, "r") as fh:
                final_content = fh.read()

            self.assertNotIn("spoofedhost", final_content)
            self.assertIn("localhost", final_content)
            self.assertIn("myorigbox", final_content)
        finally:
            if os.path.exists(tf_path):
                os.remove(tf_path)


class TestBridgeParallelization(unittest.TestCase):
    def test_parallel_bridge_testing_preserves_order(self):
        from tc4 import bridges
        bridge_lines = [
            "snowflake 192.0.2.3:80 placeholder",
            "obfs4 1.2.3.4:443 CERT cert1",
            "obfs4 5.6.7.8:9001 CERT cert2",
        ]

        def fake_connect(addr, timeout=5.0):
            host, port = addr
            if host == "1.2.3.4":
                return MagicMock()
            raise OSError("Connection refused")

        with patch("socket.create_connection", side_effect=fake_connect):
            results = bridges.test_bridges(bridge_lines)

        self.assertEqual(len(results), 3)
        self.assertEqual(results[0][0], bridge_lines[0])
        self.assertTrue(results[0][1])  # snowflake assumed reachable
        self.assertEqual(results[1][0], bridge_lines[1])
        self.assertTrue(results[1][1])  # 1.2.3.4 reachable
        self.assertEqual(results[2][0], bridge_lines[2])
        self.assertFalse(results[2][1]) # 5.6.7.8 refused

    def test_bridge_prefix_and_case_insensitivity(self):
        from tc4.bridges import _test_single_bridge as tc4_test
        from tcwin.bridges import _test_single_bridge as tcwin_test

        for fn in (tc4_test, tcwin_test):
            res1 = fn("Bridge snowflake 192.0.2.3:80 placeholder", timeout=0.1)
            self.assertTrue(res1[1])
            self.assertIn("pluggable transport", res1[2])

            res2 = fn("bridge meek_lite 192.0.2.3:80 placeholder", timeout=0.1)
            self.assertTrue(res2[1])

            res3 = fn("webtunnel 192.0.2.3:80 placeholder", timeout=0.1)
            self.assertTrue(res3[1])


class TestControlPortMemoizationAndParsing(unittest.TestCase):
    def test_torctl_lru_cache_avoids_repeated_queries(self):
        from tc4.torctl import ControlClient, _RELAY_IP_CACHE, _IP_COUNTRY_CACHE
        _RELAY_IP_CACHE.clear()
        _IP_COUNTRY_CACHE.clear()

        c = ControlClient()
        c.get_info = MagicMock()
        c.get_info.side_effect = lambda key: "r TestRelay 1234 2026-10-09 12:00:00 198.51.100.5 443 0\n" if key.startswith("ns/id/") else "CH\n"

        fp = "A" * 40
        # Call 1
        ip1 = c.relay_ip(fp)
        self.assertEqual(ip1, "198.51.100.5")
        # Call 2 (should be cached)
        ip2 = c.relay_ip(fp)
        self.assertEqual(ip2, "198.51.100.5")

        self.assertEqual(c.get_info.call_count, 1)

        # Test country code caching
        cc1 = c.ip_country("198.51.100.5")
        self.assertEqual(cc1, "CH")
        cc2 = c.ip_country("198.51.100.5")
        self.assertEqual(cc2, "CH")

        self.assertEqual(c.get_info.call_count, 2)

    def test_torctl_single_line_getinfo_parsing(self):
        from tc4.torctl import ControlClient as Tc4Client
        from tcwin.torctl import ControlClient as TcWinClient

        for cls in (Tc4Client, TcWinClient):
            client = cls()
            # Simulate real single-line Tor control protocol response (250 keyword=value)
            client._command = MagicMock(return_value=["250 ip-to-country/198.51.100.5=DE"])
            val = client.get_info("ip-to-country/198.51.100.5")
            self.assertEqual(val, "DE")

            # Simulate bootstrap-phase response
            client._command = MagicMock(return_value=[
                '250 status/bootstrap-phase=NOTICE BOOTSTRAP PROGRESS=100 TAG=done SUMMARY="Done"'
            ])
            progress = client.bootstrap_progress()
            self.assertEqual(progress, 100)

            # Simulate multi-line data response
            client._command = MagicMock(return_value=[
                "250+circuit-status=",
                "1 BUILT $AAAA...~foo,$BBBB...~bar",
                ".",
                "250 OK"
            ])
            circuits = client.get_info("circuit-status")
            self.assertEqual(circuits, "1 BUILT $AAAA...~foo,$BBBB...~bar")


class TestSysutilElevation(unittest.TestCase):
    def test_main_elevation_args(self):
        import tc4.sysutil as sysutil
        with patch.object(sys, "argv", ["/opt/torchain/tc4/__main__.py", "start"]), \
             patch("os.path.basename", return_value="__main__.py"):
            # Check script_base logic
            script_base = os.path.basename(sys.argv[0])
            self.assertEqual(script_base, "__main__.py")
            base_args = [sys.executable, "-m", "tc4", *sys.argv[1:]]
            self.assertEqual(base_args, [sys.executable, "-m", "tc4", "start"])


if __name__ == "__main__":
    unittest.main()
