from __future__ import annotations

import threading

from orcraft import (
	OrcraftStatus,
	OrcraftTestStep,
	OrcraftTestStepConfig,
	OrcraftTestStepResult,
	OrcraftResultField,
	OrcraftConfigField,
	OrcraftLogger as Logger,
)

from common.nuttcp_app import NuttcpApp, NuttcpResult, LINK_PARTNER_CONTROL_PORT


class NuttcpClientTask:
	"""A nuttcp client running in a background thread, and the result it produces when done."""

	def __init__(self) -> None:
		self.thread: threading.Thread | None = None
		self.result: NuttcpResult | None = None
		self.error = ""


class StepStartNuttcpClientConfig(OrcraftTestStepConfig):
	name = OrcraftConfigField.Text(default="Start Nuttcp Client")
	nuttcp_package_folder = OrcraftConfigField.PackageFolder(default="", label="Nuttcp Package Folder")
	target_ip = OrcraftConfigField.Text(default="127.0.0.1", label="Target IP")
	control_port = OrcraftConfigField.Numeric(default=LINK_PARTNER_CONTROL_PORT, label="Control Port")
	protocol = OrcraftConfigField.Text(default="TCP", label="Protocol")
	duration_sec = OrcraftConfigField.Numeric(default=10, label="Duration Sec")
	buffer_length = OrcraftConfigField.Text(default="", label="Buffer Length")
	window_size = OrcraftConfigField.Text(default="", label="Window Size")
	rate = OrcraftConfigField.Text(default="", label="Rate")
	log_orientation = OrcraftConfigField.Format(default=OrcraftConfigField.LogTableOrientation.VERTICAL)


class StepStartNuttcpClientResult(OrcraftTestStepResult):
	log_orientation = OrcraftResultField.Format(default=OrcraftResultField.LogTableOrientation.VERTICAL)


class StepStartNuttcpClient(OrcraftTestStep):
	"""Starts a nuttcp client on this endpoint in a background thread and returns at once.

	The running task (the thread and its result holder) is carried on the step result so the
	wait step, targeting the same endpoint, can collect the measurement later. Starting every
	client before waiting for any of them lets the transfers of a bidirectional case overlap.
	"""

	def __init__(self, config: StepStartNuttcpClientConfig | None = None) -> None:
		super().__init__(config or StepStartNuttcpClientConfig())

	def _run_step(self) -> OrcraftTestStepResult:
		self.result = StepStartNuttcpClientResult()

		app = NuttcpApp(self.config.nuttcp_package_folder)
		target_ip = str(self.config.target_ip)
		control_port = int(self.config.control_port)
		protocol = str(self.config.protocol).upper()
		duration_sec = int(self.config.duration_sec)
		buffer_length = str(self.config.buffer_length or "")
		window_size = str(self.config.window_size or "")
		rate = str(self.config.rate or "")

		task = NuttcpClientTask()

		def _worker() -> None:
			try:
				task.result = app.run_client(
					target_ip,
					control_port=control_port,
					protocol=protocol,
					duration_sec=duration_sec,
					buffer_length=buffer_length,
					window_size=window_size,
					rate=rate,
				)
			except Exception as exc:
				task.error = str(exc)

		task.thread = threading.Thread(target=_worker, daemon=True)
		task.thread.start()

		Logger.log(
			f"Started nuttcp {protocol} client to {target_ip} (control port {control_port}) "
			f"for {duration_sec} seconds in the background.",
			module_tag=False,
		)

		self.result.task = task
		self.result.status = OrcraftStatus.PASS
		return self.result
