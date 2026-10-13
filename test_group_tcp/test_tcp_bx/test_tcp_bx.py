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


class TestTcpBxConfig(TrafficTestConfig):
	name = OrcraftConfigField.Text(default="TCP Bidirectional")

	description = OrcraftConfigField.Text(
		default=(
			"Measures TCP throughput in both directions at the same time.\n"
			"The SUT and every link partner start their one-shot nuttcp servers, then all clients are started "
			"before any is waited for, so the SUT transmits to every link partner while every link partner "
			"transmits to the SUT for the configured duration.\n"
			"Each case sweeps the nuttcp buffer length and socket window size. Each direction's throughput is "
			"the sum over the link partners, and the case passes when every stream reaches the minimum."
		)
	)

	matrix = OrcraftConfigField.Matrix(
		OrcraftConfigField.Dimension("buffer_length", ("64K", "1M")),
		OrcraftConfigField.Dimension("window_size", ("256K", "4M")),
	)


class TestTcpBxResult(OrcraftTestResult):
	tx_throughput_mbps = OrcraftResultField.Numeric(default=None, label="TX Throughput Mbps")
	rx_throughput_mbps = OrcraftResultField.Numeric(default=None, label="RX Throughput Mbps")
	tx_transferred_mb = OrcraftResultField.Numeric(default=None, label="TX Transferred MB")
	rx_transferred_mb = OrcraftResultField.Numeric(default=None, label="RX Transferred MB")
	tx_retransmissions = OrcraftResultField.Numeric(default=None, label="TX Retransmissions")
	rx_retransmissions = OrcraftResultField.Numeric(default=None, label="RX Retransmissions")
	tx_per_partner_mbps = OrcraftResultField.Text(default="", label="TX Per Partner Mbps")
	rx_per_partner_mbps = OrcraftResultField.Text(default="", label="RX Per Partner Mbps")
	log_orientation = OrcraftResultField.Format(default=OrcraftResultField.LogTableOrientation.VERTICAL)


class TestTcpBx(OrcraftTest):
	def __init__(self, config: TestTcpBxConfig | None = None) -> None:
		super().__init__(config or TestTcpBxConfig())

	def _run_case(self, case: OrcraftTestCase) -> OrcraftTestResult:
		case.result = TestTcpBxResult()

		flow = FlowRunTraffic(
			FlowRunTrafficConfig(
				sut_endpoint=self.config.sut_endpoint,
				link_partner_endpoints=self.config.link_partner_endpoints,
				nuttcp_package_folder=self.config.nuttcp_package_folder,
				protocol="TCP",
				direction="BX",
				duration_sec=self.config.duration_sec,
				buffer_length=case.params["buffer_length"],
				window_size=case.params["window_size"],
				min_throughput_mbps=self.config.min_throughput_mbps,
			)
		)
		flow_result = flow.run()

		# The measurements are kept even when the flow fails, so a slow link still reports its numbers
		case.result.tx_throughput_mbps = flow_result.tx_throughput_mbps
		case.result.rx_throughput_mbps = flow_result.rx_throughput_mbps
		case.result.tx_per_partner_mbps = flow_result.tx_per_partner_mbps
		case.result.rx_per_partner_mbps = flow_result.rx_per_partner_mbps
		case.result.tx_transferred_mb = flow_result.tx_transferred_mb
		case.result.rx_transferred_mb = flow_result.rx_transferred_mb
		case.result.tx_retransmissions = flow_result.tx_retransmissions
		case.result.rx_retransmissions = flow_result.rx_retransmissions

		self.handle_errors(flow_result, case.result)

		return case.result


def main() -> None:
	test = TestTcpBx()
	test.run()


if __name__ == "__main__":
	main()
