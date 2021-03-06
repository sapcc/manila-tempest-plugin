# Copyright 2015 Andrew Kerr
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

import json
import re
import six
import time

from six.moves.urllib import parse
from tempest import config
from tempest.lib.common.utils import data_utils
from tempest.lib import exceptions

from manila_tempest_tests.common import constants
from manila_tempest_tests.services.share.json import shares_client
from manila_tempest_tests import share_exceptions
from manila_tempest_tests import utils

CONF = config.CONF
LATEST_MICROVERSION = CONF.share.max_api_microversion
EXPERIMENTAL = {'X-OpenStack-Manila-API-Experimental': 'True'}


class SharesV2Client(shares_client.SharesClient):
    """Tempest REST client for Manila.

    It handles shares and access to it in OpenStack.
    """
    api_version = 'v2'

    def __init__(self, auth_provider, **kwargs):
        super(SharesV2Client, self).__init__(auth_provider, **kwargs)
        self.API_MICROVERSIONS_HEADER = 'x-openstack-manila-api-version'

    def inject_microversion_header(self, headers, version,
                                   extra_headers=False):
        """Inject the required manila microversion header."""
        new_headers = self.get_headers()
        new_headers[self.API_MICROVERSIONS_HEADER] = version
        if extra_headers and headers:
            new_headers.update(headers)
        elif headers:
            new_headers = headers
        return new_headers

    def verify_request_id(self, response):
        response_headers = [r.lower() for r in response.keys()]
        assert_msg = ("Response is missing request ID. Response "
                      "headers are: %s") % response
        assert 'x-compute-request-id' in response_headers, assert_msg

    # Overwrite all http verb calls to inject the micro version header
    def post(self, url, body, headers=None, extra_headers=False,
             version=LATEST_MICROVERSION):
        headers = self.inject_microversion_header(headers, version,
                                                  extra_headers=extra_headers)
        resp, body = super(SharesV2Client, self).post(url, body,
                                                      headers=headers)
        self.verify_request_id(resp)
        return resp, body

    def get(self, url, headers=None, extra_headers=False,
            version=LATEST_MICROVERSION):
        headers = self.inject_microversion_header(headers, version,
                                                  extra_headers=extra_headers)
        resp, body = super(SharesV2Client, self).get(url, headers=headers)
        self.verify_request_id(resp)
        return resp, body

    def delete(self, url, headers=None, body=None, extra_headers=False,
               version=LATEST_MICROVERSION):
        headers = self.inject_microversion_header(headers, version,
                                                  extra_headers=extra_headers)
        resp, body = super(SharesV2Client, self).delete(url, headers=headers,
                                                        body=body)
        self.verify_request_id(resp)
        return resp, body

    def patch(self, url, body, headers=None, extra_headers=False,
              version=LATEST_MICROVERSION):
        headers = self.inject_microversion_header(headers, version,
                                                  extra_headers=extra_headers)
        return super(SharesV2Client, self).patch(url, body, headers=headers)

    def put(self, url, body, headers=None, extra_headers=False,
            version=LATEST_MICROVERSION):
        headers = self.inject_microversion_header(headers, version,
                                                  extra_headers=extra_headers)
        resp, body = super(SharesV2Client, self).put(url, body,
                                                     headers=headers)
        self.verify_request_id(resp)
        return resp, body

    def head(self, url, headers=None, extra_headers=False,
             version=LATEST_MICROVERSION):
        headers = self.inject_microversion_header(headers, version,
                                                  extra_headers=extra_headers)
        resp, body = super(SharesV2Client, self).head(url, headers=headers)
        self.verify_request_id(resp)
        return resp, body

    def copy(self, url, headers=None, extra_headers=False,
             version=LATEST_MICROVERSION):
        headers = self.inject_microversion_header(headers, version,
                                                  extra_headers=extra_headers)
        resp, body = super(SharesV2Client, self).copy(url, headers=headers)
        self.verify_request_id(resp)
        return resp, body

    def reset_state(self, s_id, status="error", s_type="shares",
                    headers=None, version=LATEST_MICROVERSION,
                    action_name=None):
        """Resets the state of a share, snapshot, cg, or a cgsnapshot.

        status: available, error, creating, deleting, error_deleting
        s_type: shares, share_instances, snapshots, consistency-groups,
            cgsnapshots.
        """
        if action_name is None:
            if utils.is_microversion_gt(version, "2.6"):
                action_name = 'reset_status'
            else:
                action_name = 'os-reset_status'
        body = {action_name: {"status": status}}
        body = json.dumps(body)
        resp, body = self.post("%s/%s/action" % (s_type, s_id), body,
                               headers=headers, extra_headers=True,
                               version=version)
        self.expected_success(202, resp.status)
        return body

    def force_delete(self, s_id, s_type="shares", headers=None,
                     version=LATEST_MICROVERSION, action_name=None):
        """Force delete share or snapshot.

        s_type: shares, snapshots
        """
        if action_name is None:
            if utils.is_microversion_gt(version, "2.6"):
                action_name = 'force_delete'
            else:
                action_name = 'os-force_delete'
        body = {action_name: None}
        body = json.dumps(body)
        resp, body = self.post("%s/%s/action" % (s_type, s_id), body,
                               headers=headers, extra_headers=True,
                               version=version)
        self.expected_success(202, resp.status)
        return body

    @staticmethod
    def _get_base_url(endpoint):
        url = parse.urlparse(endpoint)
        # Get any valid path components before the version string
        # regex matches version str & everything after (examples: v1, v2, v1.2)
        base_path = re.split(r'(^|/)+v\d+(\.\d+)?', url.path)[0]
        base_url = url._replace(path=base_path)
        return parse.urlunparse(base_url) + '/'

    def send_microversion_request(self, version=None, script_name=None):
        """Prepare and send the HTTP GET Request to the base URL.

        Extracts the base URL from the shares_client endpoint and makes a GET
        request with the microversions request header.
        :param version: The string to send for the value of the microversion
                        header, or None to omit the header.
        :param script_name: The first part of the URL (v1 or v2), or None to
                            omit it.
        """

        headers = self.get_headers()
        url, headers, body = self.auth_provider.auth_request(
            'GET', 'shares', headers, None, self.filters)
        url = self._get_base_url(url)
        if script_name:
            url += script_name + '/'
        if version:
            headers[self.API_MICROVERSIONS_HEADER] = version

        # Handle logging because raw_request doesn't log anything
        start = time.time()
        self._log_request_start('GET', url)
        resp, resp_body = self.raw_request(url, 'GET', headers=headers)
        end = time.time()
        self._log_request(
            'GET', url, resp, secs=(end - start), resp_body=resp_body)
        self.response_checker('GET', resp, resp_body)
        resp_body = json.loads(resp_body)
        return resp, resp_body

    def is_resource_deleted(self, *args, **kwargs):
        """Verifies whether provided resource deleted or not.

        :param kwargs: dict with expected keys 'share_id', 'snapshot_id',
        :param kwargs: 'sn_id', 'ss_id', 'vt_id' and 'server_id'
        :raises share_exceptions.InvalidResource
        """
        if "share_instance_id" in kwargs:
            return self._is_resource_deleted(
                self.get_share_instance, kwargs.get("share_instance_id"))
        elif "share_group_id" in kwargs:
            return self._is_resource_deleted(
                self.get_share_group, kwargs.get("share_group_id"))
        elif "share_group_snapshot_id" in kwargs:
            return self._is_resource_deleted(
                self.get_share_group_snapshot,
                kwargs.get("share_group_snapshot_id"))
        elif "share_group_type_id" in kwargs:
            return self._is_resource_deleted(
                self.get_share_group_type, kwargs.get("share_group_type_id"))
        elif "replica_id" in kwargs:
            return self._is_resource_deleted(
                self.get_share_replica, kwargs.get("replica_id"))
        elif "message_id" in kwargs:
            return self._is_resource_deleted(
                self.get_message, kwargs.get("message_id"))
        else:
            return super(SharesV2Client, self).is_resource_deleted(
                *args, **kwargs)

