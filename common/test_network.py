from __future__ import annotations

import ipaddress
import socket


# The network under test. Every machine of the setup has one address on it, separate from
# the address the controller uses to reach the machine, and the tests find that address by
# themselves: nothing about it is configured in the controller.
TEST_NETWORK = "192.168.0.0/24"


def find_test_ip(network: str = TEST_NETWORK) -> str:
	"""The IPv4 address this machine has on the given network, or empty when it has none."""
	wanted = ipaddress.ip_network(network, strict=False)
	for candidate in _local_ipv4_addresses(wanted):
		try:
			if ipaddress.ip_address(candidate) in wanted:
				return candidate
		except ValueError:
			continue
	return ""


def endpoint_name(endpoint: object) -> str:
	"""The host part of an endpoint, for labels: "GMG-TEST-2" out of "GMG-TEST-2:50051"."""
	target = str(getattr(endpoint, "target", endpoint) or "").strip()
	if target.startswith("[") and "]" in target:
		return target[1 : target.index("]")]
	host, _, port = target.rpartition(":")
	return host if host and port.isdigit() else target


def _local_ipv4_addresses(network: ipaddress.IPv4Network) -> list[str]:
	"""IPv4 addresses of this machine: the one that routes to the network first, then the named ones."""
	candidates: list[str] = []

	# A UDP socket "connected" to an address on the network is bound by the operating system
	# to the local address it would use to reach that network; nothing is sent. This works the
	# same way on every operating system and needs no extra package.
	probe = str(next(network.hosts(), network.network_address))
	try:
		with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
			sock.connect((probe, 9))
			candidates.append(sock.getsockname()[0])
	except OSError:
		pass

	# The addresses registered under the machine's own name cover the case of a network that
	# has no route yet, for example a link that is up but idle.
	try:
		for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
			address = info[4][0]
			if address not in candidates:
				candidates.append(address)
	except socket.gaierror:
		pass

	return candidates
