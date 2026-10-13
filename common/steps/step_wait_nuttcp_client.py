from __future__ import annotations

from orcraft import (
	OrcraftTestStep,
	OrcraftTestStepConfig,
	OrcraftTestStepResult,
	OrcraftResultField,
	OrcraftConfigField,
	OrcraftLogger as Logger,
)


# Extra time the client gets beyond the transfer duration before it counts as stuck.
CLIENT_GRACE_SEC = 30


class StepWaitNuttcpClientConfig(OrcraftTestStepConfig):
	name = OrcraftConfigField.Text(default="Wait Nuttcp Client")
	task = None
	# The expected transfer length. The framework also reads this field to size the
	# remote call's deadline, so a step that blocks this long must declare it.
	duration_sec = OrcraftConfigField.Numeric(default=10, label="Duration Sec")
	log_orientation = OrcraftConfigField.Format(default=OrcraftConfigField.LogTableOrientation.VERTICAL)


class StepWaitNuttcpClientResult(OrcraftTestStepResult):
	throughput_mbps = OrcraftResultField.Numeric(default=0.0, label="Throughput Mbps")
	transferred_mb = OrcraftResultField.Numeric(default=0.0, label="Transferred MB")
	duration_sec = OrcraftResultField.Numeric(default=0.0, label="Duration Sec")
	retransmissions = OrcraftResultField.Numeric(default=None, label="Retransmissions")
	loss_percent = OrcraftResultField.Numeric(default=None, label="Loss Percent")
	tx_cpu_percent = OrcraftResultField.Numeric(default=None, label="TX CPU Percent")
	rx_cpu_percent = OrcraftResultField.Numeric(default=None, label="RX CPU Percent")
	log_orientation = OrcraftResultField.Format(default=OrcraftResultField.LogTableOrientation.VERTICAL)


class StepWaitNuttcpClient(OrcraftTestStep):
	"""Waits for a client started earlier on this endpoint and reads its measurement."""

	def __init__(self, config: StepWaitNuttcpClientConfig | None = None) -> None:
		super().__init__(config or StepWaitNuttcpClientConfig())

	def _run_step(self) -> OrcraftTestStepResult:
		self.result = StepWaitNuttcpClientResult()

		task = self.config.task
		if task is None:
			self.checkpoint(False, "nuttcp client task is available.", "nuttcp client task is missing.")
			return self.result

		timeout_sec = float(self.config.duration_sec) + CLIENT_GRACE_SEC
		task.thread.join(timeout=timeout_sec)
		if task.thread.is_alive():
			self.checkpoint(
				False,
				"nuttcp client finished in time.",
				f"nuttcp client did not finish within {timeout_sec:.0f} seconds.",
			)
			return self.result

		if task.error:
			self.checkpoint(
				False,
				"nuttcp client ran.",
				"nuttcp client could not run.",
				task.error,
			)
			return self.result

		run = task.result

		Logger.log(f"nuttcp client command: {run.command}", module_tag=False)
		if run.stdout:
			Logger.log(run.stdout, module_tag=False)
		if run.stderr:
			Logger.log(run.stderr, color=Logger.Color.RED, module_tag=False)

		self.result.throughput_mbps = run.throughput_mbps
		self.result.transferred_mb = run.transferred_mb
		self.result.duration_sec = run.duration_sec
		self.result.retransmissions = run.retransmissions
		self.result.loss_percent = run.loss_percent
		self.result.tx_cpu_percent = run.tx_cpu_percent
		self.result.rx_cpu_percent = run.rx_cpu_percent

		self.checkpoint(
			run.completed,
			f"nuttcp client completed: {run.summary_line}",
			"nuttcp client did not complete.",
			run.error or None,
		)

		return self.result
