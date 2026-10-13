from __future__ import annotations

from orcraft import (
	OrcraftTestSuite,
	OrcraftTestSuiteConfig,
	OrcraftTestSuiteResult,
	OrcraftConfigField,
)

from test_group_tcp.test_group_tcp import TestGroupTcp
from test_group_udp.test_group_udp import TestGroupUdp


class TestSuiteNetworkConfig(OrcraftTestSuiteConfig):
	name = OrcraftConfigField.Text(default="Network Performance")
	description = OrcraftConfigField.Text(
		default=(
			"Measures network performance between a system under test and its link partners with nuttcp.\n"
			"All machines are Orcraft endpoints; the traffic runs between their addresses on the "
			"192.168.0.0/24 network under test, which every machine finds by itself, separate from "
			"the addresses the controller uses to reach them."
		)
	)
	version = OrcraftConfigField.Text(default="0.0.1")
	groups = OrcraftConfigField.Groups(
		default_factory=lambda: [
			TestGroupTcp(),
			TestGroupUdp(),
		]
	)


class TestSuiteNetworkResult(OrcraftTestSuiteResult):
	pass


class TestSuiteNetwork(OrcraftTestSuite):
	def __init__(self) -> None:
		super().__init__(config=TestSuiteNetworkConfig())
		self.result = TestSuiteNetworkResult()


def main() -> None:
	suite = TestSuiteNetwork()
	suite.run()


if __name__ == "__main__":
	main()
