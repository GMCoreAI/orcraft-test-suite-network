from __future__ import annotations

import os

from orcraft import (
	OrcraftTestStep,
	OrcraftTestStepConfig,
	OrcraftTestStepResult,
	OrcraftResultField,
	OrcraftConfigField,
	OrcraftLogger as Logger,
)

from common.nuttcp_app import NuttcpApp, stop_leftover_nuttcp


class StepVerifyNuttcpConfig(OrcraftTestStepConfig):
	name = OrcraftConfigField.Text(default="Verify Nuttcp")
	nuttcp_package_folder = OrcraftConfigField.PackageFolder(default="", label="Nuttcp Package Folder")
	log_orientation = OrcraftConfigField.Format(default=OrcraftConfigField.LogTableOrientation.VERTICAL)


class StepVerifyNuttcpResult(OrcraftTestStepResult):
	executable_path = OrcraftResultField.Text(default="", label="Executable Path")
	nuttcp_version = OrcraftResultField.Text(default="", label="Nuttcp Version")
	leftover_stopped = OrcraftResultField.Boolean(default=False, label="Leftover Stopped")
	log_orientation = OrcraftResultField.Format(default=OrcraftResultField.LogTableOrientation.VERTICAL)


class StepVerifyNuttcp(OrcraftTestStep):
	"""Checks that the uploaded package holds a nuttcp binary this endpoint can run.

	It also stops any nuttcp an aborted earlier run left behind, so that a stale one-shot
	server cannot hold the control port of this run. The endpoint is locked for this test,
	so no other run can own those processes.
	"""

	def __init__(self, config: StepVerifyNuttcpConfig | None = None) -> None:
		super().__init__(config or StepVerifyNuttcpConfig())

	def _run_step(self) -> OrcraftTestStepResult:
		self.result = StepVerifyNuttcpResult()

		self.result.leftover_stopped = stop_leftover_nuttcp()
		if self.result.leftover_stopped:
			Logger.log(
				"Stopped a nuttcp process left over from an earlier run.",
				color=Logger.Color.YELLOW,
				module_tag=False,
			)

		app = NuttcpApp(self.config.nuttcp_package_folder)

		try:
			executable = app.executable
		except FileNotFoundError as exc:
			self.checkpoint(
				False,
				"nuttcp binary found in the package folder.",
				"nuttcp binary is missing from the package folder.",
				str(exc),
			)
			return self.result

		# The result names the binary by its place in the package, which is what tells the platforms
		# apart; the log keeps the full path on this endpoint.
		self.result.executable_path = os.path.relpath(executable, app.package_folder).replace("\\", "/")
		Logger.log(f"nuttcp executable: {executable}", module_tag=False)

		version = app.get_version()
		self.result.nuttcp_version = version or ""

		self.checkpoint(
			version is not None,
			f"nuttcp {version} runs on this endpoint.",
			"nuttcp did not report its version.",
		)

		return self.result
