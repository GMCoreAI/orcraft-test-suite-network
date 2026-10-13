from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Iterable

from orcraft import (
	OrcraftLogger as Logger,
	OrcraftEndpointState,
)

from common.endpoint_topology import endpoint_is_connected, endpoint_label
from common.traffic_models import (
	PowerMode,
	PowerRecoveryResult,
	TrafficPlan,
	TrafficRunResult,
	coerce_power_mode,
)
from common.traffic_orchestration import TrafficExecutionOptions, run_traffic_plan
from common.traffic_profiles import resolve_traffic_profile


@dataclass(frozen=True)
class PowerEventOutcome:
	"""Observable outcome of a SUT power-management action."""

	power_mode: PowerMode
	endpoint_name: str
	triggered: bool
	message: str = ""
	error: str = ""
	elapsed_seconds: float = 0.0

	@property
	def succeeded(self) -> bool:
		return self.triggered and not self.error


def run_power_recovery_test(
	plan: TrafficPlan,
	options: TrafficExecutionOptions,
	*,
	power_mode: object = PowerMode.RESTART_SUT,
	recovery_timeout: float = 180.0,
	recovery_poll_interval: float = 3.0,
	min_recovery_wait: float = 5.0,
	disconnect_seconds: float = 5.0,
	min_after_throughput_mbps: float = 0.0,
	max_throughput_drop_percent: float | None = 60.0,
) -> PowerRecoveryResult:
	"""Run baseline traffic, perform the selected SUT power event, wait for recovery, and rerun traffic."""

	mode = coerce_power_mode(power_mode)
	baseline = run_traffic_plan(plan, options)
	errors: list[str] = []

	if baseline.errors:
		errors.extend(f"Baseline traffic failed: {error}" for error in baseline.errors)
		return PowerRecoveryResult(
			power_mode=mode,
			baseline=baseline,
			after_recovery=_empty_run_result_like(plan, errors=("Post-recovery traffic was not run because baseline failed.",)),
			reconnected=False,
			recovery_seconds=0.0,
			errors=tuple(_dedupe(errors)),
		)

	if mode == PowerMode.NONE:
		Logger.log("No SUT power event selected; running comparison traffic without power change.\n", module_tag=False)
		after_recovery = run_traffic_plan(plan, options)
		compare_errors = compare_traffic_results(
			baseline,
			after_recovery,
			min_after_throughput_mbps=min_after_throughput_mbps,
			max_throughput_drop_percent=max_throughput_drop_percent,
		)
		return PowerRecoveryResult(
			power_mode=mode,
			baseline=baseline,
			after_recovery=after_recovery,
			reconnected=True,
			recovery_seconds=0.0,
			errors=compare_errors,
		)

	outcome = trigger_power_event(
		plan.sut.endpoint,
		mode,
		disconnect_seconds=disconnect_seconds,
		timeout=recovery_timeout,
	)

	if not outcome.succeeded:
		errors.append(outcome.error or outcome.message or f"Failed to trigger power event: {mode.value}.")
		return PowerRecoveryResult(
			power_mode=mode,
			baseline=baseline,
			after_recovery=_empty_run_result_like(plan, errors=("Post-recovery traffic was not run because power event failed.",)),
			reconnected=False,
			recovery_seconds=outcome.elapsed_seconds,
			errors=tuple(_dedupe(errors)),
		)

	if min_recovery_wait > 0:
		Logger.log(f"Waiting {min_recovery_wait:.1f} seconds before polling SUT recovery.\n", module_tag=False)
		time.sleep(min_recovery_wait)

	recovery_started = time.monotonic()
	reconnected = wait_for_endpoint_recovery(
		plan.sut.endpoint,
		timeout=recovery_timeout,
		poll_interval=recovery_poll_interval,
	)
	recovery_seconds = round(time.monotonic() - recovery_started + min_recovery_wait, 3)

	if not reconnected:
		errors.append(f"SUT did not reconnect within {recovery_timeout:.1f} seconds: {endpoint_label(plan.sut.endpoint)}.")
		return PowerRecoveryResult(
			power_mode=mode,
			baseline=baseline,
			after_recovery=_empty_run_result_like(plan, errors=("Post-recovery traffic was not run because SUT did not reconnect.",)),
			reconnected=False,
			recovery_seconds=recovery_seconds,
			errors=tuple(_dedupe(errors)),
		)

	Logger.log(f"SUT recovered after {recovery_seconds:.1f} seconds. Running post-recovery traffic.\n", module_tag=False)

	after_recovery = run_traffic_plan(plan, options)
	errors.extend(
		compare_traffic_results(
			baseline,
			after_recovery,
			min_after_throughput_mbps=min_after_throughput_mbps,
			max_throughput_drop_percent=max_throughput_drop_percent,
		)
	)

	return PowerRecoveryResult(
		power_mode=mode,
		baseline=baseline,
		after_recovery=after_recovery,
		reconnected=reconnected,
		recovery_seconds=recovery_seconds,
		errors=tuple(_dedupe(errors)),
	)


