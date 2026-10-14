"""Unit tests for what the SQLInstance composes.

These cover what composition tests can't express: the absence of a resource (assertResources only
matches resources that exist), and validate(), whose errors stop a render before anything is
asserted.
"""

import inspect

import pytest
from pydantic import BaseModel

from function import core
from function.serialize import to_dict

XR = "db"
NS = "team"
UID = "6174cd64-19b4-5a66-b286-5356e6cd88f5"

PARAMS = {
    "region": "us-west2",
    "engine": "mysql",
    "engineVersion": "8_0",
    "storageGB": 10,
    "networkRef": {"id": "net-id"},
    "passwordSecretRef": {"name": "pw", "key": "password"},
    "managementPolicies": ["*"],
    "providerConfigName": "default",
}
BY_NAME = {**PARAMS, "networkRef": {"name": "my-network"}}

# The three forms of the network the Network publishes, each the one a provider reference
# resolver writes for the field that takes it.
NETWORK_NAME = "my-network"
NETWORK_ID = f"projects/my-project/global/networks/{NETWORK_NAME}"
NETWORK_SELF_LINK = f"https://www.googleapis.com/compute/v1/{NETWORK_ID}"


def network(**status) -> dict:
    """A Network XR as Crossplane would pass it, publishing the status given."""
    return {
        "apiVersion": "gcp.platform.upbound.io/v1alpha1",
        "kind": "Network",
        "metadata": {"name": "my-network", "namespace": NS},
        "spec": {"parameters": {"id": "my-network", "region": "us-west2"}},
        "status": status,
    }


# Before the network exists in GCP the Network publishes only what it knows from its spec.
UNPUBLISHED = network(
    vpc={"name": "my-network"},
    subnetwork={
        "name": "my-network-subnetwork",
        "region": "us-west2",
        "ipCidrRange": "172.16.0.0/16",
        "secondaryRanges": {"pods": "pods", "services": "services"},
    },
)
PUBLISHED = network(
    vpc={
        "name": NETWORK_NAME,
        "id": NETWORK_ID,
        "selfLink": NETWORK_SELF_LINK,
    },
    subnetwork={
        "name": "my-network-subnetwork",
        "region": "us-west2",
        "ipCidrRange": "172.16.0.0/16",
        "id": "projects/my-project/regions/us-west2/subnetworks/my-network-subnetwork",
        "selfLink": "https://www.googleapis.com/compute/v1/projects/my-project/regions/"
        "us-west2/subnetworks/my-network-subnetwork",
        "secondaryRanges": {"pods": "pods", "services": "services"},
    },
)


def instance(ip=None, private_network=None) -> dict:
    fp = {"region": "us-west2"}
    if private_network:
        fp["settings"] = {"ipConfiguration": {"privateNetwork": private_network}}
    obj = {"spec": {"forProvider": fp}, "status": {"atProvider": {}}}
    if ip:
        obj["status"]["atProvider"]["privateIpAddress"] = ip
    return obj


def build(params=PARAMS, **kwargs) -> dict[str, dict]:
    """Composed resources serialized exactly as fn.py sends them."""
    return {k: to_dict(v) for k, v in core.build(XR, NS, params, xr_uid=UID, **kwargs).items()}


def for_provider(res: dict) -> dict:
    return res["spec"]["forProvider"]


class TestByID:
    """networkRef.id alone: the behaviour every existing XR relies on."""

    def test_composes_the_instance_and_its_network_resources(self):
        assert list(build()) == [
            core.PRIVATE_IP_ADDRESS,
            core.PRIVATE_CONNECTION,
            core.DB_INSTANCE,
            core.CONNECTION_SECRET,
        ]

    def test_selects_the_network_by_label(self):
        got = build()
        selector = {"matchLabels": {core.NETWORK_ID_LABEL: "net-id"}}
        assert for_provider(got[core.PRIVATE_IP_ADDRESS])["networkSelector"] == selector
        assert for_provider(got[core.PRIVATE_CONNECTION])["networkSelector"] == selector
        ip_config = for_provider(got[core.DB_INSTANCE])["settings"]["ipConfiguration"]
        assert ip_config == {
            "ipv4Enabled": False,
            "privateNetworkRef": {"name": "net-id", "namespace": NS},
        }

    def test_does_not_wait_for_a_network(self):
        # Nothing to wait for: the selectors resolve on their own.
        assert core.NETWORK_DEPENDENT[0] in build(network=None)

    def test_a_network_passed_anyway_is_ignored(self):
        assert build(network=PUBLISHED) == build()


