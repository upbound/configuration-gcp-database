# GCP Database Configuration

This repository contains an Upbound DevEx configuration based on Crossplane v2, tailored for users establishing their initial control plane with [Upbound](https://cloud.upbound.io). This configuration deploys fully managed GCP database instances with private networking and service networking connections.

> **Note**: This configuration uses Crossplane v2 with namespace-scoped resources. All resources must be deployed within a namespace (default: `default`).

## Overview

The core components of a custom API in [Upbound Project](https://docs.upbound.io/learn/control-plane-project/) include:

- **CompositeResourceDefinition (XRD):** Defines the API's structure.
- **Composition(s):** Configures the Functions Pipeline
- **Embedded Function(s):** Encapsulates the Composition logic and implementation within a self-contained, reusable unit

In this specific configuration, the API contains:

- **a [GCP SQL Database](/apis/sqlinstances/definition.yaml) custom resource type.**
- **Composition:** Configured in [/apis/sqlinstances/composition.yaml](/apis/sqlinstances/composition.yaml)
- **Embedded Function:** The Composition logic is encapsulated within [embedded function](/functions/sqlinstance/main.k)

## Features

This configuration provisions:

- **Cloud SQL Database Instance** with configurable engine (MySQL/PostgreSQL) and storage
- **Private IP networking** with VPC peering for secure database access
- **Service Networking connection** for private service access
- **Database user** with configurable password via Kubernetes secret
- **Default database** named "upbound" for application use
- **Connection secrets** for database connectivity (using Crossplane v2 manual Secret composition)

## Testing

The configuration can be tested using:

- `up composition render --xrd=apis/sqlinstances/definition.yaml apis/sqlinstances/composition.yaml examples/mysql-xr.yaml` to render the MySQL composition
- `up test run tests/*` to run composition tests
- `up test run tests/* --e2e` to run end-to-end tests

## Deployment

- Execute `up project run`
- Alternatively, install the Configuration from the [Upbound Marketplace](https://marketplace.upbound.io/configurations/upbound/configuration-gcp-database)
- Check [examples](/examples/) for example XR (Composite Resource)

## Dependencies

This configuration depends on:

- [configuration-gcp-network](https://marketplace.upbound.io/configurations/upbound/configuration-gcp-network) for network resources
- GCP SQL Provider for database management
- GCP Service Networking Provider for private connections

## Parameters

The SQLInstance API supports the following parameters:

- `engine`: Database engine (`mysql` or `postgres`)
- `engineVersion`: Database version (e.g., `8_0` for MySQL, `13` for PostgreSQL)
- `storageGB`: Storage size in GB
- `region`: GCP region for deployment
- `networkRef.id`: Reference to the network from configuration-gcp-network
- `passwordSecretRef`: Reference to Kubernetes secret containing database password (namespace inferred from resource namespace in v2)
- `managementPolicies`: Resource management policies (default: `["*"]` which includes all operations; use `["Create", "Observe", "Update", "LateInitialize"]` to orphan resources)
- `providerConfigName`: Crossplane ProviderConfig name

## Crossplane v2 Migration Notes

This configuration was migrated to Crossplane v2 on January 21, 2026. Key changes from v1:

### Breaking Changes

- **API Version**: Updated from `apiextensions.crossplane.io/v1` to `v2`
- **Namespace Scope**: All resources are now namespace-scoped. You must specify `metadata.namespace` in all XR/Claim definitions.
- **Resource Kind**: Changed from `XSQLInstance` to `SQLInstance` (removed X-prefix)
- **managementPolicies**: Replaced `deletionPolicy` string field with `managementPolicies` array
  - v1: `deletionPolicy: Delete`
  - v2: `managementPolicies: ["*"]`
- **Secret References**: The `namespace` field is now optional in `passwordSecretRef` (inferred from resource namespace)
- **Connection Secrets**: Uses manual Secret composition instead of CompositeConnectionDetails
  - Connection secrets are now created as Kubernetes Secret resources with base64-encoded data
  - Secret name format: `{xr-name}-connection`
  - Available keys: `host`, `serverCACertificateCert`, `username`, `password`

### Provider Changes

- **GCP Providers**: Updated to v2 with namespace-scoped managed resources
  - provider-gcp-sql: >= v2.0.0
  - provider-gcp-servicenetworking: >= v2.0.0
- **Network Dependency**: Updated configuration-gcp-network to v2.0.0
- **Provider API Groups**: Now use namespaced APIs (e.g., `sql.gcp.m.upbound.io/v1beta1`)

### Example Updates

All examples have been updated to v2 patterns. See [examples/](./examples/) directory for:
- Namespace additions in metadata
- `managementPolicies` instead of `deletionPolicy`
- Removed `writeConnectionSecretToRef` (handled automatically via manual Secret composition)

For more information about Crossplane v2, see the [official upgrade guide](https://docs.crossplane.io/latest/guides/upgrade-to-crossplane-v2/).

## Next steps

This repository serves as a foundational step. To enhance the configuration, consider:

1. create new API definitions in this same repo
2. editing the existing API definition to your needs
3. adding backup and restore functionality
4. implementing high availability configurations

To learn more about how to build APIs for your managed control planes in Upbound, read the guide on [Upbound's docs](https://docs.upbound.io/).