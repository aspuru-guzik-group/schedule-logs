"""Network classification for schedule authentication."""

from ipaddress import ip_address, ip_network


ETHERNET_NETWORKS = (
    ip_network("10.21.0.0/16"),
    ip_network("128.100.0.0/16"),
)


def is_ethernet_client(value):
    """Return whether a single client address belongs to the Matter wired LAN."""
    try:
        address = ip_address(str(value).strip())
    except ValueError:
        return False
    return any(address in network for network in ETHERNET_NETWORKS)
