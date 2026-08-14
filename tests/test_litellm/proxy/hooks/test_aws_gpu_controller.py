import asyncio
from datetime import timedelta

import pytest
from fastapi import HTTPException

from litellm.proxy.hooks import PROXY_HOOKS
from litellm.proxy.hooks.aws_gpu_controller import (
    AWSGPUControllerHook,
    GPUController,
    GPUControllerConfig,
    GPUControllerSnapshot,
)


class _FakeEC2Ops:
    def __init__(self) -> None:
        self.describe_calls = 0
        self.start_calls = 0
        self.stop_calls = 0

    async def describe_instance_state(self) -> str:
        self.describe_calls += 1
        return "stopped"

    async def start_instance(self) -> None:
        self.start_calls += 1

    async def stop_instance(self) -> None:
        self.stop_calls += 1


class _FakeHealthProbe:
    def __init__(self, *, ready_after_calls: int = 0) -> None:
        self.calls = 0
        self.ready_after_calls = ready_after_calls
        self.ready = False

    async def is_ready(self) -> bool:
        self.calls += 1
        if self.ready:
            return True
        return self.calls > self.ready_after_calls


def _make_controller(
    *,
    autostart: bool = True,
    autostop: bool = False,
    start_timeout_seconds: float = 0.05,
    health_interval_seconds: float = 0.001,
    idle_timeout_seconds: float = 0.01,
) -> tuple[GPUController, _FakeEC2Ops, _FakeHealthProbe]:
    config = GPUControllerConfig(
        autostart=autostart,
        autostop=autostop,
        aws_region="us-east-1",
        instance_id="i-1234567890abcdef0",
        vllm_health_url="http://127.0.0.1:8000/health",
        vllm_base_url="http://127.0.0.1:8000",
        start_timeout_seconds=start_timeout_seconds,
        health_interval_seconds=health_interval_seconds,
        idle_timeout_seconds=idle_timeout_seconds,
        idle_check_interval_seconds=0.001,
    )
    ec2_ops = _FakeEC2Ops()
    health_probe = _FakeHealthProbe(ready_after_calls=2)
    controller = GPUController(config=config, ec2_ops=ec2_ops, health_probe=health_probe)
    return controller, ec2_ops, health_probe


async def test_proxy_hook_registered():
    assert "aws_gpu_controller" in PROXY_HOOKS


@pytest.mark.asyncio
async def test_concurrent_requests_share_one_startup():
    controller, ec2_ops, health_probe = _make_controller()
    hook = AWSGPUControllerHook(controller=controller)
    request_data = {"model": "vllm/self-hosted"}

    results = await asyncio.gather(
        *(
            hook.async_pre_call_hook(
                user_api_key_dict=object(),
                cache=object(),
                data=request_data,
                call_type="completion",
            )
            for _ in range(4)
        )
    )

    assert results == [None, None, None, None]
    assert ec2_ops.start_calls == 1
    assert ec2_ops.describe_calls == 1
    assert health_probe.calls >= 3
    snapshot = await controller.get_state()
    assert isinstance(snapshot, GPUControllerSnapshot)
    assert snapshot.state == "READY"

    await asyncio.gather(
        *(
            hook.async_post_call_success_hook(
                data=request_data,
                user_api_key_dict=object(),
                response=object(),
            )
            for _ in range(4)
        )
    )
    final_snapshot = await controller.get_state()
    assert final_snapshot.active_requests == 0


@pytest.mark.asyncio
async def test_idle_timeout_stops_ready_gpu_once():
    controller, ec2_ops, _ = _make_controller(autostop=True)
    hook = AWSGPUControllerHook(controller=controller)
    request_data = {"model": "vllm/self-hosted"}

    await hook.async_pre_call_hook(
        user_api_key_dict=object(),
        cache=object(),
        data=request_data,
        call_type="completion",
    )
    await hook.async_post_call_success_hook(
        data=request_data,
        user_api_key_dict=object(),
        response=object(),
    )

    controller._last_request_at = controller._now() - timedelta(seconds=controller._config.idle_timeout_seconds + 1)

    await controller.maybe_stop_idle_gpu()

    snapshot = await controller.get_state()
    assert ec2_ops.stop_calls == 1
    assert snapshot.state == "STOPPED"


@pytest.mark.asyncio
async def test_startup_error_recovers_on_next_request():
    controller, ec2_ops, health_probe = _make_controller(start_timeout_seconds=0.01)
    hook = AWSGPUControllerHook(controller=controller)
    request_data = {"model": "vllm/self-hosted"}

    with pytest.raises(HTTPException) as exc_info:
        await hook.async_pre_call_hook(
            user_api_key_dict=object(),
            cache=object(),
            data=request_data,
            call_type="completion",
        )

    assert exc_info.value.status_code == 503
    failed_snapshot = await controller.get_state()
    assert failed_snapshot.state == "ERROR"
    assert ec2_ops.start_calls == 1

    health_probe.ready = True

    await hook.async_pre_call_hook(
        user_api_key_dict=object(),
        cache=object(),
        data=request_data,
        call_type="completion",
    )

    await hook.async_post_call_success_hook(
        data=request_data,
        user_api_key_dict=object(),
        response=object(),
    )

    recovered_snapshot = await controller.get_state()
    assert recovered_snapshot.state == "READY"
    assert recovered_snapshot.active_requests == 0
    assert ec2_ops.start_calls == 1
