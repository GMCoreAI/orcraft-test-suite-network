from __future__ import annotations

from traffic_lib.base_traffic_test import BaseTrafficTest, PowerTrafficConfig


class TestSleep(BaseTrafficTest):
	"""Puts the SUT to sleep mid-suite and confirms TCP bidirectional traffic recovers afterwards.

	NOTE: Wake-from-magic-packet (Wake-on-LAN) support is not implemented yet. Until it is added,
	recovery relies on the SUT waking on its own, so this test currently scaffolds the power flow
	only. The magic-packet wake (auto-detected SUT MAC, sent from a Link Partner) is the next step.
	"""

	PROTOCOL = "TCP"
	DIRECTION = "BX"
	POWER_MODE = "Sleep"

	def __init__(self, config: PowerTrafficConfig | None = None) -> None:
		super().__init__(config or PowerTrafficConfig(name="Sleep Recovery"))


def main() -> None:
	test = TestSleep()
	test.run()


if __name__ == "__main__":
	main()
