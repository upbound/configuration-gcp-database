"""Composition function for the GCP SQLInstance.

An SQLInstance is a private Cloud SQL instance (MySQL or PostgreSQL) on an existing Network. It
composes the reserved peering range and Service Networking connection that give the Network a
private path to Cloud SQL, the database instance, and - once the instance is reachable - a user
and a database. Consumers connect through the Secret named <xr-name>-connection.
"""

import base64

import grpc
from crossplane.function import logging, resource, response
from crossplane.function.proto.v1 import run_function_pb2 as fnv1
from crossplane.function.proto.v1 import run_function_pb2_grpc as grpcv1
from models.io.k8s.api.core import v1 as corev1
from models.io.k8s.apimachinery.pkg.apis.core.meta import v1 as coremetav1
from models.io.k8s.apimachinery.pkg.apis.meta import v1 as metav1
from models.io.upbound.m.gcp.compute.globaladdress import v1beta1 as globaladdressv1beta1
from models.io.upbound.m.gcp.servicenetworking.connection import v1beta1 as connectionv1beta1
from models.io.upbound.m.gcp.sql.database import v1beta1 as databasev1beta1
from models.io.upbound.m.gcp.sql.databaseinstance import v1beta1 as databaseinstancev1beta1
from models.io.upbound.m.gcp.sql.user import v1beta1 as userv1beta1
from models.io.upbound.platform.gcp.sqlinstance import v1alpha1 as sqlinstancev1alpha1
from pydantic import BaseModel, ValidationError

# Composition resource names identify composed resources across reconciles. Renaming one would
# replace the resource - for DB_INSTANCE, the database itself. Never rename them.
PRIVATE_IP_ADDRESS = "PrivateIPAddress"
PRIVATE_CONNECTION = "PrivateConnection"
DB_INSTANCE = "DBInstance"
DATABASE_USER = "DatabaseUser"
DATABASE = "UpboundDatabase"
CONNECTION_SECRET = "connection-secret"

NETWORK_ID_LABEL = "networks.gcp.platform.upbound.io/network-id"
EXTERNAL_NAME = "crossplane.io/external-name"
USERNAME = "upbounduser"
DATABASE_NAME = "upbound"


def _get(obj, *path):
    """Walk dict keys and list indexes, returning None where the path is missing."""
    for key in path:
        if isinstance(key, int):
            obj = obj[key] if isinstance(obj, list) and 0 <= key < len(obj) else None
        else:
            obj = obj.get(key) if isinstance(obj, dict) else None
        if obj is None:
            return None
    return obj


