# Orcraft network suite

An example Orcraft suite for a test that several machines run together: it measures TCP and UDP throughput between a system under test and its link partners with nuttcp, with the system under test transmitting, receiving, or both at once. The [Network Suite](https://orcraft.app/examples/network-suite/) page explains the setup, the suite's design and a full run.

All machines are Orcraft endpoints. The traffic runs on a test network of its own, separate from the network the controller uses to reach the machines, and every machine finds its own test address when the test runs.

## Groups

- TCP Traffic
- UDP Traffic
- Power States

The entry point is `test_suite_network.py`.

## Using it

1. Build the test setup described in `docs/Orcraft_Network_Test_Setup.pdf`: a control network for the controller and a separate test network for the measured traffic.
2. Put the nuttcp binaries in a package folder with `windows`, `linux` and `macos` subfolders; the suite's Nuttcp Package Folder field points at it, and the controller ships it to the endpoints.
3. Add the suite to the controller as the [Getting started](https://orcraft.app/setup/getting-started/) guide shows for the tutorial suite.

`docs/instructions.md` is the instruction file the site's AI agent example uses with this suite.

## License

MIT, see [LICENSE](LICENSE).

## Support

Ask any question, report an issue, request a feature: support@orcraft.app.
