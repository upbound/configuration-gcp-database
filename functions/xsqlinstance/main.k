
import models.io.upbound.gcp.compute.v1beta1 as computev1beta1
import models.io.upbound.gcp.servicenetworking.v1beta1 as servicenetworkingv1beta1
import models.io.upbound.gcp.sql.v1beta1 as sqlv1beta1
import models.io.upbound.platform.gcp.v1alpha1 as platformgcpv1alpha1

oxr = platformgcpv1alpha1.XSQLInstance{**option("params").oxr} # observed composite resource
params = oxr.spec.parameters

_metadata = lambda name: str -> any {
    {
        annotations = {"krm.kcl.dev/composition-resource-name" = name}
    }
}

# Helper function to add common spec fields
_add_common_spec_fields = lambda spec: any -> any {
    spec | {
        deletionPolicy = params.deletionPolicy
        providerConfigRef = {
            name = params.providerConfigName
        }
    }
}

# Helper function for connection secret names
_connection_secret_name = lambda suffix: str -> str {
    _uid = oxr.metadata.uid if oxr.metadata?.uid else oxr.metadata.name
    "{}-gcp-{}-{}".format(_uid, params.engine, suffix)
}


_items = [
    computev1beta1.GlobalAddress{
        metadata = _metadata("PrivateIPAddress")
        spec = _add_common_spec_fields({
            forProvider = {
                address = "10.205.0.0"
                addressType = "INTERNAL"
                prefixLength = 16
                purpose = "VPC_PEERING"
                networkSelector = {
                    matchLabels = {
                        "networks.gcp.platform.upbound.io/network-id" = params.networkRef.id
                    }
                }
            }
        })
    }
    servicenetworkingv1beta1.Connection{
        metadata = _metadata("PrivateConnection")
        spec = _add_common_spec_fields({
            forProvider = {
                reservedPeeringRangesSelector = {
                    matchControllerRef = True
                }
                service = "servicenetworking.googleapis.com"
                updateOnCreationFail = True
                networkSelector = {
                    matchLabels = {
                        "networks.gcp.platform.upbound.io/network-id" = params.networkRef.id
                    }
                }
            }
        })
    }
    sqlv1beta1.DatabaseInstance{
        metadata = _metadata("DBInstance")
        spec = _add_common_spec_fields({
            forProvider = {
                region = params.region
                deletionProtection = False
                databaseVersion = "{}_{}".format(params.engine, params.engineVersion).upper()
                settings = [{
                    diskSize = params.storageGB
                    tier = "db-f1-micro"
                    ipConfiguration = [{
                        ipv4Enabled = False
                        privateNetworkRef = {
                            name = params.networkRef.id
                        }
                    }]
                }]
            }
            writeConnectionSecretToRef = {
                name = _connection_secret_name("instance")
                namespace = "upbound-system"
            }
        })
    }
    sqlv1beta1.User{
        metadata = _metadata("DatabaseUser") | {
            annotations = {
                "crossplane.io/external-name" = "upbounduser"
                "krm.kcl.dev/composition-resource-name" = "DatabaseUser"
            }
        }
        spec = _add_common_spec_fields({
            forProvider = {
                instanceSelector = {
                    matchControllerRef = True
                }
                passwordSecretRef = {
                    namespace = params.passwordSecretRef.namespace
                    name = params.passwordSecretRef.name
                    key = params.passwordSecretRef.key
                }
            }
            writeConnectionSecretToRef = {
                name = _connection_secret_name("user")
                namespace = "upbound-system"
            }
        })
    }
    sqlv1beta1.Database{
        metadata = _metadata("UpboundDatabase") | {
            annotations = {
                "crossplane.io/external-name" = "upbound"
                "krm.kcl.dev/composition-resource-name" = "UpboundDatabase"
            }
        }
        spec = _add_common_spec_fields({
            forProvider = {
                instanceSelector = {
                    matchControllerRef = True
                }
            }
        })
    }
]

items = _items
