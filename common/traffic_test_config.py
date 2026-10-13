from __future__ import annotations

from orcraft import (
	OrcraftTestConfig,
	OrcraftConfigField,
)


class TrafficTestConfig(OrcraftTestConfig):
	"""Configuration shared by every traffic test.

	The SUT and the link partners are the machines Orcraft controls. The traffic runs on the
	network under test, a separate link from the one the controller uses to reach them; each
	machine finds its own address on that network when the test runs, so no address is
	configured here. With several link partners the SUT talks to all of them at once.
	"""

	sut_endpoint = OrcraftConfigField.Endpoint(default="localhost", label="SUT Endpoint")
	link_partner_endpoints = OrcraftConfigField.MultiSelectEndpoints(
		default=("localhost",),
		label="Link Partner Endpoints",
	)

	nuttcp_package_folder = OrcraftConfigField.PackageFolder(
		default=r"C:\Orcraft\apps\NUTTCP\bin",
		label="Nuttcp Package Folder",
		required=True,
		layout=OrcraftConfigField.Layout.NewRow,
	)

	duration_sec = OrcraftConfigField.Numeric(
		default=10,
		label="Duration Sec",
		layout=OrcraftConfigField.Layout.NewRow,
	)
	min_throughput_mbps = OrcraftConfigField.Numeric(default=100, label="Min Throughput Mbps")

	log_orientation = OrcraftConfigField.Format(default=OrcraftConfigField.LogTableOrientation.VERTICAL)
