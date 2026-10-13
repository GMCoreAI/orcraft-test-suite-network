from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
from dataclasses import dataclass


# Control ports of the one-shot nuttcp servers. The data port of a transfer is always the
# control port plus one. A link partner serves one stream, on its own machine, so every
# partner uses the same port; the SUT serves one stream per link partner, so its servers
# sit two ports apart from 5100 up (see sut_control_port). The two roles have different
# ports so that the SUT and a link partner may be the same machine. On Windows the port
# must always be given because port 5000, nuttcp's default, is already taken there.
SUT_CONTROL_PORT = 5100
LINK_PARTNER_CONTROL_PORT = 5200


def split_rate(rate: str, streams: int) -> str:
	"""The nuttcp rate of one stream when ``rate`` is shared equally by ``streams`` of them.

	A traffic test's rate is the load offered at the SUT's port, so with several link
	partners each stream carries an equal share of it. nuttcp takes a rate in Kbps, or in
	Mbps and Gbps with an m or g suffix, and accepts a fraction; the share is written in
	Mbps. An empty rate, a single stream, or a notation the suite does not know (such as a
	packets-per-second rate) is passed on unchanged.
	"""
	text = str(rate or "")
	match = _RATE_RE.match(text)
	if not match or streams <= 1:
		return text
	kbps = float(match.group(1)) * _RATE_KBPS[match.group(2).lower()]
	share_mbps = f"{kbps / streams / 1000.0:.3f}".rstrip("0").rstrip(".")
	return f"{share_mbps}m"


def sut_control_port(partner_index: int) -> int:
	"""Control port of the SUT's server for the link partner at this index: 5100, 5102, 5104 and so on."""
	return SUT_CONTROL_PORT + 2 * int(partner_index)

# Socket buffer of the UDP transfers; nuttcp's default is far too small for multi-gigabit rates.
UDP_SOCKET_BUFFER = "4M"


# The brief output line nuttcp prints when a transfer ends, for example:
#   647.9830 MB /  10.01 sec =  542.9427 Mbps 9 %TX 14 %RX 0 retrans 0.25 msRTT
#   2.6330 MB /  10.00 sec =   2.2087 Mbps 99 %TX 0 %RX 7292 / 7629 drop/pkt 95.58 %loss
_SUMMARY_RE = re.compile(r"(?P<mb>[\d.]+) MB /\s*(?P<sec>[\d.]+) sec =\s*(?P<mbps>[\d.]+) Mbps")
_TX_CPU_RE = re.compile(r"(\d+) %TX")
_RX_CPU_RE = re.compile(r"(\d+) %RX")
_RETRANS_RE = re.compile(r"(\d+) retrans")
_LOSS_RE = re.compile(r"(\d+) /\s*(\d+) drop/pkt\s+([\d.]+) %loss")
_RTT_RE = re.compile(r"([\d.]+) msRTT")
_VERSION_RE = re.compile(r"nuttcp-(\d+(?:\.\d+)+)")
_RATE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([kKmMgG]?)\s*$")
_RATE_KBPS = {"": 1.0, "k": 1.0, "m": 1000.0, "g": 1000000.0}


