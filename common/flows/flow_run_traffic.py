from __future__ import annotations

from dataclasses import dataclass

from orcraft import (
	OrcraftStatus,
	OrcraftTestFlow,
	OrcraftTestFlowConfig,
	OrcraftTestFlowResult,
	OrcraftResultField,
	OrcraftConfigField,
)

from common.nuttcp_app import LINK_PARTNER_CONTROL_PORT, split_rate, sut_control_port
from common.test_network import endpoint_name
from common.steps.step_verify_nuttcp import StepVerifyNuttcp
from common.steps.step_find_test_ip import StepFindTestIp
from common.steps.step_start_nuttcp_server import StepStartNuttcpServer
from common.steps.step_start_nuttcp_client import StepStartNuttcpClient
from common.steps.step_wait_nuttcp_client import StepWaitNuttcpClient
from common.steps.step_stop_nuttcp_server import StepStopNuttcpServer


@dataclass(frozen=True)
class TrafficStream:
	"""One nuttcp transfer: a client on the transmitter sends to a one-shot server on the receiver."""

	direction: str
	partner: str
	transmitter: object
	receiver: object
	target_ip: str
	control_port: int

	@property
	def label(self) -> str:
		"""How the stream is named in checkpoints, for example "TX to GMG-TEST-2"."""
		return f"{self.direction} {'to' if self.direction == 'TX' else 'from'} {self.partner}"


class FlowRunTrafficConfig(OrcraftTestFlowConfig):
	name = OrcraftConfigField.Text(default="Run Traffic")
	sut_endpoint = OrcraftConfigField.Endpoint(default="localhost", label="SUT Endpoint")
	link_partner_endpoints = OrcraftConfigField.MultiSelectEndpoints(
		default=("localhost",),
		label="Link Partner Endpoints",
	)
	nuttcp_package_folder = OrcraftConfigField.PackageFolder(default="", label="Nuttcp Package Folder")
	protocol = OrcraftConfigField.Text(default="TCP", label="Protocol")
	direction = OrcraftConfigField.Text(default="TX", label="Direction")
	duration_sec = OrcraftConfigField.Numeric(default=10, label="Duration Sec")
	buffer_length = OrcraftConfigField.Text(default="", label="Buffer Length")
	window_size = OrcraftConfigField.Text(default="", label="Window Size")
	rate = OrcraftConfigField.Text(default="", label="Rate")
	min_throughput_mbps = OrcraftConfigField.Numeric(default=0, label="Min Throughput Mbps")
	max_loss_percent = OrcraftConfigField.Numeric(default=1.0, label="Max Loss Percent")
	log_orientation = OrcraftConfigField.Format(default=OrcraftConfigField.LogTableOrientation.VERTICAL)


class FlowRunTrafficResult(OrcraftTestFlowResult):
	tx_throughput_mbps = OrcraftResultField.Numeric(default=None, label="SUT TX Throughput Mbps")
	tx_transferred_mb = OrcraftResultField.Numeric(default=None, label="SUT TX Transferred MB")
	tx_retransmissions = OrcraftResultField.Numeric(default=None, label="SUT TX Retransmissions")
	tx_loss_percent = OrcraftResultField.Numeric(default=None, label="SUT TX Loss Percent")
	tx_per_partner_mbps = OrcraftResultField.Text(default="", label="SUT TX Per Partner Mbps")
	rx_throughput_mbps = OrcraftResultField.Numeric(default=None, label="SUT RX Throughput Mbps")
	rx_transferred_mb = OrcraftResultField.Numeric(default=None, label="SUT RX Transferred MB")
	rx_retransmissions = OrcraftResultField.Numeric(default=None, label="SUT RX Retransmissions")
	rx_loss_percent = OrcraftResultField.Numeric(default=None, label="SUT RX Loss Percent")
	rx_per_partner_mbps = OrcraftResultField.Text(default="", label="SUT RX Per Partner Mbps")
	log_orientation = OrcraftResultField.Format(default=OrcraftResultField.LogTableOrientation.VERTICAL)


