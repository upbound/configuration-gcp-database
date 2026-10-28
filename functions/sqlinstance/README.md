# SQLInstance composition function

Composes an `SQLInstance` into a private Cloud SQL instance: the reserved
peering range and Service Networking connection on the referenced `Network`,
the `DatabaseInstance`, and - once the instance reports a private IP - the
`User` and `Database`. It also composes the `<xr-name>-connection` Secret that
consumers read (`host`, `serverCACertificateCert`, `username`, `password`), and
publishes `status.connectionSecretRef` and `status.address`.

With `networkRef.name`, the function requires that `Network` and wires the
instance from its published `status.vpc` (`id`, `name` and `selfLink`),
composing the network resources only once `id` and `selfLink` are published.

- [function/core.py](function/core.py) decides what is composed and returns
  typed models; it has no Crossplane SDK dependency.
- [function/fn.py](function/fn.py) is the gRPC adapter: it validates the XR,
  requires the `Network`, serializes the models and sets the XR status.
- [function/serialize.py](function/serialize.py) dumps models as the SDK needs.

The function is built and tested with the rest of the project:

```console
up project build
up test run tests/test-sqlinstance-*
cd functions/sqlinstance && python -m pytest tests -q
```

The unit tests need `crossplane-function-sdk-python` and `pytest`, and read the
generated models from the repository's `.up/python`.
