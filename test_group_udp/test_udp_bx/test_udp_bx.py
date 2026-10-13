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
from common.nuttcp_app import UDP_SOCKET_BUFFER


class TestUdpBxConfig(TrafficTestConfig):
	name = OrcraftConfigField.Text(default="UDP Bidirectional")

	description = OrcraftConfigField.Text(
		default=(
			"Measures UDP throughput and datagram loss in both directions at the same time.\n"
			"The SUT and every link partner start their one-shot nuttcp servers, then all clients are started "
			"before any is waited for, so the SUT and every link partner send rate-limited datagrams to each "
			"other for the configured duration.\n"
			"Each case sweeps the datagram length and the transmit rate, the load at the SUT's port that "
			"the link partners share equally. Each direction's throughput is the "
			"sum over the link partners, and the case passes when every stream reaches the minimum and keeps "
			"its loss within the allowed percentage."
		)
	)

	max_loss_percent = OrcraftConfigField.Numeric(default=1.0, label="Max Loss Percent")

	matrix = OrcraftConfigField.Matrix(
		OrcraftConfigField.Dimension("buffer_length", ("1K", "8K")),
		OrcraftConfigField.Dimension("rate", ("1G", "2G")),
	)


class TestUdpBxResult(OrcraftTestResult):
	tx_throughput_mbps = OrcraftResultField.Numeric(default=None, label="TX Throughput Mbps")
	rx_throughput_mbps = OrcraftResultField.Numeric(default=None, label="RX Throughput Mbps")
	tx_transferred_mb = OrcraftResultField.Numeric(default=None, label="TX Transferred MB")
	rx_transferred_mb = OrcraftResultField.Numeric(default=None, label="RX Transferred MB")
	tx_loss_percent = OrcraftResultField.Numeric(default=None, label="TX Loss Percent")
	rx_loss_percent = OrcraftResultField.Numeric(default=None, label="RX Loss Percent")
	tx_per_partner_mbps = OrcraftResultField.Text(default="", label="TX Per Partner Mbps")
	rx_per_partner_mbps = OrcraftResultField.Text(default="", label="RX Per Partner Mbps")
	log_orientation = OrcraftResultField.Format(default=OrcraftResultField.LogTableOrientation.VERTICAL)


class TestUdpBx(OrcraftTest):
	def __init__(self, config: TestUdpBxConfig | None = None) -> None:
		super().__init__(config or TestUdpBxConfig())

	def _run_case(self, case: OrcraftTestCase) -> OrcraftTestResult:
		case.result = TestUdpBxResult()

		flow = FlowRunTraffic(
			FlowRunTrafficConfig(
				sut_endpoint=self.config.sut_endpoint,
				link_partner_endpoints=self.config.link_partner_endpoints,
				nuttcp_package_folder=self.config.nuttcp_package_folder,
				protocol="UDP",
				direction="BX",
				duration_sec=self.config.duration_sec,
				buffer_length=case.params["buffer_length"],
				rate=case.params["rate"],
				window_size=UDP_SOCKET_BUFFER,
				min_throughput_mbps=self.config.min_throughput_mbps,
				max_loss_percent=self.config.max_loss_percent,
			)
		)
		flow_result = flow.run()

		# The measurements are kept even when the flow fails, so a lossy link still reports its numbers
		case.result.tx_throughput_mbps = flow_result.tx_throughput_mbps
		case.result.rx_throughput_mbps = flow_result.rx_throughput_mbps
		case.result.tx_per_partner_mbps = flow_result.tx_per_partner_mbps
		case.result.rx_per_partner_mbps = flow_result.rx_per_partner_mbps
		case.result.tx_transferred_mb = flow_result.tx_transferred_mb
		case.result.rx_transferred_mb = flow_result.rx_transferred_mb
		case.result.tx_loss_percent = flow_result.tx_loss_percent
		case.result.rx_loss_percent = flow_result.rx_loss_percent

		self.handle_errors(flow_result, case.result)

		return case.result


def main() -> None:
	test = TestUdpBx()
	test.run()


if __name__ == "__main__":
	main()
