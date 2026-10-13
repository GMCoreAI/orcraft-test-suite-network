from __future__ import annotations

from orcraft import (
	OrcraftStatus,
	OrcraftTestStep,
	OrcraftTestStepConfig,
	OrcraftTestStepResult,
	OrcraftResultField,
	OrcraftConfigField,
	OrcraftLogger as Logger,
)


class StepStopNuttcpServerConfig(OrcraftTestStepConfig):
	name = OrcraftConfigField.Text(default="Stop Nuttcp Server")
	server = None
	log_orientation = OrcraftConfigField.Format(default=OrcraftConfigField.LogTableOrientation.VERTICAL)


class StepStopNuttcpServerResult(OrcraftTestStepResult):
	exited_on_its_own = OrcraftResultField.Boolean(default=False, label="Exited On Its Own")
	log_orientation = OrcraftResultField.Format(default=OrcraftResultField.LogTableOrientation.VERTICAL)


class StepStopNuttcpServer(OrcraftTestStep):
	"""Collects the output of a one-shot server started earlier on this endpoint.

	A one-shot server exits by itself once its transfer is over. When the transfer never
	happened the server is still listening, so this step kills it to leave the endpoint clean.
	"""

	def __init__(self, config: StepStopNuttcpServerConfig | None = None) -> None:
		super().__init__(config or StepStopNuttcpServerConfig())

	def _run_step(self) -> OrcraftTestStepResult:
		self.result = StepStopNuttcpServerResult()

		server = self.config.server
		if server is None:
			self.checkpoint(False, "nuttcp server handle is available.", "nuttcp server handle is missing.")
			return self.result

		output = server.stop()
		self.result.exited_on_its_own = not server.killed

		if output.stdout:
			Logger.log(output.stdout, module_tag=False)
		if output.stderr:
			Logger.log(output.stderr, color=Logger.Color.RED, module_tag=False)

		if server.killed:
			Logger.log(
				f"nuttcp server on control port {server.control_port} was still listening and was stopped.",
				color=Logger.Color.YELLOW,
				module_tag=False,
			)
		else:
			Logger.log(
				f"nuttcp server on control port {server.control_port} exited after serving its transfer.",
				module_tag=False,
			)

		self.result.status = OrcraftStatus.PASS
		return self.result
