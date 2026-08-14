import asyncio
import contextlib
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Final, Literal, Protocol

import boto3
import httpx
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException, status

from litellm._logging import verbose_proxy_logger
from litellm.integrations.custom_logger import CustomLogger
from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.db.db_transaction_queue.pod_lock_manager import PodLockManager
from litellm.secret_managers.main import str_to_bool
from litellm.types.utils import CallTypesLiteral

GPUControllerState = Literal["STOPPED", "STARTING", "RUNNING", "READY", "STOPPING", "ERROR"]
_MANAGED_PROVIDERS: Final[frozenset[str]] = frozenset({"vllm", "hosted_vllm"})
_GPU_CONTROLLER_LOCK_ID: Final = "aws_gpu_controller"
_DEFAULT_START_TIMEOUT_SECONDS: Final = 300.0
_DEFAULT_HEALTH_INTERVAL_SECONDS: Final = 2.0
_DEFAULT_IDLE_TIMEOUT_SECONDS: Final = 1800.0
_DEFAULT_IDLE_CHECK_INTERVAL_SECONDS: Final = 5.0


class _EC2Operations(Protocol):
    async def describe_instance_state(self) -> str: ...

    async def start_instance(self) -> None: ...

    async def stop_instance(self) -> None: ...


class _HealthProbe(Protocol):
    async def is_ready(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class GPUControllerConfig:
    autostart: bool
    autostop: bool
    aws_region: str | None
    instance_id: str | None
    vllm_health_url: str | None
    vllm_base_url: str | None
    start_timeout_seconds: float
    health_interval_seconds: float
    idle_timeout_seconds: float
    idle_check_interval_seconds: float

    @staticmethod
    def _read_bool(settings: Mapping[str, object] | None, name: str, default: bool) -> bool:
        if settings is not None and name in settings:
            value: object = settings[name]
        else:
            value = os.getenv(name.upper())
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        return str_to_bool(str(value))

    @staticmethod
    def _read_float(settings: Mapping[str, object] | None, name: str, default: float) -> float:
        if settings is not None and name in settings:
            value: object = settings[name]
        else:
            value = os.getenv(name.upper())
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _read_str(settings: Mapping[str, object] | None, name: str) -> str | None:
        if settings is not None and name in settings:
            value: object = settings[name]
        else:
            value = os.getenv(name.upper())
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    @classmethod
    def from_settings(cls, general_settings: Mapping[str, object] | None = None) -> "GPUControllerConfig":
        nested_settings: Final = (
            general_settings.get("gpu_controller")
            if isinstance(general_settings, Mapping) and isinstance(general_settings.get("gpu_controller"), Mapping)
            else None
        )
        settings: Final = nested_settings if isinstance(nested_settings, Mapping) else general_settings
        base_url: Final = cls._read_str(settings, "vllm_base_url")
        health_url: Final = cls._read_str(settings, "vllm_health_url")
        derived_health_url: Final = health_url or (None if base_url is None else base_url.rstrip("/") + "/health")
        start_timeout_seconds: Final = cls._read_float(settings, "gpu_start_timeout", _DEFAULT_START_TIMEOUT_SECONDS)
        health_interval_seconds: Final = cls._read_float(
            settings, "vllm_health_interval", _DEFAULT_HEALTH_INTERVAL_SECONDS
        )
        idle_timeout_seconds: Final = cls._read_float(settings, "gpu_idle_timeout", _DEFAULT_IDLE_TIMEOUT_SECONDS)
        config: Final = cls(
            autostart=cls._read_bool(settings, "gpu_autostart", False),
            autostop=cls._read_bool(settings, "gpu_autostop", False),
            aws_region=cls._read_str(settings, "aws_region"),
            instance_id=cls._read_str(settings, "gpu_ec2_instance_id"),
            vllm_health_url=derived_health_url,
            vllm_base_url=base_url,
            start_timeout_seconds=start_timeout_seconds,
            health_interval_seconds=health_interval_seconds,
            idle_timeout_seconds=idle_timeout_seconds,
            idle_check_interval_seconds=_DEFAULT_IDLE_CHECK_INTERVAL_SECONDS,
        )
        if config.autostart or config.autostop:
            missing: Final[tuple[str, ...]] = tuple(
                name
                for name, value in (
                    ("AWS_REGION", config.aws_region),
                    ("GPU_EC2_INSTANCE_ID", config.instance_id),
                    ("VLLM_HEALTH_URL or VLLM_BASE_URL", config.vllm_health_url),
                )
                if value is None
            )
            if missing:
                raise ValueError(
                    "GPU controller is enabled but missing required settings: " + ", ".join(missing)
                )
        return config

    @property
    def enabled(self) -> bool:
        return (self.autostart or self.autostop) and self.instance_id is not None and self.aws_region is not None

    @property
    def startup_lock_ttl_seconds(self) -> float:
        return max(self.start_timeout_seconds + 60.0, 120.0)


@dataclass(frozen=True, slots=True)
class GPUControllerSnapshot:
    state: GPUControllerState
    active_requests: int
    last_request_at: datetime | None
    last_health_check_at: datetime | None
    last_error: str | None


class _Boto3EC2Operations:
    def __init__(self, *, aws_region: str, instance_id: str) -> None:
        self._aws_region = aws_region
        self._instance_id = instance_id
        self._client = None

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = boto3.client("ec2", region_name=self._aws_region)
        return self._client

    async def describe_instance_state(self) -> str:
        response = await asyncio.to_thread(
            self._get_client().describe_instances,
            InstanceIds=[self._instance_id],
        )
        reservations: Final = response.get("Reservations") or []
        instances: Final = [
            instance
            for reservation in reservations
            for instance in (reservation.get("Instances") or [])
            if isinstance(instance, Mapping)
        ]
        if not instances:
            raise ValueError(f"EC2 instance {self._instance_id} was not found")
        state: Final = ((instances[0].get("State") or {}).get("Name") or "").lower()
        if not state:
            raise ValueError(f"EC2 instance {self._instance_id} returned an empty state")
        return state

    async def start_instance(self) -> None:
        await asyncio.to_thread(self._get_client().start_instances, InstanceIds=[self._instance_id])

    async def stop_instance(self) -> None:
        await asyncio.to_thread(self._get_client().stop_instances, InstanceIds=[self._instance_id])


class _HttpxHealthProbe:
    def __init__(self, health_url: str, timeout_seconds: float) -> None:
        self._health_url = health_url
        self._timeout_seconds = timeout_seconds

    async def is_ready(self) -> bool:
        timeout: Final = httpx.Timeout(self._timeout_seconds, connect=self._timeout_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(self._health_url)
            return response.status_code == status.HTTP_200_OK
        except httpx.HTTPError:
            return False


class GPUController:
    def __init__(
        self,
        *,
        config: GPUControllerConfig,
        ec2_ops: _EC2Operations,
        health_probe: _HealthProbe,
        pod_lock_manager: PodLockManager | None = None,
    ) -> None:
        self._config = config
        self._ec2_ops = ec2_ops
        self._health_probe = health_probe
        self._pod_lock_manager = pod_lock_manager
        self._state: GPUControllerState = "STOPPED"
        self._last_error: str | None = None
        self._active_requests = 0
        self._last_request_at: datetime | None = None
        self._last_health_check_at: datetime | None = None
        self._startup_task: asyncio.Task[None] | None = None
        self._idle_task: asyncio.Task[None] | None = None
        self._operation_lock = asyncio.Lock()

    @classmethod
    def from_settings(
        cls,
        *,
        general_settings: Mapping[str, object] | None = None,
        pod_lock_manager: PodLockManager | None = None,
    ) -> "GPUController":
        config: Final = GPUControllerConfig.from_settings(general_settings=general_settings)
        if not config.enabled:
            return cls(
                config=config,
                ec2_ops=_NoopEC2Operations(),
                health_probe=_NoopHealthProbe(),
                pod_lock_manager=pod_lock_manager,
            )
        assert config.instance_id is not None
        assert config.aws_region is not None
        assert config.vllm_health_url is not None
        return cls(
            config=config,
            ec2_ops=_Boto3EC2Operations(aws_region=config.aws_region, instance_id=config.instance_id),
            health_probe=_HttpxHealthProbe(
                health_url=config.vllm_health_url,
                timeout_seconds=config.health_interval_seconds,
            ),
            pod_lock_manager=pod_lock_manager,
        )

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _log(self, message: str, **fields: object) -> None:
        if fields:
            field_str: Final = " ".join(f"{key}={value}" for key, value in fields.items())
            verbose_proxy_logger.info("GPU_CONTROLLER: %s %s", message, field_str)
            return
        verbose_proxy_logger.info("GPU_CONTROLLER: %s", message)

    def _snapshot(self) -> GPUControllerSnapshot:
        return GPUControllerSnapshot(
            state=self._state,
            active_requests=self._active_requests,
            last_request_at=self._last_request_at,
            last_health_check_at=self._last_health_check_at,
            last_error=self._last_error,
        )

    async def get_state(self) -> GPUControllerSnapshot:
        return self._snapshot()

    def _health_check_is_fresh(self) -> bool:
        if self._last_health_check_at is None:
            return False
        elapsed_seconds: Final = (self._now() - self._last_health_check_at).total_seconds()
        return elapsed_seconds < self._config.health_interval_seconds

    async def is_gpu_ready(self) -> bool:
        if not self.enabled:
            return False
        if self._state == "READY" and self._health_check_is_fresh():
            return True
        ready: Final = await self._health_probe.is_ready()
        self._last_health_check_at = self._now()
        if ready:
            self._state = "READY"
            self._last_error = None
        return ready

    async def record_request_start(self) -> None:
        if not self.enabled:
            return
        async with self._operation_lock:
            self._active_requests += 1
            self._last_request_at = self._now()
            self._log("request_start", active_requests=self._active_requests, state=self._state)

    async def record_request_end(self) -> None:
        if not self.enabled:
            return
        async with self._operation_lock:
            self._active_requests = max(0, self._active_requests - 1)
            self._log("request_end", active_requests=self._active_requests, state=self._state)

    async def ensure_ready(self) -> None:
        if not self.enabled:
            return
        if await self.is_gpu_ready():
            return

        task: Final = await self._get_or_create_startup_task()
        try:
            await task
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"error": str(exc)},
            ) from exc

    async def _get_or_create_startup_task(self) -> asyncio.Task[None]:
        async with self._operation_lock:
            if self._startup_task is not None and not self._startup_task.done():
                return self._startup_task
            self._startup_task = asyncio.create_task(self._startup_sequence())
            return self._startup_task

    async def _startup_sequence(self) -> None:
        start_at: Final = time.monotonic()
        self._state = "STARTING"
        self._last_error = None
        self._log("state", state=self._state, action="ensure_ready")
        try:
            lock_acquired: Final = await self._acquire_start_lock()
            if not lock_acquired:
                await self._wait_for_remote_startup(start_at=start_at)
                return
            try:
                ec2_state: Final = await self._ec2_ops.describe_instance_state()
                self._log("ec2_state", state=ec2_state)
                if ec2_state == "stopped":
                    await self._start_instance()
                elif ec2_state in {"pending", "running"}:
                    self._state = "RUNNING"
                elif ec2_state == "stopping":
                    self._state = "STOPPING"
                else:
                    raise ValueError(f"Unsupported EC2 state {ec2_state}")
                await self.wait_for_vllm(start_at=start_at)
            finally:
                await self._release_start_lock()
        except HTTPException as exc:
            self._state = "ERROR"
            self._last_error = str(exc.detail)
            self._log("state", state=self._state, error=self._last_error)
            raise
        except (BotoCoreError, ClientError, TimeoutError, ValueError) as exc:
            self._state = "ERROR"
            self._last_error = str(exc)
            self._log("state", state=self._state, error=self._last_error)
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"error": str(exc)}) from exc
        finally:
            self._startup_task = None

    async def _acquire_start_lock(self) -> bool:
        if self._pod_lock_manager is None:
            return True
        acquired: Final = await self._pod_lock_manager.acquire_lock(
            cronjob_id=_GPU_CONTROLLER_LOCK_ID,
            ttl=int(self._config.startup_lock_ttl_seconds),
        )
        return bool(acquired is True or acquired is None)

    async def _release_start_lock(self) -> None:
        if self._pod_lock_manager is None:
            return
        await self._pod_lock_manager.release_lock(cronjob_id=_GPU_CONTROLLER_LOCK_ID)

    async def _start_instance(self) -> None:
        self._state = "STARTING"
        self._log("action=start_instance", state=self._state)
        await self._ec2_ops.start_instance()

    async def wait_for_vllm(self, *, start_at: float | None = None) -> None:
        deadline: Final = (start_at or time.monotonic()) + self._config.start_timeout_seconds
        while True:
            if await self._health_probe.is_ready():
                self._state = "READY"
                self._last_health_check_at = self._now()
                self._last_error = None
                self._log("state", state=self._state)
                return
            self._last_health_check_at = self._now()
            if time.monotonic() >= deadline:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={
                        "error": (
                            f"vLLM did not become healthy within {self._config.start_timeout_seconds:.0f} seconds"
                        )
                    },
                )
            await asyncio.sleep(self._config.health_interval_seconds)

    async def _wait_for_remote_startup(self, *, start_at: float) -> None:
        deadline: Final = start_at + self._config.start_timeout_seconds
        while True:
            if await self.is_gpu_ready():
                return
            lock_acquired: Final = await self._acquire_start_lock()
            if lock_acquired:
                try:
                    ec2_state: Final = await self._ec2_ops.describe_instance_state()
                    self._log("ec2_state", state=ec2_state)
                    if ec2_state == "stopped":
                        await self._start_instance()
                    elif ec2_state in {"pending", "running"}:
                        self._state = "RUNNING"
                    elif ec2_state == "stopping":
                        self._state = "STOPPING"
                    else:
                        raise ValueError(f"Unsupported EC2 state {ec2_state}")
                    await self.wait_for_vllm(start_at=start_at)
                    return
                finally:
                    await self._release_start_lock()
            if time.monotonic() >= deadline:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={
                        "error": (
                            "GPU is starting elsewhere but vLLM did not become healthy within "
                            f"{self._config.start_timeout_seconds:.0f} seconds"
                        )
                    },
                )
            await asyncio.sleep(self._config.health_interval_seconds)

    async def stop_gpu(self) -> None:
        if not self.enabled:
            return
        async with self._operation_lock:
            if self._active_requests > 0 or self._state in {"STOPPED", "STOPPING"}:
                return
            self._state = "STOPPING"
            self._log("action=stop_instance", state=self._state)
            try:
                await self._ec2_ops.stop_instance()
                self._state = "STOPPED"
                self._last_error = None
                self._last_health_check_at = None
                self._log("state", state=self._state)
            except (BotoCoreError, ClientError) as exc:
                self._state = "ERROR"
                self._last_error = str(exc)
                self._log("state", state=self._state, error=self._last_error)
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"error": str(exc)}) from exc

    async def maybe_stop_idle_gpu(self) -> None:
        if not self.enabled or not self._config.autostop:
            return
        if self._state != "READY" or self._active_requests > 0 or self._last_request_at is None:
            return
        idle_seconds: Final = (self._now() - self._last_request_at).total_seconds()
        if idle_seconds < self._config.idle_timeout_seconds:
            return
        await self.stop_gpu()

    async def shutdown(self) -> None:
        idle_task: Final = self._idle_task
        if idle_task is not None:
            idle_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await idle_task

    def start_background_tasks(self) -> None:
        if not self.enabled or not self._config.autostop:
            return
        if self._idle_task is not None and not self._idle_task.done():
            return
        self._idle_task = asyncio.create_task(self._idle_monitor_loop())
        self._log("background_task_started", interval=self._config.idle_check_interval_seconds)

    async def _idle_monitor_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._config.idle_check_interval_seconds)
                await self.maybe_stop_idle_gpu()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._state = "ERROR"
            self._last_error = str(exc)
            self._log("state", state=self._state, error=self._last_error)