@dataclass
class NuttcpResult:
	"""Outcome of one nuttcp run. Hides the parsing of nuttcp's output from callers."""

	command: str
	stdout: str
	stderr: str
	returncode: int

	@property
	def summary_line(self) -> str:
		"""The brief result line nuttcp prints when the transfer ends, or empty."""
		for line in reversed(self.stdout.splitlines()):
			if _SUMMARY_RE.search(line):
				return line.strip()
		return ""

	@property
	def completed(self) -> bool:
		"""True when nuttcp exited cleanly and reported a throughput."""
		return self.returncode == 0 and bool(self.summary_line)

	@property
	def error(self) -> str:
		"""Why the run did not complete, or empty when it did."""
		if self.completed:
			return ""
		if self.stderr:
			return self.stderr
		if self.returncode != 0:
			return f"nuttcp exited with code {self.returncode}"
		return "nuttcp printed no throughput summary"

	@property
	def transferred_mb(self) -> float:
		match = _SUMMARY_RE.search(self.summary_line)
		return float(match.group("mb")) if match else 0.0

	@property
	def duration_sec(self) -> float:
		match = _SUMMARY_RE.search(self.summary_line)
		return float(match.group("sec")) if match else 0.0

	@property
	def throughput_mbps(self) -> float:
		match = _SUMMARY_RE.search(self.summary_line)
		return float(match.group("mbps")) if match else 0.0

	@property
	def tx_cpu_percent(self) -> int | None:
		match = _TX_CPU_RE.search(self.summary_line)
		return int(match.group(1)) if match else None

	@property
	def rx_cpu_percent(self) -> int | None:
		match = _RX_CPU_RE.search(self.summary_line)
		return int(match.group(1)) if match else None

	@property
	def retransmissions(self) -> int | None:
		"""TCP retransmissions, when the nuttcp build reports them."""
		match = _RETRANS_RE.search(self.summary_line)
		return int(match.group(1)) if match else None

	@property
	def loss_percent(self) -> float | None:
		"""UDP datagram loss in percent, or None for a TCP transfer."""
		match = _LOSS_RE.search(self.summary_line)
		return float(match.group(3)) if match else None

	@property
	def rtt_ms(self) -> float | None:
		match = _RTT_RE.search(self.summary_line)
		return float(match.group(1)) if match else None


@dataclass
class NuttcpServer:
	"""A one-shot nuttcp server running on this machine. It serves one transfer, then exits."""

	command: str
	process: subprocess.Popen
	control_port: int
	killed: bool = False

	@property
	def pid(self) -> int:
		return int(self.process.pid)

	@property
	def running(self) -> bool:
		return self.process.poll() is None

	def stop(self, timeout_sec: float = 5.0) -> NuttcpResult:
		"""Wait for the server to exit on its own, kill it when it is still listening, and return its output."""
		try:
			stdout, stderr = self.process.communicate(timeout=timeout_sec)
		except subprocess.TimeoutExpired:
			self.process.kill()
			self.killed = True
			stdout, stderr = self.process.communicate()
		return NuttcpResult(self.command, stdout.strip(), stderr.strip(), int(self.process.returncode))


