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

import ddt
import six
from tempest import config
from tempest.lib.common.utils import data_utils
import testtools
from testtools import testcase as tc

from manila_tempest_tests.common import constants
from manila_tempest_tests.tests.api import base
from manila_tempest_tests import utils

CONF = config.CONF
LATEST_MICROVERSION = CONF.share.max_api_microversion


@ddt.ddt
class SharesActionsTest(base.BaseSharesTest):
    """Covers share functionality, that doesn't related to share type."""

    @classmethod
    def resource_setup(cls):
        super(SharesActionsTest, cls).resource_setup()

        cls.shares = []

        # create share
        cls.share_name = data_utils.rand_name("tempest-share-name")
        cls.share_desc = data_utils.rand_name("tempest-share-description")
        cls.metadata = {
            'foo_key_share_1': 'foo_value_share_1',
            'bar_key_share_1': 'foo_value_share_1',
        }
        cls.shares.append(cls.create_share(
            name=cls.share_name,
            description=cls.share_desc,
            metadata=cls.metadata,
        ))

        if CONF.share.run_snapshot_tests:
            # create snapshot
            cls.snap_name = data_utils.rand_name("tempest-snapshot-name")
            cls.snap_desc = data_utils.rand_name(
                "tempest-snapshot-description")
            cls.snap = cls.create_snapshot_wait_for_active(
                cls.shares[0]["id"], cls.snap_name, cls.snap_desc)

            if CONF.share.capability_create_share_from_snapshot_support:

                # create second share from snapshot for purposes of sorting and
                # snapshot filtering
                cls.share_name2 = data_utils.rand_name("tempest-share-name")
                cls.share_desc2 = data_utils.rand_name(
                    "tempest-share-description")
                cls.metadata2 = {
                    'foo_key_share_2': 'foo_value_share_2',
                    'bar_key_share_2': 'foo_value_share_2',
                }
                cls.shares.append(cls.create_share(
                    name=cls.share_name2,
                    description=cls.share_desc2,
                    metadata=cls.metadata2,
                    snapshot_id=cls.snap['id'],
                ))

    def _get_share(self, version):

        # get share
        share = self.shares_v2_client.get_share(
            self.shares[0]['id'], version=six.text_type(version))

        # verify keys
        expected_keys = [
            "status", "description", "links", "availability_zone",
            "created_at", "project_id", "volume_type", "share_proto", "name",
            "snapshot_id", "id", "size", "share_network_id", "metadata",
            "snapshot_id", "is_public",
        ]
        if utils.is_microversion_lt(version, '2.9'):
            expected_keys.extend(["export_location", "export_locations"])
        if utils.is_microversion_ge(version, '2.2'):
            expected_keys.append("snapshot_support")
        if utils.is_microversion_ge(version, '2.5'):
            expected_keys.append("share_type_name")
        if utils.is_microversion_ge(version, '2.10'):
            expected_keys.append("access_rules_status")
        if utils.is_microversion_ge(version, '2.11'):
            expected_keys.append("replication_type")
        if utils.is_microversion_ge(version, '2.16'):
            expected_keys.append("user_id")
        if utils.is_microversion_ge(version, '2.24'):
            expected_keys.append("create_share_from_snapshot_support")
        if utils.is_microversion_ge(version,
                                    constants.REVERT_TO_SNAPSHOT_MICROVERSION):
            expected_keys.append("revert_to_snapshot_support")
        actual_keys = list(share.keys())
        [self.assertIn(key, actual_keys) for key in expected_keys]

        # verify values
        msg = "Expected name: '%s', actual name: '%s'" % (self.share_name,
                                                          share["name"])
        self.assertEqual(self.share_name, six.text_type(share["name"]), msg)

        msg = ("Expected description: '%s', "
               "actual description: '%s'" % (self.share_desc,
                                             share["description"]))
        self.assertEqual(
            self.share_desc, six.text_type(share["description"]), msg)

        msg = "Expected size: '%s', actual size: '%s'" % (
            CONF.share.share_size, share["size"])
        self.assertEqual(CONF.share.share_size, int(share["size"]), msg)

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    def test_get_share_v2_1(self):
        self._get_share('2.1')

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    def test_get_share_with_snapshot_support_key(self):
        self._get_share('2.2')

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    @utils.skip_if_microversion_not_supported('2.6')
    def test_get_share_with_share_type_name_key(self):
        self._get_share('2.6')

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    @utils.skip_if_microversion_not_supported('2.9')
    def test_get_share_export_locations_removed(self):
        self._get_share('2.9')

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    @utils.skip_if_microversion_not_supported('2.10')
    def test_get_share_with_access_rules_status(self):
        self._get_share('2.10')

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    @utils.skip_if_microversion_not_supported('2.11')
    def test_get_share_with_replication_type_key(self):
        self._get_share('2.11')

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    @utils.skip_if_microversion_not_supported('2.16')
    def test_get_share_with_user_id(self):
        self._get_share('2.16')

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    @utils.skip_if_microversion_not_supported('2.24')
    def test_get_share_with_create_share_from_snapshot_support(self):
        self._get_share('2.24')

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    @utils.skip_if_microversion_not_supported(
        constants.REVERT_TO_SNAPSHOT_MICROVERSION)
    def test_get_share_with_revert_to_snapshot_support(self):
        self._get_share(constants.REVERT_TO_SNAPSHOT_MICROVERSION)

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    def test_list_shares(self):

        # list shares
        shares = self.shares_v2_client.list_shares()

        # verify keys
        keys = ["name", "id", "links"]
        [self.assertIn(key, sh.keys()) for sh in shares for key in keys]

        # our share id in list and have no duplicates
        for share in self.shares:
            gen = [sid["id"] for sid in shares if sid["id"] in share["id"]]
            msg = "expected id lists %s times in share list" % (len(gen))
            self.assertEqual(1, len(gen), msg)

    def _list_shares_with_detail(self, version):

        # list shares
        shares = self.shares_v2_client.list_shares_with_detail(
            version=six.text_type(version))

        # verify keys
        keys = [
            "status", "description", "links", "availability_zone",
            "created_at", "project_id", "volume_type", "share_proto", "name",
            "snapshot_id", "id", "size", "share_network_id", "metadata",
            "snapshot_id", "is_public", "share_type",
        ]
        if utils.is_microversion_lt(version, '2.9'):
            keys.extend(["export_location", "export_locations"])
        if utils.is_microversion_ge(version, '2.2'):
            keys.append("snapshot_support")
        if utils.is_microversion_ge(version, '2.6'):
            keys.append("share_type_name")
        if utils.is_microversion_ge(version, '2.10'):
            keys.append("access_rules_status")
        if utils.is_microversion_ge(version, '2.11'):
            keys.append("replication_type")
        if utils.is_microversion_ge(version, '2.16'):
            keys.append("user_id")
        if utils.is_microversion_ge(version, '2.24'):
            keys.append("create_share_from_snapshot_support")
        if utils.is_microversion_ge(version,
                                    constants.REVERT_TO_SNAPSHOT_MICROVERSION):
            keys.append("revert_to_snapshot_support")
        [self.assertIn(key, sh.keys()) for sh in shares for key in keys]

        # our shares in list and have no duplicates
        for share in self.shares:
            gen = [sid["id"] for sid in shares if sid["id"] in share["id"]]
            msg = "expected id lists %s times in share list" % (len(gen))
            self.assertEqual(1, len(gen), msg)

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    def test_list_shares_with_detail_v2_1(self):
        self._list_shares_with_detail('2.1')

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    def test_list_shares_with_detail_and_snapshot_support_key(self):
        self._list_shares_with_detail('2.2')

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    @utils.skip_if_microversion_not_supported('2.6')
    def test_list_shares_with_detail_share_type_name_key(self):
        self._list_shares_with_detail('2.6')

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    @utils.skip_if_microversion_not_supported('2.9')
    def test_list_shares_with_detail_export_locations_removed(self):
        self._list_shares_with_detail('2.9')

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    @utils.skip_if_microversion_not_supported('2.10')
    def test_list_shares_with_detail_with_access_rules_status(self):
        self._list_shares_with_detail('2.10')

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    @utils.skip_if_microversion_not_supported('2.11')
    def test_list_shares_with_detail_replication_type_key(self):
        self._list_shares_with_detail('2.11')

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    @utils.skip_if_microversion_not_supported('2.16')
    def test_list_shares_with_user_id(self):
        self._list_shares_with_detail('2.16')

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    def test_list_shares_with_detail_and_create_share_from_snapshot_support(
            self):
        self._list_shares_with_detail('2.24')

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    @utils.skip_if_microversion_not_supported(
        constants.REVERT_TO_SNAPSHOT_MICROVERSION)
    def test_list_shares_with_detail_with_revert_to_snapshot_support(self):
        self._list_shares_with_detail(
            constants.REVERT_TO_SNAPSHOT_MICROVERSION)

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    def test_list_shares_with_detail_filter_by_metadata(self):
        filters = {'metadata': self.metadata}

        # list shares
        shares = self.shares_client.list_shares_with_detail(params=filters)

        # verify response
        self.assertGreater(len(shares), 0)
        for share in shares:
            self.assertDictContainsSubset(
                filters['metadata'], share['metadata'])
        if CONF.share.capability_create_share_from_snapshot_support:
            self.assertFalse(self.shares[1]['id'] in [s['id'] for s in shares])

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    @testtools.skipIf(
        not CONF.share.multitenancy_enabled, "Only for multitenancy.")
    def test_list_shares_with_detail_filter_by_share_network_id(self):
        base_share = self.shares_client.get_share(self.shares[0]['id'])
        filters = {'share_network_id': base_share['share_network_id']}

        # list shares
        shares = self.shares_client.list_shares_with_detail(params=filters)

        # verify response
        self.assertGreater(len(shares), 0)
        for share in shares:
            self.assertEqual(
                filters['share_network_id'], share['share_network_id'])

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    @testtools.skipUnless(CONF.share.run_snapshot_tests,
                          "Snapshot tests are disabled.")
    @testtools.skipUnless(
        CONF.share.capability_create_share_from_snapshot_support,
        "Create share from snapshot tests are disabled.")
    def test_list_shares_with_detail_filter_by_snapshot_id(self):
        filters = {'snapshot_id': self.snap['id']}

        # list shares
        shares = self.shares_client.list_shares_with_detail(params=filters)

        # verify response
        self.assertGreater(len(shares), 0)
        for share in shares:
            self.assertEqual(filters['snapshot_id'], share['snapshot_id'])
        self.assertFalse(self.shares[0]['id'] in [s['id'] for s in shares])

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    def test_list_shares_with_detail_with_asc_sorting(self):
        filters = {'sort_key': 'created_at', 'sort_dir': 'asc'}

        # list shares
        shares = self.shares_client.list_shares_with_detail(params=filters)

        # verify response
        self.assertGreater(len(shares), 0)
        sorted_list = [share['created_at'] for share in shares]
        self.assertEqual(sorted(sorted_list), sorted_list)

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    def test_list_shares_with_detail_filter_by_existed_name(self):
        # list shares by name, at least one share is expected
        params = {"name": self.share_name}
        shares = self.shares_client.list_shares_with_detail(params)
        self.assertEqual(self.share_name, shares[0]["name"])

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    @base.skip_if_microversion_lt("2.36")
    def test_list_shares_with_detail_filter_by_existed_description(self):
        # list shares by description, at least one share is expected
        params = {"description": self.share_desc}
        shares = self.shares_v2_client.list_shares_with_detail(params)
        self.assertEqual(self.share_name, shares[0]["name"])

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    @base.skip_if_microversion_lt("2.36")
    def test_list_shares_with_detail_filter_by_inexact_name(self):
        # list shares by name, at least one share is expected
        params = {"name~": 'tempest-share'}
        shares = self.shares_v2_client.list_shares_with_detail(params)
        for share in shares:
            self.assertIn('tempest-share', share["name"])

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    def test_list_shares_with_detail_filter_by_fake_name(self):
        # list shares by fake name, no shares are expected
        params = {"name": data_utils.rand_name("fake-nonexistent-name")}
        shares = self.shares_client.list_shares_with_detail(params)
        self.assertEqual(0, len(shares))

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    def test_list_shares_with_detail_filter_by_active_status(self):
        # list shares by active status, at least one share is expected
        params = {"status": "available"}
        shares = self.shares_client.list_shares_with_detail(params)
        self.assertGreater(len(shares), 0)
        for share in shares:
            self.assertEqual(params["status"], share["status"])

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    def test_list_shares_with_detail_filter_by_fake_status(self):
        # list shares by fake status, no shares are expected
        params = {"status": 'fake'}
        shares = self.shares_client.list_shares_with_detail(params)
        self.assertEqual(0, len(shares))

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    def test_list_shares_with_detail_filter_by_all_tenants(self):
        # non-admin user can get shares only from his project
        params = {"all_tenants": 1}
        shares = self.shares_client.list_shares_with_detail(params)
        self.assertGreater(len(shares), 0)

        # get share with detailed info, we need its 'project_id'
        share = self.shares_client.get_share(self.shares[0]["id"])
        project_id = share["project_id"]
        for share in shares:
            self.assertEqual(project_id, share["project_id"])

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    @base.skip_if_microversion_lt("2.42")
    def test_list_shares_with_detail_with_count(self):
        # list shares by name, at least one share is expected
        params = {"with_count": 'true'}
        shares = self.shares_v2_client.list_shares_with_detail(params)
        self.assertGreater(shares["count"], 0)

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    @testtools.skipUnless(CONF.share.run_public_tests,
                          "Public tests are disabled.")
    def test_list_shares_public_with_detail(self):
        public_share = self.create_share(
            name='public_share',
            description='public_share_desc',
            is_public=True,
            cleanup_in_class=False
        )
        private_share = self.create_share(
            name='private_share',
            description='private_share_desc',
            is_public=False,
            cleanup_in_class=False
        )

        params = {"is_public": True}
        isolated_client = self.get_client_with_isolated_creds(
            type_of_creds='alt')
        shares = isolated_client.list_shares_with_detail(params)

        keys = [
            "status", "description", "links", "availability_zone",
            "created_at", "export_location", "share_proto",
            "name", "snapshot_id", "id", "size", "project_id", "is_public",
        ]
        [self.assertIn(key, sh.keys()) for sh in shares for key in keys]

        gen = [sid["id"] for sid in shares if sid["id"] == public_share["id"]]
        msg = "expected id lists %s times in share list" % (len(gen))
        self.assertEqual(1, len(gen), msg)

        self.assertFalse(any([s["id"] == private_share["id"] for s in shares]))

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    @testtools.skipUnless(CONF.share.run_snapshot_tests,
                          "Snapshot tests are disabled.")
    @ddt.data(None, '2.16', LATEST_MICROVERSION)
    def test_get_snapshot(self, version):

        # get snapshot
        if version is None:
            snapshot = self.shares_client.get_snapshot(self.snap["id"])
        else:
            self.skip_if_microversion_not_supported(version)
            snapshot = self.shares_v2_client.get_snapshot(
                self.snap["id"], version=version)

        # verify keys
        expected_keys = ["status", "links", "share_id", "name",
                         "share_proto", "created_at",
                         "description", "id", "share_size", "size"]
        if version and utils.is_microversion_ge(version, '2.17'):
            expected_keys.extend(["user_id", "project_id"])
        actual_keys = snapshot.keys()

        # strict key check
        self.assertEqual(set(expected_keys), set(actual_keys))

        # verify data
        msg = "Expected name: '%s', actual name: '%s'" % (self.snap_name,
                                                          snapshot["name"])
        self.assertEqual(self.snap_name, snapshot["name"], msg)

        msg = ("Expected description: '%s' actual description: '%s'" %
               (self.snap_desc, snapshot["description"]))
        self.assertEqual(self.snap_desc, snapshot["description"], msg)

        msg = ("Expected share_id: '%s', actual share_id: '%s'" %
               (self.shares[0]["id"], snapshot["share_id"]))
        self.assertEqual(self.shares[0]["id"], snapshot["share_id"], msg)

        # Verify that the user_id and project_id are same as the one for
        # the base share
        if version and utils.is_microversion_ge(version, '2.17'):
            msg = ("Expected %(key)s in snapshot: '%(expected)s', "
                   "actual %(key)s in snapshot: '%(actual)s'")
            self.assertEqual(self.shares[0]['user_id'],
                             snapshot['user_id'],
                             msg % {
                                 'expected': self.shares[0]['user_id'],
                                 'actual': snapshot['user_id'],
                                 'key': 'user_id'})
            self.assertEqual(self.shares[0]['project_id'],
                             snapshot['project_id'],
                             msg % {
                                 'expected': self.shares[0]['project_id'],
                                 'actual': snapshot['project_id'],
                                 'key': 'project_id'})

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    @testtools.skipUnless(CONF.share.run_snapshot_tests,
                          "Snapshot tests are disabled.")
    def test_list_snapshots(self):

        # list share snapshots
        snaps = self.shares_client.list_snapshots()

        # verify keys
        keys = ["id", "name", "links"]
        [self.assertIn(key, sn.keys()) for sn in snaps for key in keys]

        # our share id in list and have no duplicates
        gen = [sid["id"] for sid in snaps if sid["id"] in self.snap["id"]]
        msg = "expected id lists %s times in share list" % (len(gen))
        self.assertEqual(1, len(gen), msg)

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    @testtools.skipUnless(CONF.share.run_snapshot_tests,
                          "Snapshot tests are disabled.")
    @ddt.data(None, '2.16', '2.36', LATEST_MICROVERSION)
    def test_list_snapshots_with_detail(self, version):
        params = None
        if version and utils.is_microversion_ge(version, '2.36'):
            params = {'name~': 'tempest', 'description~': 'tempest'}
        # list share snapshots
        if version is None:
            snaps = self.shares_client.list_snapshots_with_detail()
        else:
            self.skip_if_microversion_not_supported(version)
            snaps = self.shares_v2_client.list_snapshots_with_detail(
                version=version, params=params)

        # verify keys
        expected_keys = ["status", "links", "share_id", "name",
                         "share_proto", "created_at", "description", "id",
                         "share_size", "size"]
        if version and utils.is_microversion_ge(version, '2.17'):
            expected_keys.extend(["user_id", "project_id"])

        # strict key check
        [self.assertEqual(set(expected_keys), set(s.keys())) for s in snaps]

        # our share id in list and have no duplicates
        gen = [sid["id"] for sid in snaps if sid["id"] in self.snap["id"]]
        msg = "expected id lists %s times in share list" % (len(gen))
        self.assertEqual(1, len(gen), msg)

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    @testtools.skipUnless(CONF.share.run_snapshot_tests,
                          "Snapshot tests are disabled.")
    def test_list_snapshots_with_detail_use_limit(self):
        for l, o in [('1', '1'), ('0', '1')]:
            filters = {
                'limit': l,
                'offset': o,
                'share_id': self.shares[0]['id'],
            }

            # list snapshots
            snaps = self.shares_client.list_snapshots_with_detail(
                params=filters)

            # Our snapshot should not be listed
            self.assertEqual(0, len(snaps))

        # Only our one snapshot should be listed
        snaps = self.shares_client.list_snapshots_with_detail(
            params={'limit': '1', 'offset': '0',
                    'share_id': self.shares[0]['id']})

        self.assertEqual(1, len(snaps['snapshots']))
        self.assertEqual(self.snap['id'], snaps['snapshots'][0]['id'])

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    @testtools.skipUnless(CONF.share.run_snapshot_tests,
                          "Snapshot tests are disabled.")
    def test_list_snapshots_with_detail_filter_by_status_and_name(self):
        filters = {'status': 'available', 'name': self.snap_name}

        # list snapshots
        snaps = self.shares_client.list_snapshots_with_detail(
            params=filters)

        # verify response
        self.assertGreater(len(snaps), 0)
        for snap in snaps:
            self.assertEqual(filters['status'], snap['status'])
            self.assertEqual(filters['name'], snap['name'])

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    @testtools.skipUnless(CONF.share.run_snapshot_tests,
                          "Snapshot tests are disabled.")
    @base.skip_if_microversion_not_supported("2.35")
    def test_list_snapshots_with_detail_filter_by_description(self):
        filters = {'description': self.snap_desc}

        # list snapshots
        snaps = self.shares_client.list_snapshots_with_detail(
            params=filters)

        # verify response
        self.assertGreater(len(snaps), 0)
        for snap in snaps:
            self.assertEqual(filters['description'], snap['description'])

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    @testtools.skipUnless(CONF.share.run_snapshot_tests,
                          "Snapshot tests are disabled.")
    def test_list_snapshots_with_detail_and_asc_sorting(self):
        filters = {'sort_key': 'share_id', 'sort_dir': 'asc'}

        # list snapshots
        snaps = self.shares_client.list_snapshots_with_detail(
            params=filters)

        # verify response
        self.assertGreater(len(snaps), 0)
        sorted_list = [snap['share_id'] for snap in snaps]
        self.assertEqual(sorted(sorted_list), sorted_list)

    @tc.attr(base.TAG_POSITIVE, base.TAG_BACKEND)
    @testtools.skipUnless(
        CONF.share.run_extend_tests,
        "Share extend tests are disabled.")
    def test_extend_share(self):
        share = self.create_share(cleanup_in_class=False)
        new_size = int(share['size']) + 1

        # extend share and wait for active status
        self.shares_v2_client.extend_share(share['id'], new_size)
        self.shares_client.wait_for_share_status(share['id'], 'available')

        # check state and new size
        share_get = self.shares_v2_client.get_share(share['id'])
        msg = (
            "Share could not be extended. "
            "Expected %(expected)s, got %(actual)s." % {
                "expected": new_size,
                "actual": share_get['size'],
            }
        )
        self.assertEqual(new_size, share_get['size'], msg)

    @tc.attr(base.TAG_POSITIVE, base.TAG_BACKEND)
    @testtools.skipUnless(
        CONF.share.run_shrink_tests,
        "Share shrink tests are disabled.")
    def test_shrink_share(self):
        size = CONF.share.share_size + 1
        share = self.create_share(size=size, cleanup_in_class=False)
        new_size = int(share['size']) - 1

        # shrink share and wait for active status
        self.shares_v2_client.shrink_share(share['id'], new_size)
        self.shares_client.wait_for_share_status(share['id'], 'available')

        # check state and new size
        share_get = self.shares_v2_client.get_share(share['id'])
        msg = (
            "Share could not be shrunk. "
            "Expected %(expected)s, got %(actual)s." % {
                "expected": new_size,
                "actual": share_get['size'],
            }
        )
        self.assertEqual(new_size, share_get['size'], msg)


