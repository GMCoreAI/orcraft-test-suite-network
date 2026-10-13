from __future__ import annotations

from orcraft import (
	OrcraftTest,
	OrcraftTestCase,
	OrcraftTestResult,
	OrcraftResultField,
	OrcraftConfigField,
)

from common.traffic_test_config import TrafficTestConfig
from common.flows.flow_run_traffic import FlowRunTraffic, FlowRunTrafficConfig


class TestTcpRxConfig(TrafficTestConfig):
	name = OrcraftConfigField.Text(default="TCP Receive")

	description = OrcraftConfigField.Text(
		default=(
			"Measures TCP throughput from the link partners to the SUT.\n"
			"A one-shot nuttcp server per link partner is started on the SUT, each on its own port, and a "
			"nuttcp client on every link partner sends to the SUT's test IP for the configured duration, all streams at once.\n"
			"Each case sweeps the nuttcp buffer length and socket window size. The reported throughput is "
			"the sum over the link partners, and the case passes when every link partner's stream reaches the minimum."
		)
	)

	matrix = OrcraftConfigField.Matrix(
		OrcraftConfigField.Dimension("buffer_length", ("64K", "1M")),
		OrcraftConfigField.Dimension("window_size", ("256K", "4M")),
	)


class TestTcpRxResult(OrcraftTestResult):
	throughput_mbps = OrcraftResultField.Numeric(default=None, label="Throughput Mbps")
	transferred_mb = OrcraftResultField.Numeric(default=None, label="Transferred MB")
	retransmissions = OrcraftResultField.Numeric(default=None, label="Retransmissions")
	per_partner_mbps = OrcraftResultField.Text(default="", label="Per Partner Mbps")
	log_orientation = OrcraftResultField.Format(default=OrcraftResultField.LogTableOrientation.VERTICAL)


class TestTcpRx(OrcraftTest):
	def __init__(self, config: TestTcpRxConfig | None = None) -> None:
		super().__init__(config or TestTcpRxConfig())

	def _run_case(self, case: OrcraftTestCase) -> OrcraftTestResult:
		case.result = TestTcpRxResult()

		flow = FlowRunTraffic(
			FlowRunTrafficConfig(
				sut_endpoint=self.config.sut_endpoint,
				link_partner_endpoints=self.config.link_partner_endpoints,
				nuttcp_package_folder=self.config.nuttcp_package_folder,
				protocol="TCP",
				direction="RX",
				duration_sec=self.config.duration_sec,
				buffer_length=case.params["buffer_length"],
				window_size=case.params["window_size"],
				min_throughput_mbps=self.config.min_throughput_mbps,
			)
		)
		flow_result = flow.run()

		# The measurement is kept even when the flow fails, so a slow link still reports its numbers
		case.result.throughput_mbps = flow_result.rx_throughput_mbps
		case.result.per_partner_mbps = flow_result.rx_per_partner_mbps
		case.result.transferred_mb = flow_result.rx_transferred_mb
		case.result.retransmissions = flow_result.rx_retransmissions

		self.handle_errors(flow_result, case.result)

		return case.result


def main() -> None:
	test = TestTcpRx()
	test.run()


if __name__ == "__main__":
	main()