class _NoopEC2Operations:
    async def describe_instance_state(self) -> str:
        return "stopped"

    async def start_instance(self) -> None:
        return None

    async def stop_instance(self) -> None:
        return None


class _NoopHealthProbe:
    async def is_ready(self) -> bool:
        return False


class AWSGPUControllerHook(CustomLogger):
    def __init__(
        self,
        *,
        general_settings: Mapping[str, object] | None = None,
        llm_router: object | None = None,
        pod_lock_manager: PodLockManager | None = None,
        controller: GPUController | None = None,
    ) -> None:
        super().__init__()
        self._llm_router = llm_router
        self._controller = controller or GPUController.from_settings(
            general_settings=general_settings,
            pod_lock_manager=pod_lock_manager,
        )

    def _request_is_managed(self, data: Mapping[str, object] | None) -> bool:
        if data is None or not self._controller.enabled:
            return False
        model = data.get("model")
        if not isinstance(model, str) or not model:
            return False
        provider = self._resolve_provider(model_name=model)
        return provider in _MANAGED_PROVIDERS

    def _resolve_provider(self, *, model_name: str) -> str | None:
        deployment = None
        if self._llm_router is not None:
            try:
                deployment = self._llm_router.get_deployment_by_model_group_name(model_group_name=model_name)
            except Exception:
                deployment = None
        if deployment is not None:
            litellm_params = getattr(deployment, "litellm_params", None)
            provider = getattr(litellm_params, "custom_llm_provider", None)
            if isinstance(provider, str) and provider:
                return provider
            deployment_model = getattr(litellm_params, "model", None)
            if isinstance(deployment_model, str) and "/" in deployment_model:
                return deployment_model.split("/", 1)[0]
        if "/" in model_name:
            return model_name.split("/", 1)[0]
        return None

    async def async_pre_call_hook(
        self,
        user_api_key_dict: UserAPIKeyAuth,
        cache: object,
        data: dict,
        call_type: CallTypesLiteral,
    ) -> Exception | str | dict | None:
        if not self._request_is_managed(data):
            return None
        await self._controller.record_request_start()
        try:
            await self._controller.ensure_ready()
        except Exception:
            await self._controller.record_request_end()
            raise
        return None

    async def async_post_call_success_hook(
        self,
        data: dict,
        user_api_key_dict: UserAPIKeyAuth,
        response: object,
    ) -> object | None:
        if self._request_is_managed(data):
            await self._controller.record_request_end()
        return None

    async def async_post_call_failure_hook(
        self,
        request_data: dict,
        original_exception: Exception,
        user_api_key_dict: UserAPIKeyAuth,
        traceback_str: str | None = None,
    ) -> object | None:
        if self._request_is_managed(request_data):
            await self._controller.record_request_end()
        return None

    def start_background_tasks(self) -> None:
        self._controller.start_background_tasks()
