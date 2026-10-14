# SQLInstance composition function

Composes an `SQLInstance` into a private Cloud SQL instance: the reserved
peering range and Service Networking connection on the referenced `Network`,
the `DatabaseInstance`, and - once the instance reports a private IP - the
`User` and `Database`. It also composes the `<xr-name>-connection` Secret that
consumers read (`host`, `serverCACertificateCert`, `username`, `password`).

`compose()` in [function/fn.py](function/fn.py) holds the logic and has no gRPC
dependency. The function is built and tested with the rest of the project:

```console
up project build
up test run tests/test-sqlinstance-mysql tests/test-sqlinstance-postgres
```