class NuttcpApp:
	"""Wrapper around the nuttcp executable found in the uploaded package folder.

	The package folder holds the nuttcp binary for the endpoint's operating system, either
	directly ("nuttcp.exe" on Windows, "nuttcp" elsewhere) or in a subfolder named
	"windows", "linux" or "macos", so one package can serve a mixed fleet.
	"""

	def __init__(self, package_folder: str) -> None:
		self.package_folder = _normalize_long_path(package_folder)

	@property
	def executable(self) -> str:
		"""Path of the nuttcp binary for this operating system. Raises when the package has none."""
		name = "nuttcp.exe" if sys.platform == "win32" else "nuttcp"
		platform_folder = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
		for candidate in (
			os.path.join(self.package_folder, name),
			os.path.join(self.package_folder, platform_folder, name),
		):
			if os.path.isfile(candidate):
				return _ensure_executable(candidate).replace("\\", "/")
		raise FileNotFoundError(
			f"No {name} found in {self.package_folder} or in its {platform_folder} subfolder"
		)

	def get_version(self) -> str | None:
		"""Version reported by "nuttcp -V", for example "8.2.2", or None when it cannot be read."""
		completed = subprocess.run(
			[self.executable, "-V"],
			cwd=self.package_folder,
			capture_output=True,
			text=True,
			encoding="utf-8",
			errors="replace",
			timeout=10,
			**_child_process_options(),
		)
		match = _VERSION_RE.search(completed.stdout + completed.stderr)
		return match.group(1) if match else None

	def start_server(self, control_port: int) -> NuttcpServer:
		"""Start a one-shot server that stays in the foreground and exits after one transfer."""
		args = [self.executable, "-1", "--nofork", f"-P{int(control_port)}"]
		process = subprocess.Popen(
			args,
			cwd=self.package_folder,
			stdout=subprocess.PIPE,
			stderr=subprocess.PIPE,
			text=True,
			encoding="utf-8",
			errors="replace",
			**_child_process_options(),
		)
		return NuttcpServer(_display_command(args), process, int(control_port))

	def run_client(
		self,
		target_ip: str,
		*,
		control_port: int,
		protocol: str = "TCP",
		duration_sec: float = 10,
		buffer_length: str = "",
		window_size: str = "",
		rate: str = "",
	) -> NuttcpResult:
		"""Transmit to the server at target_ip for duration_sec seconds and return the parsed result.

		buffer_length ("-l"), window_size ("-w") and rate ("-R") take nuttcp's own notation,
		such as "64K", "1M" or "1G", and are left to nuttcp's defaults when empty.
		"""
		args = [
			self.executable,
			f"-T{duration_sec}",
			f"-P{int(control_port)}",
			f"-p{int(control_port) + 1}",
		]
		if str(protocol).upper() == "UDP":
			args.append("-u")
		if buffer_length:
			args.append(f"-l{buffer_length}")
		if window_size:
			args.append(f"-w{window_size}")
		if rate:
			args.append(f"-R{rate}")
		args.append(str(target_ip))

		completed = subprocess.run(
			args,
			cwd=self.package_folder,
			capture_output=True,
			text=True,
			encoding="utf-8",
			errors="replace",
			timeout=float(duration_sec) + 20.0,
			**_child_process_options(),
		)
		return NuttcpResult(
			_display_command(args),
			completed.stdout.strip(),
			completed.stderr.strip(),
			completed.returncode,
		)


def stop_leftover_nuttcp() -> bool:
	"""Kill nuttcp processes an aborted earlier run may have left on this machine.

	A one-shot server keeps listening until a client arrives, so a leftover one would take
	the control port of the next run. Returns True when something was stopped.
	"""
	if sys.platform == "win32":
		command = ["taskkill", "/IM", "nuttcp.exe", "/F"]
	else:
		command = ["pkill", "-x", "nuttcp"]
	try:
		completed = subprocess.run(command, capture_output=True, text=True, timeout=10, **_child_process_options())
	except FileNotFoundError:
		return False
	return completed.returncode == 0


def _child_process_options() -> dict:
	"""Options that keep a child process away from the endpoint's console.

	The cygwin build of nuttcp restores the console mode it inherited when it exits, which
	on Windows switches off ANSI colour handling for the endpoint's own log. Giving nuttcp no
	console window and no inherited stdin leaves the endpoint's console untouched.
	"""
	options: dict = {"stdin": subprocess.DEVNULL}
	if sys.platform == "win32":
		options["creationflags"] = subprocess.CREATE_NO_WINDOW
	return options


def _display_command(args: list[str]) -> str:
	return " ".join([os.path.basename(args[0])] + args[1:])


def _ensure_executable(path: str) -> str:
	"""Give an uploaded Unix binary its execute bit back; package uploads do not keep it."""
	if sys.platform != "win32" and not os.access(path, os.X_OK):
		os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
	return path


def _normalize_long_path(path: object) -> str:
	"""Coerce to str, strip whitespace, and resolve Windows 8.3 short path components.

	Uploaded package folders can arrive in short form on Windows; nuttcp is run from the
	long form so that its logged command lines stay readable.
	"""
	path = str(path or "").strip()

	if sys.platform != "win32":
		return path

	import ctypes
	current = path
	trailing: list[str] = []
	while current:
		buf = ctypes.create_unicode_buffer(32768)
		if ctypes.windll.kernel32.GetLongPathNameW(current, buf, 32768):
			result = os.path.join(buf.value, *reversed(trailing)) if trailing else buf.value
			return result.replace("\\", "/")
		parent = os.path.dirname(current)
		if parent == current:
			break
		trailing.append(os.path.basename(current))
		current = parent

	return path