def trigger_power_event(
	endpoint: Any,
	power_mode: object,
	*,
	disconnect_seconds: float = 5.0,
	timeout: float = 120.0,
) -> PowerEventOutcome:
	"""Trigger the requested Orcraft endpoint power action through the endpoint object's public API."""

	mode = coerce_power_mode(power_mode)
	name = endpoint_label(endpoint)
	start = time.monotonic()

	if mode == PowerMode.NONE:
		return PowerEventOutcome(
			power_mode=mode,
			endpoint_name=name,
			triggered=True,
			message="No power event requested.",
			elapsed_seconds=0.0,
		)

	Logger.log(f"Triggering {mode.value} on SUT endpoint: {name}\n", module_tag=False)

	if mode == PowerMode.RESTART_SUT:
		outcome = restart_endpoint(endpoint, timeout=timeout)
	elif mode == PowerMode.DISCONNECT_RECONNECT:
		outcome = disconnect_reconnect_endpoint(endpoint, disconnect_seconds=disconnect_seconds, timeout=timeout)
	elif mode == PowerMode.SLEEP:
		outcome = sleep_endpoint(endpoint, timeout=timeout)
	else:
		outcome = PowerEventOutcome(
			power_mode=mode,
			endpoint_name=name,
			triggered=False,
			error=f"Unsupported power mode: {mode.value}.",
		)

	elapsed = round(time.monotonic() - start, 3)
	return PowerEventOutcome(
		power_mode=outcome.power_mode,
		endpoint_name=outcome.endpoint_name,
		triggered=outcome.triggered,
		message=outcome.message,
		error=outcome.error,
		elapsed_seconds=elapsed,
	)


def restart_endpoint(endpoint: Any, *, timeout: float = 120.0) -> PowerEventOutcome:
	"""Restart or reboot the selected SUT endpoint using supported Orcraft endpoint methods."""

	name = endpoint_label(endpoint)
	result = _invoke_endpoint_action(
		endpoint,
		(
			"restart",
			"reboot",
			"restart_endpoint",
			"reboot_endpoint",
			"power_restart",
			"power_cycle",
			"reset",
		),
		timeout=timeout,
	)

	if result[0]:
		return PowerEventOutcome(
			power_mode=PowerMode.RESTART_SUT,
			endpoint_name=name,
			triggered=True,
			message=result[1] or "Restart command accepted.",
		)

	return PowerEventOutcome(
		power_mode=PowerMode.RESTART_SUT,
		endpoint_name=name,
		triggered=False,
		error=result[1] or f"Endpoint does not expose a supported restart method: {name}.",
	)


def disconnect_reconnect_endpoint(
	endpoint: Any,
	*,
	disconnect_seconds: float = 5.0,
	timeout: float = 120.0,
) -> PowerEventOutcome:
	"""Disconnect and reconnect the selected SUT endpoint when supported by the endpoint API."""

	name = endpoint_label(endpoint)

	cycle_result = _invoke_endpoint_action(
		endpoint,
		(
			"disconnect_reconnect",
			"disconnect_and_reconnect",
			"cycle_connection",
			"power_cycle",
			"network_cycle",
		),
		timeout=timeout,
		duration=disconnect_seconds,
	)
	if cycle_result[0]:
		return PowerEventOutcome(
			power_mode=PowerMode.DISCONNECT_RECONNECT,
			endpoint_name=name,
			triggered=True,
			message=cycle_result[1] or "Disconnect/reconnect command accepted.",
		)

	disconnect_result = _invoke_endpoint_action(
		endpoint,
		(
			"disconnect",
			"disconnect_endpoint",
			"simulate_disconnect",
			"disable_network",
			"power_off",
			"power_off_endpoint",
		),
		timeout=timeout,
	)
	if not disconnect_result[0]:
		return PowerEventOutcome(
			power_mode=PowerMode.DISCONNECT_RECONNECT,
			endpoint_name=name,
			triggered=False,
			error=disconnect_result[1] or f"Endpoint does not expose a supported disconnect method: {name}.",
		)

	time.sleep(max(0.0, disconnect_seconds))

	reconnect_result = _invoke_endpoint_action(
		endpoint,
		(
			"reconnect",
			"connect",
			"reconnect_endpoint",
			"connect_endpoint",
			"enable_network",
			"power_on",
			"power_on_endpoint",
		),
		timeout=timeout,
	)
	if not reconnect_result[0]:
		return PowerEventOutcome(
			power_mode=PowerMode.DISCONNECT_RECONNECT,
			endpoint_name=name,
			triggered=False,
			error=reconnect_result[1] or f"Endpoint disconnected but reconnect command failed: {name}.",
		)

	return PowerEventOutcome(
		power_mode=PowerMode.DISCONNECT_RECONNECT,
		endpoint_name=name,
		triggered=True,
		message="Disconnect and reconnect commands accepted.",
	)


