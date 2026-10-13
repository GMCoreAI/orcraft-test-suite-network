from __future__ import annotations

import time

from orcraft import (
	OrcraftTestStep,
	OrcraftTestStepConfig,
	OrcraftTestStepResult,
	OrcraftResultField,
	OrcraftConfigField,
	OrcraftLogger as Logger,
)

from common.nuttcp_app import NuttcpApp, SUT_CONTROL_PORT


# How long the server gets to bind its port before the step looks at it.
STARTUP_WAIT_SEC = 1.0


class StepStartNuttcpServerConfig(OrcraftTestStepConfig):
	name = OrcraftConfigField.Text(default="Start Nuttcp Server")
	nuttcp_package_folder = OrcraftConfigField.PackageFolder(default="", label="Nuttcp Package Folder")
	control_port = OrcraftConfigField.Numeric(default=SUT_CONTROL_PORT, label="Control Port")
	log_orientation = OrcraftConfigField.Format(default=OrcraftConfigField.LogTableOrientation.VERTICAL)


class StepStartNuttcpServerResult(OrcraftTestStepResult):
	pid = OrcraftResultField.Numeric(default=0, label="PID")
	log_orientation = OrcraftResultField.Format(default=OrcraftResultField.LogTableOrientation.VERTICAL)


class StepStartNuttcpServer(OrcraftTestStep):
	"""Starts a one-shot nuttcp server on this endpoint and returns while it keeps listening.

	The server handle is carried on the step result so the stop step, targeting the same
	endpoint, can collect its output once the transfer is over.
	"""

	def __init__(self, config: StepStartNuttcpServerConfig | None = None) -> None:
		super().__init__(config or StepStartNuttcpServerConfig())

	def _run_step(self) -> OrcraftTestStepResult:
		self.result = StepStartNuttcpServerResult()

		control_port = int(self.config.control_port)
		server = NuttcpApp(self.config.nuttcp_package_folder).start_server(control_port)

		Logger.log(f"Started nuttcp server: {server.command}", module_tag=False)

		time.sleep(STARTUP_WAIT_SEC)
		running = server.running
		details = "" if running else server.stop().error

		self.checkpoint(
			running,
			f"nuttcp one-shot server is listening on control port {control_port} (PID {server.pid}).",
			f"nuttcp server exited during startup on control port {control_port}.",
			details or None,
		)

		if running:
			self.result.server = server
			self.result.pid = server.pid

		return self.result
