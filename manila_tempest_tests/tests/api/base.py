# Copyright 2014 Mirantis Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import copy
import inspect
import os
import re
import traceback

from oslo_concurrency import lockutils
from oslo_log import log
import six
from tempest.common import credentials_factory as common_creds

from tempest import config
from tempest.lib.common import dynamic_creds
from tempest.lib.common import preprov_creds
from tempest.lib.common.utils import data_utils
from tempest.lib import exceptions
from tempest import test

from manila_tempest_tests import clients
from manila_tempest_tests.common import constants
from manila_tempest_tests import share_exceptions
from manila_tempest_tests import utils

CONF = config.CONF
LOG = log.getLogger(__name__)

# Test tags related to test direction
TAG_POSITIVE = "positive"
TAG_NEGATIVE = "negative"

# Test tags related to service involvement
TAG_API = "api"
TAG_BACKEND = "backend"
TAG_API_WITH_BACKEND = "api_with_backend"

TAGS_MAPPER = {
    "p": TAG_POSITIVE,
    "n": TAG_NEGATIVE,
    "a": TAG_API,
    "b": TAG_BACKEND,
    "ab": TAG_API_WITH_BACKEND,
}
TAGS_PATTERN = re.compile(
    r"(?=.*\[.*\b(%(p)s|%(n)s)\b.*\])(?=.*\[.*\b(%(a)s|%(b)s|%(ab)s)\b.*\])" %
    TAGS_MAPPER)


def verify_test_has_appropriate_tags(self):
    if not TAGS_PATTERN.match(self.id()):
        msg = (
            "Required attributes either not set or set improperly. "
            "Two test attributes are expected:\n"
            " - one of '%(p)s' or '%(n)s' and \n"
            " - one of '%(a)s', '%(b)s' or '%(ab)s'."
        ) % TAGS_MAPPER
        raise self.failureException(msg)


class handle_cleanup_exceptions(object):
    """Handle exceptions raised with cleanup operations.

    Always suppress errors when exceptions.NotFound or exceptions.Forbidden
    are raised.
    Suppress all other exceptions only in case config opt
    'suppress_errors_in_cleanup' in config group 'share' is True.
    """

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if not (isinstance(exc_value,
                           (exceptions.NotFound, exceptions.Forbidden)) or
                CONF.share.suppress_errors_in_cleanup):
            return False  # Do not suppress error if any
        if exc_traceback:
            LOG.error("Suppressed cleanup error in Manila: "
                      "\n%s", traceback.format_exc())
        return True  # Suppress error if any


def network_synchronized(f):

    def wrapped_func(self, *args, **kwargs):
        with_isolated_creds = True if len(args) > 2 else False
        no_lock_required = kwargs.get(
            "isolated_creds_client", with_isolated_creds)
        if no_lock_required:
            # Usage of not reusable network. No need in lock.
            return f(self, *args, **kwargs)

        # Use lock assuming reusage of common network.
        @lockutils.synchronized("manila_network_lock", external=True)
        def source_func(self, *args, **kwargs):
            return f(self, *args, **kwargs)

        return source_func(self, *args, **kwargs)

    return wrapped_func


skip_if_microversion_not_supported = utils.skip_if_microversion_not_supported
skip_if_microversion_lt = utils.skip_if_microversion_lt