def sleep_endpoint(endpoint: Any, *, timeout: float = 120.0) -> PowerEventOutcome:
	"""Put the selected SUT endpoint to sleep using supported Orcraft endpoint methods.

	NOTE: Wake-from-magic-packet (Wake-on-LAN) is not implemented yet. This helper only issues the
	sleep/suspend command; the wake step (send a magic packet from a Link Partner to the SUT MAC) is
	the next piece of work for the Sleep power state.
	"""

	name = endpoint_label(endpoint)
	result = _invoke_endpoint_action(
		endpoint,
		(
			"sleep",
			"suspend",
			"standby",
			"hibernate",
			"sleep_endpoint",
			"suspend_endpoint",
			"enter_sleep",
			"power_sleep",
		),
		timeout=timeout,
	)

	if result[0]:
		return PowerEventOutcome(
			power_mode=PowerMode.SLEEP,
			endpoint_name=name,
			triggered=True,
			message=result[1] or "Sleep command accepted.",
		)

	return PowerEventOutcome(
		power_mode=PowerMode.SLEEP,
		endpoint_name=name,
		triggered=False,
		error=result[1] or f"Endpoint does not expose a supported sleep method: {name}.",
	)


def wait_for_endpoint_recovery(
	endpoint: Any,
	*,
	timeout: float = 180.0,
	poll_interval: float = 3.0,
) -> bool:
	"""Wait until the Orcraft endpoint reports a connected or ready state."""

	name = endpoint_label(endpoint)
	Logger.log(f"Waiting for SUT endpoint recovery: {name}\n", module_tag=False)

	wait_result = _invoke_wait_method(endpoint, timeout=timeout)
	if wait_result is not None:
		if wait_result:
			Logger.log(f"SUT endpoint recovery confirmed by endpoint wait method: {name}\n", module_tag=False)
			return True
		Logger.log(f"Endpoint wait method returned before SUT was connected: {name}\n", color=Logger.Color.YELLOW, module_tag=False)

	deadline = time.monotonic() + max(0.0, timeout)

	while time.monotonic() <= deadline:
		_refresh_endpoint(endpoint)
		if endpoint_is_connected(endpoint):
			Logger.log(f"SUT endpoint is connected: {name}\n", module_tag=False)
			return True

		time.sleep(max(0.2, poll_interval))

	return False


def compare_traffic_results(
	baseline: TrafficRunResult,
	after_recovery: TrafficRunResult,
	*,
	min_after_throughput_mbps: float = 0.0,
	max_throughput_drop_percent: float | None = 60.0,
) -> tuple[str, ...]:
	"""Compare baseline and post-event traffic results for recovery validation."""

	errors: list[str] = []

	if baseline.errors:
		errors.extend(f"Baseline traffic error: {error}" for error in baseline.errors)

	if after_recovery.errors:
		errors.extend(f"Post-recovery traffic error: {error}" for error in after_recovery.errors)

	if not after_recovery.worker_results:
		errors.append("Post-recovery traffic produced no worker results.")

	if after_recovery.sut_throughput_mbps <= 0:
		errors.append("Post-recovery SUT throughput was not positive.")

	if min_after_throughput_mbps > 0 and after_recovery.sut_throughput_mbps < min_after_throughput_mbps:
		errors.append(
			f"Post-recovery SUT throughput {after_recovery.sut_throughput_mbps:.3f} Mbps "
			f"is below required minimum {min_after_throughput_mbps:.3f} Mbps."
		)

	if (
		max_throughput_drop_percent is not None
		and baseline.sut_throughput_mbps > 0
		and after_recovery.sut_throughput_mbps >= 0
	):
		drop_percent = (
			(baseline.sut_throughput_mbps - after_recovery.sut_throughput_mbps)
			/ baseline.sut_throughput_mbps
			* 100.0
		)
		if drop_percent > max_throughput_drop_percent:
			errors.append(
				f"Post-recovery SUT throughput dropped by {drop_percent:.2f}% "
				f"from baseline, exceeding the allowed {max_throughput_drop_percent:.2f}%."
			)

	return tuple(_dedupe(errors))


