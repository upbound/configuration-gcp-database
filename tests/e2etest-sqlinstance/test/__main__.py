"""Generate the SQLInstance E2ETest and print it as YAML."""

import yaml
from models.io.k8s.apimachinery.pkg.apis.meta import v1 as k8s
from models.io.upbound.dev.meta.e2etest import v1alpha1 as e2etest

NAMESPACE = "default"
# Base64 of the database password both engines use.
PASSWORD = "dXBiMHVuZHIwY2s1ITMxMzM3"


def network(name: str) -> dict:
    return {
        "apiVersion": "gcp.platform.upbound.io/v1alpha1",
        "kind": "Network",
        "metadata": {"name": name, "namespace": NAMESPACE},
        "spec": {
            "parameters": {
                "id": name,
                "region": "us-west2",
                "managementPolicies": ["*"],
                "providerConfigName": "default",
            },
        },
    }


def password_secret(name: str) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": name, "namespace": NAMESPACE},
        "type": "Opaque",
        "data": {"password": PASSWORD},
    }


def sql_instance(name: str, engine: str, version: str, network: str, secret: str) -> dict:
    return {
        "apiVersion": "gcp.platform.upbound.io/v1alpha1",
        "kind": "SQLInstance",
        "metadata": {"name": name, "namespace": NAMESPACE},
        "spec": {
            "parameters": {
                "region": "us-west2",
                "engine": engine,
                "engineVersion": version,
                "storageGB": 10,
                "networkRef": {"name": network},
                "passwordSecretRef": {"name": secret, "key": "password"},
                "managementPolicies": ["*"],
                "providerConfigName": "default",
            },
        },
    }


# One instance of each engine, each on its own network and referencing it by name, so the
# instances are wired from the Networks' published status.
test = e2etest.E2ETest(
    metadata=k8s.ObjectMeta(name="e2e-sqlinstance-engines"),
    spec=e2etest.Spec(
        crossplane=e2etest.Crossplane(
            version="2.0.2-up.5",
            autoUpgrade=e2etest.AutoUpgrade(channel="Rapid"),
        ),
        defaultConditions=["Ready"],
        manifests=[
            network("e2e-mysql-network"),
            network("e2e-postgres-network"),
            password_secret("mysqlsecret"),
            password_secret("postgresqlsecret"),
            sql_instance("test-mysql-xr", "mysql", "8_0", "e2e-mysql-network", "mysqlsecret"),
            sql_instance(
                "test-postgres-xr", "postgres", "13", "e2e-postgres-network", "postgresqlsecret"
            ),
        ],
        extraResources=[
            {
                "apiVersion": "gcp.m.upbound.io/v1beta1",
                "kind": "ProviderConfig",
                "metadata": {"name": "default", "namespace": NAMESPACE},
                "spec": {
                    "projectID": "crossplane-playground",
                    "credentials": {
                        "source": "Upbound",
                        "upbound": {
                            "federation": {
                                "providerID": "projects/283222062215/locations/global/workloadIdentityPools/solutions-upbound-oidc-pool/providers/solutions-u5d-oidc-pool",
                                "serviceAccount": "solutions-u5d-service-account@crossplane-playground.iam.gserviceaccount.com",
                            },
                        },
                    },
                },
            },
        ],
        # If True, skip cleanup of test resources and control plane after test
        # completion. Useful for debugging and inspecting test state. Defaults to
        # False.
        skipDelete=False,
        timeoutSeconds=4500,
    ),
)

# The test runner expects an "items" array, one entry per test.
output = {"items": [test.model_dump(by_alias=True, exclude_none=True)]}
print(yaml.dump(output))
