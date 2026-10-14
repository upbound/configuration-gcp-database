"""Tests for the gRPC adapter: what it asks Crossplane for, and what it tells the user.

Composition tests can't see requirements or results, only the resources rendered.
"""

import asyncio

from crossplane.function import resource
from crossplane.function.proto.v1 import run_function_pb2 as fnv1
from test_core import BY_NAME, NS, PARAMS, PUBLISHED, UNPUBLISHED, XR

from function import core, fn


def run(params, network=None, *, extra=False) -> fnv1.RunFunctionResponse:
    req = fnv1.RunFunctionRequest()
    resource.update(
        req.observed.composite,
        {"metadata": {"name": XR, "namespace": NS}, "spec": {"parameters": params}},
    )
    if network is not None:
        # Older Crossplane versions deliver required resources as extra resources.
        found = req.extra_resources if extra else req.required_resources
        resource.update(found[fn.NETWORK_REQUIREMENT].items.add(), network)
    return asyncio.run(fn.FunctionRunner().RunFunction(req, None))


def test_by_id_requires_nothing():
    rsp = run(PARAMS)
    assert not rsp.requirements.resources
    assert not rsp.results


def test_by_name_requires_the_network_in_the_xr_namespace():
    for network in (None, UNPUBLISHED, PUBLISHED):
        selector = run(BY_NAME, network).requirements.resources[fn.NETWORK_REQUIREMENT]
        assert selector.api_version == "gcp.platform.upbound.io/v1alpha1"
        assert selector.kind == "Network"
        assert selector.match_name == "my-network"
        assert selector.namespace == NS


def test_says_what_it_is_waiting_for():
    for network, why in ((None, "was not found"), (UNPUBLISHED, "has not published")):
        rsp = run(BY_NAME, network)
        assert [r.severity for r in rsp.results] == [fnv1.SEVERITY_NORMAL]
        assert "Network my-network" in rsp.results[0].message
        assert why in rsp.results[0].message
        assert list(rsp.desired.resources) == [core.CONNECTION_SECRET]


def test_published_network_is_used_and_nothing_is_said():
    for extra in (False, True):
        rsp = run(BY_NAME, PUBLISHED, extra=extra)
        assert not rsp.results
        address = resource.struct_to_dict(rsp.desired.resources[core.PRIVATE_IP_ADDRESS].resource)
        assert address["spec"]["forProvider"]["network"] == PUBLISHED["status"]["vpc"]["id"]


def test_invalid_parameters_are_fatal_and_compose_nothing():
    rsp = run({**PARAMS, "networkRef": {}})
    assert [r.severity for r in rsp.results] == [fnv1.SEVERITY_FATAL]
    assert "networkRef must set id or name" in rsp.results[0].message
    assert not rsp.desired.resources


def test_publishes_status():
    status = resource.struct_to_dict(run(PARAMS).desired.composite.resource)["status"]
    assert status == {"connectionSecretRef": {"name": f"{XR}-connection"}}