class SharesRenameTest(base.BaseSharesTest):

    @classmethod
    def resource_setup(cls):
        super(SharesRenameTest, cls).resource_setup()

        # create share
        cls.share_name = data_utils.rand_name("tempest-share-name")
        cls.share_desc = data_utils.rand_name("tempest-share-description")
        cls.share = cls.create_share(
            name=cls.share_name, description=cls.share_desc)

        if CONF.share.run_snapshot_tests:
            # create snapshot
            cls.snap_name = data_utils.rand_name("tempest-snapshot-name")
            cls.snap_desc = data_utils.rand_name(
                "tempest-snapshot-description")
            cls.snap = cls.create_snapshot_wait_for_active(
                cls.share["id"], cls.snap_name, cls.snap_desc)

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    def test_update_share(self):

        # get share
        share = self.shares_client.get_share(self.share['id'])
        self.assertEqual(self.share_name, share["name"])
        self.assertEqual(self.share_desc, share["description"])
        self.assertFalse(share["is_public"])
        is_public = CONF.share.run_public_tests

        # update share
        new_name = data_utils.rand_name("tempest-new-name")
        new_desc = data_utils.rand_name("tempest-new-description")
        updated = self.shares_client.update_share(
            share["id"], new_name, new_desc, is_public=is_public)
        self.assertEqual(new_name, updated["name"])
        self.assertEqual(new_desc, updated["description"])

        self.assertEqual(updated["is_public"], is_public)

        # get share
        share = self.shares_client.get_share(self.share['id'])
        self.assertEqual(new_name, share["name"])
        self.assertEqual(new_desc, share["description"])
        self.assertEqual(share["is_public"], is_public)

    @tc.attr(base.TAG_POSITIVE, base.TAG_API_WITH_BACKEND)
    @testtools.skipUnless(CONF.share.run_snapshot_tests,
                          "Snapshot tests are disabled.")
    def test_rename_snapshot(self):

        # get snapshot
        get = self.shares_client.get_snapshot(self.snap["id"])
        self.assertEqual(self.snap_name, get["name"])
        self.assertEqual(self.snap_desc, get["description"])

        # rename snapshot
        new_name = data_utils.rand_name("tempest-new-name-for-snapshot")
        new_desc = data_utils.rand_name("tempest-new-description-for-snapshot")
        renamed = self.shares_client.rename_snapshot(
            self.snap["id"], new_name, new_desc)
        self.assertEqual(new_name, renamed["name"])
        self.assertEqual(new_desc, renamed["description"])

        # get snapshot
        get = self.shares_client.get_snapshot(self.snap["id"])
        self.assertEqual(new_name, get["name"])
        self.assertEqual(new_desc, get["description"])
