from __future__ import annotations

from orcraft import (
	OrcraftTestStep,
	OrcraftTestStepConfig,
	OrcraftTestStepResult,
	OrcraftResultField,
	OrcraftConfigField,
	OrcraftLogger as Logger,
)

from common.test_network import TEST_NETWORK, find_test_ip


class StepFindTestIpConfig(OrcraftTestStepConfig):
	name = OrcraftConfigField.Text(default="Find Test IP")
	network = OrcraftConfigField.Text(default=TEST_NETWORK, label="Network")
	log_orientation = OrcraftConfigField.Format(default=OrcraftConfigField.LogTableOrientation.VERTICAL)


class StepFindTestIpResult(OrcraftTestStepResult):
	test_ip = OrcraftResultField.Text(default="", label="Test IP")
	log_orientation = OrcraftResultField.Format(default=OrcraftResultField.LogTableOrientation.VERTICAL)


class StepFindTestIp(OrcraftTestStep):
	"""Finds the address this endpoint has on the network under test.

	The traffic runs between these addresses, not between the addresses the controller uses
	to reach the endpoints, so every machine of a test looks its own up before the transfers.
	"""

	def __init__(self, config: StepFindTestIpConfig | None = None) -> None:
		super().__init__(config or StepFindTestIpConfig())

	def _run_step(self) -> OrcraftTestStepResult:
		self.result = StepFindTestIpResult()

		network = str(self.config.network)
		self.result.test_ip = find_test_ip(network)

		if self.result.test_ip:
			Logger.log(f"Test IP on {network}: {self.result.test_ip}", module_tag=False)

		self.checkpoint(
			bool(self.result.test_ip),
			f"This endpoint is on {network} as {self.result.test_ip}.",
			f"This endpoint has no address on {network}; connect it to the network under test.",
		)

		return self.result