class BaseSharesTest(test.BaseTestCase):
    """Base test case class for all Manila API tests."""

    credentials = ('primary', )
    force_tenant_isolation = False
    protocols = ["nfs", "cifs", "glusterfs", "hdfs", "cephfs", "maprfs"]

    # Will be cleaned up in resource_cleanup
    class_resources = []

    # Will be cleaned up in tearDown method
    method_resources = []

    # Will be cleaned up in resource_cleanup
    class_isolated_creds = []

    # Will be cleaned up in tearDown method
    method_isolated_creds = []

    # NOTE(andreaf) Override the client manager class to be used, so that
    # a stable class is used, which includes plugin registered services as well
    client_manager = clients.Clients

    def skip_if_microversion_not_supported(self, microversion):
        if not utils.is_microversion_supported(microversion):
            raise self.skipException(
                "Microversion '%s' is not supported." % microversion)

    def skip_if_microversion_lt(self, microversion):
        if utils.is_microversion_lt(CONF.share.max_api_microversion,
                                    microversion):
            raise self.skipException(
                "Microversion must be greater than or equal to '%s'." %
                microversion)

    @classmethod
    def _get_dynamic_creds(cls, name, network_resources=None):
        identity_version = CONF.identity.auth_version
        if identity_version == 'v3':
            identity_uri = CONF.identity.uri_v3
            identity_admin_endpoint_type = CONF.identity.v3_endpoint_type
        elif identity_version == 'v2':
            identity_uri = CONF.identity.uri
            identity_admin_endpoint_type = CONF.identity.v2_admin_endpoint_type

        if CONF.auth.use_dynamic_credentials:
            return dynamic_creds.DynamicCredentialProvider(
                identity_version=identity_version,
                name=name,
                network_resources=network_resources,
                credentials_domain=CONF.auth.default_credentials_domain_name,
                admin_role=CONF.identity.admin_role,
                admin_creds=common_creds.get_configured_admin_credentials(),
                identity_admin_domain_scope=CONF.identity.admin_domain_scope,
                identity_admin_role=CONF.identity.admin_role,
                extra_roles=None,
                neutron_available=CONF.service_available.neutron,
                create_networks=(
                    CONF.share.create_networks_when_multitenancy_enabled),
                project_network_cidr=CONF.network.project_network_cidr,
                project_network_mask_bits=CONF.network.project_network_mask_bits,
                public_network_id=CONF.network.public_network_id,
                resource_prefix='tempest',
                identity_admin_endpoint_type=identity_admin_endpoint_type,
                identity_uri=identity_uri)
        else:
            if CONF.auth.test_accounts_file:
                accounts_lock_dir = os.path.join(lockutils.get_lock_path(CONF),
                                         'test_accounts')
                # Most params are not relevant for pre-created accounts
                return preprov_creds.PreProvisionedCredentialProvider(
                    name=name,
                    identity_version=identity_version,
                    accounts_lock_dir=accounts_lock_dir,
                    test_accounts_file=CONF.auth.test_accounts_file,
                    credentials_domain=CONF.auth.default_credentials_domain_name,
                    admin_role=CONF.identity.admin_role,
                    identity_uri=identity_uri)
            else:
                raise exceptions.InvalidConfiguration(
                    'A valid credential provider is needed')

    @classmethod
    def get_client_with_isolated_creds(cls,
                                       name=None,
                                       type_of_creds="admin",
                                       cleanup_in_class=False,
                                       client_version='1'):
        """Creates isolated creds.

        :param name: name, will be used for naming ic and related stuff
        :param type_of_creds: admin, alt or primary
        :param cleanup_in_class: defines place where to delete
        :returns: SharesClient -- shares client with isolated creds.
        :returns: To client added dict attr 'creds' with
        :returns: key elements 'tenant' and 'user'.
        """
        if name is None:
            # Get name of test method
            name = inspect.stack()[1][3]
            if len(name) > 32:
                name = name[0:32]

        # Choose type of isolated creds
        ic = cls._get_dynamic_creds(name)
        if "admin" in type_of_creds:
            creds = ic.get_admin_creds().credentials
        elif "alt" in type_of_creds:
            creds = ic.get_alt_creds().credentials
        else:
            creds = ic.get_primary_creds().credentials
        ic.type_of_creds = type_of_creds

        # create client with isolated creds
        os = clients.Clients(creds)
        if client_version == '1':
            client = os.share_v1.SharesClient()
        elif client_version == '2':
            client = os.share_v2.SharesV2Client()

        # Set place where will be deleted isolated creds
        ic_res = {
            "method": ic.clear_creds,
            "deleted": False,
        }
        if cleanup_in_class:
            cls.class_isolated_creds.insert(0, ic_res)
        else:
            cls.method_isolated_creds.insert(0, ic_res)

        # Provide share network
        if CONF.share.multitenancy_enabled:
            if (not CONF.service_available.neutron and
                    CONF.share.create_networks_when_multitenancy_enabled):
                raise cls.skipException("Neutron support is required")
            nc = os.network.NetworksClient()
            share_network_id = cls.provide_share_network(client, nc, ic)
            client.share_network_id = share_network_id
            resource = {
                "type": "share_network",
                "id": client.share_network_id,
                "client": client,
            }
            if cleanup_in_class:
                cls.class_resources.insert(0, resource)
            else:
                cls.method_resources.insert(0, resource)
        return client

    @classmethod
    def skip_checks(cls):
        super(BaseSharesTest, cls).skip_checks()
        if not CONF.service_available.manila:
            raise cls.skipException("Manila support is required")

    @classmethod
    def verify_nonempty(cls, *args):
        if not all(args):
            msg = "Missing API credentials in configuration."
            raise cls.skipException(msg)

    @classmethod
    def setup_clients(cls):
        super(BaseSharesTest, cls).setup_clients()
        os = getattr(cls, 'os_%s' % cls.credentials[0])
        # Initialise share clients for test credentials
        cls.shares_client = os.share_v1.SharesClient()
        cls.shares_v2_client = os.share_v2.SharesV2Client()
        # Initialise network clients for test credentials
        if CONF.service_available.neutron:
            cls.networks_client = os.network.NetworksClient()
            cls.subnets_client = os.network.SubnetsClient()
        else:
            cls.networks_client = None
            cls.subnets_client = None

        if CONF.identity.auth_version == 'v3':
            project_id = os.auth_provider.auth_data[1]['project']['id']
        else:
            project_id = os.auth_provider.auth_data[1]['token']['tenant']['id']
        cls.tenant_id = project_id
        cls.user_id = os.auth_provider.auth_data[1]['user']['id']

        if CONF.share.multitenancy_enabled:
            if (not CONF.service_available.neutron and
                    CONF.share.create_networks_when_multitenancy_enabled):
                raise cls.skipException("Neutron support is required")
            share_network_id = cls.provide_share_network(
                cls.shares_v2_client, cls.networks_client)
            cls.shares_client.share_network_id = share_network_id
            cls.shares_v2_client.share_network_id = share_network_id
            resource = {
                "type": "share_network",
                "id": share_network_id,
                "client": cls.shares_v2_client,
            }
            cls.class_resources.insert(0, resource)

    @classmethod
    def resource_setup(cls):
        if not (any(p in CONF.share.enable_protocols
                    for p in cls.protocols) and
                CONF.service_available.manila):
            skip_msg = "Manila is disabled"
            raise cls.skipException(skip_msg)
        super(BaseSharesTest, cls).resource_setup()

    def setUp(self):
        super(BaseSharesTest, self).setUp()
        self.addCleanup(self.clear_isolated_creds)
        self.addCleanup(self.clear_resources)
        verify_test_has_appropriate_tags(self)

    @classmethod
    def resource_cleanup(cls):
        cls.clear_resources(cls.class_resources)
        cls.clear_isolated_creds(cls.class_isolated_creds)
        super(BaseSharesTest, cls).resource_cleanup()

    @classmethod
    @network_synchronized
    def provide_share_network(cls, shares_client, networks_client,
                              isolated_creds_client=None,
                              ignore_multitenancy_config=False):
        """Used for finding/creating share network for multitenant driver.

        This method creates/gets entity share-network for one tenant. This
        share-network will be used for creation of service vm.

        :param shares_client: shares client, which requires share-network
        :param networks_client: network client from same tenant as shares
        :param isolated_creds_client: DynamicCredentialProvider instance
            If provided, then its networking will be used if needed.
            If not provided, then common network will be used if needed.
        :param ignore_multitenancy_config: provide a share network regardless
            of 'multitenancy_enabled' configuration value.
        :returns: str -- share network id for shares_client tenant
        :returns: None -- if single-tenant driver used
        """

        sc = shares_client
        search_word = "reusable"
        sn_name = "autogenerated_by_tempest_%s" % search_word

        if (not ignore_multitenancy_config and
                not CONF.share.multitenancy_enabled):
            # Assumed usage of a single-tenant driver
            share_network_id = None
        else:
            if sc.share_network_id:
                # Share-network already exists, use it
                share_network_id = sc.share_network_id
            elif not CONF.share.create_networks_when_multitenancy_enabled:
                share_network_id = None

                # ccloud BEGIN
                share_networks = sc.list_share_networks_with_detail()
                for sn in share_networks:
                    if search_word in sn["name"]:
                        share_network_id = sn["id"]
                        break

                if share_network_id is None:
                    skip_msg = "ccloud no share net in %s" % sc.tenant_id
                    raise cls.skipException(skip_msg)
                else:
                    return share_network_id
                # ccloud END
            else:
                net_id = subnet_id = share_network_id = None

                # ccloud BEGIN
                share_networks = sc.list_share_networks_with_detail()
                for sn in share_networks:
                    if search_word in sn["name"]:
                        share_network_id = sn["id"]
                        break

                if share_network_id is None:
                    skip_msg = "ccloud no share net in %s" % sc.tenant_id
                    raise cls.skipException(skip_msg)
                else:
                    return share_network_id
                # ccloud END

                if not isolated_creds_client:
                    # Search for networks, created in previous runs
                    service_net_name = "share-service"
                    networks = networks_client.list_networks()
                    if "networks" in networks.keys():
                        networks = networks["networks"]
                    for network in networks:
                        if (service_net_name in network["name"] and
                                sc.tenant_id == network['tenant_id']):
                            net_id = network["id"]
                            if len(network["subnets"]) > 0:
                                subnet_id = network["subnets"][0]
                                break

                    # Create suitable network
                    if net_id is None or subnet_id is None:
                        ic = cls._get_dynamic_creds(service_net_name)
                        net_data = ic._create_network_resources(sc.tenant_id)
                        network, subnet, router = net_data
                        net_id = network["id"]
                        subnet_id = subnet["id"]

                    # Try get suitable share-network
                    share_networks = sc.list_share_networks_with_detail()
                    for sn in share_networks:
                        if (net_id == sn["neutron_net_id"] and
                                subnet_id == sn["neutron_subnet_id"] and
                                sn["name"] and search_word in sn["name"]):
                            share_network_id = sn["id"]
                            break
                else:
                    sn_name = "autogenerated_by_tempest_for_isolated_creds"
                    # Use precreated network and subnet from isolated creds
                    net_id = isolated_creds_client.get_credentials(
                        isolated_creds_client.type_of_creds).network['id']
                    subnet_id = isolated_creds_client.get_credentials(
                        isolated_creds_client.type_of_creds).subnet['id']

                # Create suitable share-network
                if share_network_id is None:
                    sn_desc = "This share-network was created by tempest"
                    sn = sc.create_share_network(name=sn_name,
                                                 description=sn_desc,
                                                 neutron_net_id=net_id,
                                                 neutron_subnet_id=subnet_id)
                    share_network_id = sn["id"]

        return share_network_id

    @classmethod
    def _create_share(cls, share_protocol=None, size=None, name=None,
                      snapshot_id=None, description=None, metadata=None,
                      share_network_id=None, share_type_id=None,
                      share_group_id=None, client=None,
                      cleanup_in_class=True, is_public=False, **kwargs):
        client = client or cls.shares_v2_client
        description = description or "Tempest's share"
        share_network_id = (share_network_id or
                            CONF.share.share_network_id or
                            client.share_network_id or None)
        metadata = metadata or {}
        size = size or CONF.share.share_size
        kwargs.update({
            'share_protocol': share_protocol,
            'size': size,
            'name': name,
            'snapshot_id': snapshot_id,
            'description': description,
            'metadata': metadata,
            'share_network_id': share_network_id,
            'share_type_id': share_type_id,
            'is_public': is_public,
        })
        if share_group_id:
            kwargs['share_group_id'] = share_group_id

        share = client.create_share(**kwargs)
        resource = {"type": "share", "id": share["id"], "client": client,
                    "share_group_id": share_group_id}
        cleanup_list = (cls.class_resources if cleanup_in_class else
                        cls.method_resources)
        cleanup_list.insert(0, resource)
        return share

    @classmethod
    def migrate_share(
            cls, share_id, dest_host, wait_for_status, client=None,
            force_host_assisted_migration=False, writable=False,
            nondisruptive=False, preserve_metadata=False,
            preserve_snapshots=False, new_share_network_id=None,
            new_share_type_id=None, **kwargs):
        client = client or cls.shares_v2_client
        client.migrate_share(
            share_id, dest_host,
            force_host_assisted_migration=force_host_assisted_migration,
            writable=writable, preserve_metadata=preserve_metadata,
            nondisruptive=nondisruptive, preserve_snapshots=preserve_snapshots,
            new_share_network_id=new_share_network_id,
            new_share_type_id=new_share_type_id, **kwargs)
        share = client.wait_for_migration_status(
            share_id, dest_host, wait_for_status, **kwargs)
        return share

    @classmethod
    def migration_complete(cls, share_id, dest_host, client=None, **kwargs):
        client = client or cls.shares_v2_client
        client.migration_complete(share_id, **kwargs)
        share = client.wait_for_migration_status(
            share_id, dest_host, 'migration_success', **kwargs)
        return share

    @classmethod
    def migration_cancel(cls, share_id, dest_host, client=None, **kwargs):
        client = client or cls.shares_v2_client
        client.migration_cancel(share_id, **kwargs)
        share = client.wait_for_migration_status(
            share_id, dest_host, 'migration_cancelled', **kwargs)
        return share

    @classmethod
    def create_share(cls, *args, **kwargs):
        """Create one share and wait for available state. Retry if allowed."""
        result = cls.create_shares([{"args": args, "kwargs": kwargs}])
        return result[0]

    @classmethod
    def create_shares(cls, share_data_list):
        """Creates several shares in parallel with retries.

        Use this method when you want to create more than one share at same
        time. Especially if config option 'share.share_creation_retry_number'
        has value more than zero (0).
        All shares will be expected to have 'available' status with or without
        recreation else error will be raised.

        :param share_data_list: list -- list of dictionaries with 'args' and
            'kwargs' for '_create_share' method of this base class.
            example of data:
                share_data_list=[{'args': ['quuz'], 'kwargs': {'foo': 'bar'}}}]
        :returns: list -- list of shares created using provided data.
        """

        for d in share_data_list:
            if not isinstance(d, dict):
                raise exceptions.TempestException(
                    "Expected 'dict', got '%s'" % type(d))
            if "args" not in d:
                d["args"] = []
            if "kwargs" not in d:
                d["kwargs"] = {}
            if len(d) > 2:
                raise exceptions.TempestException(
                    "Expected only 'args' and 'kwargs' keys. "
                    "Provided %s" % list(d))

        data = []
        for d in share_data_list:
            client = d["kwargs"].pop("client", cls.shares_v2_client)
            wait_for_status = d["kwargs"].pop("wait_for_status", True)
            local_d = {
                "args": d["args"],
                "kwargs": copy.deepcopy(d["kwargs"]),
            }
            local_d["kwargs"]["client"] = client
            local_d["share"] = cls._create_share(
                *local_d["args"], **local_d["kwargs"])
            local_d["cnt"] = 0
            local_d["available"] = False
            local_d["wait_for_status"] = wait_for_status
            data.append(local_d)

        while not all(d["available"] for d in data):
            for d in data:
                if not d["wait_for_status"]:
                    d["available"] = True
                if d["available"]:
                    continue
                client = d["kwargs"]["client"]
                share_id = d["share"]["id"]
                try:
                    client.wait_for_share_status(share_id, "available")
                    d["available"] = True
                except (share_exceptions.ShareBuildErrorException,
                        exceptions.TimeoutException) as e:
                    if CONF.share.share_creation_retry_number > d["cnt"]:
                        d["cnt"] += 1
                        msg = ("Share '%s' failed to be built. "
                               "Trying create another." % share_id)
                        LOG.error(msg)
                        LOG.error(e)
                        cg_id = d["kwargs"].get("consistency_group_id")
                        if cg_id:
                            # NOTE(vponomaryov): delete errored share
                            # immediately in case share is part of CG.
                            client.delete_share(
                                share_id,
                                params={"consistency_group_id": cg_id})
                            client.wait_for_resource_deletion(
                                share_id=share_id)
                        d["share"] = cls._create_share(
                            *d["args"], **d["kwargs"])
                    else:
                        raise

        return [d["share"] for d in data]

    @classmethod
    def create_share_group(cls, client=None, cleanup_in_class=True,
                           share_network_id=None, **kwargs):
        client = client or cls.shares_v2_client
        if kwargs.get('source_share_group_snapshot_id') is None:
            kwargs['share_network_id'] = (share_network_id or
                                          client.share_network_id or None)
        share_group = client.create_share_group(**kwargs)
        resource = {
            "type": "share_group",
            "id": share_group["id"],
            "client": client,
        }
        if cleanup_in_class:
            cls.class_resources.insert(0, resource)
        else:
            cls.method_resources.insert(0, resource)

        if kwargs.get('source_share_group_snapshot_id'):
            new_share_group_shares = client.list_shares(
                detailed=True,
                params={'share_group_id': share_group['id']},
                experimental=True)

            for share in new_share_group_shares:
                resource = {"type": "share",
                            "id": share["id"],
                            "client": client,
                            "share_group_id": share.get("share_group_id")}
                if cleanup_in_class:
                    cls.class_resources.insert(0, resource)
                else:
                    cls.method_resources.insert(0, resource)

        client.wait_for_share_group_status(share_group['id'], 'available')
        return share_group

    @classmethod
    def create_share_group_type(cls, name=None, share_types=(), is_public=None,
                                group_specs=None, client=None,
                                cleanup_in_class=True, **kwargs):
        client = client or cls.shares_v2_client
        if (group_specs is None and
                CONF.share.capability_sg_consistent_snapshot_support):
            group_specs = {
                'consistent_snapshot_support': (
                    CONF.share.capability_sg_consistent_snapshot_support),
            }
        share_group_type = client.create_share_group_type(
            name=name,
            share_types=share_types,
            is_public=is_public,
            group_specs=group_specs,
            **kwargs)
        resource = {
            "type": "share_group_type",
            "id": share_group_type["id"],
            "client": client,
        }
        if cleanup_in_class:
            cls.class_resources.insert(0, resource)
        else:
            cls.method_resources.insert(0, resource)
        return share_group_type

    @classmethod
    def create_snapshot_wait_for_active(cls, share_id, name=None,
                                        description=None, force=False,
                                        client=None, cleanup_in_class=True):
        if client is None:
            client = cls.shares_v2_client
        if description is None:
            description = "Tempest's snapshot"
        snapshot = client.create_snapshot(share_id, name, description, force)
        resource = {
            "type": "snapshot",
            "id": snapshot["id"],
            "client": client,
        }
        if cleanup_in_class:
            cls.class_resources.insert(0, resource)
        else:
            cls.method_resources.insert(0, resource)
        client.wait_for_snapshot_status(snapshot["id"], "available")
        return snapshot

    @classmethod
    def create_share_group_snapshot_wait_for_active(
            cls, share_group_id, name=None, description=None, client=None,
            cleanup_in_class=True, **kwargs):
        client = client or cls.shares_v2_client
        if description is None:
            description = "Tempest's share group snapshot"
        sg_snapshot = client.create_share_group_snapshot(
            share_group_id, name=name, description=description, **kwargs)
        resource = {
            "type": "share_group_snapshot",
            "id": sg_snapshot["id"],
            "client": client,
        }
        if cleanup_in_class:
            cls.class_resources.insert(0, resource)
        else:
            cls.method_resources.insert(0, resource)
        client.wait_for_share_group_snapshot_status(
            sg_snapshot["id"], "available")
        return sg_snapshot

    @classmethod
    def get_availability_zones(cls, client=None, backends=None):
        """List the availability zones for "manila-share" services

         that are currently in "up" state.
         """
        client = client or cls.admin_shares_v2_client
        backends = (
            '|'.join(['^%s$' % backend for backend in backends])
            if backends else '.*'
        )
        cls.services = client.list_services()
        zones = [service['zone'] for service in cls.services if
                 service['binary'] == 'manila-share' and
                 service['state'] == 'up' and
                 re.search(backends, service['host'])]
        return zones

    @classmethod
    def get_pools_matching_share_type(cls, share_type, client=None):
        client = client or cls.admin_shares_v2_client
        if utils.is_microversion_supported('2.23'):
            return client.list_pools(
                search_opts={'share_type': share_type['id']})['pools']

        pools = client.list_pools(detail=True)['pools']
        share_type = client.get_share_type(share_type['id'])['share_type']
        extra_specs = {}
        for k, v in share_type['extra_specs'].items():
            extra_specs[k] = (
                True if six.text_type(v).lower() == 'true'
                else False if six.text_type(v).lower() == 'false' else v
            )
        return [
            pool for pool in pools if all(y in pool['capabilities'].items()
                                          for y in extra_specs.items())
        ]

    @classmethod
    def get_availability_zones_matching_share_type(cls, share_type,
                                                   client=None):

        client = client or cls.admin_shares_v2_client
        pools_matching_share_type = cls.get_pools_matching_share_type(
            share_type, client=client)
        backends_matching_share_type = set(
            [pool['name'].split("#")[0] for pool in pools_matching_share_type]
        )
        azs = cls.get_availability_zones(backends=backends_matching_share_type)
        return azs

    def get_pools_for_replication_domain(self):
        # Get the list of pools for the replication domain
        pools = self.admin_client.list_pools(detail=True)['pools']
        instance_host = self.admin_client.get_share(
            self.shares[0]['id'])['host']
        host_pool = [p for p in pools if p['name'] == instance_host][0]
        rep_domain = host_pool['capabilities']['replication_domain']
        pools_in_rep_domain = [p for p in pools if p['capabilities'][
            'replication_domain'] == rep_domain]
        return rep_domain, pools_in_rep_domain

    @classmethod
    def create_share_replica(cls, share_id, availability_zone, client=None,
                             cleanup_in_class=False, cleanup=True):
        client = client or cls.shares_v2_client
        replica = client.create_share_replica(share_id, availability_zone)
        resource = {
            "type": "share_replica",
            "id": replica["id"],
            "client": client,
            "share_id": share_id,
        }
        # NOTE(Yogi1): Cleanup needs to be disabled during promotion tests.
        if cleanup:
            if cleanup_in_class:
                cls.class_resources.insert(0, resource)
            else:
                cls.method_resources.insert(0, resource)
        client.wait_for_share_replica_status(
            replica["id"], constants.STATUS_AVAILABLE)
        return replica

    @classmethod
    def delete_share_replica(cls, replica_id, client=None):
        client = client or cls.shares_v2_client
        try:
            client.delete_share_replica(replica_id)
            client.wait_for_resource_deletion(replica_id=replica_id)
        except exceptions.NotFound:
            pass

    @classmethod
    def promote_share_replica(cls, replica_id, client=None):
        client = client or cls.shares_v2_client
        replica = client.promote_share_replica(replica_id)
        client.wait_for_share_replica_status(
            replica["id"],
            constants.REPLICATION_STATE_ACTIVE,
            status_attr="replica_state")
        return replica

    def _get_access_rule_data_from_config(self):
        """Get the first available access type/to combination from config.

        This method opportunistically picks the first configured protocol
        to create the share. Do not use this method in tests where you need
        to test depth and breadth in the access types and access recipients.
        """
        protocol = self.shares_v2_client.share_protocol

        if protocol in CONF.share.enable_ip_rules_for_protocols:
            access_type = "ip"
            access_to = utils.rand_ip()
        elif protocol in CONF.share.enable_user_rules_for_protocols:
            access_type = "user"
            access_to = CONF.share.username_for_user_rules
        elif protocol in CONF.share.enable_cert_rules_for_protocols:
            access_type = "cert"
            access_to = "client3.com"
        elif protocol in CONF.share.enable_cephx_rules_for_protocols:
            access_type = "cephx"
            access_to = "eve"
        else:
            message = "Unrecognized protocol and access rules configuration."
            raise self.skipException(message)

        return access_type, access_to

    @classmethod
    def create_share_network(cls, client=None,
                             cleanup_in_class=False, **kwargs):
        if client is None:
            client = cls.shares_client
        share_network = client.create_share_network(**kwargs)
        resource = {
            "type": "share_network",
            "id": share_network["id"],
            "client": client,
        }
        if cleanup_in_class:
            cls.class_resources.insert(0, resource)
        else:
            cls.method_resources.insert(0, resource)
        return share_network

    @classmethod
    def create_security_service(cls, ss_type="ldap", client=None,
                                cleanup_in_class=False, **kwargs):
        if client is None:
            client = cls.shares_client
        security_service = client.create_security_service(ss_type, **kwargs)
        resource = {
            "type": "security_service",
            "id": security_service["id"],
            "client": client,
        }
        if cleanup_in_class:
            cls.class_resources.insert(0, resource)
        else:
            cls.method_resources.insert(0, resource)
        return security_service

    @classmethod
    def create_share_type(cls, name, is_public=True, client=None,
                          cleanup_in_class=True, **kwargs):
        if client is None:
            client = cls.shares_v2_client
        share_type = client.create_share_type(name, is_public, **kwargs)
        resource = {
            "type": "share_type",
            "id": share_type["share_type"]["id"],
            "client": client,
        }
        if cleanup_in_class:
            cls.class_resources.insert(0, resource)
        else:
            cls.method_resources.insert(0, resource)
        return share_type

    @staticmethod
    def add_extra_specs_to_dict(extra_specs=None):
        """Add any required extra-specs to share type dictionary"""
        dhss = six.text_type(CONF.share.multitenancy_enabled)
        snapshot_support = six.text_type(
            CONF.share.capability_snapshot_support)
        create_from_snapshot_support = six.text_type(
            CONF.share.capability_create_share_from_snapshot_support)

        extra_specs_dict = {
            "driver_handles_share_servers": dhss,
        }

        optional = {
            "snapshot_support": snapshot_support,
            "create_share_from_snapshot_support": create_from_snapshot_support,
        }
        # NOTE(gouthamr): In micro-versions < 2.24, snapshot_support is a
        # required extra-spec
        extra_specs_dict.update(optional)

        if extra_specs:
            extra_specs_dict.update(extra_specs)

        return extra_specs_dict

    @classmethod
    def clear_isolated_creds(cls, creds=None):
        if creds is None:
            creds = cls.method_isolated_creds
        for ic in creds:
            if "deleted" not in ic.keys():
                ic["deleted"] = False
            if not ic["deleted"]:
                with handle_cleanup_exceptions():
                    ic["method"]()
                ic["deleted"] = True

    @classmethod
    def clear_share_replicas(cls, share_id, client=None):
        client = client or cls.shares_v2_client
        share_replicas = client.list_share_replicas(
            share_id=share_id)

        for replica in share_replicas:
            try:
                cls.delete_share_replica(replica['id'])
            except exceptions.BadRequest:
                # Ignore the exception due to deletion of last active replica
                pass

    @classmethod
    def clear_resources(cls, resources=None):
        """Deletes resources, that were created in test suites.

        This method tries to remove resources from resource list,
        if it is not found, assumed it was deleted in test itself.
        It is expected, that all resources were added as LIFO
        due to restriction of deletion resources, that is in the chain.

        :param resources: dict with keys 'type','id','client' and 'deleted'
        """
        if resources is None:
            resources = cls.method_resources
        for res in resources:
            if "deleted" not in res.keys():
                res["deleted"] = False
            if "client" not in res.keys():
                res["client"] = cls.shares_client
            if not(res["deleted"]):
                res_id = res['id']
                client = res["client"]
                with handle_cleanup_exceptions():
                    if res["type"] is "share":
                        cls.clear_share_replicas(res_id)
                        share_group_id = res.get('share_group_id')
                        if share_group_id:
                            params = {'share_group_id': share_group_id}
                            client.delete_share(res_id, params=params)
                        else:
                            client.force_delete(res_id)
                        client.wait_for_resource_deletion(share_id=res_id)
                    elif res["type"] is "snapshot":
                        client.delete_snapshot(res_id)
                        client.wait_for_resource_deletion(snapshot_id=res_id)
                    elif (res["type"] is "share_network" and
                            res_id != CONF.share.share_network_id):
                        client.delete_share_network(res_id)
                        client.wait_for_resource_deletion(sn_id=res_id)
                    elif res["type"] is "security_service":
                        client.delete_security_service(res_id)
                        client.wait_for_resource_deletion(ss_id=res_id)
                    elif res["type"] is "share_type":
                        client.delete_share_type(res_id)
                        client.wait_for_resource_deletion(st_id=res_id)
                    elif res["type"] is "share_group":
                        client.delete_share_group(res_id)
                        client.wait_for_resource_deletion(
                            share_group_id=res_id)
                    elif res["type"] is "share_group_type":
                        client.delete_share_group_type(res_id)
                        client.wait_for_resource_deletion(
                            share_group_type_id=res_id)
                    elif res["type"] is "share_group_snapshot":
                        client.delete_share_group_snapshot(res_id)
                        client.wait_for_resource_deletion(
                            share_group_snapshot_id=res_id)
                    elif res["type"] is "share_replica":
                        client.delete_share_replica(res_id)
                        client.wait_for_resource_deletion(replica_id=res_id)
                    else:
                        LOG.warning("Provided unsupported resource type for "
                                    "cleanup '%s'. Skipping.", res["type"])
                res["deleted"] = True

    @classmethod
    def generate_share_network_data(self):
        data = {
            "name": data_utils.rand_name("sn-name"),
            "description": data_utils.rand_name("sn-desc"),
            "neutron_net_id": data_utils.rand_name("net-id"),
            "neutron_subnet_id": data_utils.rand_name("subnet-id"),
        }
        return data

    @classmethod
    def generate_security_service_data(self, set_ou=False):
        data = {
            "name": data_utils.rand_name("ss-name"),
            "description": data_utils.rand_name("ss-desc"),
            "dns_ip": utils.rand_ip(),
            "server": utils.rand_ip(),
            "domain": data_utils.rand_name("ss-domain"),
            "user": data_utils.rand_name("ss-user"),
            "password": data_utils.rand_name("ss-password"),
        }
        if set_ou:
            data["ou"] = data_utils.rand_name("ss-ou")

        return data

    # Useful assertions
    def assertDictMatch(self, d1, d2, approx_equal=False, tolerance=0.001):
        """Assert two dicts are equivalent.

        This is a 'deep' match in the sense that it handles nested
        dictionaries appropriately.

        NOTE:

            If you don't care (or don't know) a given value, you can specify
            the string DONTCARE as the value. This will cause that dict-item
            to be skipped.

        """
        def raise_assertion(msg):
            d1str = str(d1)
            d2str = str(d2)
            base_msg = ('Dictionaries do not match. %(msg)s d1: %(d1str)s '
                        'd2: %(d2str)s' %
                        {"msg": msg, "d1str": d1str, "d2str": d2str})
            raise AssertionError(base_msg)

        d1keys = set(d1.keys())
        d2keys = set(d2.keys())
        if d1keys != d2keys:
            d1only = d1keys - d2keys
            d2only = d2keys - d1keys
            raise_assertion('Keys in d1 and not d2: %(d1only)s. '
                            'Keys in d2 and not d1: %(d2only)s' %
                            {"d1only": d1only, "d2only": d2only})

        for key in d1keys:
            d1value = d1[key]
            d2value = d2[key]
            try:
                error = abs(float(d1value) - float(d2value))
                within_tolerance = error <= tolerance
            except (ValueError, TypeError):
                # If both values aren't convertible to float, just ignore
                # ValueError if arg is a str, TypeError if it's something else
                # (like None)
                within_tolerance = False

            if hasattr(d1value, 'keys') and hasattr(d2value, 'keys'):
                self.assertDictMatch(d1value, d2value)
            elif 'DONTCARE' in (d1value, d2value):
                continue
            elif approx_equal and within_tolerance:
                continue
            elif d1value != d2value:
                raise_assertion("d1['%(key)s']=%(d1value)s != "
                                "d2['%(key)s']=%(d2value)s" %
                                {
                                    "key": key,
                                    "d1value": d1value,
                                    "d2value": d2value
                                })

    def create_user_message(self):
        """Trigger a 'no valid host' situation to generate a message."""
        extra_specs = {
            'vendor_name': 'foobar',
            'driver_handles_share_servers': CONF.share.multitenancy_enabled,
        }
        share_type_name = data_utils.rand_name("share-type")

        bogus_type = self.create_share_type(
            name=share_type_name,
            extra_specs=extra_specs)['share_type']

        params = {'share_type_id': bogus_type['id'],
                  'share_network_id': self.shares_v2_client.share_network_id}
        share = self.shares_v2_client.create_share(**params)
        self.addCleanup(self.shares_v2_client.delete_share, share['id'])
        self.shares_v2_client.wait_for_share_status(share['id'], "error")
        return self.shares_v2_client.wait_for_message(share['id'])


