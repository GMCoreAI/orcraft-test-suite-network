from __future__ import annotations

from orcraft import (
	OrcraftTestGroup,
	OrcraftTestGroupConfig,
	OrcraftTestGroupResult,
	OrcraftConfigField,
)

from test_group_tcp.test_tcp_tx.test_tcp_tx import TestTcpTx
from test_group_tcp.test_tcp_rx.test_tcp_rx import TestTcpRx
from test_group_tcp.test_tcp_bx.test_tcp_bx import TestTcpBx


class TestGroupTcpConfig(OrcraftTestGroupConfig):
	name = OrcraftConfigField.Text(default="TCP Traffic")
	description = OrcraftConfigField.Text(
		default=(
			"Measures TCP throughput between the SUT and its link partners with nuttcp, all at once: "
			"the SUT transmitting, the SUT receiving, and both directions at once."
		)
	)
	tests = OrcraftConfigField.Tests(
		default_factory=lambda: [
			TestTcpTx(),
			TestTcpRx(),
			TestTcpBx(),
		]
	)


class TestGroupTcpResult(OrcraftTestGroupResult):
	pass


class TestGroupTcp(OrcraftTestGroup):
	def __init__(self) -> None:
		super().__init__(config=TestGroupTcpConfig())
		self.result = TestGroupTcpResult()


def main() -> None:
	group = TestGroupTcp()
	group.run()


if __name__ == "__main__":
	main()
