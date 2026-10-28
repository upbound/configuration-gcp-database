"""Generate the CompositionTests for an SQLInstance referencing its Network by name.

The Network is supplied as an extra resource, which is how the test runner answers the function's
requirement for it: once before it has published its network id, and once after. Absence can't be
asserted here; the unit tests check that nothing network-dependent is composed while waiting.
"""

import yaml
from models.io.k8s.apimachinery.pkg.apis.meta import v1 as k8s
from models.io.upbound.dev.meta.compositiontest import v1alpha1 as compositiontest

COMPOSITION = "../../apis/sqlinstances/composition.yaml"
XRD = "../../apis/sqlinstances/definition.yaml"
XR = "../../examples/mysql-xr-network-name.yaml"

NAME = "test-mysql-network-name"
NETWORK = "e2e-db-test-network"
NETWORK_ID = f"projects/crossplane-playground/global/networks/{NETWORK}"
NETWORK_SELF_LINK = f"https://www.googleapis.com/compute/v1/{NETWORK_ID}"
SUBNETWORK_ID = f"projects/crossplane-playground/regions/us-west2/subnetworks/{NETWORK}-subnetwork"
PRIVATE_IP = "10.205.0.2"

COMPOSITE_LABELS = {"crossplane.io/composite": NAME}
PROVIDER_CONFIG_REF = {"kind": "ProviderConfig", "name": "default"}
CONNECTION_SECRET_REF = {"name": f"{NAME}-connection"}


def network(status: dict) -> dict:
    """The Network XR as configuration-gcp-network publishes it."""
    return {
        "apiVersion": "gcp.platform.upbound.io/v1alpha1",
        "kind": "Network",
        "metadata": {"name": NETWORK, "namespace": "default"},
        "spec": {"parameters": {"id": NETWORK, "region": "us-west2"}},
        "status": status,
    }


SUBNETWORK = {
    "name": f"{NETWORK}-subnetwork",
    "region": "us-west2",
    "ipCidrRange": "172.16.0.0/16",
    "secondaryRanges": {"pods": "pods", "services": "services"},
}
# Before the network exists in GCP, the Network publishes only what its spec tells it. Once it
# does, each resource gets the network in the form the provider's resolver would write: the
# GlobalAddress its id, the Connection its name and the DatabaseInstance its self link.
UNPUBLISHED = network({"vpc": {"name": NETWORK}, "subnetwork": SUBNETWORK})
PUBLISHED = network(
    {
        "vpc": {
            "name": NETWORK,
            "id": NETWORK_ID,
            "selfLink": NETWORK_SELF_LINK,
        },
        "subnetwork": {
            **SUBNETWORK,
            "id": SUBNETWORK_ID,
            "selfLink": f"https://www.googleapis.com/compute/v1/{SUBNETWORK_ID}",
        },
    }
)

CONNECTION_SECRET = {
    "apiVersion": "v1",
    "kind": "Secret",
    "metadata": {"name": f"{NAME}-connection", "namespace": "default", "labels": COMPOSITE_LABELS},
    "type": "connection.crossplane.io/v1alpha1",
}


def xr(status: dict) -> dict:
    return {
        "apiVersion": "gcp.platform.upbound.io/v1alpha1",
        "kind": "SQLInstance",
        "metadata": {"name": NAME, "namespace": "default"},
        "spec": {"parameters": {"networkRef": {"name": NETWORK}}},
        "status": status,
    }


def composition_test(name: str, **spec) -> compositiontest.CompositionTest:
    return compositiontest.CompositionTest(
        metadata=k8s.ObjectMeta(name=name),
        spec=compositiontest.Spec(
            compositionPath=COMPOSITION,
            xrPath=XR,
            xrdPath=XRD,
            timeoutSeconds=60,
            validate=True,
            **spec,
        ),
    )


waiting = composition_test(
    "test-mysql-network-name-waiting",
    # Only the connection Secret is composed, so consumers can reference it straight away.
    extraResources=[UNPUBLISHED],
    assertResources=[xr({"connectionSecretRef": CONNECTION_SECRET_REF}), CONNECTION_SECRET],
)

published = composition_test(
    "test-mysql-network-name-published",
    extraResources=[PUBLISHED],
    # A running instance reports its private IP, so the user and database are composed too.
    observedResources=[
        {
            "apiVersion": "sql.gcp.m.upbound.io/v1beta1",
            "kind": "DatabaseInstance",
            "metadata": {
                "name": f"{NAME}-dbinstance",
                "namespace": "default",
                "annotations": {"crossplane.io/composition-resource-name": "DBInstance"},
            },
            "spec": {"forProvider": {"region": "us-west2"}, "managementPolicies": ["*"]},
            "status": {"atProvider": {"privateIpAddress": PRIVATE_IP}},
        },
    ],
    assertResources=[
        xr({"connectionSecretRef": CONNECTION_SECRET_REF, "address": PRIVATE_IP}),
        {
            "apiVersion": "compute.gcp.m.upbound.io/v1beta1",
            "kind": "GlobalAddress",
            "metadata": {"labels": COMPOSITE_LABELS},
            "spec": {
                "managementPolicies": ["*"],
                "forProvider": {
                    "address": "10.205.0.0",
                    "addressType": "INTERNAL",
                    "prefixLength": 16,
                    "purpose": "VPC_PEERING",
                    "network": NETWORK_ID,
                },
                "providerConfigRef": PROVIDER_CONFIG_REF,
            },
        },
        {
            "apiVersion": "servicenetworking.gcp.m.upbound.io/v1beta1",
            "kind": "Connection",
            "metadata": {"labels": COMPOSITE_LABELS},
            "spec": {
                "managementPolicies": ["*"],
                "forProvider": {
                    "reservedPeeringRangesSelector": {"matchControllerRef": True},
                    "service": "servicenetworking.googleapis.com",
                    "updateOnCreationFail": True,
                    "network": NETWORK,
                },
                "providerConfigRef": PROVIDER_CONFIG_REF,
            },
        },
        {
            "apiVersion": "sql.gcp.m.upbound.io/v1beta1",
            "kind": "DatabaseInstance",
            "metadata": {"labels": COMPOSITE_LABELS},
            "spec": {
                "managementPolicies": ["*"],
                "forProvider": {
                    "region": "us-west2",
                    "deletionProtection": False,
                    "databaseVersion": "MYSQL_8_0",
                    "settings": {
                        "diskSize": 10,
                        "tier": "db-f1-micro",
                        "ipConfiguration": {
                            "ipv4Enabled": False,
                            "privateNetwork": NETWORK_SELF_LINK,
                        },
                    },
                },
                "providerConfigRef": PROVIDER_CONFIG_REF,
            },
        },
        {
            "apiVersion": "sql.gcp.m.upbound.io/v1beta1",
            "kind": "User",
            "metadata": {
                "labels": COMPOSITE_LABELS,
                "annotations": {"crossplane.io/external-name": "upbounduser"},
            },
            "spec": {
                "forProvider": {
                    "instanceSelector": {"matchControllerRef": True},
                    "passwordSecretRef": {"name": "mysqlsecret", "key": "password"},
                },
            },
        },
        {
            "apiVersion": "sql.gcp.m.upbound.io/v1beta1",
            "kind": "Database",
            "metadata": {
                "labels": COMPOSITE_LABELS,
                "annotations": {"crossplane.io/external-name": "upbound"},
            },
        },
        CONNECTION_SECRET,
    ],
)

# The test runner expects an "items" array, one entry per test.
output = {"items": [t.model_dump(by_alias=True, exclude_none=True) for t in (waiting, published)]}
print(yaml.dump(output))
