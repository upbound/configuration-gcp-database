"""Generate the MySQL SQLInstance CompositionTest and print it as YAML."""

import yaml
from models.io.k8s.apimachinery.pkg.apis.meta import v1 as k8s
from models.io.upbound.dev.meta.compositiontest import v1alpha1 as compositiontest

COMPOSITION = "../../apis/sqlinstances/composition.yaml"
XRD = "../../apis/sqlinstances/definition.yaml"
XR = "../../examples/mysql-xr.yaml"

NAME = "test-mysql-instance"
# The UID the test runner gives the XR, which names the user's connection Secret.
XR_UID = "6174cd64-19b4-5a66-b286-5356e6cd88f5"
NETWORK_ID = "e2e-db-test-network"

COMPOSITE_LABELS = {"crossplane.io/composite": NAME}
NETWORK_SELECTOR = {"matchLabels": {"networks.gcp.platform.upbound.io/network-id": NETWORK_ID}}
PROVIDER_CONFIG_REF = {"kind": "ProviderConfig", "name": "default"}

test = compositiontest.CompositionTest(
    metadata=k8s.ObjectMeta(name=NAME),
    spec=compositiontest.Spec(
        compositionPath=COMPOSITION,
        xrPath=XR,
        xrdPath=XRD,
        timeoutSeconds=60,
        validate=True,
        # A running instance reports its private IP, so the user and database are composed.
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
                "status": {"atProvider": {"privateIpAddress": "10.205.0.2"}},
            },
        ],
        assertResources=[
            {
                "apiVersion": "gcp.platform.upbound.io/v1alpha1",
                "kind": "SQLInstance",
                "metadata": {"name": NAME, "namespace": "default"},
                "spec": {
                    "parameters": {
                        "region": "us-west2",
                        "engine": "mysql",
                        "engineVersion": "8_0",
                        "storageGB": 10,
                        "networkRef": {"id": NETWORK_ID},
                        "passwordSecretRef": {"name": "mysqlsecret", "key": "password"},
                        "managementPolicies": ["*"],
                        "providerConfigName": "default",
                    },
                },
            },
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
                        "networkSelector": NETWORK_SELECTOR,
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
                        "networkSelector": NETWORK_SELECTOR,
                    },
                    "providerConfigRef": PROVIDER_CONFIG_REF,
                },
            },
            {
                "apiVersion": "sql.gcp.m.upbound.io/v1beta1",
                "kind": "DatabaseInstance",
                "metadata": {
                    "labels": COMPOSITE_LABELS,
                    "ownerReferences": [
                        {
                            "apiVersion": "gcp.platform.upbound.io/v1alpha1",
                            "blockOwnerDeletion": True,
                            "controller": True,
                            "kind": "SQLInstance",
                            "name": NAME,
                            "uid": XR_UID,
                        },
                    ],
                },
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
                                "privateNetworkRef": {"name": NETWORK_ID},
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
                    "managementPolicies": ["*"],
                    "writeConnectionSecretToRef": {"name": f"{XR_UID}-gcp-mysql-user"},
                    "forProvider": {
                        "instanceSelector": {"matchControllerRef": True},
                        "passwordSecretRef": {"name": "mysqlsecret", "key": "password"},
                    },
                    "providerConfigRef": PROVIDER_CONFIG_REF,
                },
            },
            {
                "apiVersion": "sql.gcp.m.upbound.io/v1beta1",
                "kind": "Database",
                "metadata": {
                    "labels": COMPOSITE_LABELS,
                    "annotations": {"crossplane.io/external-name": "upbound"},
                },
                "spec": {
                    "managementPolicies": ["*"],
                    "forProvider": {"instanceSelector": {"matchControllerRef": True}},
                    "providerConfigRef": PROVIDER_CONFIG_REF,
                },
            },
        ],
    ),
)

# The test runner expects an "items" array, one entry per test.
output = {"items": [test.model_dump(by_alias=True, exclude_none=True)]}
print(yaml.dump(output))
