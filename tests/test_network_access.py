import unittest

from network_access import is_ethernet_client


class NetworkAccessTest(unittest.TestCase):
    def test_matter_ethernet_addresses_are_trusted(self):
        for address in (
            "10.21.0.1",
            "10.21.10.221",
            "10.21.101.76",
            "10.21.255.254",
            "128.100.27.79",
        ):
            with self.subTest(address=address):
                self.assertTrue(is_ethernet_client(address))

    def test_non_ethernet_addresses_require_slack(self):
        for address in (
            "",
            "10.20.255.255",
            "10.22.0.1",
            "128.101.20.76",
            "127.0.0.1",
            "2001:db8::1",
        ):
            with self.subTest(address=address):
                self.assertFalse(is_ethernet_client(address))

    def test_forwarded_chain_is_not_accepted_as_an_address(self):
        self.assertFalse(is_ethernet_client("10.21.10.221, 203.0.113.10"))


if __name__ == "__main__":
    unittest.main()