def _b64(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


def compose(
    xr: sqlinstancev1alpha1.SQLInstance,
    observed: dict[str, dict],
    connection_details: dict[str, dict[str, bytes]],
) -> dict[str, BaseModel]:
    """Return the desired composed resources, keyed by composition resource name.

    observed holds the observed composed resources and connection_details their connection
    details, both keyed by composition resource name.
    """
    name = xr.metadata.name
    namespace = xr.metadata.namespace
    params = xr.spec.parameters
    policies = params.managementPolicies or ["*"]
    provider_config = params.providerConfigName or "default"
    network_labels = {NETWORK_ID_LABEL: params.networkRef.id}

    desired: dict[str, BaseModel] = {
        PRIVATE_IP_ADDRESS: globaladdressv1beta1.GlobalAddress(
            spec=globaladdressv1beta1.Spec(
                managementPolicies=policies,
                providerConfigRef=globaladdressv1beta1.ProviderConfigRef(
                    kind="ProviderConfig", name=provider_config
                ),
                forProvider=globaladdressv1beta1.ForProvider(
                    address="10.205.0.0",
                    addressType="INTERNAL",
                    prefixLength=16,
                    purpose="VPC_PEERING",
                    networkSelector=globaladdressv1beta1.NetworkSelector(
                        matchLabels=network_labels
                    ),
                ),
            ),
        ),
        PRIVATE_CONNECTION: connectionv1beta1.Connection(
            spec=connectionv1beta1.Spec(
                managementPolicies=policies,
                providerConfigRef=connectionv1beta1.ProviderConfigRef(
                    kind="ProviderConfig", name=provider_config
                ),
                forProvider=connectionv1beta1.ForProvider(
                    reservedPeeringRangesSelector=connectionv1beta1.ReservedPeeringRangesSelector(
                        matchControllerRef=True
                    ),
                    service="servicenetworking.googleapis.com",
                    updateOnCreationFail=True,
                    networkSelector=connectionv1beta1.NetworkSelector(matchLabels=network_labels),
                ),
            ),
        ),
        DB_INSTANCE: databaseinstancev1beta1.DatabaseInstance(
            spec=databaseinstancev1beta1.Spec(
                managementPolicies=policies,
                providerConfigRef=databaseinstancev1beta1.ProviderConfigRef(
                    kind="ProviderConfig", name=provider_config
                ),
                forProvider=databaseinstancev1beta1.ForProvider(
                    region=params.region,
                    deletionProtection=False,
                    databaseVersion=f"{params.engine}_{params.engineVersion}".upper(),
                    settings=databaseinstancev1beta1.Settings(
                        diskSize=params.storageGB,
                        tier="db-f1-micro",
                        ipConfiguration=databaseinstancev1beta1.IpConfiguration(
                            ipv4Enabled=False,
                            privateNetworkRef=databaseinstancev1beta1.PrivateNetworkRef(
                                name=params.networkRef.id, namespace=namespace
                            ),
                        ),
                    ),
                ),
            ),
        ),
    }

    # Cloud SQL reports privateIpAddress only once the instance is RUNNABLE, which is later than
    # its Ready condition; the user and database can't be created before then. Once they exist
    # keep them, so the instance becoming unreachable doesn't delete them.
    db_instance = observed.get(DB_INSTANCE)
    private_ip = _get(db_instance, "status", "atProvider", "privateIpAddress") or ""

    if private_ip or DATABASE_USER in observed:
        desired[DATABASE_USER] = userv1beta1.User(
            metadata=metav1.ObjectMeta(annotations={EXTERNAL_NAME: USERNAME}),
            spec=userv1beta1.Spec(
                managementPolicies=policies,
                providerConfigRef=userv1beta1.ProviderConfigRef(
                    kind="ProviderConfig", name=provider_config
                ),
                writeConnectionSecretToRef=userv1beta1.WriteConnectionSecretToRef(
                    name=f"{xr.metadata.uid or name}-gcp-{params.engine}-user"
                ),
                forProvider=userv1beta1.ForProvider(
                    instanceSelector=userv1beta1.InstanceSelector(matchControllerRef=True),
                    passwordSecretRef=userv1beta1.PasswordSecretRef(
                        name=params.passwordSecretRef.name, key=params.passwordSecretRef.key
                    ),
                ),
            ),
        )

    if private_ip or DATABASE in observed:
        desired[DATABASE] = databasev1beta1.Database(
            metadata=metav1.ObjectMeta(annotations={EXTERNAL_NAME: DATABASE_NAME}),
            spec=databasev1beta1.Spec(
                managementPolicies=policies,
                providerConfigRef=databasev1beta1.ProviderConfigRef(
                    kind="ProviderConfig", name=provider_config
                ),
                forProvider=databasev1beta1.ForProvider(
                    instanceSelector=databasev1beta1.InstanceSelector(matchControllerRef=True),
                ),
            ),
        )

    # The connection Secret is composed directly, since Crossplane v2 doesn't aggregate XR
    # connection details. It stays empty until both the instance and the user exist.
    data = {}
    if DB_INSTANCE in observed and DATABASE_USER in observed:
        cert = _get(db_instance, "status", "atProvider", "serverCaCert", 0, "cert") or ""
        # The provider publishes the user's password in its connection details, as raw bytes.
        password = connection_details.get(DATABASE_USER, {}).get("password", b"")
        data = {
            "host": _b64(private_ip),
            "serverCACertificateCert": _b64(cert),
            "username": _b64(USERNAME),
            "password": base64.b64encode(password).decode(),
        }
    desired[CONNECTION_SECRET] = corev1.Secret(
        metadata=coremetav1.ObjectMeta(
            name=f"{name}-connection",
            namespace=namespace,
            labels={"crossplane.io/composite": name},
        ),
        type="connection.crossplane.io/v1alpha1",
        data=data,
    )

    return desired


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

        # Validate only the fields the composition reads, so that fields Crossplane adds to the
        # XR (such as spec.crossplane and status) can't fail it.
        oxr = resource.struct_to_dict(req.observed.composite.resource)
        try:
            xr = sqlinstancev1alpha1.SQLInstance(
                metadata=oxr.get("metadata"),
                spec={"parameters": (oxr.get("spec") or {}).get("parameters")},
            )
        except ValidationError as e:
            response.fatal(rsp, f"invalid SQLInstance: {e}")
            return rsp

        observed = {
            name: resource.struct_to_dict(r.resource) for name, r in req.observed.resources.items()
        }
        connection_details = {
            name: dict(r.connection_details) for name, r in req.observed.resources.items()
        }

        desired = compose(xr, observed, connection_details)
        for name, r in desired.items():
            # Dump with defaults included, so that schema defaults set on the models are emitted.
            resource.update(
                rsp.desired.resources[name], r.model_dump(exclude_none=True, by_alias=True)
            )

        log.info("Composed resources", count=len(desired))
        return rsp