class FlowRunTraffic(OrcraftTestFlow):
	"""Runs nuttcp traffic between the SUT and every link partner in one direction, or both at once.

	Direction is relative to the SUT: "TX" means the SUT transmits to the link partners, "RX"
	means the link partners transmit to the SUT, and "BX" runs both at once. Every transfer is
	one stream between the SUT and one link partner; all streams of a run are started before
	any is waited for, so with several link partners the SUT carries them all together. The
	receiver of a stream runs a one-shot nuttcp server and the transmitter runs the client.

	The SUT's throughput of a direction is the sum over its streams, and a rate limit is the
	load offered at the SUT's port, shared equally by the streams. The pass criteria are
	checked on every stream, so each link partner has to reach the minimum by itself.
	"""

	result_type = FlowRunTrafficResult

	def __init__(self, config: FlowRunTrafficConfig) -> None:
		super().__init__(config)

	def _run_flow(self) -> None:
		partners = tuple(self.config.link_partner_endpoints)
		protocol = str(self.config.protocol).upper()

		self.checkpoint(
			bool(partners),
			f"{len(partners)} link partner(s) selected.",
			"No link partner is selected.",
		)
		if not partners:
			return

		endpoints = (self.config.sut_endpoint, *partners)

		# Step 1: verify the nuttcp package on the SUT and on every link partner
		for endpoint in endpoints:
			step_1_result = self.run_step(
				StepVerifyNuttcp,
				endpoint=endpoint,
				nuttcp_package_folder=self.config.nuttcp_package_folder,
			)

			if self.handle_errors(step_1_result, self.result):
				return

		# Step 2: find the address of every machine on the network under test
		test_ips: list[str] = []
		for endpoint in endpoints:
			step_2_result = self.run_step(StepFindTestIp, endpoint=endpoint)

			if self.handle_errors(step_2_result, self.result):
				return

			test_ips.append(step_2_result.test_ip)

		streams = self._build_streams(partners, sut_ip=test_ips[0], partner_ips=test_ips[1:])

		# A rate is the load offered at the SUT's port: every partner's stream gets an equal share
		stream_rate = split_rate(str(self.config.rate or ""), len(partners))

		# Step 3: start a one-shot server on the receiver of every stream
		servers: list[tuple[TrafficStream, object]] = []
		for stream in streams:
			step_3_result = self.run_step(
				StepStartNuttcpServer,
				endpoint=stream.receiver,
				nuttcp_package_folder=self.config.nuttcp_package_folder,
				control_port=stream.control_port,
			)

			if self.handle_errors(step_3_result, self.result):
				self._stop_servers(servers)
				return

			servers.append((stream, step_3_result.server))

		# Step 4: start a client on the transmitter of every stream; each returns at once
		clients: list[tuple[TrafficStream, object]] = []
		for stream in streams:
			step_4_result = self.run_step(
				StepStartNuttcpClient,
				endpoint=stream.transmitter,
				nuttcp_package_folder=self.config.nuttcp_package_folder,
				target_ip=stream.target_ip,
				control_port=stream.control_port,
				protocol=protocol,
				duration_sec=self.config.duration_sec,
				buffer_length=self.config.buffer_length,
				window_size=self.config.window_size,
				rate=stream_rate,
			)

			if self.handle_errors(step_4_result, self.result):
				self._stop_servers(servers)
				return

			clients.append((stream, step_4_result.task))

		# Step 5: wait for every client and read its measurement
		measurements: list[tuple[TrafficStream, object]] = []
		for stream, task in clients:
			step_5_result = self.run_step(
				StepWaitNuttcpClient,
				endpoint=stream.transmitter,
				task=task,
				duration_sec=self.config.duration_sec,
			)
			measurements.append((stream, step_5_result))

		# Step 6: collect the servers; they exit on their own once their transfer is over
		self._stop_servers(servers)

		# A failed or errored wait step has already marked this flow; it carries no measurement
		for stream, step_5_result in measurements:
			if step_5_result.status is not OrcraftStatus.PASS:
				return

		for direction in ("TX", "RX"):
			self._store_measurements(
				direction,
				[(stream, result) for stream, result in measurements if stream.direction == direction],
			)

		# Pass criteria: every stream reached the minimum throughput, and for UDP kept its loss low
		min_throughput = float(self.config.min_throughput_mbps)
		max_loss = float(self.config.max_loss_percent)
		for stream, step_5_result in measurements:
			self.checkpoint(
				step_5_result.throughput_mbps >= min_throughput,
				f"SUT {stream.label} throughput {step_5_result.throughput_mbps:.1f} Mbps "
				f"reaches the minimum of {min_throughput:.1f} Mbps.",
				f"SUT {stream.label} throughput {step_5_result.throughput_mbps:.1f} Mbps "
				f"is below the minimum of {min_throughput:.1f} Mbps.",
			)

			if protocol == "UDP":
				loss = step_5_result.loss_percent or 0.0
				self.checkpoint(
					loss <= max_loss,
					f"SUT {stream.label} loss {loss:.2f}% is within the allowed {max_loss:.2f}%.",
					f"SUT {stream.label} loss {loss:.2f}% exceeds the allowed {max_loss:.2f}%.",
				)

	def _build_streams(self, partners: tuple, *, sut_ip: str, partner_ips: list[str]) -> list[TrafficStream]:
		direction = str(self.config.direction).upper()
		if direction not in {"TX", "RX", "BX"}:
			raise ValueError(f"Unsupported traffic direction: {self.config.direction!r}")

		streams: list[TrafficStream] = []
		for index, (partner, partner_ip) in enumerate(zip(partners, partner_ips)):
			name = endpoint_name(partner)

			# The SUT transmits: the server sits on the partner, one per machine, on the partner port
			if direction in {"TX", "BX"}:
				streams.append(
					TrafficStream(
						direction="TX",
						partner=name,
						transmitter=self.config.sut_endpoint,
						receiver=partner,
						target_ip=partner_ip,
						control_port=LINK_PARTNER_CONTROL_PORT,
					)
				)

			# The SUT receives: every partner gets its own server on the SUT, on its own ports
			if direction in {"RX", "BX"}:
				streams.append(
					TrafficStream(
						direction="RX",
						partner=name,
						transmitter=partner,
						receiver=self.config.sut_endpoint,
						target_ip=sut_ip,
						control_port=sut_control_port(index),
					)
				)

		return streams

	def _stop_servers(self, servers: list[tuple[TrafficStream, object]]) -> None:
		for stream, server in servers:
			self.run_step(
				StepStopNuttcpServer,
				endpoint=stream.receiver,
				server=server,
			)

	def _store_measurements(self, direction: str, measurements: list[tuple[TrafficStream, object]]) -> None:
		"""Sum the streams of one direction into the SUT's numbers and keep the per-partner breakdown."""
		if not measurements:
			return

		prefix = direction.lower()
		results = [step_result for _stream, step_result in measurements]
		retransmissions = [r.retransmissions for r in results if r.retransmissions is not None]
		losses = [r.loss_percent for r in results if r.loss_percent is not None]

		setattr(self.result, f"{prefix}_throughput_mbps", round(sum(r.throughput_mbps for r in results), 1))
		setattr(self.result, f"{prefix}_transferred_mb", round(sum(r.transferred_mb for r in results), 1))
		setattr(self.result, f"{prefix}_retransmissions", sum(retransmissions) if retransmissions else None)
		setattr(self.result, f"{prefix}_loss_percent", max(losses) if losses else None)
		setattr(
			self.result,
			f"{prefix}_per_partner_mbps",
			"; ".join(f"{stream.partner}: {r.throughput_mbps:.1f}" for stream, r in measurements),
		)
