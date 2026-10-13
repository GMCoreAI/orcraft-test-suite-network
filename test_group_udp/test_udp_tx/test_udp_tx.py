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


class TestUdpTxConfig(TrafficTestConfig):
	name = OrcraftConfigField.Text(default="UDP Transmit")

	description = OrcraftConfigField.Text(
		default=(
			"Measures UDP throughput and datagram loss from the SUT to its link partners.\n"
			"A one-shot nuttcp server is started on every link partner, and a nuttcp client per link partner "
			"on the SUT sends rate-limited datagrams to that partner's test IP for the configured duration, all streams at once.\n"
			"Each case sweeps the datagram length and the transmit rate, the load at the SUT's port that "
			"the link partners share equally. The reported throughput is the sum "
			"over the link partners, and the case passes when every stream reaches the minimum and keeps its "
			"loss within the allowed percentage."
		)
	)

	max_loss_percent = OrcraftConfigField.Numeric(default=1.0, label="Max Loss Percent")

	matrix = OrcraftConfigField.Matrix(
		OrcraftConfigField.Dimension("buffer_length", ("1K", "8K")),
		OrcraftConfigField.Dimension("rate", ("1G", "2G")),
	)


class TestUdpTxResult(OrcraftTestResult):
	throughput_mbps = OrcraftResultField.Numeric(default=None, label="Throughput Mbps")
	transferred_mb = OrcraftResultField.Numeric(default=None, label="Transferred MB")
	loss_percent = OrcraftResultField.Numeric(default=None, label="Loss Percent")
	per_partner_mbps = OrcraftResultField.Text(default="", label="Per Partner Mbps")
	log_orientation = OrcraftResultField.Format(default=OrcraftResultField.LogTableOrientation.VERTICAL)


class TestUdpTx(OrcraftTest):
	def __init__(self, config: TestUdpTxConfig | None = None) -> None:
		super().__init__(config or TestUdpTxConfig())

	def _run_case(self, case: OrcraftTestCase) -> OrcraftTestResult:
		case.result = TestUdpTxResult()

		flow = FlowRunTraffic(
			FlowRunTrafficConfig(
				sut_endpoint=self.config.sut_endpoint,
				link_partner_endpoints=self.config.link_partner_endpoints,
				nuttcp_package_folder=self.config.nuttcp_package_folder,
				protocol="UDP",
				direction="TX",
				duration_sec=self.config.duration_sec,
				buffer_length=case.params["buffer_length"],
				rate=case.params["rate"],
				window_size=UDP_SOCKET_BUFFER,
				min_throughput_mbps=self.config.min_throughput_mbps,
				max_loss_percent=self.config.max_loss_percent,
			)
		)
		flow_result = flow.run()

		# The measurement is kept even when the flow fails, so a lossy link still reports its numbers
		case.result.throughput_mbps = flow_result.tx_throughput_mbps
		case.result.per_partner_mbps = flow_result.tx_per_partner_mbps
		case.result.transferred_mb = flow_result.tx_transferred_mb
		case.result.loss_percent = flow_result.tx_loss_percent

		self.handle_errors(flow_result, case.result)

		return case.result


def main() -> None:
	test = TestUdpTx()
	test.run()


if __name__ == "__main__":
	main()
