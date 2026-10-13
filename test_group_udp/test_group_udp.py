from __future__ import annotations

from orcraft import (
	OrcraftTestGroup,
	OrcraftTestGroupConfig,
	OrcraftTestGroupResult,
	OrcraftConfigField,
)

from test_group_udp.test_udp_tx.test_udp_tx import TestUdpTx
from test_group_udp.test_udp_rx.test_udp_rx import TestUdpRx
from test_group_udp.test_udp_bx.test_udp_bx import TestUdpBx


class TestGroupUdpConfig(OrcraftTestGroupConfig):
	name = OrcraftConfigField.Text(default="UDP Traffic")
	description = OrcraftConfigField.Text(
		default=(
			"Measures UDP throughput and datagram loss between the SUT and its link partners, all at once, with "
			"rate-limited nuttcp traffic: the SUT transmitting, the SUT receiving, and both directions at once."
		)
	)
	tests = OrcraftConfigField.Tests(
		default_factory=lambda: [
			TestUdpTx(),
			TestUdpRx(),
			TestUdpBx(),
		]
	)


class TestGroupUdpResult(OrcraftTestGroupResult):
	pass


class TestGroupUdp(OrcraftTestGroup):
	def __init__(self) -> None:
		super().__init__(config=TestGroupUdpConfig())
		self.result = TestGroupUdpResult()


def main() -> None:
	group = TestGroupUdp()
	group.run()


if __name__ == "__main__":
	main()
