"""Build the composed resources for one SQLInstance XR.

An SQLInstance is a private Cloud SQL instance (MySQL or PostgreSQL) on a Network. It composes
the reserved peering range and Service Networking connection that give the Network a private path
to Cloud SQL, the database instance, and - once the instance is reachable - a user and a database.
Consumers connect through the Secret named <xr-name>-connection.

Resources are built from the models `up` generates from the provider CRDs, so field names are
checked when they are built, and returned rather than written anywhere: fn.py talks to Crossplane.
"""

import base64

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

# The resources that need the network. With networkRef.name they wait for the Network to publish
# its network, and the rest of the instance waits on them.
NETWORK_DEPENDENT = (PRIVATE_IP_ADDRESS, PRIVATE_CONNECTION, DB_INSTANCE)

# The Network an SQLInstance references by networkRef.name, read through its published status.
NETWORK_API_VERSION = "gcp.platform.upbound.io/v1alpha1"
NETWORK_KIND = "Network"

# How the network MR is found when only networkRef.id is set. That reaches into the Network's
# implementation, which is why networkRef.name exists; it stays for existing XRs.
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


def network_name(params: dict) -> str | None:
    """The Network referenced by name, or None when the XR uses networkRef.id."""
    return _get(params, "networkRef", "name") or None


def published_network(network: dict | None) -> dict | None:
    """The Network's published status.vpc, once its network exists in GCP, else None.

    id and selfLink are published only once the network has been observed in GCP, so both being
    present is the signal that it exists.
    """
    published = _get(network, "status", "vpc") or {}
    if published.get("id") and published.get("selfLink"):
        return published
    return None


def connection_secret_name(xr_name: str) -> str:
    return f"{xr_name}-connection"


def private_ip(observed: dict | None) -> str:
    """The instance's private IP, empty until Cloud SQL reports it."""
    return _get(observed, DB_INSTANCE, "status", "atProvider", "privateIpAddress") or ""


def validate(params: dict) -> list[str]:
    """Return fatal configuration errors.

    The networkRef rule duplicates the XRD's CEL rule on purpose: CEL runs only in the API server,
    and `up composition render` and composition tests don't execute it.
    """
    try:
        sqlinstancev1alpha1.Parameters.model_validate(params)
    except ValidationError as e:
        return [
            f"spec.parameters.{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
            for err in e.errors()
        ]
    if not (_get(params, "networkRef", "id") or network_name(params)):
        return ["spec.parameters.networkRef must set id or name"]
    return []


