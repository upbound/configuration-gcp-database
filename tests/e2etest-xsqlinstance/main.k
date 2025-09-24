
import models.io.upbound.dev.meta.v1alpha1 as metav1alpha1
import models.io.upbound.platform.gcp.v1alpha1 as platformgcpv1alpha1
import models.io.k8s.api.core.v1 as k8sv1
import models.io.upbound.gcp.v1beta1 as gcpv1beta1

_network_xr = platformgcpv1alpha1.XNetwork{
    metadata = {
        name = "e2e-db-test-network"
    }
    spec = {
        parameters = {
            id = "e2e-db-test-network"
            region = "us-west2"
            deletionPolicy = "Delete"
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

_mysql_claim = platformgcpv1alpha1.SQLInstance{
    metadata = {
        name = "test-mysql-claim"
        namespace = "default"
    }
    spec = {
        parameters = {
            region = "us-west2"
            engine = "mysql"
            engineVersion = "8_0"
            storageGB = 10
            networkRef = {
                id = "e2e-db-test-network"
            }
            passwordSecretRef = {
                namespace = "default"
                name = "mysqlsecret"
                key = "password"
            }
            deletionPolicy = "Delete"
            providerConfigName = "default"
        }
        writeConnectionSecretToRef = {
            name = "mysql-conn"
        }
    }
}

_items = [
    metav1alpha1.E2ETest{
        metadata.name: "e2e-mysql-instance"
        spec = {
            crossplane.autoUpgrade.channel: "Rapid"
            defaultConditions: ["Ready"]
            manifests: [
                _network_xr,
                _mysql_secret,
                _mysql_claim
            ]
            extraResources: [
                gcpv1beta1.ProviderConfig{
                    metadata.name: "default"
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