class BaseSharesAltTest(BaseSharesTest):
    """Base test case class for all Shares Alt API tests."""
    credentials = ('alt', )


class BaseSharesAdminTest(BaseSharesTest):
    """Base test case class for all Shares Admin API tests."""
    credentials = ('admin', )

    @classmethod
    def setup_clients(cls):
        super(BaseSharesAdminTest, cls).setup_clients()
        # Initialise share clients
        cls.admin_shares_v2_client = cls.os_admin.share_v2.SharesV2Client()

    @classmethod
    def _create_share_type(cls, specs=None):
        name = data_utils.rand_name("unique_st_name")
        extra_specs = cls.add_extra_specs_to_dict(specs)
        return cls.create_share_type(
            name, extra_specs=extra_specs,
            client=cls.admin_shares_v2_client)['share_type']

    @classmethod
    def _create_share_group_type(cls):
        share_group_type_name = data_utils.rand_name("unique_sgtype_name")
        return cls.create_share_group_type(
            name=share_group_type_name, share_types=[cls.share_type_id],
            client=cls.admin_shares_v2_client)

    def _create_share_for_manage(self):
        creation_data = {
            'share_type_id': self.st['share_type']['id'],
            'share_protocol': self.protocol,
        }

        share = self.create_share(**creation_data)
        share = self.shares_v2_client.get_share(share['id'])

        if utils.is_microversion_ge(CONF.share.max_api_microversion, "2.9"):
            el = self.shares_v2_client.list_share_export_locations(share["id"])
            share["export_locations"] = el

        return share

    def _unmanage_share_and_wait(self, share):
        self.shares_v2_client.unmanage_share(share['id'])
        self.shares_v2_client.wait_for_resource_deletion(share_id=share['id'])

    def _reset_state_and_delete_share(self, share):
        self.shares_v2_client.reset_state(share['id'])
        self._delete_share_and_wait(share)

    def _delete_snapshot_and_wait(self, snap):
        self.shares_v2_client.delete_snapshot(snap['id'])
        self.shares_v2_client.wait_for_resource_deletion(
            snapshot_id=snap['id']
        )
        self.assertRaises(exceptions.NotFound,
                          self.shares_v2_client.get_snapshot,
                          snap['id'])

    def _delete_share_and_wait(self, share):
        self.shares_v2_client.delete_share(share['id'])
        self.shares_v2_client.wait_for_resource_deletion(share_id=share['id'])
        self.assertRaises(exceptions.NotFound,
                          self.shares_v2_client.get_share,
                          share['id'])

    def _manage_share(self, share, name, description, share_server_id):
        managed_share = self.shares_v2_client.manage_share(
            service_host=share['host'],
            export_path=share['export_locations'][0],
            protocol=share['share_proto'],
            share_type_id=self.share_type['share_type']['id'],
            name=name,
            description=description,
            share_server_id=share_server_id
        )
        self.shares_v2_client.wait_for_share_status(
            managed_share['id'], constants.STATUS_AVAILABLE
        )

        return managed_share

    def _unmanage_share_server_and_wait(self, server):
        self.shares_v2_client.unmanage_share_server(server['id'])
        self.shares_v2_client.wait_for_resource_deletion(
            server_id=server['id']
        )

    def _manage_share_server(self, share_server, fields=None):
        params = fields or {}
        managed_share_server = self.shares_v2_client.manage_share_server(
            params.get('host', share_server['host']),
            params.get('share_network_id', share_server['share_network_id']),
            params.get('identifier', share_server['identifier']),
        )
        self.shares_v2_client.wait_for_share_server_status(
            managed_share_server['id'],
            constants.SERVER_STATE_ACTIVE,
        )

        return managed_share_server

    def _delete_share_server_and_wait(self, share_server_id):
        self.shares_v2_client.delete_share_server(
            share_server_id
        )
        self.shares_v2_client.wait_for_resource_deletion(
            server_id=share_server_id)