class TestUserAndDatabase:
    def test_not_composed_before_the_instance_reports_a_private_ip(self):
        got = build(observed={core.DB_INSTANCE: instance()})
        assert core.DATABASE_USER not in got
        assert core.DATABASE not in got

    def test_composed_once_it_does(self):
        got = build(observed={core.DB_INSTANCE: instance(ip="10.205.0.2")})
        user = got[core.DATABASE_USER]
        assert user["metadata"]["annotations"] == {"crossplane.io/external-name": "upbounduser"}
        assert user["spec"]["writeConnectionSecretToRef"] == {"name": f"{UID}-gcp-mysql-user"}
        assert for_provider(user)["passwordSecretRef"] == {"name": "pw", "key": "password"}
        assert core.DATABASE in got

    def test_kept_once_they_exist(self):
        got = build(
            observed={core.DB_INSTANCE: instance(), core.DATABASE_USER: {}, core.DATABASE: {}}
        )
        assert core.DATABASE_USER in got
        assert core.DATABASE in got


class TestConnectionSecret:
    def test_empty_until_the_instance_and_user_exist(self):
        assert build()[core.CONNECTION_SECRET]["data"] == {}
        got = build(observed={core.DB_INSTANCE: instance(ip="10.205.0.2")})
        assert got[core.CONNECTION_SECRET]["data"] == {}

    def test_filled_from_the_instance_and_the_users_connection_details(self):
        inst = instance(ip="10.205.0.2")
        inst["status"]["atProvider"]["serverCaCert"] = [{"cert": "CERT"}]
        got = build(
            observed={core.DB_INSTANCE: inst, core.DATABASE_USER: {}},
            connection_details={core.DATABASE_USER: {"password": b"s3cret"}},
        )
        assert got[core.CONNECTION_SECRET]["data"] == {
            "host": "MTAuMjA1LjAuMg==",
            "serverCACertificateCert": "Q0VSVA==",
            "username": "dXBib3VuZHVzZXI=",
            "password": "czNjcmV0",
        }

    @pytest.mark.parametrize("net", [None, UNPUBLISHED, PUBLISHED])
    def test_composed_in_every_mode_so_consumers_can_reference_it_early(self, net):
        got = build(BY_NAME, network=net)[core.CONNECTION_SECRET]
        assert got["metadata"]["name"] == f"{XR}-connection"
        assert got["metadata"]["namespace"] == NS


class TestByNameWaiting:
    """networkRef.name before the Network has published its network's id and selfLink."""

    @pytest.mark.parametrize("net", [None, network(), UNPUBLISHED], ids=["absent", "bare", "name"])
    def test_composes_nothing_that_needs_the_network(self, net):
        assert list(build(BY_NAME, network=net)) == [core.CONNECTION_SECRET]

    @pytest.mark.parametrize("missing", ["id", "selfLink"])
    def test_waits_for_both_id_and_self_link(self, missing):
        published = {k: v for k, v in PUBLISHED["status"]["vpc"].items() if k != missing}
        net = network(vpc=published)
        assert list(build(BY_NAME, network=net)) == [core.CONNECTION_SECRET]

    def test_nothing_waits_on_the_subnetwork_status(self):
        # SQL needs only the network: a published subnetwork alone changes nothing.
        net = network(subnetwork=PUBLISHED["status"]["subnetwork"], vpc={"name": "x"})
        assert list(build(BY_NAME, network=net)) == [core.CONNECTION_SECRET]

    def test_keeps_existing_resources_with_the_network_they_have(self):
        # A Network that stops publishing mustn't delete the database it carries.
        observed = {
            core.PRIVATE_IP_ADDRESS: {"spec": {"forProvider": {"network": NETWORK_ID}}},
            core.PRIVATE_CONNECTION: {"spec": {"forProvider": {"network": NETWORK_NAME}}},
            core.DB_INSTANCE: instance(ip="10.205.0.2", private_network=NETWORK_SELF_LINK),
            core.DATABASE_USER: {},
        }
        got = build(BY_NAME, network=UNPUBLISHED, observed=observed)
        assert set(got) == {*observed, core.DATABASE, core.CONNECTION_SECRET}
        assert for_provider(got[core.PRIVATE_IP_ADDRESS])["network"] == NETWORK_ID
        assert for_provider(got[core.PRIVATE_CONNECTION])["network"] == NETWORK_NAME
        ip_config = for_provider(got[core.DB_INSTANCE])["settings"]["ipConfiguration"]
        assert ip_config["privateNetwork"] == NETWORK_SELF_LINK

    def test_keeps_only_what_exists(self):
        observed = {core.PRIVATE_IP_ADDRESS: {"spec": {"forProvider": {"network": NETWORK_ID}}}}
        got = build(BY_NAME, network=None, observed=observed)
        assert list(got) == [core.PRIVATE_IP_ADDRESS, core.CONNECTION_SECRET]

    def test_never_falls_back_to_selectors(self):
        observed = {core.PRIVATE_IP_ADDRESS: {"spec": {"forProvider": {}}}}
        got = build(BY_NAME, network=None, observed=observed)
        assert (
            for_provider(got[core.PRIVATE_IP_ADDRESS])
            .keys()
            .isdisjoint({"network", "networkRef", "networkSelector"})
        )


