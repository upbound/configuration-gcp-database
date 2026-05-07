import models.io.k8s.api.core.v1 as corev1
import models.io.upbound.dev.meta.v1alpha1 as metav1alpha1
import models.io.upbound.gcpm.compute.v1beta1 as computev1beta1
import models.io.upbound.gcpm.servicenetworking.v1beta1 as servicenetworkingv1beta1
import models.io.upbound.gcpm.sql.v1beta1 as sqlv1beta1
import models.io.upbound.platform.gcp.v1alpha1 as platformgcpv1alpha1


_items = [
    metav1alpha1.CompositionTest{
        metadata.name: "test-postgres-instance"
        spec= {
            assertResources: [
                platformgcpv1alpha1.SQLInstance{
                    metadata = {
                        name = "test-postgres-instance"
                        namespace = "default"
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
                                name = "postgresqlsecret"
                                key = "password"
                            }
                            managementPolicies = ["*"]
                            providerConfigName = "default"
                        }
                    }
                }
                sqlv1beta1.User{
                    metadata = {
                        labels = {
                            "crossplane.io/composite" = "test-postgres-instance"
                        }
                        annotations = {
                            "crossplane.io/external-name" = "upbounduser"
                        }
                    }
                    spec = {
                        managementPolicies = ["*"]
                        writeConnectionSecretToRef = {
                            name = "test-postgres-instance-gcp-postgres-user"
                        }
                        forProvider = {
                            instanceSelector = {
                                matchControllerRef = True
                            }
                            passwordSecretRef = {
                                name = "postgresqlsecret"
                                key = "password"
                            }
                        }
                        providerConfigRef = {
                            kind = "ProviderConfig"
                            name = "default"
                        }
                    }
                }
            ]
            compositionPath: "apis/sqlinstances/composition.yaml"
            xrPath: "examples/postgres-xr.yaml"
            xrdPath: "apis/sqlinstances/definition.yaml"
            timeoutSeconds: 60
            validate: False
        }
    }
]
items= _items