###############

    def create_share(self, share_protocol=None, size=None,
                     name=None, snapshot_id=None, description=None,
                     metadata=None, share_network_id=None,
                     share_type_id=None, is_public=False,
                     share_group_id=None, availability_zone=None,
                     version=LATEST_MICROVERSION, experimental=False):
        headers = EXPERIMENTAL if experimental else None
        metadata = metadata or {}
        if name is None:
            name = data_utils.rand_name("tempest-created-share")
        if description is None:
            description = data_utils.rand_name("tempest-created-share-desc")
        if size is None:
            size = self.share_size
        if share_protocol is None:
            share_protocol = self.share_protocol
        if share_protocol is None:
            raise share_exceptions.ShareProtocolNotSpecified()
        post_body = {
            "share": {
                "share_proto": share_protocol,
                "description": description,
                "snapshot_id": snapshot_id,
                "name": name,
                "size": size,
                "metadata": metadata,
                "is_public": is_public,
            }
        }
        if availability_zone:
            post_body["share"]["availability_zone"] = availability_zone
        if share_network_id:
            post_body["share"]["share_network_id"] = share_network_id
        if share_type_id:
            post_body["share"]["share_type"] = share_type_id
        if share_group_id:
            post_body["share"]["share_group_id"] = share_group_id
        body = json.dumps(post_body)
        resp, body = self.post("shares", body, headers=headers,
                               extra_headers=experimental, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def list_shares(self, detailed=False, params=None,
                    version=LATEST_MICROVERSION, experimental=False):
        """Get list of shares w/o filters."""
        headers = EXPERIMENTAL if experimental else None
        uri = 'shares/detail' if detailed else 'shares'
        uri += '?%s' % parse.urlencode(params) if params else ''
        resp, body = self.get(uri, headers=headers, extra_headers=experimental,
                              version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def list_shares_with_detail(self, params=None,
                                version=LATEST_MICROVERSION,
                                experimental=False):
        """Get detailed list of shares w/o filters."""
        return self.list_shares(detailed=True, params=params,
                                version=version, experimental=experimental)

    def get_share(self, share_id, version=LATEST_MICROVERSION,
                  experimental=False):
        headers = EXPERIMENTAL if experimental else None
        resp, body = self.get("shares/%s" % share_id, headers=headers,
                              extra_headers=experimental, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def get_share_export_location(
            self, share_id, export_location_uuid, version=LATEST_MICROVERSION):
        resp, body = self.get(
            "shares/%(share_id)s/export_locations/%(el_uuid)s" % {
                "share_id": share_id, "el_uuid": export_location_uuid},
            version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def list_share_export_locations(
            self, share_id, version=LATEST_MICROVERSION):
        resp, body = self.get(
            "shares/%(share_id)s/export_locations" % {"share_id": share_id},
            version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def delete_share(self, share_id, params=None,
                     version=LATEST_MICROVERSION):
        uri = "shares/%s" % share_id
        uri += '?%s' % (parse.urlencode(params) if params else '')
        resp, body = self.delete(uri, version=version)
        self.expected_success(202, resp.status)
        return body

###############

    def get_instances_of_share(self, share_id, version=LATEST_MICROVERSION):
        resp, body = self.get("shares/%s/instances" % share_id,
                              version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def list_share_instances(self, version=LATEST_MICROVERSION,
                             params=None):
        uri = 'share_instances'
        uri += '?%s' % parse.urlencode(params) if params else ''
        resp, body = self.get(uri, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def get_share_instance(self, instance_id, version=LATEST_MICROVERSION):
        resp, body = self.get("share_instances/%s" % instance_id,
                              version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def get_share_instance_export_location(
            self, instance_id, export_location_uuid,
            version=LATEST_MICROVERSION):
        resp, body = self.get(
            "share_instances/%(instance_id)s/export_locations/%(el_uuid)s" % {
                "instance_id": instance_id, "el_uuid": export_location_uuid},
            version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def list_share_instance_export_locations(
            self, instance_id, version=LATEST_MICROVERSION):
        resp, body = self.get(
            "share_instances/%s/export_locations" % instance_id,
            version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def wait_for_share_instance_status(self, instance_id, status,
                                       version=LATEST_MICROVERSION):
        """Waits for a share to reach a given status."""
        body = self.get_share_instance(instance_id, version=version)
        instance_status = body['status']
        start = int(time.time())

        while instance_status != status:
            time.sleep(self.build_interval)
            body = self.get_share(instance_id)
            instance_status = body['status']
            if instance_status == status:
                return
            elif 'error' in instance_status.lower():
                raise share_exceptions.ShareInstanceBuildErrorException(
                    id=instance_id)

            if int(time.time()) - start >= self.build_timeout:
                message = ('Share instance %s failed to reach %s status within'
                           ' the required time (%s s).' %
                           (instance_id, status, self.build_timeout))
                raise exceptions.TimeoutException(message)

    def wait_for_share_status(self, share_id, status, status_attr='status',
                              version=LATEST_MICROVERSION):
        """Waits for a share to reach a given status."""
        body = self.get_share(share_id, version=version)
        share_status = body[status_attr]
        start = int(time.time())

        while share_status != status:
            time.sleep(self.build_interval)
            body = self.get_share(share_id, version=version)
            share_status = body[status_attr]
            if share_status == status:
                return
            elif 'error' in share_status.lower():
                raise share_exceptions.ShareBuildErrorException(
                    share_id=share_id)

            if int(time.time()) - start >= self.build_timeout:
                message = ("Share's %(status_attr)s failed to transition to "
                           "%(status)s within the required time %(seconds)s." %
                           {"status_attr": status_attr, "status": status,
                            "seconds": self.build_timeout})
                raise exceptions.TimeoutException(message)

###############

    def extend_share(self, share_id, new_size, version=LATEST_MICROVERSION,
                     action_name=None):
        if action_name is None:
            if utils.is_microversion_gt(version, "2.6"):
                action_name = 'extend'
            else:
                action_name = 'os-extend'
        post_body = {
            action_name: {
                "new_size": new_size,
            }
        }
        body = json.dumps(post_body)
        resp, body = self.post(
            "shares/%s/action" % share_id, body, version=version)
        self.expected_success(202, resp.status)
        return body

    def shrink_share(self, share_id, new_size, version=LATEST_MICROVERSION,
                     action_name=None):
        if action_name is None:
            if utils.is_microversion_gt(version, "2.6"):
                action_name = 'shrink'
            else:
                action_name = 'os-shrink'
        post_body = {
            action_name: {
                "new_size": new_size,
            }
        }
        body = json.dumps(post_body)
        resp, body = self.post(
            "shares/%s/action" % share_id, body, version=version)
        self.expected_success(202, resp.status)
        return body

###############

    def manage_share(self, service_host, protocol, export_path,
                     share_type_id, name=None, description=None,
                     is_public=False, version=LATEST_MICROVERSION,
                     url=None, share_server_id=None):
        post_body = {
            "share": {
                "export_path": export_path,
                "service_host": service_host,
                "protocol": protocol,
                "share_type": share_type_id,
                "name": name,
                "description": description,
                "is_public": is_public,
            }
        }
        if share_server_id is not None:
            post_body['share']['share_server_id'] = share_server_id
        if url is None:
            if utils.is_microversion_gt(version, "2.6"):
                url = 'shares/manage'
            else:
                url = 'os-share-manage'
        body = json.dumps(post_body)
        resp, body = self.post(url, body, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def unmanage_share(self, share_id, version=LATEST_MICROVERSION, url=None,
                       action_name=None, body=None):
        if url is None:
            if utils.is_microversion_gt(version, "2.6"):
                url = 'shares'
            else:
                url = 'os-share-unmanage'
        if action_name is None:
            if utils.is_microversion_gt(version, "2.6"):
                action_name = 'action'
            else:
                action_name = 'unmanage'
        if body is None and utils.is_microversion_gt(version, "2.6"):
            body = json.dumps({'unmanage': {}})
        resp, body = self.post(
            "%(url)s/%(share_id)s/%(action_name)s" % {
                'url': url, 'share_id': share_id, 'action_name': action_name},
            body,
            version=version)
        self.expected_success(202, resp.status)
        return body

###############

    def create_snapshot(self, share_id, name=None, description=None,
                        force=False, version=LATEST_MICROVERSION):
        if name is None:
            name = data_utils.rand_name("tempest-created-share-snap")
        if description is None:
            description = data_utils.rand_name(
                "tempest-created-share-snap-desc")
        post_body = {
            "snapshot": {
                "name": name,
                "force": force,
                "description": description,
                "share_id": share_id,
            }
        }
        body = json.dumps(post_body)
        resp, body = self.post("snapshots", body, version=version)
        self.expected_success(202, resp.status)
        return self._parse_resp(body)

    def get_snapshot(self, snapshot_id, version=LATEST_MICROVERSION):
        resp, body = self.get("snapshots/%s" % snapshot_id, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def list_snapshots(self, detailed=False, params=None,
                       version=LATEST_MICROVERSION):
        """Get list of share snapshots w/o filters."""
        uri = 'snapshots/detail' if detailed else 'snapshots'
        uri += '?%s' % parse.urlencode(params) if params else ''
        resp, body = self.get(uri, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def list_snapshots_for_share(self, share_id, detailed=False,
                                 version=LATEST_MICROVERSION):
        """Get list of snapshots for given share."""
        uri = ('snapshots/detail?share_id=%s' % share_id
               if detailed else 'snapshots?share_id=%s' % share_id)
        resp, body = self.get(uri, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def list_snapshots_with_detail(self, params=None,
                                   version=LATEST_MICROVERSION):
        """Get detailed list of share snapshots w/o filters."""
        return self.list_snapshots(detailed=True, params=params,
                                   version=version)

    def delete_snapshot(self, snap_id, version=LATEST_MICROVERSION):
        resp, body = self.delete("snapshots/%s" % snap_id, version=version)
        self.expected_success(202, resp.status)
        return body

    def wait_for_snapshot_status(self, snapshot_id, status,
                                 version=LATEST_MICROVERSION):
        """Waits for a snapshot to reach a given status."""
        body = self.get_snapshot(snapshot_id, version=version)
        snapshot_name = body['name']
        snapshot_status = body['status']
        start = int(time.time())

        while snapshot_status != status:
            time.sleep(self.build_interval)
            body = self.get_snapshot(snapshot_id, version=version)
            snapshot_status = body['status']
            if snapshot_status == status:
                return
            if 'error' in snapshot_status:
                raise (share_exceptions.
                       SnapshotBuildErrorException(snapshot_id=snapshot_id))

            if int(time.time()) - start >= self.build_timeout:
                message = ('Share Snapshot %s failed to reach %s status '
                           'within the required time (%s s).' %
                           (snapshot_name, status, self.build_timeout))
                raise exceptions.TimeoutException(message)

    def manage_snapshot(self, share_id, provider_location,
                        name=None, description=None,
                        version=LATEST_MICROVERSION,
                        driver_options=None):
        if name is None:
            name = data_utils.rand_name("tempest-manage-snapshot")
        if description is None:
            description = data_utils.rand_name("tempest-manage-snapshot-desc")
        post_body = {
            "snapshot": {
                "share_id": share_id,
                "provider_location": provider_location,
                "name": name,
                "description": description,
                "driver_options": driver_options if driver_options else {},
            }
        }
        url = 'snapshots/manage'
        body = json.dumps(post_body)
        resp, body = self.post(url, body, version=version)
        self.expected_success(202, resp.status)
        return self._parse_resp(body)

    def unmanage_snapshot(self, snapshot_id, version=LATEST_MICROVERSION,
                          body=None):
        url = 'snapshots'
        action_name = 'action'
        if body is None:
            body = json.dumps({'unmanage': {}})
        resp, body = self.post(
            "%(url)s/%(snapshot_id)s/%(action_name)s" % {
                'url': url, 'snapshot_id': snapshot_id,
                'action_name': action_name},
            body,
            version=version)
        self.expected_success(202, resp.status)
        return body

    def snapshot_reset_state(self, snapshot_id,
                             status=constants.STATUS_AVAILABLE,
                             version=LATEST_MICROVERSION):
        self.reset_state(snapshot_id, status=status, s_type='snapshots',
                         version=version)

###############

    def revert_to_snapshot(self, share_id, snapshot_id,
                           version=LATEST_MICROVERSION):
        url = 'shares/%s/action' % share_id
        body = json.dumps({'revert': {'snapshot_id': snapshot_id}})
        resp, body = self.post(url, body, version=version)
        self.expected_success(202, resp.status)
        return self._parse_resp(body)

###############

    def create_share_type_extra_specs(self, share_type_id, extra_specs,
                                      version=LATEST_MICROVERSION):
        url = "types/%s/extra_specs" % share_type_id
        post_body = json.dumps({'extra_specs': extra_specs})
        resp, body = self.post(url, post_body, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def get_share_type_extra_spec(self, share_type_id, extra_spec_name,
                                  version=LATEST_MICROVERSION):
        uri = "types/%s/extra_specs/%s" % (share_type_id, extra_spec_name)
        resp, body = self.get(uri, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def get_share_type_extra_specs(self, share_type_id, params=None,
                                   version=LATEST_MICROVERSION):
        uri = "types/%s/extra_specs" % share_type_id
        if params is not None:
            uri += '?%s' % parse.urlencode(params)
        resp, body = self.get(uri, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def update_share_type_extra_spec(self, share_type_id, spec_name,
                                     spec_value, version=LATEST_MICROVERSION):
        uri = "types/%s/extra_specs/%s" % (share_type_id, spec_name)
        extra_spec = {spec_name: spec_value}
        post_body = json.dumps(extra_spec)
        resp, body = self.put(uri, post_body, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def update_share_type_extra_specs(self, share_type_id, extra_specs,
                                      version=LATEST_MICROVERSION):
        uri = "types/%s/extra_specs" % share_type_id
        extra_specs = {"extra_specs": extra_specs}
        post_body = json.dumps(extra_specs)
        resp, body = self.post(uri, post_body, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def delete_share_type_extra_spec(self, share_type_id, extra_spec_name,
                                     version=LATEST_MICROVERSION):
        uri = "types/%s/extra_specs/%s" % (share_type_id, extra_spec_name)
        resp, body = self.delete(uri, version=version)
        self.expected_success(202, resp.status)
        return body

###############

    def get_snapshot_instance(self, instance_id, version=LATEST_MICROVERSION):
        resp, body = self.get("snapshot-instances/%s" % instance_id,
                              version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def list_snapshot_instances(self, detail=False, snapshot_id=None,
                                version=LATEST_MICROVERSION):
        """Get list of share snapshot instances."""
        uri = "snapshot-instances%s" % ('/detail' if detail else '')
        if snapshot_id is not None:
            uri += '?snapshot_id=%s' % snapshot_id
        resp, body = self.get(uri, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def reset_snapshot_instance_status(self, instance_id,
                                       status=constants.STATUS_AVAILABLE,
                                       version=LATEST_MICROVERSION):
        """Reset the status."""
        uri = 'snapshot-instances/%s/action' % instance_id
        post_body = {
            'reset_status': {
                'status': status
            }
        }
        body = json.dumps(post_body)
        resp, body = self.post(uri, body, extra_headers=True, version=version)
        self.expected_success(202, resp.status)
        return self._parse_resp(body)

    def wait_for_snapshot_instance_status(self, instance_id, expected_status):
        """Waits for a snapshot instance status to reach a given status."""
        body = self.get_snapshot_instance(instance_id)
        instance_status = body['status']
        start = int(time.time())

        while instance_status != expected_status:
            time.sleep(self.build_interval)
            body = self.get_snapshot_instance(instance_id)
            instance_status = body['status']
            if instance_status == expected_status:
                return
            if 'error' in instance_status:
                raise share_exceptions.SnapshotInstanceBuildErrorException(
                    id=instance_id)

            if int(time.time()) - start >= self.build_timeout:
                message = ('The status of snapshot instance %(id)s failed to '
                           'reach %(expected_status)s status within the '
                           'required time (%(time)ss). Current '
                           'status: %(current_status)s.' %
                           {
                               'expected_status': expected_status,
                               'time': self.build_timeout,
                               'id': instance_id,
                               'current_status': instance_status,
                           })
                raise exceptions.TimeoutException(message)

    def get_snapshot_instance_export_location(
            self, instance_id, export_location_uuid,
            version=LATEST_MICROVERSION):
        resp, body = self.get(
            "snapshot-instances/%(instance_id)s/export-locations/%("
            "el_uuid)s" % {
                "instance_id": instance_id,
                "el_uuid": export_location_uuid},
            version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def list_snapshot_instance_export_locations(
            self, instance_id, version=LATEST_MICROVERSION):
        resp, body = self.get(
            "snapshot-instances/%s/export-locations" % instance_id,
            version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

###############

    def _get_access_action_name(self, version, action):
        if utils.is_microversion_gt(version, "2.6"):
            return action.split('os-')[-1]
        return action

    def create_access_rule(self, share_id, access_type="ip",
                           access_to="0.0.0.0", access_level=None,
                           version=LATEST_MICROVERSION, metadata=None,
                           action_name=None):
        post_body = {
            self._get_access_action_name(version, 'os-allow_access'): {
                "access_type": access_type,
                "access_to": access_to,
                "access_level": access_level,
            }
        }
        if metadata is not None:
            post_body['allow_access']['metadata'] = metadata
        body = json.dumps(post_body)
        resp, body = self.post(
            "shares/%s/action" % share_id, body, version=version,
            extra_headers=True)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def list_access_rules(self, share_id, version=LATEST_MICROVERSION,
                          metadata=None, action_name=None):
        if utils.is_microversion_lt(version, "2.45"):
            body = {
                self._get_access_action_name(version, 'os-access_list'): None
            }
            resp, body = self.post(
                "shares/%s/action" % share_id, json.dumps(body),
                version=version)
            self.expected_success(200, resp.status)
        else:
            return self.list_access_rules_with_new_API(
                share_id, metadata=metadata, version=version,
                action_name=action_name)
        return self._parse_resp(body)

    def list_access_rules_with_new_API(self, share_id, metadata=None,
                                       version=LATEST_MICROVERSION,
                                       action_name=None):
        metadata = metadata or {}
        query_string = ''

        params = sorted(
            [(k, v) for (k, v) in list(metadata.items()) if v])
        if params:
            query_string = "&%s" % parse.urlencode(params)

        url = 'share-access-rules?share_id=%s' % share_id + query_string
        resp, body = self.get(url, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def delete_access_rule(self, share_id, rule_id,
                           version=LATEST_MICROVERSION, action_name=None):
        post_body = {
            self._get_access_action_name(version, 'os-deny_access'): {
                "access_id": rule_id,
            }
        }
        body = json.dumps(post_body)
        resp, body = self.post(
            "shares/%s/action" % share_id, body, version=version)
        self.expected_success(202, resp.status)
        return body

    def get_access(self, access_id, version=LATEST_MICROVERSION):
        resp, body = self.get("share-access-rules/%s" % access_id,
                              version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def update_access_metadata(self, access_id, metadata,
                               version=LATEST_MICROVERSION):
        url = 'share-access-rules/%s/metadata' % access_id
        body = {"metadata": metadata}
        resp, body = self.put(url, json.dumps(body), version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def delete_access_metadata(self, access_id, key,
                               version=LATEST_MICROVERSION):
        url = "share-access-rules/%s/metadata/%s" % (access_id, key)
        resp, body = self.delete(url, version=version)
        self.expected_success(200, resp.status)
        return body


###############

    def list_availability_zones(self, url='availability-zones',
                                version=LATEST_MICROVERSION):
        """Get list of availability zones."""
        if url is None:
            if utils.is_microversion_gt(version, "2.6"):
                url = 'availability-zones'
            else:
                url = 'os-availability-zone'
        resp, body = self.get(url, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

###############

    def list_services(self, params=None, url=None,
                      version=LATEST_MICROVERSION):
        """List services."""
        if url is None:
            if utils.is_microversion_gt(version, "2.6"):
                url = 'services'
            else:
                url = 'os-services'
        if params:
            url += '?%s' % parse.urlencode(params)
        resp, body = self.get(url, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

###############

    def list_share_types(self, params=None, default=False,
                         version=LATEST_MICROVERSION):
        uri = 'types'
        if default:
            uri += '/default'
        if params is not None:
            uri += '?%s' % parse.urlencode(params)
        resp, body = self.get(uri, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def create_share_type(self, name, is_public=True,
                          version=LATEST_MICROVERSION, **kwargs):
        if utils.is_microversion_gt(version, "2.6"):
            is_public_keyname = 'share_type_access:is_public'
        else:
            is_public_keyname = 'os-share-type-access:is_public'
        post_body = {
            'name': name,
            'extra_specs': kwargs.get('extra_specs'),
            is_public_keyname: is_public,
        }
        if kwargs.get('description'):
            post_body['description'] = kwargs.get('description')
        post_body = json.dumps({'share_type': post_body})
        resp, body = self.post('types', post_body, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def delete_share_type(self, share_type_id, version=LATEST_MICROVERSION):
        resp, body = self.delete("types/%s" % share_type_id, version=version)
        self.expected_success(202, resp.status)
        return body

    def get_share_type(self, share_type_id, version=LATEST_MICROVERSION):
        resp, body = self.get("types/%s" % share_type_id, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def list_access_to_share_type(self, share_type_id,
                                  version=LATEST_MICROVERSION,
                                  action_name=None):
        if action_name is None:
            if utils.is_microversion_gt(version, "2.6"):
                action_name = 'share_type_access'
            else:
                action_name = 'os-share-type-access'
        url = 'types/%(st_id)s/%(action_name)s' % {
            'st_id': share_type_id, 'action_name': action_name}
        resp, body = self.get(url, version=version)
        # [{"share_type_id": "%st_id%", "project_id": "%project_id%"}, ]
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

###############

    @staticmethod
    def _get_quotas_url(version):
        if utils.is_microversion_gt(version, "2.6"):
            return 'quota-sets'
        return 'os-quota-sets'

    @staticmethod
    def _get_quotas_url_arguments_as_str(user_id=None, share_type=None):
        args_str = ''
        if not (user_id is None or share_type is None):
            args_str = "?user_id=%s&share_type=%s" % (user_id, share_type)
        elif user_id is not None:
            args_str = "?user_id=%s" % user_id
        elif share_type is not None:
            args_str = "?share_type=%s" % share_type
        return args_str

    def default_quotas(self, tenant_id, url=None, version=LATEST_MICROVERSION):
        if url is None:
            url = self._get_quotas_url(version)
        url += '/%s' % tenant_id
        resp, body = self.get("%s/defaults" % url, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def show_quotas(self, tenant_id, user_id=None, share_type=None, url=None,
                    version=LATEST_MICROVERSION):
        if url is None:
            url = self._get_quotas_url(version)
        url += '/%s' % tenant_id
        url += self._get_quotas_url_arguments_as_str(user_id, share_type)
        resp, body = self.get(url, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def reset_quotas(self, tenant_id, user_id=None, share_type=None, url=None,
                     version=LATEST_MICROVERSION):
        if url is None:
            url = self._get_quotas_url(version)
        url += '/%s' % tenant_id
        url += self._get_quotas_url_arguments_as_str(user_id, share_type)
        resp, body = self.delete(url, version=version)
        self.expected_success(202, resp.status)
        return body

    def detail_quotas(self, tenant_id, user_id=None, share_type=None, url=None,
                      version=LATEST_MICROVERSION):
        if url is None:
            url = self._get_quotas_url(version)
        url += '/%s/detail' % tenant_id
        url += self._get_quotas_url_arguments_as_str(user_id, share_type)
        resp, body = self.get(url, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def update_quotas(self, tenant_id, user_id=None, shares=None,
                      snapshots=None, gigabytes=None, snapshot_gigabytes=None,
                      share_networks=None,
                      share_groups=None, share_group_snapshots=None,
                      force=True, share_type=None,
                      url=None, version=LATEST_MICROVERSION):
        if url is None:
            url = self._get_quotas_url(version)
        url += '/%s' % tenant_id
        url += self._get_quotas_url_arguments_as_str(user_id, share_type)

        put_body = {"tenant_id": tenant_id}
        if force:
            put_body["force"] = "true"
        if shares is not None:
            put_body["shares"] = shares
        if snapshots is not None:
            put_body["snapshots"] = snapshots
        if gigabytes is not None:
            put_body["gigabytes"] = gigabytes
        if snapshot_gigabytes is not None:
            put_body["snapshot_gigabytes"] = snapshot_gigabytes
        if share_networks is not None:
            put_body["share_networks"] = share_networks
        if share_groups is not None:
            put_body["share_groups"] = share_groups
        if share_group_snapshots is not None:
            put_body["share_group_snapshots"] = share_group_snapshots
        put_body = json.dumps({"quota_set": put_body})

        resp, body = self.put(url, put_body, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

###############

    def create_share_group(self, name=None, description=None,
                           share_group_type_id=None, share_type_ids=(),
                           share_network_id=None,
                           source_share_group_snapshot_id=None,
                           availability_zone=None,
                           version=LATEST_MICROVERSION):
        """Create a new share group."""
        uri = 'share-groups'
        post_body = {}
        if name:
            post_body['name'] = name
        if description:
            post_body['description'] = description
        if share_group_type_id:
            post_body['share_group_type_id'] = share_group_type_id
        if share_type_ids:
            post_body['share_types'] = share_type_ids
        if source_share_group_snapshot_id:
            post_body['source_share_group_snapshot_id'] = (
                source_share_group_snapshot_id)
        if share_network_id:
            post_body['share_network_id'] = share_network_id
        if availability_zone:
            post_body['availability_zone'] = availability_zone
        body = json.dumps({'share_group': post_body})

        resp, body = self.post(uri, body, headers=EXPERIMENTAL,
                               extra_headers=True, version=version)

        self.expected_success(202, resp.status)
        return self._parse_resp(body)

    def delete_share_group(self, share_group_id, version=LATEST_MICROVERSION):
        """Delete a share group."""
        uri = 'share-groups/%s' % share_group_id
        resp, body = self.delete(uri, headers=EXPERIMENTAL,
                                 extra_headers=True, version=version)
        self.expected_success(202, resp.status)
        return self._parse_resp(body)

    def list_share_groups(self, detailed=False, params=None,
                          version=LATEST_MICROVERSION):
        """Get list of share groups w/o filters."""
        uri = 'share-groups%s' % ('/detail' if detailed else '')
        uri += '?%s' % (parse.urlencode(params) if params else '')
        resp, body = self.get(uri, headers=EXPERIMENTAL, extra_headers=True,
                              version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def get_share_group(self, share_group_id, version=LATEST_MICROVERSION):
        """Get share group info."""
        uri = 'share-groups/%s' % share_group_id
        resp, body = self.get(uri, headers=EXPERIMENTAL, extra_headers=True,
                              version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def update_share_group(self, share_group_id, name=None, description=None,
                           version=LATEST_MICROVERSION, **kwargs):
        """Update an existing share group."""
        uri = 'share-groups/%s' % share_group_id
        post_body = {}
        if name:
            post_body['name'] = name
        if description:
            post_body['description'] = description
        if kwargs:
            post_body.update(kwargs)
        body = json.dumps({'share_group': post_body})

        resp, body = self.put(uri, body, headers=EXPERIMENTAL,
                              extra_headers=True, version=version)

        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def share_group_reset_state(self, share_group_id, status='error',
                                version=LATEST_MICROVERSION):
        self.reset_state(share_group_id, status=status, s_type='groups',
                         headers=EXPERIMENTAL, version=version)

    def share_group_force_delete(self, share_group_id,
                                 version=LATEST_MICROVERSION):
        self.force_delete(share_group_id, s_type='share-groups',
                          headers=EXPERIMENTAL, version=version)

    def wait_for_share_group_status(self, share_group_id, status):
        """Waits for a share group to reach a given status."""
        body = self.get_share_group(share_group_id)
        sg_name = body['name']
        sg_status = body['status']
        start = int(time.time())

        while sg_status != status:
            time.sleep(self.build_interval)
            body = self.get_share_group(share_group_id)
            sg_status = body['status']
            if 'error' in sg_status and status != 'error':
                raise share_exceptions.ShareGroupBuildErrorException(
                    share_group_id=share_group_id)

            if int(time.time()) - start >= self.build_timeout:
                sg_name = sg_name or share_group_id
                message = ('Share Group %s failed to reach %s status '
                           'within the required time (%s s). '
                           'Current status: %s' %
                           (sg_name, status, self.build_timeout, sg_status))
                raise exceptions.TimeoutException(message)

###############

    def create_share_group_type(self, name=None, share_types=(),
                                is_public=None, group_specs=None,
                                version=LATEST_MICROVERSION):
        """Create a new share group type."""
        uri = 'share-group-types'
        post_body = {}
        if isinstance(share_types, (tuple, list)):
            share_types = list(share_types)
        else:
            share_types = [share_types]
        if name is not None:
            post_body['name'] = name
        if share_types:
            post_body['share_types'] = share_types
        if is_public is not None:
            post_body['is_public'] = is_public
        if group_specs:
            post_body['group_specs'] = group_specs
        body = json.dumps({'share_group_type': post_body})
        resp, body = self.post(uri, body, headers=EXPERIMENTAL,
                               extra_headers=True, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def list_share_group_types(self, detailed=False, params=None,
                               version=LATEST_MICROVERSION):
        """Get list of share group types."""
        uri = 'share-group-types%s' % ('/detail' if detailed else '')
        uri += '?%s' % (parse.urlencode(params) if params else '')
        resp, body = self.get(uri, headers=EXPERIMENTAL, extra_headers=True,
                              version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def get_share_group_type(self, share_group_type_id,
                             version=LATEST_MICROVERSION):
        """Get share group type info."""
        uri = 'share-group-types/%s' % share_group_type_id
        resp, body = self.get(uri, headers=EXPERIMENTAL, extra_headers=True,
                              version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def get_default_share_group_type(self, version=LATEST_MICROVERSION):
        """Get default share group type info."""
        uri = 'share-group-types/default'
        resp, body = self.get(uri, headers=EXPERIMENTAL, extra_headers=True,
                              version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def delete_share_group_type(self, share_group_type_id,
                                version=LATEST_MICROVERSION):
        """Delete an existing share group type."""
        uri = 'share-group-types/%s' % share_group_type_id
        resp, body = self.delete(uri, headers=EXPERIMENTAL,
                                 extra_headers=True, version=version)
        self.expected_success(204, resp.status)
        return self._parse_resp(body)

    def add_access_to_share_group_type(self, share_group_type_id, project_id,
                                       version=LATEST_MICROVERSION):
        uri = 'share-group-types/%s/action' % share_group_type_id
        post_body = {'project': project_id}
        post_body = json.dumps({'addProjectAccess': post_body})
        resp, body = self.post(uri, post_body, headers=EXPERIMENTAL,
                               extra_headers=True, version=version)
        self.expected_success(202, resp.status)
        return self._parse_resp(body)

    def remove_access_from_share_group_type(self, share_group_type_id,
                                            project_id,
                                            version=LATEST_MICROVERSION):
        uri = 'share-group-types/%s/action' % share_group_type_id
        post_body = {'project': project_id}
        post_body = json.dumps({'removeProjectAccess': post_body})
        resp, body = self.post(uri, post_body, headers=EXPERIMENTAL,
                               extra_headers=True, version=version)
        self.expected_success(202, resp.status)
        return self._parse_resp(body)

    def list_access_to_share_group_type(self, share_group_type_id,
                                        version=LATEST_MICROVERSION):
        uri = 'share-group-types/%s/access' % share_group_type_id
        resp, body = self.get(uri, headers=EXPERIMENTAL, extra_headers=True,
                              version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

###############

    def create_share_group_type_specs(self, share_group_type_id,
                                      group_specs_dict,
                                      version=LATEST_MICROVERSION):
        url = "share-group-types/%s/group-specs" % share_group_type_id
        post_body = json.dumps({'group_specs': group_specs_dict})
        resp, body = self.post(url, post_body, headers=EXPERIMENTAL,
                               extra_headers=True, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def get_share_group_type_spec(self, share_group_type_id, group_spec_key,
                                  version=LATEST_MICROVERSION):
        uri = "group-types/%s/group_specs/%s" % (
            share_group_type_id, group_spec_key)
        resp, body = self.get(uri, headers=EXPERIMENTAL, extra_headers=True,
                              version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def list_share_group_type_specs(self, share_group_type_id, params=None,
                                    version=LATEST_MICROVERSION):
        uri = "share-group-types/%s/group_specs" % share_group_type_id
        if params is not None:
            uri += '?%s' % parse.urlencode(params)
        resp, body = self.get(uri, headers=EXPERIMENTAL, extra_headers=True,
                              version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def update_share_group_type_spec(self, share_group_type_id, group_spec_key,
                                     group_spec_value,
                                     version=LATEST_MICROVERSION):
        uri = "share-group-types/%s/group-specs/%s" % (
            share_group_type_id, group_spec_key)
        group_spec = {group_spec_key: group_spec_value}
        post_body = json.dumps(group_spec)
        resp, body = self.put(uri, post_body, headers=EXPERIMENTAL,
                              extra_headers=True, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def update_share_group_type_specs(self, share_group_type_id,
                                      group_specs_dict,
                                      version=LATEST_MICROVERSION):
        return self.create_share_group_type_specs(
            share_group_type_id, group_specs_dict, version=version)

    def delete_share_group_type_spec(self, share_type_id, group_spec_key,
                                     version=LATEST_MICROVERSION):
        uri = "share-group-types/%s/group-specs/%s" % (
            share_type_id, group_spec_key)
        resp, body = self.delete(uri, headers=EXPERIMENTAL, extra_headers=True,
                                 version=version)
        self.expected_success(204, resp.status)
        return body

###############

    def create_share_group_snapshot(self, share_group_id, name=None,
                                    description=None,
                                    version=LATEST_MICROVERSION):
        """Create a new share group snapshot of an existing share group."""
        uri = 'share-group-snapshots'
        post_body = {'share_group_id': share_group_id}
        if name:
            post_body['name'] = name
        if description:
            post_body['description'] = description
        body = json.dumps({'share_group_snapshot': post_body})
        resp, body = self.post(uri, body, headers=EXPERIMENTAL,
                               extra_headers=True, version=version)
        self.expected_success(202, resp.status)
        return self._parse_resp(body)

    def delete_share_group_snapshot(self, share_group_snapshot_id,
                                    version=LATEST_MICROVERSION):
        """Delete an existing share group snapshot."""
        uri = 'share-group-snapshots/%s' % share_group_snapshot_id
        resp, body = self.delete(uri, headers=EXPERIMENTAL,
                                 extra_headers=True, version=version)
        self.expected_success(202, resp.status)
        return body

    def list_share_group_snapshots(self, detailed=False, params=None,
                                   version=LATEST_MICROVERSION):
        """Get list of share group snapshots w/o filters."""
        uri = 'share-group-snapshots%s' % ('/detail' if detailed else '')
        uri += '?%s' % (parse.urlencode(params) if params else '')
        resp, body = self.get(uri, headers=EXPERIMENTAL, extra_headers=True,
                              version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def get_share_group_snapshot(self, share_group_snapshot_id,
                                 version=LATEST_MICROVERSION):
        """Get share group snapshot info."""
        uri = 'share-group-snapshots/%s' % share_group_snapshot_id
        resp, body = self.get(uri, headers=EXPERIMENTAL, extra_headers=True,
                              version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def update_share_group_snapshot(self, share_group_snapshot_id, name=None,
                                    description=None,
                                    version=LATEST_MICROVERSION):
        """Update an existing share group snapshot."""
        uri = 'share-group-snapshots/%s' % share_group_snapshot_id
        post_body = {}
        if name:
            post_body['name'] = name
        if description:
            post_body['description'] = description
        body = json.dumps({'share_group_snapshot': post_body})
        resp, body = self.put(uri, body, headers=EXPERIMENTAL,
                              extra_headers=True, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def share_group_snapshot_reset_state(self, share_group_snapshot_id,
                                         status='error',
                                         version=LATEST_MICROVERSION):
        self.reset_state(
            share_group_snapshot_id, status=status,
            s_type='group-snapshots', headers=EXPERIMENTAL, version=version)

    def share_group_snapshot_force_delete(self, share_group_snapshot_id,
                                          version=LATEST_MICROVERSION):
        self.force_delete(
            share_group_snapshot_id, s_type='share-group-snapshots',
            headers=EXPERIMENTAL, version=version)

    def wait_for_share_group_snapshot_status(self, share_group_snapshot_id,
                                             status):
        """Waits for a share group snapshot to reach a given status."""
        body = self.get_share_group_snapshot(share_group_snapshot_id)
        sg_snapshot_name = body['name']
        sg_snapshot_status = body['status']
        start = int(time.time())

        while sg_snapshot_status != status:
            time.sleep(self.build_interval)
            body = self.get_share_group_snapshot(share_group_snapshot_id)
            sg_snapshot_status = body['status']
            if 'error' in sg_snapshot_status and status != 'error':
                raise share_exceptions.ShareGroupSnapshotBuildErrorException(
                    share_group_snapshot_id=share_group_snapshot_id)

            if int(time.time()) - start >= self.build_timeout:
                message = ('Share Group Snapshot %s failed to reach %s status '
                           'within the required time (%s s).' %
                           (sg_snapshot_name, status, self.build_timeout))
                raise exceptions.TimeoutException(message)

###############

    def manage_share_server(self, host, share_network_id, identifier,
                            driver_options=None, version=LATEST_MICROVERSION):
        body = {
            'share_server': {
                'host': host,
                'share_network_id': share_network_id,
                'identifier': identifier,
                'driver_options': driver_options if driver_options else {},
            }
        }

        body = json.dumps(body)
        resp, body = self.post('share-servers/manage', body,
                               extra_headers=True, version=version)
        self.expected_success(202, resp.status)
        return self._parse_resp(body)

    def unmanage_share_server(self, share_server_id,
                              version=LATEST_MICROVERSION):
        body = json.dumps({'unmanage': None})
        resp, body = self.post('share-servers/%s/action' % share_server_id,
                               body, extra_headers=True, version=version)
        self.expected_success(202, resp.status)
        return self._parse_resp(body)

    def wait_for_share_server_status(self, server_id, status,
                                     status_attr='status'):
        """Waits for a share to reach a given status."""
        body = self.show_share_server(server_id)
        server_status = body[status_attr]
        start = int(time.time())

        while server_status != status:
            time.sleep(self.build_interval)
            body = self.show_share_server(server_id)
            server_status = body[status_attr]
            if server_status == status:
                return
            elif constants.STATUS_ERROR in server_status.lower():
                raise share_exceptions.ShareServerBuildErrorException(
                    server_id=server_id)

            if int(time.time()) - start >= self.build_timeout:
                message = ("Share server's %(status_attr)s failed to "
                           "transition to %(status)s within the required "
                           "time %(seconds)s." %
                           {"status_attr": status_attr, "status": status,
                            "seconds": self.build_timeout})
                raise exceptions.TimeoutException(message)

    def share_server_reset_state(self, share_server_id,
                                 status=constants.SERVER_STATE_ACTIVE,
                                 version=LATEST_MICROVERSION):
        self.reset_state(share_server_id, status=status,
                         s_type='share-servers', version=version)

###############

    def migrate_share(self, share_id, host,
                      force_host_assisted_migration=False,
                      new_share_network_id=None, writable=False,
                      preserve_metadata=False, preserve_snapshots=False,
                      nondisruptive=False, new_share_type_id=None,
                      version=LATEST_MICROVERSION):

        body = {
            'migration_start': {
                'host': host,
                'force_host_assisted_migration': force_host_assisted_migration,
                'new_share_network_id': new_share_network_id,
                'new_share_type_id': new_share_type_id,
                'writable': writable,
                'preserve_metadata': preserve_metadata,
                'preserve_snapshots': preserve_snapshots,
                'nondisruptive': nondisruptive,
            }
        }

        body = json.dumps(body)
        return self.post('shares/%s/action' % share_id, body,
                         headers=EXPERIMENTAL, extra_headers=True,
                         version=version)

    def migration_complete(self, share_id, version=LATEST_MICROVERSION,
                           action_name='migration_complete'):
        post_body = {
            action_name: None,
        }
        body = json.dumps(post_body)
        return self.post('shares/%s/action' % share_id, body,
                         headers=EXPERIMENTAL, extra_headers=True,
                         version=version)

    def migration_cancel(self, share_id, version=LATEST_MICROVERSION,
                         action_name='migration_cancel'):
        post_body = {
            action_name: None,
        }
        body = json.dumps(post_body)
        return self.post('shares/%s/action' % share_id, body,
                         headers=EXPERIMENTAL, extra_headers=True,
                         version=version)

    def migration_get_progress(self, share_id, version=LATEST_MICROVERSION,
                               action_name='migration_get_progress'):
        post_body = {
            action_name: None,
        }
        body = json.dumps(post_body)
        result = self.post('shares/%s/action' % share_id, body,
                           headers=EXPERIMENTAL, extra_headers=True,
                           version=version)
        return json.loads(result[1])

    def reset_task_state(
            self, share_id, task_state, version=LATEST_MICROVERSION,
            action_name='reset_task_state'):
        post_body = {
            action_name: {
                'task_state': task_state,
            }
        }
        body = json.dumps(post_body)
        return self.post('shares/%s/action' % share_id, body,
                         headers=EXPERIMENTAL, extra_headers=True,
                         version=version)

    def wait_for_migration_status(self, share_id, dest_host, status_to_wait,
                                  version=LATEST_MICROVERSION):
        """Waits for a share to migrate to a certain host."""
        statuses = ((status_to_wait,)
                    if not isinstance(status_to_wait, (tuple, list, set))
                    else status_to_wait)
        share = self.get_share(share_id, version=version)
        migration_timeout = CONF.share.migration_timeout
        start = int(time.time())
        while share['task_state'] not in statuses:
            time.sleep(self.build_interval)
            share = self.get_share(share_id, version=version)
            if share['task_state'] in statuses:
                break
            elif share['task_state'] == 'migration_error':
                raise share_exceptions.ShareMigrationException(
                    share_id=share['id'], src=share['host'], dest=dest_host)
            elif int(time.time()) - start >= migration_timeout:
                message = ('Share %(share_id)s failed to reach a status in'
                           '%(status)s when migrating from host %(src)s to '
                           'host %(dest)s within the required time '
                           '%(timeout)s.' % {
                               'src': share['host'],
                               'dest': dest_host,
                               'share_id': share['id'],
                               'timeout': self.build_timeout,
                               'status': six.text_type(statuses),
                           })
                raise exceptions.TimeoutException(message)
        return share

################

    def create_share_replica(self, share_id, availability_zone=None,
                             version=LATEST_MICROVERSION):
        """Add a share replica of an existing share."""
        uri = "share-replicas"
        post_body = {
            'share_id': share_id,
            'availability_zone': availability_zone,
        }

        body = json.dumps({'share_replica': post_body})
        resp, body = self.post(uri, body,
                               headers=EXPERIMENTAL,
                               extra_headers=True,
                               version=version)
        self.expected_success(202, resp.status)
        return self._parse_resp(body)

    def get_share_replica(self, replica_id, version=LATEST_MICROVERSION):
        """Get the details of share_replica."""
        resp, body = self.get("share-replicas/%s" % replica_id,
                              headers=EXPERIMENTAL,
                              extra_headers=True,
                              version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def list_share_replicas(self, share_id=None, version=LATEST_MICROVERSION):
        """Get list of replicas."""
        uri = "share-replicas/detail"
        uri += ("?share_id=%s" % share_id) if share_id is not None else ''
        resp, body = self.get(uri, headers=EXPERIMENTAL,
                              extra_headers=True, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def list_share_replicas_summary(self, share_id=None,
                                    version=LATEST_MICROVERSION):
        """Get summary list of replicas."""
        uri = "share-replicas"
        uri += ("?share_id=%s" % share_id) if share_id is not None else ''
        resp, body = self.get(uri, headers=EXPERIMENTAL,
                              extra_headers=True, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def delete_share_replica(self, replica_id, version=LATEST_MICROVERSION):
        """Delete share_replica."""
        uri = "share-replicas/%s" % replica_id
        resp, body = self.delete(uri,
                                 headers=EXPERIMENTAL,
                                 extra_headers=True,
                                 version=version)
        self.expected_success(202, resp.status)
        return body

    def promote_share_replica(self, replica_id, expected_status=202,
                              version=LATEST_MICROVERSION):
        """Promote a share replica to active state."""
        uri = "share-replicas/%s/action" % replica_id
        post_body = {
            'promote': None,
        }
        body = json.dumps(post_body)
        resp, body = self.post(uri, body,
                               headers=EXPERIMENTAL,
                               extra_headers=True,
                               version=version)
        self.expected_success(expected_status, resp.status)
        return self._parse_resp(body)

    def list_share_replica_export_locations(self, replica_id,
                                            expected_status=200,
                                            version=LATEST_MICROVERSION):
        uri = "share-replicas/%s/export-locations" % replica_id
        resp, body = self.get(uri, headers=EXPERIMENTAL,
                              extra_headers=True, version=version)
        self.expected_success(expected_status, resp.status)
        return self._parse_resp(body)

    def get_share_replica_export_location(self, replica_id,
                                          export_location_id,
                                          expected_status=200,
                                          version=LATEST_MICROVERSION):
        uri = "share-replicas/%s/export-locations/%s" % (replica_id,
                                                         export_location_id)
        resp, body = self.get(uri, headers=EXPERIMENTAL,
                              extra_headers=True, version=version)
        self.expected_success(expected_status, resp.status)
        return self._parse_resp(body)

    def wait_for_share_replica_status(self, replica_id, expected_status,
                                      status_attr='status'):
        """Waits for a replica's status_attr to reach a given status."""
        body = self.get_share_replica(replica_id)
        replica_status = body[status_attr]
        start = int(time.time())

        while replica_status != expected_status:
            time.sleep(self.build_interval)
            body = self.get_share_replica(replica_id)
            replica_status = body[status_attr]
            if replica_status == expected_status:
                return
            if ('error' in replica_status
                    and expected_status != constants.STATUS_ERROR):
                raise share_exceptions.ShareInstanceBuildErrorException(
                    id=replica_id)

            if int(time.time()) - start >= self.build_timeout:
                message = ('The %(status_attr)s of Replica %(id)s failed to '
                           'reach %(expected_status)s status within the '
                           'required time (%(time)ss). Current '
                           '%(status_attr)s: %(current_status)s.' %
                           {
                               'status_attr': status_attr,
                               'expected_status': expected_status,
                               'time': self.build_timeout,
                               'id': replica_id,
                               'current_status': replica_status,
                           })
                raise exceptions.TimeoutException(message)

    def reset_share_replica_status(self, replica_id,
                                   status=constants.STATUS_AVAILABLE,
                                   version=LATEST_MICROVERSION):
        """Reset the status."""
        uri = 'share-replicas/%s/action' % replica_id
        post_body = {
            'reset_status': {
                'status': status
            }
        }
        body = json.dumps(post_body)
        resp, body = self.post(uri, body,
                               headers=EXPERIMENTAL,
                               extra_headers=True,
                               version=version)
        self.expected_success(202, resp.status)
        return self._parse_resp(body)

    def reset_share_replica_state(self, replica_id,
                                  state=constants.REPLICATION_STATE_ACTIVE,
                                  version=LATEST_MICROVERSION):
        """Reset the replication state of a replica."""
        uri = 'share-replicas/%s/action' % replica_id
        post_body = {
            'reset_replica_state': {
                'replica_state': state
            }
        }
        body = json.dumps(post_body)
        resp, body = self.post(uri, body,
                               headers=EXPERIMENTAL,
                               extra_headers=True,
                               version=version)
        self.expected_success(202, resp.status)
        return self._parse_resp(body)

    def resync_share_replica(self, replica_id, expected_result=202,
                             version=LATEST_MICROVERSION):
        """Force an immediate resync of the replica."""
        uri = 'share-replicas/%s/action' % replica_id
        post_body = {
            'resync': None
        }
        body = json.dumps(post_body)
        resp, body = self.post(uri, body,
                               headers=EXPERIMENTAL,
                               extra_headers=True,
                               version=version)
        self.expected_success(expected_result, resp.status)
        return self._parse_resp(body)

    def force_delete_share_replica(self, replica_id,
                                   version=LATEST_MICROVERSION):
        """Force delete a replica."""
        uri = 'share-replicas/%s/action' % replica_id
        post_body = {
            'force_delete': None
        }
        body = json.dumps(post_body)
        resp, body = self.post(uri, body,
                               headers=EXPERIMENTAL,
                               extra_headers=True,
                               version=version)
        self.expected_success(202, resp.status)
        return self._parse_resp(body)

    def list_share_networks(self, detailed=False, params=None,
                            version=LATEST_MICROVERSION):
        """Get list of share networks w/o filters."""
        uri = 'share-networks/detail' if detailed else 'share-networks'
        uri += '?%s' % parse.urlencode(params) if params else ''
        resp, body = self.get(uri, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def list_share_networks_with_detail(self, params=None,
                                        version=LATEST_MICROVERSION):
        """Get detailed list of share networks w/o filters."""
        return self.list_share_networks(
            detailed=True, params=params, version=version)

    def get_share_network(self, share_network_id, version=LATEST_MICROVERSION):
        resp, body = self.get("share-networks/%s" % share_network_id,
                              version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

################

    def create_snapshot_access_rule(self, snapshot_id, access_type="ip",
                                    access_to="0.0.0.0/0"):
        body = {
            "allow_access": {
                "access_type": access_type,
                "access_to": access_to
            }
        }
        resp, body = self.post("snapshots/%s/action" % snapshot_id,
                               json.dumps(body), version=LATEST_MICROVERSION)
        self.expected_success(202, resp.status)
        return self._parse_resp(body)

    def get_snapshot_access_rule(self, snapshot_id, rule_id):
        resp, body = self.get("snapshots/%s/access-list" % snapshot_id,
                              version=LATEST_MICROVERSION)
        body = self._parse_resp(body)
        found_rules = [r for r in body if r['id'] == rule_id]

        return found_rules[0] if len(found_rules) > 0 else None

    def wait_for_snapshot_access_rule_status(self, snapshot_id, rule_id,
                                             expected_state='active'):
        rule = self.get_snapshot_access_rule(snapshot_id, rule_id)
        state = rule['state']
        start = int(time.time())

        while state != expected_state:
            time.sleep(self.build_interval)
            rule = self.get_snapshot_access_rule(snapshot_id, rule_id)
            state = rule['state']
            if state == expected_state:
                return
            if 'error' in state:
                raise share_exceptions.AccessRuleBuildErrorException(
                    snapshot_id)

            if int(time.time()) - start >= self.build_timeout:
                message = ('The status of snapshot access rule %(id)s failed '
                           'to reach %(expected_state)s state within the '
                           'required time (%(time)ss). Current '
                           'state: %(current_state)s.' %
                           {
                               'expected_state': expected_state,
                               'time': self.build_timeout,
                               'id': rule_id,
                               'current_state': state,
                           })
                raise exceptions.TimeoutException(message)

    def delete_snapshot_access_rule(self, snapshot_id, rule_id):
        body = {
            "deny_access": {
                "access_id": rule_id,
            }
        }
        resp, body = self.post("snapshots/%s/action" % snapshot_id,
                               json.dumps(body), version=LATEST_MICROVERSION)
        self.expected_success(202, resp.status)
        return self._parse_resp(body)

    def wait_for_snapshot_access_rule_deletion(self, snapshot_id, rule_id):
        rule = self.get_snapshot_access_rule(snapshot_id, rule_id)
        start = int(time.time())

        while rule is not None:
            time.sleep(self.build_interval)

            rule = self.get_snapshot_access_rule(snapshot_id, rule_id)

            if rule is None:
                return
            if int(time.time()) - start >= self.build_timeout:
                message = ('The snapshot access rule %(id)s failed to delete '
                           'within the required time (%(time)ss).' %
                           {
                               'time': self.build_timeout,
                               'id': rule_id,
                           })
                raise exceptions.TimeoutException(message)

    def get_snapshot_export_location(self, snapshot_id, export_location_uuid,
                                     version=LATEST_MICROVERSION):
        resp, body = self.get(
            "snapshots/%(snapshot_id)s/export-locations/%(el_uuid)s" % {
                "snapshot_id": snapshot_id, "el_uuid": export_location_uuid},
            version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def list_snapshot_export_locations(
            self, snapshot_id, version=LATEST_MICROVERSION):
        resp, body = self.get(
            "snapshots/%s/export-locations" % snapshot_id, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

###############

    def get_message(self, message_id, version=LATEST_MICROVERSION):
        """Show details for a single message."""
        url = 'messages/%s' % message_id
        resp, body = self.get(url, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def list_messages(self, params=None, version=LATEST_MICROVERSION):
        """List all messages."""
        url = 'messages'
        url += '?%s' % parse.urlencode(params) if params else ''
        resp, body = self.get(url, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def delete_message(self, message_id, version=LATEST_MICROVERSION):
        """Delete a single message."""
        url = 'messages/%s' % message_id
        resp, body = self.delete(url, version=version)
        self.expected_success(204, resp.status)
        return self._parse_resp(body)

    def wait_for_message(self, resource_id):
        """Waits until a message for a resource with given id exists"""
        start = int(time.time())
        message = None

        while not message:
            time.sleep(self.build_interval)
            for msg in self.list_messages():
                if msg['resource_id'] == resource_id:
                    return msg

            if int(time.time()) - start >= self.build_timeout:
                message = ('No message for resource with id %s was created in'
                           ' the required time (%s s).' %
                           (resource_id, self.build_timeout))
                raise exceptions.TimeoutException(message)

###############

    def create_security_service(self, ss_type="ldap",
                                version=LATEST_MICROVERSION, **kwargs):
        """Creates Security Service.

        :param ss_type: ldap, kerberos, active_directory
        :param version: microversion string
        :param kwargs: name, description, dns_ip, server, ou, domain, user,
        :param kwargs: password
        """
        post_body = {"type": ss_type}
        post_body.update(kwargs)
        body = json.dumps({"security_service": post_body})
        resp, body = self.post("security-services", body, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def update_security_service(self, ss_id, version=LATEST_MICROVERSION,
                                **kwargs):
        """Updates Security Service.

        :param ss_id: id of security-service entity
        :param version: microversion string
        :param kwargs: dns_ip, server, ou, domain, user, password, name,
        :param kwargs: description
        :param kwargs: for 'active' status can be changed
        :param kwargs: only 'name' and 'description' fields
        """
        body = json.dumps({"security_service": kwargs})
        resp, body = self.put("security-services/%s" % ss_id, body,
                              version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def get_security_service(self, ss_id, version=LATEST_MICROVERSION):
        resp, body = self.get("security-services/%s" % ss_id, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)

    def list_security_services(self, detailed=False, params=None,
                               version=LATEST_MICROVERSION):
        uri = "security-services"
        if detailed:
            uri += '/detail'
        if params:
            uri += "?%s" % parse.urlencode(params)
        resp, body = self.get(uri, version=version)
        self.expected_success(200, resp.status)
        return self._parse_resp(body)
