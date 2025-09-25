# GCP Database Configuration

This repository contains an Upbound project, tailored for users establishing their initial control plane with [Upbound](https://cloud.upbound.io). This configuration deploys fully managed GCP database instances with private networking and service networking connections.

## Overview

The core components of a custom API in [Upbound Project](https://docs.upbound.io/learn/control-plane-project/) include:

- **CompositeResourceDefinition (XRD):** Defines the API's structure.
- **Composition(s):** Configures the Functions Pipeline
- **Embedded Function(s):** Encapsulates the Composition logic and implementation within a self-contained, reusable unit

In this specific configuration, the API contains:

- **a [GCP SQL Database](/apis/definition.yaml) custom resource type.**
- **Composition:** Configured in [/apis/composition.yaml](/apis/composition.yaml)
- **Embedded Function:** The Composition logic is encapsulated within [embedded function](/functions/xsqlinstance/main.k)

## Features

This configuration provisions:

- **Cloud SQL Database Instance** with configurable engine (MySQL/PostgreSQL) and storage
- **Private IP networking** with VPC peering for secure database access
- **Service Networking connection** for private service access
- **Database user** with configurable password via Kubernetes secret
- **Default database** named "upbound" for application use
- **Connection secrets** for database connectivity

## Testing

The configuration can be tested using:

- `up composition render --xrd=apis/definition.yaml apis/composition.yaml examples/mysql-xr.yaml` to render the MySQL composition
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

The XSQLInstance API supports the following parameters:

- `engine`: Database engine (`mysql` or `postgres`)
- `engineVersion`: Database version (e.g., `8_0` for MySQL, `13` for PostgreSQL)
- `storageGB`: Storage size in GB
- `region`: GCP region for deployment
- `networkRef.id`: Reference to the network from configuration-gcp-network
- `passwordSecretRef`: Reference to Kubernetes secret containing database password
- `deletionPolicy`: Resource deletion policy (`Delete` or `Orphan`)
- `providerConfigName`: Crossplane ProviderConfig name

## Next steps

This repository serves as a foundational step. To enhance the configuration, consider:

1. create new API definitions in this same repo
2. editing the existing API definition to your needs
3. adding backup and restore functionality
4. implementing high availability configurations

To learn more about how to build APIs for your managed control planes in Upbound, read the guide on [Upbound's docs](https://docs.upbound.io/).