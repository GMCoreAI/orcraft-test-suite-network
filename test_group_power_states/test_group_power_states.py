from __future__ import annotations

from orcraft import (
	OrcraftConfigField,
	OrcraftTestGroup,
	OrcraftTestGroupConfig,
	OrcraftTestGroupResult,
)

from test_group_power_states.test_reboot.test_reboot import TestReboot
from test_group_power_states.test_sleep.test_sleep import TestSleep


class TestGroupPowerStatesConfig(OrcraftTestGroupConfig):
	name = OrcraftConfigField.Text(default="Power States", label="Name")
	description = OrcraftConfigField.Text(default="Exercises SUT power-management transitions (reboot and sleep) while a single TCP bidirectional traffic case runs, confirming distributed nuttcp traffic recovers after the SUT returns.")
	tests = OrcraftConfigField.Tests(default_factory=lambda: [
		TestReboot(),
		TestSleep(),
	])


class TestGroupPowerStatesResult(OrcraftTestGroupResult):
	pass


class TestGroupPowerStates(OrcraftTestGroup):
	def __init__(self) -> None:
		super().__init__(config=TestGroupPowerStatesConfig())
		self.result = TestGroupPowerStatesResult()


def main() -> None:
	group = TestGroupPowerStates()
	group.run()


if __name__ == "__main__":
	main()
