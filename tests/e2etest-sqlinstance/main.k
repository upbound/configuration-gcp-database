import models.io.upbound.dev.meta.v1alpha1 as metav1alpha1
import models.io.upbound.platform.gcp.v1alpha1 as platformgcpv1alpha1
import models.io.k8s.api.core.v1 as k8sv1
import models.io.upbound.gcp.v1beta1 as gcpv1beta1

_mysql_network_xr = platformgcpv1alpha1.Network{
    metadata = {
        name = "e2e-mysql-network"
        namespace = "default"
    }
    spec = {
        parameters = {
            id = "e2e-mysql-network"
            region = "us-west2"
            managementPolicies = ["*"]
            providerConfigName = "default"
        }
    }
}

_postgres_network_xr = platformgcpv1alpha1.Network{
    metadata = {
        name = "e2e-postgres-network"
        namespace = "default"
    }
    spec = {
        parameters = {
            id = "e2e-postgres-network"
            region = "us-west2"
            managementPolicies = ["*"]
            providerConfigName = "default"
        }
    }
}

_mysql_secret = k8sv1.Secret{
    metadata = {
        name = "mysqlsecret"
        namespace = "default"
    }
    type = "Opaque"
    data = {
        password = "dXBiMHVuZHIwY2s1ITMxMzM3"  # base64 encoded password
    }
}

_postgres_secret = k8sv1.Secret{
    metadata = {
        name = "postgresqlsecret"
        namespace = "default"
    }
    type = "Opaque"
    data = {
        password = "dXBiMHVuZHIwY2s1ITMxMzM3"
    }
}

_mysql_xr = platformgcpv1alpha1.SQLInstance{
    metadata = {
        name = "test-mysql-xr"
        namespace = "default"
    }
    spec = {
        parameters = {
            region = "us-west2"
            engine = "mysql"
            engineVersion = "8_0"
            storageGB = 10
            networkRef = {
                id = "e2e-mysql-network"
            }
            passwordSecretRef = {
                name = "mysqlsecret"
                key = "password"
            }
            managementPolicies = ["*"]
            providerConfigName = "default"
        }
    }
}

_postgres_xr = platformgcpv1alpha1.SQLInstance{
    metadata = {
        name = "test-postgres-xr"
        namespace = "default"
    }
    spec = {
        parameters = {
            region = "us-west2"
            engine = "postgres"
            engineVersion = "13"
            storageGB = 10
            networkRef = {
                id = "e2e-postgres-network"
            }
            passwordSecretRef = {
                name = "postgresqlsecret"
                key = "password"
            }
            managementPolicies = ["*"]
            providerConfigName = "default"
        }
    }
}

_items = [
    metav1alpha1.E2ETest{
        metadata.name: "e2e-sqlinstance-engines"
        spec = {
            crossplane = {
                version = "2.0.2-up.5"
                autoUpgrade.channel = "Rapid"
            }
            defaultConditions: ["Ready"]
            manifests: [
                _mysql_network_xr,
                _postgres_network_xr,
                _mysql_secret,
                _postgres_secret,
                _mysql_xr,
                _postgres_xr
            ]
            extraResources: [
                {
                    apiVersion: "gcp.m.upbound.io/v1beta1"
                    kind: "ProviderConfig"
                    metadata: {
                        name: "default"
                        namespace: "default"
                    }
                    spec: {
                        projectID: "crossplane-playground"
                        credentials: {
                            source: "Upbound"
                            upbound: {
                                federation: {
                                    providerID: "projects/283222062215/locations/global/workloadIdentityPools/solutions-upbound-oidc-pool/providers/solutions-u5d-oidc-pool"
                                    serviceAccount: "solutions-u5d-service-account@crossplane-playground.iam.gserviceaccount.com"
                                }
                            }
                        }
                    }
                }
            ]
            skipDelete: False
            timeoutSeconds: 4500
        }
    }
]
items = _items