
import models.io.upbound.dev.meta.v1alpha1 as metav1alpha1
import models.io.upbound.gcp.compute.v1beta1 as computev1beta1
import models.io.upbound.gcp.servicenetworking.v1beta1 as servicenetworkingv1beta1
import models.io.upbound.gcp.sql.v1beta1 as sqlv1beta1
import models.io.upbound.platform.gcp.v1alpha1 as platformgcpv1alpha1

_items = [
    metav1alpha1.CompositionTest {
        metadata.name: "test-mysql-instance"
        spec = {
            assertResources: [
                platformgcpv1alpha1.XSQLInstance{
                    metadata = {
                        name = "test-mysql-instance"
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
                    }
                }
                computev1beta1.GlobalAddress{
                    metadata = {
                        labels = {
                            "crossplane.io/composite" = "test-mysql-instance"
                        }
                    }
                    spec = {
                        deletionPolicy = "Delete"
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
                        deletionPolicy = "Delete"
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
                            kind = "XSQLInstance"
                            name = "test-mysql-instance"
                            uid = ""
                        }]
                    }
                    spec = {
                        deletionPolicy = "Delete"
                        forProvider = {
                            region = "us-west2"
                            deletionProtection = False
                            databaseVersion = "MYSQL_8_0"
                            settings = [{
                                diskSize = 10
                                tier = "db-f1-micro"
                                ipConfiguration = [{
                                    ipv4Enabled = False
                                    privateNetworkRef = {
                                        name = "e2e-db-test-network"
                                    }
                                }]
                            }]
                        }
                        providerConfigRef = {
                            name = "default"
                        }
                        writeConnectionSecretToRef = {
                            name = "test-mysql-instance-gcp-mysql-instance"
                            namespace = "upbound-system"
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
                        deletionPolicy = "Delete"
                        forProvider = {
                            instanceSelector = {
                                matchControllerRef = True
                            }
                            passwordSecretRef = {
                                namespace = "default"
                                name = "mysqlsecret"
                                key = "password"
                            }
                        }
                        providerConfigRef = {
                            name = "default"
                        }
                        writeConnectionSecretToRef = {
                            name = "test-mysql-instance-gcp-mysql-user"
                            namespace = "upbound-system"
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
                        deletionPolicy = "Delete"
                        forProvider = {
                            instanceSelector = {
                                matchControllerRef = True
                            }
                        }
                        providerConfigRef = {
                            name = "default"
                        }
                    }
                }
            ]
            compositionPath: "apis/composition.yaml"
            xrPath: "examples/mysql-xr.yaml"
            xrdPath: "apis/definition.yaml"
            timeoutSeconds: 60
            validate: False
        }
    }
]
items = _items