def endpoint_power_event_supported(endpoint: Any, power_mode: object) -> bool:
	mode = coerce_power_mode(power_mode)

	if mode == PowerMode.NONE:
		return True

	if mode == PowerMode.RESTART_SUT:
		return _has_endpoint_action(
			endpoint,
			(
				"restart",
				"reboot",
				"restart_endpoint",
				"reboot_endpoint",
				"power_restart",
				"power_cycle",
				"reset",
			),
		)

	if mode == PowerMode.SLEEP:
		return _has_endpoint_action(
			endpoint,
			(
				"sleep",
				"suspend",
				"standby",
				"hibernate",
				"sleep_endpoint",
				"suspend_endpoint",
				"enter_sleep",
				"power_sleep",
			),
		)

	return _has_endpoint_action(
		endpoint,
		(
			"disconnect_reconnect",
			"disconnect_and_reconnect",
			"cycle_connection",
			"network_cycle",
			"disconnect",
			"disconnect_endpoint",
			"simulate_disconnect",
			"disable_network",
			"power_off",
			"power_cycle",
		),
	)


def _invoke_endpoint_action(
	endpoint: Any,
	method_names: Iterable[str],
	*,
	timeout: float,
	duration: float | None = None,
) -> tuple[bool, str]:
	errors: list[str] = []

	for target in _endpoint_targets(endpoint):
		for name in method_names:
			method = getattr(target, name, None)
			if not callable(method):
				continue

			for args, kwargs in _call_variants(timeout=timeout, duration=duration):
				try:
					result = method(*args, **kwargs)
					if result is False:
						errors.append(f"{name} returned False.")
						continue
					message = "" if result is None else str(result)
					return True, message
				except TypeError:
					continue
				except Exception as exc:
					errors.append(f"{name} failed: {exc}")

	return False, "; ".join(_dedupe(errors))


def _invoke_wait_method(endpoint: Any, *, timeout: float) -> bool | None:
	wait_methods = (
		"wait_until_connected",
		"wait_for_connected",
		"wait_for_reconnect",
		"wait_until_online",
		"wait_for_online",
		"wait_until_ready",
		"wait_for_ready",
	)

	for target in _endpoint_targets(endpoint):
		for name in wait_methods:
			method = getattr(target, name, None)
			if not callable(method):
				continue

			for args, kwargs in (((timeout,), {}), ((), {"timeout": timeout}), ((), {})):
				try:
					result = method(*args, **kwargs)
					return result is not False
				except TypeError:
					continue
				except Exception as exc:
					Logger.log(f"Endpoint wait method {name} failed: {exc}", color=Logger.Color.YELLOW, module_tag=False)
					return False

	return None


def _refresh_endpoint(endpoint: Any) -> None:
	for target in _endpoint_targets(endpoint):
		for name in ("refresh", "reload", "update", "sync", "poll"):
			method = getattr(target, name, None)
			if not callable(method):
				continue
			try:
				method()
				return
			except TypeError:
				continue
			except Exception:
				return


def _has_endpoint_action(endpoint: Any, method_names: Iterable[str]) -> bool:
	for target in _endpoint_targets(endpoint):
		for name in method_names:
			if callable(getattr(target, name, None)):
				return True
	return False


def _endpoint_targets(endpoint: Any) -> tuple[Any, ...]:
	if endpoint is None or isinstance(endpoint, str):
		return tuple()

	targets: list[Any] = [endpoint]

	for attr in ("power", "power_control", "management", "manager", "client", "controller", "network"):
		value = getattr(endpoint, attr, None)
		if value is not None and value not in targets:
			targets.append(value)

	return tuple(targets)


def _call_variants(*, timeout: float, duration: float | None) -> tuple[tuple[tuple[Any, ...], dict[str, Any]], ...]:
	variants: list[tuple[tuple[Any, ...], dict[str, Any]]] = [
		((), {"timeout": timeout}),
		((timeout,), {}),
		((), {}),
	]

	if duration is not None:
		variants.insert(0, ((), {"timeout": timeout, "duration": duration}))
		variants.insert(1, ((), {"timeout": timeout, "disconnect_seconds": duration}))
		variants.insert(2, ((duration,), {}))

	return tuple(variants)


def _empty_run_result_like(plan: TrafficPlan, *, errors: Iterable[str]) -> TrafficRunResult:
	profile_name = resolve_traffic_profile(plan.config.profile).name

	return TrafficRunResult(
		direction=plan.config.normalized_direction,
		protocol=plan.config.normalized_protocol,
		profile_name=profile_name,
		duration_seconds=float(plan.config.duration_seconds),
		worker_results=tuple(),
		errors=tuple(_dedupe(errors)),
	)


def connected_state_values() -> tuple[Any, ...]:
	values: list[Any] = []
	for name in ("CONNECTED", "READY", "ONLINE", "RUNNING", "AVAILABLE"):
		if hasattr(OrcraftEndpointState, name):
			values.append(getattr(OrcraftEndpointState, name))
	return tuple(values)


def _dedupe(values: Iterable[str]) -> list[str]:
	result: list[str] = []
	seen: set[str] = set()

	for value in values:
		text = str(value or "").strip()
		key = text.lower()
		if text and key not in seen:
			result.append(text)
			seen.add(key)

	return result
