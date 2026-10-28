"""Composition function for the GCP SQLInstance.

The gRPC side only: reading the request, asking Crossplane for the referenced Network, and writing
the response. What gets composed is decided in core.py.
"""

import grpc
from crossplane.function import logging, request, resource, response
from crossplane.function.proto.v1 import run_function_pb2 as fnv1
from crossplane.function.proto.v1 import run_function_pb2_grpc as grpcv1

from . import core
from .serialize import to_dict

# The name this function's Network requirement goes by in requests and responses.
NETWORK_REQUIREMENT = "network"


class FunctionRunner(grpcv1.FunctionRunnerService):
    """A FunctionRunner handles gRPC RunFunctionRequests."""

    def __init__(self):
        """Create a new FunctionRunner."""
        self.log = logging.get_logger()

    async def RunFunction(
        self, req: fnv1.RunFunctionRequest, _: grpc.aio.ServicerContext
    ) -> fnv1.RunFunctionResponse:
        """Run the function."""
        log = self.log.bind(tag=req.meta.tag)
        rsp = response.to(req)

        xr = resource.struct_to_dict(req.observed.composite.resource)
        meta = xr.get("metadata") or {}
        xr_name = meta.get("name")
        namespace = meta.get("namespace")
        params = (xr.get("spec") or {}).get("parameters") or {}

        for field, value in (("name", xr_name), ("namespace", namespace)):
            if not value:
                response.fatal(rsp, f"observed composite resource has no metadata.{field}")
                return rsp

        errors = core.validate(params)
        if errors:
            response.fatal(rsp, "invalid SQLInstance: " + "; ".join(errors))
            return rsp

        observed = {
            name: resource.struct_to_dict(r.resource) for name, r in req.observed.resources.items()
        }
        connection_details = {
            name: dict(r.connection_details) for name, r in req.observed.resources.items()
        }

        # Requirements are declared on every call: Crossplane calls the function again until the
        # set it asks for stops changing, then passes what it found.
        network_name = core.network_name(params)
        network = None
        if network_name:
            response.require_resources(
                rsp,
                NETWORK_REQUIREMENT,
                core.NETWORK_API_VERSION,
                core.NETWORK_KIND,
                match_name=network_name,
                namespace=namespace,
            )
            network = _required(req, NETWORK_REQUIREMENT)

        desired = core.build(
            xr_name,
            namespace,
            params,
            xr_uid=meta.get("uid"),
            observed=observed,
            connection_details=connection_details,
            network=network,
        )
        for name, model in desired.items():
            resource.update(rsp.desired.resources[name], to_dict(model))

        if network_name and not core.published_network(network):
            waiting = [n for n in core.NETWORK_DEPENDENT if n not in desired]
            if waiting:
                found = "has not published its network" if network else "was not found"
                response.normal(
                    rsp,
                    f"Waiting for Network {network_name}: it {found} yet, so "
                    f"{', '.join(waiting)} {'is' if len(waiting) == 1 else 'are'} not composed",
                )

        resource.update(rsp.desired.composite, {"status": core.status(xr_name, observed)})

        log.info("Composed resources", count=len(desired), network=network_name or "<by id>")
        return rsp


def _required(req: fnv1.RunFunctionRequest, name: str) -> dict | None:
    """The single required resource called name, or None until Crossplane has found it.

    Older Crossplane versions deliver required resources as extra_resources.
    """
    found = request.get_required_resource(req, name)
    if found is None and name in req.extra_resources:
        items = req.extra_resources[name].items
        found = resource.struct_to_dict(items[0].resource) if items else None
    return found