def build(
    xr_name: str,
    namespace: str,
    params: dict,
    *,
    xr_uid: str | None = None,
    observed: dict[str, dict] | None = None,
    connection_details: dict[str, dict[str, bytes]] | None = None,
    network: dict | None = None,
) -> dict[str, BaseModel]:
    """Return the desired composed resources as models, keyed by composition resource name.

    observed maps composition resource names to the observed composed resources, and
    connection_details to their connection details. network is the Network named by
    networkRef.name as Crossplane last read it, or None if it hasn't been read or doesn't exist.

    With networkRef.name, the network-dependent resources are wired by value from the Network's
    published status.vpc and wait for it, though one that already exists is kept with the
    network it was given. Without it, they select the network MR by label, exactly as before
    networkRef.name existed.
    """
    observed = observed or {}
    connection_details = connection_details or {}
    p = sqlinstancev1alpha1.Parameters.model_validate(params)
    policies = p.managementPolicies or ["*"]
    provider_config = p.providerConfigName or "default"
    by_name = network_name(params) is not None
    published = published_network(network)

    def network_for(name: str, field: str, *path) -> str | None:
        """The published network field, or else the value the existing resource name was given."""
        if published:
            return published.get(field)
        return _get(observed.get(name), "spec", "forProvider", *path)

    desired: dict[str, BaseModel] = {}

    if not by_name:
        network_labels = {NETWORK_ID_LABEL: p.networkRef.id}
        desired[PRIVATE_IP_ADDRESS] = _global_address(
            policies,
            provider_config,
            networkSelector=globaladdressv1beta1.NetworkSelector(matchLabels=network_labels),
        )
        desired[PRIVATE_CONNECTION] = _connection(
            policies,
            provider_config,
            networkSelector=connectionv1beta1.NetworkSelector(matchLabels=network_labels),
        )
        desired[DB_INSTANCE] = _db_instance(
            p,
            policies,
            provider_config,
            privateNetworkRef=databaseinstancev1beta1.PrivateNetworkRef(
                name=p.networkRef.id, namespace=namespace
            ),
        )
    else:
        # Until the Network publishes its network only resources that already exist are composed,
        # so a Network that stops publishing can't delete the database.
        #
        # Each field gets the format the provider's reference resolver writes for it in id mode:
        # the network's id, its name and its self link. So switching an existing SQLInstance from
        # networkRef.id to networkRef.name changes nothing on its resources.
        if published or PRIVATE_IP_ADDRESS in observed:
            desired[PRIVATE_IP_ADDRESS] = _global_address(
                policies, provider_config, network=network_for(PRIVATE_IP_ADDRESS, "id", "network")
            )
        if published or PRIVATE_CONNECTION in observed:
            desired[PRIVATE_CONNECTION] = _connection(
                policies,
                provider_config,
                network=network_for(PRIVATE_CONNECTION, "name", "network"),
            )
        if published or DB_INSTANCE in observed:
            desired[DB_INSTANCE] = _db_instance(
                p,
                policies,
                provider_config,
                privateNetwork=network_for(
                    DB_INSTANCE, "selfLink", "settings", "ipConfiguration", "privateNetwork"
                ),
            )

    # Cloud SQL reports privateIpAddress only once the instance is RUNNABLE, which is later than
    # its Ready condition; the user and database can't be created before then. Once they exist
    # keep them, so the instance becoming unreachable doesn't delete them.
    ip = private_ip(observed)

    if ip or DATABASE_USER in observed:
        desired[DATABASE_USER] = userv1beta1.User(
            metadata=metav1.ObjectMeta(annotations={EXTERNAL_NAME: USERNAME}),
            spec=userv1beta1.Spec(
                managementPolicies=policies,
                providerConfigRef=userv1beta1.ProviderConfigRef(
                    kind="ProviderConfig", name=provider_config
                ),
                writeConnectionSecretToRef=userv1beta1.WriteConnectionSecretToRef(
                    name=f"{xr_uid or xr_name}-gcp-{p.engine}-user"
                ),
                forProvider=userv1beta1.ForProvider(
                    instanceSelector=userv1beta1.InstanceSelector(matchControllerRef=True),
                    passwordSecretRef=userv1beta1.PasswordSecretRef(
                        name=p.passwordSecretRef.name, key=p.passwordSecretRef.key
                    ),
                ),
            ),
        )

    if ip or DATABASE in observed:
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
    # connection details. It exists from the start, so consumers can reference it before the
    # instance is up, and stays empty until both the instance and the user exist.
    data = {}
    if DB_INSTANCE in observed and DATABASE_USER in observed:
        cert = _get(observed[DB_INSTANCE], "status", "atProvider", "serverCaCert", 0, "cert")
        # The provider publishes the user's password in its connection details, as raw bytes.
        password = connection_details.get(DATABASE_USER, {}).get("password", b"")
        data = {
            "host": _b64(ip),
            "serverCACertificateCert": _b64(cert or ""),
            "username": _b64(USERNAME),
            "password": base64.b64encode(password).decode(),
        }
    desired[CONNECTION_SECRET] = corev1.Secret(
        metadata=coremetav1.ObjectMeta(
            name=connection_secret_name(xr_name),
            namespace=namespace,
            labels={"crossplane.io/composite": xr_name},
        ),
        type="connection.crossplane.io/v1alpha1",
        data=data,
    )

    return desired


def status(xr_name: str, observed: dict[str, dict] | None = None) -> dict:
    """The XR status this function publishes: where to connect, and the address once known."""
    out = {"connectionSecretRef": {"name": connection_secret_name(xr_name)}}
    if ip := private_ip(observed):
        out["address"] = ip
    return out


def _global_address(policies, provider_config, **network) -> BaseModel:
    return globaladdressv1beta1.GlobalAddress(
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
                **network,
            ),
        ),
    )


def _connection(policies, provider_config, **network) -> BaseModel:
    return connectionv1beta1.Connection(
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
                **network,
            ),
        ),
    )


def _db_instance(p, policies, provider_config, **network) -> BaseModel:
    return databaseinstancev1beta1.DatabaseInstance(
        spec=databaseinstancev1beta1.Spec(
            managementPolicies=policies,
            providerConfigRef=databaseinstancev1beta1.ProviderConfigRef(
                kind="ProviderConfig", name=provider_config
            ),
            forProvider=databaseinstancev1beta1.ForProvider(
                region=p.region,
                deletionProtection=False,
                databaseVersion=f"{p.engine}_{p.engineVersion}".upper(),
                settings=databaseinstancev1beta1.Settings(
                    diskSize=p.storageGB,
                    tier="db-f1-micro",
                    ipConfiguration=databaseinstancev1beta1.IpConfiguration(
                        ipv4Enabled=False, **network
                    ),
                ),
            ),
        ),
    )
