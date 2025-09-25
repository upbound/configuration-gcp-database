
import models.io.upbound.dev.meta.v1alpha1 as metav1alpha1
import models.io.upbound.gcp.compute.v1beta1 as computev1beta1
import models.io.upbound.gcp.servicenetworking.v1beta1 as servicenetworkingv1beta1
import models.io.upbound.gcp.sql.v1beta1 as sqlv1beta1
import models.io.upbound.platform.gcp.v1alpha1 as platformgcpv1alpha1


_items = [
    metav1alpha1.CompositionTest{
        metadata.name: "test-postgres-instance"
        spec= {
            assertResources: [
                platformgcpv1alpha1.XSQLInstance{
                    metadata = {
                        name = "test-postgres-instance"
                    }
                    spec = {
                        parameters = {
                            region = "us-west2"
                            engine = "postgres"
                            engineVersion = "13"
                            storageGB = 10
                            networkRef = {
                                id = "e2e-db-test-network"
                            }
                            passwordSecretRef = {
                                namespace = "default"
                                name = "postgresqlsecret"
                                key = "password"
                            }
                            deletionPolicy = "Delete"
                            providerConfigName = "default"
                        }
                    }
                }
            ]
            compositionPath: "apis/composition.yaml"
            xrPath: "examples/postgres-xr.yaml"
            xrdPath: "apis/definition.yaml"
            timeoutSeconds: 60
            validate: False
        }
    }
]
items= _items