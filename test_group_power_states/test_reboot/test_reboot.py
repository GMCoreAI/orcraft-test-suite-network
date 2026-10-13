from __future__ import annotations

from traffic_lib.base_traffic_test import BaseTrafficTest, PowerTrafficConfig


class TestReboot(BaseTrafficTest):
	"""Reboots the SUT mid-suite and confirms TCP bidirectional traffic recovers afterwards."""

	PROTOCOL = "TCP"
	DIRECTION = "BX"
	POWER_MODE = "Restart SUT"

	def __init__(self, config: PowerTrafficConfig | None = None) -> None:
		super().__init__(config or PowerTrafficConfig(name="Reboot Recovery"))


def main() -> None:
	test = TestReboot()
	test.run()


if __name__ == "__main__":
	main()
