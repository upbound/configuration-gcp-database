"""Generate the PostgreSQL SQLInstance CompositionTest and print it as YAML."""

import yaml
from models.io.k8s.apimachinery.pkg.apis.meta import v1 as k8s
from models.io.upbound.dev.meta.compositiontest import v1alpha1 as compositiontest

COMPOSITION = "../../apis/sqlinstances/composition.yaml"
XRD = "../../apis/sqlinstances/definition.yaml"
XR = "../../examples/postgres-xr.yaml"

NAME = "test-postgres-instance"
# The UID the test runner gives the XR, which names the user's connection Secret.
XR_UID = "4b713ce0-93de-5b78-8d59-0a2233b524fc"

test = compositiontest.CompositionTest(
    metadata=k8s.ObjectMeta(name=NAME),
    spec=compositiontest.Spec(
        compositionPath=COMPOSITION,
        xrPath=XR,
        xrdPath=XRD,
        timeoutSeconds=60,
        validate=True,
        # A running instance reports its private IP, so the user is composed.
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
                        "engine": "postgres",
                        "engineVersion": "13",
                        "storageGB": 10,
                        "networkRef": {"id": "e2e-db-test-network"},
                        "passwordSecretRef": {"name": "postgresqlsecret", "key": "password"},
                        "managementPolicies": ["*"],
                        "providerConfigName": "default",
                    },
                },
            },
            {
                "apiVersion": "sql.gcp.m.upbound.io/v1beta1",
                "kind": "User",
                "metadata": {
                    "labels": {"crossplane.io/composite": NAME},
                    "annotations": {"crossplane.io/external-name": "upbounduser"},
                },
                "spec": {
                    "managementPolicies": ["*"],
                    "writeConnectionSecretToRef": {"name": f"{XR_UID}-gcp-postgres-user"},
                    "forProvider": {
                        "instanceSelector": {"matchControllerRef": True},
                        "passwordSecretRef": {"name": "postgresqlsecret", "key": "password"},
                    },
                    "providerConfigRef": {"kind": "ProviderConfig", "name": "default"},
                },
            },
        ],
    ),
)

# The test runner expects an "items" array, one entry per test.
output = {"items": [test.model_dump(by_alias=True, exclude_none=True)]}
print(yaml.dump(output))