class TestByNamePublished:
    """networkRef.name once the Network has published its network's id and selfLink."""

    def test_composes_the_same_set_as_by_id(self):
        assert list(build(BY_NAME, network=PUBLISHED)) == list(build())

    def test_wires_the_network_by_value_in_the_format_each_resolver_writes(self):
        # By label, the provider resolves GlobalAddress.network to the network's id,
        # Connection.network to its external name and privateNetwork to its self link. The same
        # values here mean switching an existing SQLInstance to networkRef.name changes nothing.
        got = build(BY_NAME, network=PUBLISHED)
        assert for_provider(got[core.PRIVATE_IP_ADDRESS])["network"] == NETWORK_ID
        assert for_provider(got[core.PRIVATE_CONNECTION])["network"] == NETWORK_NAME
        ip_config = for_provider(got[core.DB_INSTANCE])["settings"]["ipConfiguration"]
        assert ip_config == {"ipv4Enabled": False, "privateNetwork": NETWORK_SELF_LINK}

    def test_uses_no_selectors_or_references(self):
        got = build(BY_NAME, network=PUBLISHED)
        for name in (core.PRIVATE_IP_ADDRESS, core.PRIVATE_CONNECTION):
            assert "networkSelector" not in for_provider(got[name]), name
            assert "networkRef" not in for_provider(got[name]), name
        ip_config = for_provider(got[core.DB_INSTANCE])["settings"]["ipConfiguration"]
        assert "privateNetworkRef" not in ip_config
        assert "privateNetworkSelector" not in ip_config

    def test_published_values_win_over_what_a_resource_already_has(self):
        observed = {
            core.PRIVATE_IP_ADDRESS: {"spec": {"forProvider": {"network": "old"}}},
            core.PRIVATE_CONNECTION: {"spec": {"forProvider": {"network": "old"}}},
            core.DB_INSTANCE: instance(private_network="old"),
        }
        assert build(BY_NAME, network=PUBLISHED, observed=observed) == build(
            BY_NAME, network=PUBLISHED
        )

    def test_name_wins_when_id_is_also_set(self):
        both = {**PARAMS, "networkRef": {"id": "net-id", "name": "my-network"}}
        assert build(both, network=PUBLISHED) == build(BY_NAME, network=PUBLISHED)
        assert list(build(both, network=None)) == [core.CONNECTION_SECRET]

    def test_everything_else_matches_by_id(self):
        # Only the network wiring differs between the two modes.
        def strip(resources):
            for res in resources.values():
                fp = res.get("spec", {}).get("forProvider", {})
                for key in ("network", "networkSelector"):
                    fp.pop(key, None)
                fp.get("settings", {}).pop("ipConfiguration", None)
            return resources

        observed = {core.DB_INSTANCE: instance(ip="10.205.0.2"), core.DATABASE_USER: {}}
        assert strip(build(BY_NAME, network=PUBLISHED, observed=observed)) == strip(
            build(observed=observed)
        )


class TestStatus:
    def test_connection_secret_is_always_published(self):
        assert core.status(XR) == {"connectionSecretRef": {"name": f"{XR}-connection"}}
        assert core.status(XR, {core.DB_INSTANCE: instance()}) == core.status(XR)

    def test_address_is_published_once_the_instance_reports_one(self):
        got = core.status(XR, {core.DB_INSTANCE: instance(ip="10.205.0.2")})
        assert got == {"connectionSecretRef": {"name": f"{XR}-connection"}, "address": "10.205.0.2"}


class TestValidate:
    def test_valid_parameters_have_no_errors(self):
        assert core.validate(PARAMS) == []
        assert core.validate(BY_NAME) == []
        assert core.validate({**PARAMS, "networkRef": {"id": "a", "name": "b"}}) == []

    @pytest.mark.parametrize("ref", [{}, {"id": ""}, {"name": ""}], ids=["empty", "id", "name"])
    def test_network_ref_needs_an_id_or_a_name(self, ref):
        assert core.validate({**PARAMS, "networkRef": ref}) == [
            "spec.parameters.networkRef must set id or name"
        ]

    @pytest.mark.parametrize("field", ["region", "storageGB", "networkRef", "passwordSecretRef"])
    def test_required_fields(self, field):
        params = {k: v for k, v in PARAMS.items() if k != field}
        errors = core.validate(params)
        assert len(errors) == 1
        assert errors[0].startswith(f"spec.parameters.{field}:")

    def test_reports_every_schema_error(self):
        errors = core.validate({**PARAMS, "engine": "oracle", "passwordSecretRef": {}})
        assert len(errors) == 3, errors


class TestModule:
    def test_build_returns_models(self):
        for name, res in core.build(XR, NS, PARAMS).items():
            assert isinstance(res, BaseModel), name

    def test_user_secret_is_named_from_the_xr_without_a_uid(self):
        got = core.build(XR, NS, PARAMS, observed={core.DB_INSTANCE: instance(ip="10.0.0.1")})
        assert (
            got[core.DATABASE_USER].spec.writeConnectionSecretToRef.name == f"{XR}-gcp-mysql-user"
        )

    def test_core_does_not_import_the_crossplane_sdk(self):
        assert "crossplane.function" not in inspect.getsource(core)