class BaseSharesMixedTest(BaseSharesTest):
    """Base test case class for all Shares API tests with all user roles."""
    credentials = ('primary', 'alt', 'admin')

    @classmethod
    def setup_clients(cls):
        super(BaseSharesMixedTest, cls).setup_clients()
        # Initialise share clients
        cls.admin_shares_client = cls.os_admin.share_v1.SharesClient()
        cls.admin_shares_v2_client = cls.os_admin.share_v2.SharesV2Client()
        cls.alt_shares_client = cls.os_alt.share_v1.SharesClient()
        cls.alt_shares_v2_client = cls.os_alt.share_v2.SharesV2Client()
        # Initialise network clients
        cls.os_admin.networks_client = cls.os_admin.network.NetworksClient()
        cls.os_alt.networks_client = cls.os_alt.network.NetworksClient()

        if CONF.share.multitenancy_enabled:
            admin_share_network_id = cls.provide_share_network(
                cls.admin_shares_v2_client, cls.os_admin.networks_client)
            cls.admin_shares_client.share_network_id = admin_share_network_id
            cls.admin_shares_v2_client.share_network_id = (
                admin_share_network_id)

            alt_share_network_id = cls.provide_share_network(
                cls.alt_shares_v2_client, cls.os_alt.networks_client)
            cls.alt_shares_client.share_network_id = alt_share_network_id
            cls.alt_shares_v2_client.share_network_id = alt_share_network_id
            resource = {
                "type": "share_network",
                "id": alt_share_network_id,
                "client": cls.alt_shares_v2_client,
            }
            cls.class_resources.insert(0, resource)

    @classmethod
    def _create_share_type(cls, specs=None):
        name = data_utils.rand_name("unique_st_name")
        extra_specs = cls.add_extra_specs_to_dict(specs)
        return cls.create_share_type(
            name, extra_specs=extra_specs,
            client=cls.admin_shares_v2_client)['share_type']

    @classmethod
    def _create_share_group_type(cls):
        share_group_type_name = data_utils.rand_name("unique_sgtype_name")
        return cls.create_share_group_type(
            name=share_group_type_name, share_types=[cls.share_type_id],
            client=cls.admin_shares_v2_client)
