# Copyright 2019 NetApp Inc.
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

from tempest import config
from tempest.lib.common.utils import data_utils
import testtools
from testtools import testcase as tc

from manila_tempest_tests.tests.api import base

CONF = config.CONF


@base.skip_if_microversion_lt("2.49")
@testtools.skipUnless(
    CONF.share.multitenancy_enabled,
    'Multitenancy tests are disabled.')
@testtools.skipUnless(
    CONF.share.run_manage_unmanage_tests,
    'Manage/unmanage tests are disabled.')
class ManageShareServersTest(base.BaseSharesAdminTest):

    @classmethod
    def resource_setup(cls):
        super(ManageShareServersTest, cls).resource_setup()

        # create share type
        cls.st_name = data_utils.rand_name("manage-st-name")
        cls.extra_specs = {
            'storage_protocol': CONF.share.capability_storage_protocol,
            'driver_handles_share_servers': CONF.share.multitenancy_enabled,
        }
        cls.share_type = cls.create_share_type(
            name=cls.st_name,
            cleanup_in_class=True,
            extra_specs=cls.extra_specs)

    @testtools.skipIf(CONF.share.share_network_id != "",
                      "This test is not suitable for pre-existing "
                      "share_network.")
    @tc.attr(base.TAG_POSITIVE, base.TAG_BACKEND)
    def test_manage_share_server(self):

        # create a new share network to make sure that a new share server
        # will be created
        original_share_network = self.shares_v2_client.get_share_network(
            self.shares_v2_client.share_network_id
        )
        share_network = self.create_share_network(
            neutron_net_id=original_share_network['neutron_net_id'],
            neutron_subnet_id=original_share_network['neutron_subnet_id'],
            cleanup_in_class=True
        )

        # create share
        share = self.create_share(
            share_type_id=self.share_type['share_type']['id'],
            share_network_id=share_network['id']
        )
        share = self.shares_v2_client.get_share(share['id'])
        el = self.shares_v2_client.list_share_export_locations(share['id'])
        share['export_locations'] = el
        share_server = self.shares_v2_client.show_share_server(
            share['share_server_id']
        )

        keys = [
            "id",
            "host",
            "project_id",
            "status",
            "share_network_name",
            "created_at",
            "updated_at",
            "backend_details",
            "is_auto_deletable",
            "identifier",
        ]
        # all expected keys are present
        for key in keys:
            self.assertIn(key, share_server)

        # check that the share server is initially auto-deletable
        self.assertIs(True, share_server["is_auto_deletable"])
        self.assertIsNotNone(share_server["identifier"])

        self._unmanage_share_and_wait(share)

        # Starting from microversion 2.49, any share server that has ever had
        # an unmanaged share will never be auto-deleted.
        share_server = self.shares_v2_client.show_share_server(
            share_server['id']
        )
        self.assertIs(False, share_server['is_auto_deletable'])

        # unmanage share server and manage it again
        self._unmanage_share_server_and_wait(share_server)
        managed_share_server = self._manage_share_server(share_server)
        managed_share = self._manage_share(
            share,
            name="managed share that had ID %s" % share['id'],
            description="description for managed share",
            share_server_id=managed_share_server['id']
        )

        # check managed share server
        managed_share_server = self.shares_v2_client.show_share_server(
            managed_share_server['id']
        )

        # all expected keys are present in the managed share server
        for key in keys:
            self.assertIn(key, managed_share_server)

        # check that managed share server is used by the managed share
        self.assertEqual(
            managed_share['share_server_id'],
            managed_share_server['id']
        )

        # check that the managed share server is still not auto-deletable
        self.assertIs(False, managed_share_server["is_auto_deletable"])

        # delete share
        self._delete_share_and_wait(managed_share)

        # delete share server
        self._delete_share_server_and_wait(managed_share_server['id'])
