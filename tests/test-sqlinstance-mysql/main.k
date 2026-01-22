import models.io.k8s.api.core.v1 as corev1
import models.io.upbound.dev.meta.v1alpha1 as metav1alpha1
import models.io.upbound.gcpm.compute.v1beta1 as computev1beta1
import models.io.upbound.gcpm.servicenetworking.v1beta1 as servicenetworkingv1beta1
import models.io.upbound.gcpm.sql.v1beta1 as sqlv1beta1
import models.io.upbound.platform.gcp.v1alpha1 as platformgcpv1alpha1

_items = [
    metav1alpha1.CompositionTest {
        metadata.name: "test-mysql-instance"
        spec = {
            assertResources: [
                platformgcpv1alpha1.SQLInstance{
                    metadata = {
                        name = "test-mysql-instance"
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
                                name = "mysqlsecret"
                                key = "password"
                            }
                            managementPolicies = ["*"]
                            providerConfigName = "default"
                        }
                    }
                }
                computev1beta1.GlobalAddress{
                    metadata = {
                        labels = {
                            "crossplane.io/composite" = "test-mysql-instance"
                        }
                    }
                    spec = {
                        managementPolicies = ["*"]
                        forProvider = {
                            address = "10.205.0.0"
                            addressType = "INTERNAL"
                            prefixLength = 16
                            purpose = "VPC_PEERING"
                            networkSelector = {
                                matchLabels = {
                                    "networks.gcp.platform.upbound.io/network-id" = "e2e-db-test-network"
                                }
                            }
                        }
                        providerConfigRef = {
                            kind = "ProviderConfig"
                            name = "default"
                        }
                    }
                }
                servicenetworkingv1beta1.Connection{
                    metadata = {
                        labels = {
                            "crossplane.io/composite" = "test-mysql-instance"
                        }
                    }
                    spec = {
                        managementPolicies = ["*"]
                        forProvider = {
                            reservedPeeringRangesSelector = {
                                matchControllerRef = True
                            }
                            service = "servicenetworking.googleapis.com"
                            updateOnCreationFail = True
                            networkSelector = {
                                matchLabels = {
                                    "networks.gcp.platform.upbound.io/network-id" = "e2e-db-test-network"
                                }
                            }
                        }
                        providerConfigRef = {
                            kind = "ProviderConfig"
                            name = "default"
                        }
                    }
                }
                sqlv1beta1.DatabaseInstance{
                    metadata = {
                        labels = {
                            "crossplane.io/composite" = "test-mysql-instance"
                        }
                        ownerReferences = [{
                            apiVersion = "gcp.platform.upbound.io/v1alpha1"
                            blockOwnerDeletion = True
                            controller = True
                            kind = "SQLInstance"
                            name = "test-mysql-instance"
                            uid = ""
                        }]
                    }
                    spec = {
                        managementPolicies = ["*"]
                        forProvider = {
                            region = "us-west2"
                            deletionProtection = False
                            databaseVersion = "MYSQL_8_0"
                            settings = {
                                diskSize = 10
                                tier = "db-f1-micro"
                                ipConfiguration = {
                                    ipv4Enabled = False
                                    privateNetworkRef = {
                                        name = "e2e-db-test-network"
                                    }
                                }
                            }
                        }
                        providerConfigRef = {
                            kind = "ProviderConfig"
                            name = "default"
                        }
                    }
                }
                sqlv1beta1.User{
                    metadata = {
                        labels = {
                            "crossplane.io/composite" = "test-mysql-instance"
                        }
                        annotations = {
                            "crossplane.io/external-name" = "upbounduser"
                        }
                    }
                    spec = {
                        managementPolicies = ["*"]
                        forProvider = {
                            instanceSelector = {
                                matchControllerRef = True
                            }
                            passwordSecretRef = {
                                name = "mysqlsecret"
                                key = "password"
                            }
                        }
                        providerConfigRef = {
                            kind = "ProviderConfig"
                            name = "default"
                        }
                    }
                }
                sqlv1beta1.Database{
                    metadata = {
                        labels = {
                            "crossplane.io/composite" = "test-mysql-instance"
                        }
                        annotations = {
                            "crossplane.io/external-name" = "upbound"
                        }
                    }
                    spec = {
                        managementPolicies = ["*"]
                        forProvider = {
                            instanceSelector = {
                                matchControllerRef = True
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
            xrPath: "examples/mysql-xr.yaml"
            xrdPath: "apis/sqlinstances/definition.yaml"
            timeoutSeconds: 60
            validate: False
        }
    }
]
items = _items