import base64
import models.io.k8s.api.core.v1 as corev1
import models.io.upbound.gcpm.compute.v1beta1 as computev1beta1
import models.io.upbound.gcpm.servicenetworking.v1beta1 as servicenetworkingv1beta1
import models.io.upbound.gcpm.sql.v1beta1 as sqlv1beta1
import models.io.upbound.platform.gcp.v1alpha1 as platformgcpv1alpha1

oxr = platformgcpv1alpha1.SQLInstance{**option("params").oxr}
_ocds = option("params").ocds
params = oxr.spec.parameters
providerConfigRefName = params.providerConfigName or "default"

_metadata = lambda name: str -> any {
    {
        annotations = {"krm.kcl.dev/composition-resource-name" = name}
    }
}

_defaults = {
    managementPolicies = params.managementPolicies or ["*"]
    if providerConfigRefName:
        providerConfigRef = {
            kind = "ProviderConfig"
            name = providerConfigRefName
        }
}

_connection_secret_name = lambda suffix: str -> str {
    _uid = oxr.metadata.uid if oxr.metadata?.uid else oxr.metadata.name
    "{}-gcp-{}-{}".format(_uid, params.engine, suffix)
}

# Manual Secret composition for v2 (replaces CompositeConnectionDetails)
_connection_secret = corev1.Secret{
    metadata = _metadata("connection-secret") | {
        name = "{}-connection".format(oxr.metadata.name)
        namespace = oxr.metadata.namespace
        labels = {
            "crossplane.io/composite" = oxr.metadata.name
        }
    }
    type = "connection.crossplane.io/v1alpha1"
    if "DBInstance" in _ocds and "DatabaseUser" in _ocds:
        data = {
            # Base64-encode values from status (not from ConnectionDetails)
            host = base64.encode(_ocds["DBInstance"].Resource?.status?.atProvider?.privateIpAddress or "")
            serverCACertificateCert = base64.encode(_ocds["DBInstance"].Resource?.status?.atProvider?.serverCaCert?[0]?.cert or "")
            username = base64.encode("upbounduser")
            # Password comes pre-encoded from managed resource's connection secret
            password = _ocds["DatabaseUser"].ConnectionDetails?.password or ""
        }
    else:
        data = {}
}

_items = [
    computev1beta1.GlobalAddress{
        metadata = _metadata("PrivateIPAddress")
        spec = _defaults | {
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
        }
    }
    servicenetworkingv1beta1.Connection{
        metadata = _metadata("PrivateConnection")
        spec = _defaults | {
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
        }
    }
    sqlv1beta1.DatabaseInstance{
        metadata = _metadata("DBInstance")
        spec = _defaults | {
            forProvider = {
                region = params.region
                deletionProtection = False
                databaseVersion = "{}_{}".format(params.engine, params.engineVersion).upper()
                settings = {
                    diskSize = params.storageGB
                    tier = "db-f1-micro"
                    ipConfiguration = {
                        ipv4Enabled = False
                        privateNetworkRef = {
                            name = params.networkRef.id
                        }
                    }
                }
            }
        }
    }
    sqlv1beta1.User{
        metadata = _metadata("DatabaseUser") | {
            annotations = {
                "crossplane.io/external-name" = "upbounduser"
                "krm.kcl.dev/composition-resource-name" = "DatabaseUser"
            }
        }
        spec = _defaults | {
            forProvider = {
                instanceSelector = {
                    matchControllerRef = True
                }
                passwordSecretRef = {
                    name = params.passwordSecretRef.name
                    key = params.passwordSecretRef.key
                }
            }
        }
    }
    sqlv1beta1.Database{
        metadata = _metadata("UpboundDatabase") | {
            annotations = {
                "crossplane.io/external-name" = "upbound"
                "krm.kcl.dev/composition-resource-name" = "UpboundDatabase"
            }
        }
        spec = _defaults | {
            forProvider = {
                instanceSelector = {
                    matchControllerRef = True
                }
            }
        }
    }
    _connection_secret
]

items = _items
