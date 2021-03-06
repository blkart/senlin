# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import copy

import mock
from oslo_serialization import jsonutils
from oslo_utils import uuidutils
import six
from webob import exc

from senlin.api.common import util
from senlin.api.middleware import fault
from senlin.api.openstack.v1 import clusters
from senlin.common import exception as senlin_exc
from senlin.common import policy
from senlin.objects.requests import clusters as vorc
from senlin.rpc import client as rpc_client
from senlin.tests.unit.api import shared
from senlin.tests.unit.common import base
from senlin.tests.unit.common import utils


@mock.patch.object(policy, 'enforce')
class ClusterControllerTest(shared.ControllerTest, base.SenlinTestCase):
    '''Test case for the cluster controoler.'''

    def setUp(self):
        super(ClusterControllerTest, self).setUp()

        class DummyConfig(object):
            bind_port = 8778

        cfgopts = DummyConfig()
        self.controller = clusters.ClusterController(options=cfgopts)
        self.context = utils.dummy_context()

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test_index(self, mock_call, mock_parse, mock_enforce):
        self._mock_enforce_setup(mock_enforce, 'index', True)
        req = self._get('/clusters')

        engine_resp = [{'foo': 'bar'}]
        mock_call.return_value = engine_resp
        obj = vorc.ClusterListRequest()
        mock_parse.return_value = obj

        result = self.controller.index(req)

        expected = {u'clusters': engine_resp}
        self.assertEqual(expected, result)

        mock_parse.assert_called_once_with('ClusterListRequest', req,
                                           {'project_safe': True})
        mock_call.assert_called_once_with(req.context, 'cluster_list2', obj)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test_index_with_params(self, mock_call, mock_parse, mock_enforce):
        self._mock_enforce_setup(mock_enforce, 'index', True)
        fake_id = uuidutils.generate_uuid()
        params = {
            'name': 'name1',
            'status': 'ACTIVE',
            'limit': '3',
            'marker': fake_id,
            'sort': 'name:asc',
            'global_project': 'True',
        }
        req = self._get('/clusters', params=params)
        obj = vorc.ClusterListRequest()
        mock_parse.return_value = obj
        engine_resp = [{'foo': 'bar'}]
        mock_call.return_value = engine_resp

        result = self.controller.index(req)

        expected = {u'clusters': engine_resp}
        self.assertEqual(expected, result)
        mock_parse.assert_called_once_with(
            'ClusterListRequest', req,
            {
                'name': ['name1'],
                'status': ['ACTIVE'],
                'limit': '3',
                'marker': fake_id,
                'sort': 'name:asc',
                'project_safe': False
            })

        mock_call.assert_called_once_with(req.context, 'cluster_list2', obj)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test_index_failed_with_exception(self, mock_call, mock_parse,
                                         mock_enforce):
        self._mock_enforce_setup(mock_enforce, 'index', True)
        req = self._get('/clusters', params={})
        mock_parse.side_effect = exc.HTTPBadRequest("Boom")
        ex = self.assertRaises(exc.HTTPBadRequest,
                               self.controller.index,
                               req)

        self.assertEqual("Boom", six.text_type(ex))
        mock_parse.assert_called_once_with(
            "ClusterListRequest", req, {'project_safe': True})
        self.assertEqual(0, mock_call.call_count)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test_index_failed_engine_error(self, mock_call, mock_parse,
                                       mock_enforce):
        self._mock_enforce_setup(mock_enforce, 'index', True)
        params = {'global_project': True}
        req = self._get('/clusters', params=params)
        obj = mock.Mock()
        mock_parse.return_value = obj
        error = senlin_exc.Forbidden()
        mock_call.side_effect = shared.to_remote_error(error)

        resp = shared.request_with_middleware(fault.FaultWrapper,
                                              self.controller.index,
                                              req)

        self.assertEqual(403, resp.json['code'])
        self.assertEqual('Forbidden', resp.json['error']['type'])
        mock_parse.assert_called_once_with(
            "ClusterListRequest", mock.ANY, {'project_safe': False})
        mock_call.assert_called_once_with(req.context, 'cluster_list2', obj)

    def test_index_error_denied_policy(self, mock_enforce):
        self._mock_enforce_setup(mock_enforce, 'index', False)
        req = self._get('/clusters')

        resp = shared.request_with_middleware(fault.FaultWrapper,
                                              self.controller.index,
                                              req)

        self.assertEqual(403, resp.status_int)
        self.assertIn('403 Forbidden', six.text_type(resp))

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test_create(self, mock_call, mock_parse, mock_enforce):
        self._mock_enforce_setup(mock_enforce, 'create', True)
        body = {
            'cluster': {
                'name': 'test_cluster',
                'desired_capacity': 0,
                'profile_id': 'xxxx-yyyy',
                'min_size': 0,
                'max_size': 0,
                'metadata': {},
                'timeout': None,
            }
        }
        req = self._post('/clusters', jsonutils.dumps(body))
        engine_response = {
            'id': 'FAKE_ID',
            'name': 'test_cluster',
            'desired_capacity': 0,
            'profile_id': 'xxxx-yyyy',
            'min_size': 0,
            'max_size': 0,
            'metadata': {},
            'timeout': 60,
            'action': 'fake_action'
        }
        mock_call.return_value = engine_response
        obj = mock.Mock()
        mock_parse.return_value = obj

        resp = self.controller.create(req, body=body)

        self.assertEqual(engine_response, resp['cluster'])
        self.assertEqual('/actions/fake_action', resp['location'])
        mock_parse.assert_called_once_with(
            "ClusterCreateRequest", mock.ANY, body, 'cluster')
        mock_call.assert_called_once_with(req.context, 'cluster_create2',
                                          obj.cluster)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test_create_failed_request(self, mock_call, mock_parse, mock_enforce):
        self._mock_enforce_setup(mock_enforce, 'create', True)
        body = {'foo': 'bar'}
        req = self._post('/clusters', jsonutils.dumps(body))
        mock_parse.side_effect = exc.HTTPBadRequest('Boom')

        ex = self.assertRaises(exc.HTTPBadRequest,
                               self.controller.create,
                               req, body=body)

        self.assertEqual("Boom", six.text_type(ex))
        self.assertEqual(0, mock_call.call_count)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test_create_failed_engine(self, mock_call, mock_parse, mock_enforce):
        self._mock_enforce_setup(mock_enforce, 'create', True)
        body = {'foo': 'bar'}
        req = self._post('/clusters', jsonutils.dumps(body))
        obj = mock.Mock()
        mock_parse.return_value = obj
        error = senlin_exc.BadRequest(msg='bad')
        mock_call.side_effect = shared.to_remote_error(error)

        resp = shared.request_with_middleware(fault.FaultWrapper,
                                              self.controller.create,
                                              req, body=body)

        self.assertEqual(400, resp.json['code'])
        self.assertEqual('BadRequest', resp.json['error']['type'])
        mock_parse.assert_called_once_with(
            "ClusterCreateRequest", mock.ANY, {'foo': 'bar'}, 'cluster')
        mock_call.assert_called_once_with(req.context, 'cluster_create2',
                                          obj.cluster)

    def test_create_err_denied_policy(self, mock_enforce):
        self._mock_enforce_setup(mock_enforce, 'create', False)
        body = {
            'cluster': {
                'name': 'test_cluster',
                'profile_id': 'xxxx-yyyy',
            }
        }
        req = self._post('/clusters', jsonutils.dumps(body))

        resp = shared.request_with_middleware(fault.FaultWrapper,
                                              self.controller.create,
                                              req, body=body)

        self.assertEqual(403, resp.status_int)
        self.assertIn('403 Forbidden', six.text_type(resp))

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test_get(self, mock_call, mock_parse, mock_enforce):
        self._mock_enforce_setup(mock_enforce, 'get', True)
        cid = 'cid'
        req = self._get('/clusters/%s' % cid)
        engine_resp = {'foo': 'bar'}
        mock_call.return_value = engine_resp
        obj = mock.Mock()
        mock_parse.return_value = obj

        response = self.controller.get(req, cluster_id=cid)

        self.assertEqual({'cluster': {'foo': 'bar'}}, response)
        mock_parse.assert_called_once_with(
            "ClusterGetRequest", req, {'identity': 'cid'})
        mock_call.assert_called_once_with(req.context, 'cluster_get2', obj)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test_get_failed_request(self, mock_call, mock_parse, mock_enforce):
        self._mock_enforce_setup(mock_enforce, 'get', True)
        cid = 'FAKE_ID'
        req = self._get('/clusters/%s' % cid)
        mock_parse.side_effect = exc.HTTPBadRequest("Boom")
        ex = self.assertRaises(exc.HTTPBadRequest,
                               self.controller.get,
                               req, cluster_id=cid)

        self.assertEqual("Boom", six.text_type(ex))
        mock_parse.assert_called_once_with(
            "ClusterGetRequest", req, {'identity': cid})
        self.assertEqual(0, mock_call.call_count)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test_get_failed_engine(self, mock_call, mock_parse, mock_enforce):
        self._mock_enforce_setup(mock_enforce, 'get', True)
        cid = 'non-existent-cluster'
        req = self._get('/clusters/%s' % cid)

        error = senlin_exc.ResourceNotFound(type='cluster', id=cid)
        mock_call.side_effect = shared.to_remote_error(error)

        resp = shared.request_with_middleware(fault.FaultWrapper,
                                              self.controller.get,
                                              req, cluster_id=cid)

        self.assertEqual(404, resp.json['code'])
        self.assertEqual('ResourceNotFound', resp.json['error']['type'])
        mock_parse.assert_called_once_with(
            "ClusterGetRequest", mock.ANY, {'identity': cid})

    def test_get_denied_policy(self, mock_enforce):
        self._mock_enforce_setup(mock_enforce, 'get', False)
        cid = 'cid'
        req = self._get('/clusters/%s' % cid)

        resp = shared.request_with_middleware(fault.FaultWrapper,
                                              self.controller.get,
                                              req, cluster_id=cid)

        self.assertEqual(403, resp.status_int)
        self.assertIn('403 Forbidden', six.text_type(resp))

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test_update(self, mock_call, mock_parse, mock_enforce):
        self._mock_enforce_setup(mock_enforce, 'update', True)
        cid = 'aaaa-bbbb-cccc'
        body = {'cluster': {'foo': 'bar'}}
        engine_resp = {
            'id': cid,
            'action': 'fake_action',
        }
        req = self._patch('/clusters/%s' % cid, jsonutils.dumps(body))
        mock_call.return_value = engine_resp
        obj = mock.Mock()
        mock_parse.return_value = obj

        res = self.controller.update(req, cluster_id=cid, body=body)

        self.assertEqual(
            {'cluster': {'id': cid}, 'location': '/actions/fake_action'},
            res)
        mock_parse.assert_called_once_with(
            "ClusterUpdateRequest", req,
            {'identity': 'aaaa-bbbb-cccc', 'foo': 'bar'})
        mock_call.assert_called_once_with(req.context, 'cluster_update2', obj)

    def test_update_missing_cluster_key(self, mock_enforce):
        self._mock_enforce_setup(mock_enforce, 'update', True)
        cid = 'aaaa-bbbb-cccc'
        body = {'profile_id': 'xxxx-yyyy-zzzz'}
        req = self._patch('/clusters/%s' % cid, jsonutils.dumps(body))
        mock_call = self.patchobject(rpc_client.EngineClient, 'call2')

        ex = self.assertRaises(exc.HTTPBadRequest,
                               self.controller.update,
                               req, cluster_id=cid, body=body)

        self.assertIn("Malformed request data, missing 'cluster' key "
                      "in request body.", six.text_type(ex))
        self.assertFalse(mock_call.called)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test_update_failed_request(self, mock_call, mock_parse, mock_enforce):
        self._mock_enforce_setup(mock_enforce, 'update', True)
        cid = 'aaaa-bbbb-cccc'
        body = {'cluster': {'name': 'foo bar'}}
        req = self._patch('/clusters/%s' % cid, jsonutils.dumps(body))
        mock_parse.side_effect = exc.HTTPBadRequest('Boom')

        ex = self.assertRaises(exc.HTTPBadRequest,
                               self.controller.update,
                               req, cluster_id=cid, body=body)

        self.assertEqual("Boom", six.text_type(ex))
        mock_parse.assert_called_once_with(
            "ClusterUpdateRequest", req,
            {'identity': 'aaaa-bbbb-cccc', 'name': 'foo bar'})
        self.assertFalse(mock_call.called)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test_update_engine_error(self, mock_call, mock_parse, mock_enforce):
        self._mock_enforce_setup(mock_enforce, 'update', True)
        cid = 'non-existent-cluster'
        body = {'cluster': {'profile_id': 'xxxx-yyyy-zzzz'}}
        req = self._patch('/clusters/%s' % cid, jsonutils.dumps(body))
        obj = mock.Mock()
        mock_parse.return_value = obj
        error = senlin_exc.ResourceNotFound(type='cluster', id=cid)
        mock_call.side_effect = shared.to_remote_error(error)

        resp = shared.request_with_middleware(fault.FaultWrapper,
                                              self.controller.update,
                                              req, cluster_id=cid, body=body)

        self.assertEqual(404, resp.json['code'])
        self.assertEqual('ResourceNotFound', resp.json['error']['type'])
        mock_parse.assert_called_once_with(
            "ClusterUpdateRequest", mock.ANY,
            {'identity': cid, 'profile_id': 'xxxx-yyyy-zzzz'})
        mock_call.assert_called_once_with(req.context, 'cluster_update2', obj)

    def test_update_err_denied_policy(self, mock_enforce):
        self._mock_enforce_setup(mock_enforce, 'update', False)
        cid = 'aaaa-bbbb-cccc'
        body = {'cluster': {'profile_id': 'xxxx-yyyy-zzzz'}}

        req = self._patch('/clusters/%(cluster_id)s' % {'cluster_id': cid},
                          jsonutils.dumps(body))

        resp = shared.request_with_middleware(fault.FaultWrapper,
                                              self.controller.update,
                                              req, cluster_id=cid, body=body)

        self.assertEqual(403, resp.status_int)
        self.assertIn('403 Forbidden', six.text_type(resp))

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__add_nodes(self, mock_call, mock_parse, mock_enforce):
        req = mock.Mock()
        cid = 'FAKE_ID'
        nodes = ['NODE1']
        mock_call.return_value = {'action': 'action-id'}
        obj = mock.Mock()
        mock_parse.return_value = obj

        resp = self.controller._add_nodes(req, cid, nodes)

        self.assertEqual({'action': 'action-id'}, resp)
        mock_parse.assert_called_once_with(
            'ClusterAddNodesRequest', req, {'identity': cid, 'nodes': nodes})
        mock_call.assert_called_once_with(
            req.context, 'cluster_add_nodes2', obj)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__add_nodes_failed_request(self, mock_call, mock_parse, _ignore):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        nodes = ['NODE2']
        mock_parse.side_effect = exc.HTTPBadRequest('Boom')

        ex = self.assertRaises(exc.HTTPBadRequest,
                               self.controller._add_nodes,
                               req, cid, nodes)

        self.assertEqual("Boom", six.text_type(ex))
        mock_parse.assert_called_once_with(
            'ClusterAddNodesRequest', req, {'identity': cid, 'nodes': nodes})
        self.assertFalse(mock_call.called)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__add_nodes_failed_engine(self, mock_call, mock_parse, _ignore):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        nodes = ['NODE3']
        obj = mock.Mock()
        mock_parse.return_value = obj
        mock_call.side_effect = senlin_exc.BadRequest(msg='Boom')

        ex = self.assertRaises(senlin_exc.BadRequest,
                               self.controller._add_nodes,
                               req, cid, nodes)

        mock_parse.assert_called_once_with(
            'ClusterAddNodesRequest', req, {'identity': cid, 'nodes': nodes})
        self.assertEqual("The request is malformed: Boom.", six.text_type(ex))
        mock_call.assert_called_once_with(
            req.context, 'cluster_add_nodes2', obj)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__del_nodes(self, mock_call, mock_parse, _ignore):
        req = mock.Mock()
        cid = 'FAKE_ID'
        nodes = ['NODE4']
        mock_call.return_value = {'action': 'action-id'}
        obj = mock.Mock()
        mock_parse.return_value = obj

        resp = self.controller._del_nodes(req, cid, nodes)

        self.assertEqual({'action': 'action-id'}, resp)
        mock_parse.assert_called_once_with(
            'ClusterDelNodesRequest', req, {'identity': cid, 'nodes': nodes})
        mock_call.assert_called_once_with(
            req.context, 'cluster_del_nodes2', obj)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__del_nodes_failed_request(self, mock_call, mock_parse, _ignore):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        nodes = ['NODE5']
        mock_parse.side_effect = exc.HTTPBadRequest('Boom')

        ex = self.assertRaises(exc.HTTPBadRequest,
                               self.controller._del_nodes,
                               req, cid, nodes)

        self.assertEqual("Boom", six.text_type(ex))
        mock_parse.assert_called_once_with(
            'ClusterDelNodesRequest', req, {'identity': cid, 'nodes': nodes})
        self.assertFalse(mock_call.called)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__del_nodes_failed_engine(self, mock_call, mock_parse, _ignore):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        nodes = ['NODE6']
        obj = mock.Mock()
        mock_parse.return_value = obj
        mock_call.side_effect = senlin_exc.BadRequest(msg='Boom')

        ex = self.assertRaises(senlin_exc.BadRequest,
                               self.controller._del_nodes,
                               req, cid, nodes)

        mock_parse.assert_called_once_with(
            'ClusterDelNodesRequest', req, {'identity': cid, 'nodes': nodes})
        self.assertEqual("The request is malformed: Boom.", six.text_type(ex))
        mock_call.assert_called_once_with(
            req.context, 'cluster_del_nodes2', obj)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__replace_nodes(self, mock_call, mock_parse, _ignore):
        req = mock.Mock()
        cid = 'FAKE_ID'
        nodes = {'OLD': 'NEW'}
        mock_call.return_value = {'action': 'action-id'}
        obj = mock.Mock()
        mock_parse.return_value = obj

        resp = self.controller._replace_nodes(req, cid, nodes)

        self.assertEqual({'action': 'action-id'}, resp)
        mock_parse.assert_called_once_with(
            'ClusterReplaceNodesRequest', req,
            {'identity': cid, 'nodes': nodes})
        mock_call.assert_called_once_with(
            req.context, 'cluster_replace_nodes2', obj)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__replace_nodes_none(self, mock_call, mock_parse, _ign):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'

        ex = self.assertRaises(exc.HTTPBadRequest,
                               self.controller._replace_nodes,
                               req, cid, None)

        self.assertEqual("The data provided is not a map", six.text_type(ex))
        self.assertEqual(0, mock_parse.call_count)
        self.assertFalse(mock_call.called)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__replace_nodes_not_map(self, mock_call, mock_parse, _ign):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        nodes = ['abc', 'def']
        ex = self.assertRaises(exc.HTTPBadRequest,
                               self.controller._replace_nodes,
                               req, cid, nodes)

        self.assertEqual("The data provided is not a map", six.text_type(ex))
        self.assertEqual(0, mock_parse.call_count)
        self.assertFalse(mock_call.called)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__replace_nodes_failed_request(self, mock_call, mock_parse, _ign):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        nodes = {'OLD': 'NEW'}
        mock_parse.side_effect = exc.HTTPBadRequest('Boom')

        ex = self.assertRaises(exc.HTTPBadRequest,
                               self.controller._replace_nodes,
                               req, cid, nodes)

        self.assertEqual("Boom", six.text_type(ex))
        mock_parse.assert_called_once_with(
            'ClusterReplaceNodesRequest', req,
            {'identity': cid, 'nodes': nodes})
        self.assertFalse(mock_call.called)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__replace_nodes_failed_engine(self, mock_call, mock_parse, _ign):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        nodes = {'OLD': 'NEW'}
        obj = mock.Mock()
        mock_parse.return_value = obj
        mock_call.side_effect = senlin_exc.BadRequest(msg='Boom')

        ex = self.assertRaises(senlin_exc.BadRequest,
                               self.controller._replace_nodes,
                               req, cid, nodes)

        mock_parse.assert_called_once_with(
            'ClusterReplaceNodesRequest', req,
            {'identity': cid, 'nodes': nodes})
        self.assertEqual("The request is malformed: Boom.", six.text_type(ex))
        mock_call.assert_called_once_with(
            req.context, 'cluster_replace_nodes2', obj)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def _test_resize_with_type(self, adj_type, mock_call, mock_parse):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        data = {
            'adjustment_type': adj_type,
            'number': 1,
            'min_size': 0,
            'max_size': 10,
            'min_step': 1,
            'strict': True
        }
        mock_call.return_value = {'action': 'action-id'}
        # We are using a real object for testing
        obj = vorc.ClusterResizeRequest(identity=cid, **data)
        mock_parse.return_value = obj

        resp = self.controller._do_resize(req, cid, data)

        self.assertEqual({'action': 'action-id'}, resp)
        params = copy.deepcopy(data)
        params['identity'] = cid
        mock_parse.assert_called_once_with(
            'ClusterResizeRequest', req, params)
        mock_call.assert_called_once_with(req.context, 'cluster_resize2', obj)

    def test__do_resize_exact_capacity(self, mock_enforce):
        self._test_resize_with_type('EXACT_CAPACITY')

    def test__do_resize_with_change_capacity(self, mock_enforce):
        self._test_resize_with_type('CHANGE_IN_CAPACITY')

    def test__do_resize_with_change_percentage(self, mock_enforce):
        self._test_resize_with_type('CHANGE_IN_PERCENTAGE')

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__do_resize_failed_request(self, mock_call, mock_parse, _ign):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        data = {'adjustment_type': 'EXACT_CAPACITY', 'number': 10}
        mock_parse.side_effect = exc.HTTPBadRequest('Boom')

        ex = self.assertRaises(exc.HTTPBadRequest,
                               self.controller._do_resize,
                               req, cid, data)

        self.assertEqual("Boom", six.text_type(ex))
        mock_parse.assert_called_once_with(
            'ClusterResizeRequest', req,
            {
                'identity': cid,
                'adjustment_type': 'EXACT_CAPACITY',
                'number': 10
            })
        self.assertFalse(mock_call.called)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__do_resize_missing_number(self, mock_call, mock_parse, _ign):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        data = {'adjustment_type': 'EXACT_CAPACITY'}
        obj = vorc.ClusterResizeRequest(identity=cid, **data)
        mock_parse.return_value = obj
        ex = self.assertRaises(exc.HTTPBadRequest,
                               self.controller._do_resize,
                               req, cid, data)

        self.assertEqual('Missing number value for size adjustment.',
                         six.text_type(ex))
        self.assertEqual(0, mock_call.call_count)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__do_resize_missing_type(self, mock_call, mock_parse, _ign):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        data = {'number': 2}
        obj = vorc.ClusterResizeRequest(identity=cid, **data)
        mock_parse.return_value = obj

        ex = self.assertRaises(exc.HTTPBadRequest,
                               self.controller._do_resize,
                               req, cid, data)

        self.assertEqual("Missing adjustment_type value for size adjustment.",
                         six.text_type(ex))
        self.assertEqual(0, mock_call.call_count)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__do_resize_max_size_too_small(self, mock_call, mock_parse, _ign):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        data = {'min_size': 2, 'max_size': 1}
        obj = vorc.ClusterResizeRequest(identity=cid, **data)
        mock_parse.return_value = obj

        ex = self.assertRaises(exc.HTTPBadRequest,
                               self.controller._do_resize,
                               req, cid, data)

        self.assertEqual("The specified min_size (2) is greater than "
                         "the specified max_size (1).", six.text_type(ex))
        self.assertEqual(0, mock_call.call_count)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__do_resize_failed_engine(self, mock_call, mock_parse, _ign):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        data = {'max_size': 200}
        obj = vorc.ClusterResizeRequest(identity=cid, **data)
        mock_parse.return_value = obj
        mock_call.side_effect = senlin_exc.BadRequest(msg='Boom')

        ex = self.assertRaises(senlin_exc.BadRequest,
                               self.controller._do_resize,
                               req, cid, data)

        mock_parse.assert_called_once_with(
            'ClusterResizeRequest', req, {'identity': cid, 'max_size': 200})
        self.assertEqual("The request is malformed: Boom.", six.text_type(ex))
        mock_call.assert_called_once_with(
            req.context, 'cluster_resize2', obj)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__do_scale_out(self, mock_call, mock_parse, _ignore):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        count = 1
        mock_call.return_value = {'action': 'action-id'}
        obj = mock.Mock()
        mock_parse.return_value = obj

        resp = self.controller._do_scale_out(req, cid, count)

        self.assertEqual({'action': 'action-id'}, resp)
        mock_parse.assert_called_once_with(
            'ClusterScaleOutRequest', req, {'identity': cid, 'count': count})
        mock_call.assert_called_once_with(
            req.context, 'cluster_scale_out2', obj)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__do_scale_out_failed_request(self, mock_call, mock_parse, _ign):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        count = 2
        mock_parse.side_effect = exc.HTTPBadRequest('Boom')

        ex = self.assertRaises(exc.HTTPBadRequest,
                               self.controller._do_scale_out,
                               req, cid, count)

        self.assertEqual("Boom", six.text_type(ex))
        mock_parse.assert_called_once_with(
            'ClusterScaleOutRequest', req, {'identity': cid, 'count': count})
        self.assertFalse(mock_call.called)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__do_scale_out_failed_engine(self, mock_call, mock_parse, _ign):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        count = 3
        obj = mock.Mock()
        mock_parse.return_value = obj
        mock_call.side_effect = senlin_exc.BadRequest(msg='Boom')

        ex = self.assertRaises(senlin_exc.BadRequest,
                               self.controller._do_scale_out,
                               req, cid, count)

        mock_parse.assert_called_once_with(
            'ClusterScaleOutRequest', req, {'identity': cid, 'count': count})
        self.assertEqual("The request is malformed: Boom.", six.text_type(ex))
        mock_call.assert_called_once_with(
            req.context, 'cluster_scale_out2', obj)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__do_scale_in(self, mock_call, mock_parse, _ignore):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        count = 4
        mock_call.return_value = {'action': 'action-id'}
        obj = mock.Mock()
        mock_parse.return_value = obj

        resp = self.controller._do_scale_in(req, cid, count)

        self.assertEqual({'action': 'action-id'}, resp)
        mock_parse.assert_called_once_with(
            'ClusterScaleInRequest', req, {'identity': cid, 'count': count})
        mock_call.assert_called_once_with(
            req.context, 'cluster_scale_in2', obj)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__do_scale_in_failed_request(self, mock_call, mock_parse, _ign):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        count = 5
        mock_parse.side_effect = exc.HTTPBadRequest('Boom')

        ex = self.assertRaises(exc.HTTPBadRequest,
                               self.controller._do_scale_in,
                               req, cid, count)

        self.assertEqual("Boom", six.text_type(ex))
        mock_parse.assert_called_once_with(
            'ClusterScaleInRequest', req, {'identity': cid, 'count': count})
        self.assertFalse(mock_call.called)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__do_scale_in_failed_engine(self, mock_call, mock_parse, _ign):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        count = 6
        obj = mock.Mock()
        mock_parse.return_value = obj
        mock_call.side_effect = senlin_exc.BadRequest(msg='Boom')

        ex = self.assertRaises(senlin_exc.BadRequest,
                               self.controller._do_scale_in,
                               req, cid, count)

        mock_parse.assert_called_once_with(
            'ClusterScaleInRequest', req, {'identity': cid, 'count': count})
        self.assertEqual("The request is malformed: Boom.", six.text_type(ex))
        mock_call.assert_called_once_with(
            req.context, 'cluster_scale_in2', obj)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__do_policy_attach(self, mock_call, mock_parse, _ign):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        data = {'policy_id': 'xxxx-yyyy'}
        mock_call.return_value = {'action': 'action-id'}
        obj = mock.Mock()
        mock_parse.return_value = obj

        resp = self.controller._do_policy_attach(req, cid, data)

        self.assertEqual({'action': 'action-id'}, resp)
        mock_parse.assert_called_once_with(
            'ClusterAttachPolicyRequest', req,
            {'identity': cid, 'policy_id': 'xxxx-yyyy'})
        mock_call.assert_called_once_with(
            req.context, 'cluster_policy_attach2', obj)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__do_policy_attach_not_map(self, mock_call, mock_parse, _ign):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        data = ['xxxx-yyyy']

        ex = self.assertRaises(exc.HTTPBadRequest,
                               self.controller._do_policy_attach,
                               req, cid, data)

        self.assertEqual("The data provided is not a map", six.text_type(ex))
        self.assertEqual(0, mock_parse.call_count)
        self.assertEqual(0, mock_call.called)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__do_policy_attach_failed_request(self, mock_call, mock_parse, _i):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        data = {'policy_id': 'xxxx-yyyy'}
        mock_parse.side_effect = exc.HTTPBadRequest('Boom')

        ex = self.assertRaises(exc.HTTPBadRequest,
                               self.controller._do_policy_attach,
                               req, cid, data)

        self.assertEqual("Boom", six.text_type(ex))
        mock_parse.assert_called_once_with(
            'ClusterAttachPolicyRequest', req,
            {'identity': cid, 'policy_id': 'xxxx-yyyy'})
        self.assertFalse(mock_call.called)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__do_policy_attach_failed_engine(self, mock_call, mock_parse, _i):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        data = {'policy_id': 'xxxx-yyyy'}
        obj = mock.Mock()
        mock_parse.return_value = obj
        mock_call.side_effect = senlin_exc.BadRequest(msg='Boom')

        ex = self.assertRaises(senlin_exc.BadRequest,
                               self.controller._do_policy_attach,
                               req, cid, data)

        mock_parse.assert_called_once_with(
            'ClusterAttachPolicyRequest', req,
            {'identity': cid, 'policy_id': 'xxxx-yyyy'})
        self.assertEqual("The request is malformed: Boom.", six.text_type(ex))
        mock_call.assert_called_once_with(
            req.context, 'cluster_policy_attach2', obj)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__do_policy_detach(self, mock_call, mock_parse, _ign):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        data = {'policy_id': 'xxxx-yyyy'}
        mock_call.return_value = {'action': 'action-id'}
        obj = mock.Mock()
        mock_parse.return_value = obj

        resp = self.controller._do_policy_detach(req, cid, data)

        self.assertEqual({'action': 'action-id'}, resp)
        mock_parse.assert_called_once_with(
            'ClusterDetachPolicyRequest', req,
            {'identity': cid, 'policy_id': 'xxxx-yyyy'})
        mock_call.assert_called_once_with(
            req.context, 'cluster_policy_detach2', obj)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__do_policy_detach_not_map(self, mock_call, mock_parse, _ign):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        data = ['xxxx-yyyy']

        ex = self.assertRaises(exc.HTTPBadRequest,
                               self.controller._do_policy_detach,
                               req, cid, data)

        self.assertEqual("The data provided is not a map", six.text_type(ex))
        self.assertEqual(0, mock_parse.call_count)
        self.assertEqual(0, mock_call.called)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__do_policy_detach_failed_request(self, mock_call, mock_parse, _i):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        data = {'policy_id': 'xxxx-yyyy'}
        mock_parse.side_effect = exc.HTTPBadRequest('Boom')

        ex = self.assertRaises(exc.HTTPBadRequest,
                               self.controller._do_policy_detach,
                               req, cid, data)

        self.assertEqual("Boom", six.text_type(ex))
        mock_parse.assert_called_once_with(
            'ClusterDetachPolicyRequest', req,
            {'identity': cid, 'policy_id': 'xxxx-yyyy'})
        self.assertFalse(mock_call.called)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__do_policy_detach_failed_engine(self, mock_call, mock_parse, _i):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        data = {'policy_id': 'xxxx-yyyy'}
        obj = mock.Mock()
        mock_parse.return_value = obj
        mock_call.side_effect = senlin_exc.BadRequest(msg='Boom')

        ex = self.assertRaises(senlin_exc.BadRequest,
                               self.controller._do_policy_detach,
                               req, cid, data)

        mock_parse.assert_called_once_with(
            'ClusterDetachPolicyRequest', req,
            {'identity': cid, 'policy_id': 'xxxx-yyyy'})
        self.assertEqual("The request is malformed: Boom.", six.text_type(ex))
        mock_call.assert_called_once_with(
            req.context, 'cluster_policy_detach2', obj)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__do_policy_update(self, mock_call, mock_parse, _ign):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        data = {'policy_id': 'xxxx-yyyy'}
        mock_call.return_value = {'action': 'action-id'}
        obj = mock.Mock()
        mock_parse.return_value = obj

        resp = self.controller._do_policy_update(req, cid, data)

        self.assertEqual({'action': 'action-id'}, resp)
        mock_parse.assert_called_once_with(
            'ClusterUpdatePolicyRequest', req,
            {'identity': cid, 'policy_id': 'xxxx-yyyy'})
        mock_call.assert_called_once_with(
            req.context, 'cluster_policy_update2', obj)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__do_policy_update_not_map(self, mock_call, mock_parse, _ign):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        data = ['xxxx-yyyy']

        ex = self.assertRaises(exc.HTTPBadRequest,
                               self.controller._do_policy_update,
                               req, cid, data)

        self.assertEqual("The data provided is not a map", six.text_type(ex))
        self.assertEqual(0, mock_parse.call_count)
        self.assertEqual(0, mock_call.called)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__do_policy_update_failed_request(self, mock_call, mock_parse, _i):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        data = {'policy_id': 'xxxx-yyyy'}
        mock_parse.side_effect = exc.HTTPBadRequest('Boom')

        ex = self.assertRaises(exc.HTTPBadRequest,
                               self.controller._do_policy_update,
                               req, cid, data)

        self.assertEqual("Boom", six.text_type(ex))
        mock_parse.assert_called_once_with(
            'ClusterUpdatePolicyRequest', req,
            {'identity': cid, 'policy_id': 'xxxx-yyyy'})
        self.assertFalse(mock_call.called)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__do_policy_update_failed_engine(self, mock_call, mock_parse, _i):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        data = {'policy_id': 'xxxx-yyyy'}
        obj = mock.Mock()
        mock_parse.return_value = obj
        mock_call.side_effect = senlin_exc.BadRequest(msg='Boom')

        ex = self.assertRaises(senlin_exc.BadRequest,
                               self.controller._do_policy_update,
                               req, cid, data)

        mock_parse.assert_called_once_with(
            'ClusterUpdatePolicyRequest', req,
            {'identity': cid, 'policy_id': 'xxxx-yyyy'})
        self.assertEqual("The request is malformed: Boom.", six.text_type(ex))
        mock_call.assert_called_once_with(
            req.context, 'cluster_policy_update2', obj)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__do_check(self, mock_call, mock_parse, _ignore):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        data = {'op': 'value'}
        obj = mock.Mock()
        mock_parse.return_value = obj
        eng_resp = {'action': 'action-id'}
        mock_call.return_value = eng_resp

        resp = self.controller._do_check(req, cid, data)

        self.assertEqual({'action': 'action-id'}, resp)
        mock_parse.assert_called_once_with(
            'ClusterCheckRequest', req,
            {'identity': cid, 'params': {'op': 'value'}})
        mock_call.assert_called_once_with(req.context, 'cluster_check2', obj)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__do_check_failed_request(self, mock_call, mock_parse, _ign):
        cid = 'fake-cluster'
        data = {}
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        mock_parse.side_effect = exc.HTTPBadRequest('Boom')

        ex = self.assertRaises(exc.HTTPBadRequest,
                               self.controller._do_check,
                               req, cid, data)

        self.assertEqual("Boom", six.text_type(ex))
        mock_parse.assert_called_once_with(
            'ClusterCheckRequest', req, {'identity': cid, 'params': {}})
        self.assertFalse(mock_call.called)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__do_check_failed_engine(self, mock_call, mock_parse, _i):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        data = {}
        obj = mock.Mock()
        mock_parse.return_value = obj
        mock_call.side_effect = senlin_exc.BadRequest(msg='Boom')

        ex = self.assertRaises(senlin_exc.BadRequest,
                               self.controller._do_check,
                               req, cid, data)

        mock_parse.assert_called_once_with(
            'ClusterCheckRequest', req, {'identity': cid, 'params': {}})
        self.assertEqual("The request is malformed: Boom.", six.text_type(ex))
        mock_call.assert_called_once_with(
            req.context, 'cluster_check2', obj)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__do_recover(self, mock_call, mock_parse, _ignore):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        data = {'op': 'value'}
        obj = mock.Mock()
        mock_parse.return_value = obj
        eng_resp = {'action': 'action-id'}
        mock_call.return_value = eng_resp

        resp = self.controller._do_recover(req, cid, data)

        self.assertEqual({'action': 'action-id'}, resp)
        mock_parse.assert_called_once_with(
            'ClusterRecoverRequest', req,
            {'identity': cid, 'params': {'op': 'value'}})
        mock_call.assert_called_once_with(req.context, 'cluster_recover2', obj)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__do_recover_failed_request(self, mock_call, mock_parse, _ign):
        cid = 'fake-cluster'
        data = {}
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        mock_parse.side_effect = exc.HTTPBadRequest('Boom')

        ex = self.assertRaises(exc.HTTPBadRequest,
                               self.controller._do_recover,
                               req, cid, data)

        self.assertEqual("Boom", six.text_type(ex))
        mock_parse.assert_called_once_with(
            'ClusterRecoverRequest', req, {'identity': cid, 'params': {}})
        self.assertFalse(mock_call.called)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test__do_recover_failed_engine(self, mock_call, mock_parse, _i):
        req = mock.Mock()
        cid = 'aaaa-bbbb-cccc'
        data = {}
        obj = mock.Mock()
        mock_parse.return_value = obj
        mock_call.side_effect = senlin_exc.BadRequest(msg='Boom')

        ex = self.assertRaises(senlin_exc.BadRequest,
                               self.controller._do_recover,
                               req, cid, data)

        mock_parse.assert_called_once_with(
            'ClusterRecoverRequest', req, {'identity': cid, 'params': {}})
        self.assertEqual("The request is malformed: Boom.", six.text_type(ex))
        mock_call.assert_called_once_with(
            req.context, 'cluster_recover2', obj)

    def test_cluster_action_missing_action(self, mock_enforce):
        self._mock_enforce_setup(mock_enforce, 'action', True)
        cid = 'aaaa-bbbb-cccc'
        body = {}
        req = self._post('/clusters/%s/actions' % cid, jsonutils.dumps(body))

        mock_call = self.patchobject(rpc_client.EngineClient, 'call')
        ex = self.assertRaises(exc.HTTPBadRequest,
                               self.controller.action,
                               req, cluster_id=cid, body=body)
        self.assertEqual('No action specified', six.text_type(ex))
        self.assertFalse(mock_call.called)

    def test_cluster_action_multiple_actions(self, mock_enforce):
        self._mock_enforce_setup(mock_enforce, 'action', True)
        cid = 'aaaa-bbbb-cccc'
        body = {'action_1': {}, 'action_2': {}}
        req = self._post('/clusters/%s/actions' % cid, jsonutils.dumps(body))

        mock_call = self.patchobject(rpc_client.EngineClient, 'call')
        ex = self.assertRaises(exc.HTTPBadRequest,
                               self.controller.action,
                               req, cluster_id=cid, body=body)
        self.assertEqual('Multiple actions specified', six.text_type(ex))
        self.assertFalse(mock_call.called)

    def test_cluster_action_unsupported_action(self, mock_enforce):
        self._mock_enforce_setup(mock_enforce, 'action', True)
        cid = 'aaaa-bbbb-cccc'
        body = {'fly': None}
        req = self._post('/clusters/%s/actions' % cid, jsonutils.dumps(body))

        mock_call = self.patchobject(rpc_client.EngineClient, 'call')
        ex = self.assertRaises(exc.HTTPBadRequest,
                               self.controller.action,
                               req, cluster_id=cid, body=body)
        self.assertEqual("Unrecognized action 'fly' specified",
                         six.text_type(ex))
        self.assertFalse(mock_call.called)

    def test_cluster_action_err_denied_policy(self, mock_enforce):
        self._mock_enforce_setup(mock_enforce, 'action', False)
        cid = 'aaaa-bbbb-cccc'
        body = {'someaction': {'param': 'value'}}

        req = self._post('/clusters/%s/actions' % cid, jsonutils.dumps(body))

        resp = shared.request_with_middleware(fault.FaultWrapper,
                                              self.controller.action,
                                              req, cluster_id=cid, body=body)

        self.assertEqual(403, resp.status_int)
        self.assertIn('403 Forbidden', six.text_type(resp))

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test_collect(self, mock_call, mock_parse, mock_enforce):
        req = mock.Mock(context=self.context)
        cid = 'aaaa-bbbb-cccc'
        path = 'foo.bar'
        eng_resp = {'cluster_attributes': [{'key': 'value'}]}
        mock_call.return_value = eng_resp
        obj = vorc.ClusterResizeRequest(identity=cid, path=path)
        mock_parse.return_value = obj

        resp = self.controller.collect(req, cluster_id=cid, path=path)

        self.assertEqual(eng_resp, resp)
        mock_call.assert_called_once_with(req.context, 'cluster_collect2', obj)

    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test_collect_version_mismatch(self, mock_call, mock_enforce):
        # NOTE: we skip the mock_enforce setup below because api version check
        #       comes before the policy enforcement and the check fails in
        #       this test case.
        cid = 'aaaa-bbbb-cccc'
        path = 'foo.bar'
        req = self._get('/clusters/%(cid)s/attrs/%(path)s' %
                        {'cid': cid, 'path': path}, version='1.1')

        ex = self.assertRaises(senlin_exc.MethodVersionNotFound,
                               self.controller.collect,
                               req, cluster_id=cid, path=path)

        self.assertEqual(0, mock_call.call_count)
        self.assertEqual('API version 1.1 is not supported on this method.',
                         six.text_type(ex))

    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test_collect_path_not_provided(self, mock_call, mock_enforce):
        self._mock_enforce_setup(mock_enforce, 'collect', True)
        req = mock.Mock(context=self.context)
        cid = 'aaaa-bbbb-cccc'
        path = '    '
        req = self._get('/clusters/%(cid)s/attrs/%(path)s' %
                        {'cid': cid, 'path': path}, version='1.2')

        ex = self.assertRaises(exc.HTTPBadRequest,
                               self.controller.collect,
                               req, cluster_id=cid, path=path)

        self.assertEqual('Required path attribute is missing.',
                         six.text_type(ex))
        self.assertEqual(0, mock_call.call_count)

    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test_collect_path_is_none(self, mock_call, mock_enforce):
        self._mock_enforce_setup(mock_enforce, 'collect', True)
        req = mock.Mock(context=self.context)
        cid = 'aaaa-bbbb-cccc'
        path = 'None'
        req = self._get('/clusters/%(cid)s/attrs/%(path)s' %
                        {'cid': cid, 'path': path}, version='1.2')

        ex = self.assertRaises(exc.HTTPBadRequest,
                               self.controller.collect,
                               req, cluster_id=cid, path=path)

        self.assertEqual('Required path attribute is missing.',
                         six.text_type(ex))
        self.assertEqual(0, mock_call.call_count)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test_collect_failed_request(self, mock_call, mock_parse, mock_enforce):
        self._mock_enforce_setup(mock_enforce, 'collect', True)
        req = mock.Mock(context=self.context)
        cid = 'aaaa-bbbb-cccc'
        path = 'foo.bar'
        mock_parse.side_effect = exc.HTTPBadRequest('Boom')

        ex = self.assertRaises(exc.HTTPBadRequest,
                               self.controller.collect,
                               req, cluster_id=cid, path=path)

        self.assertEqual("Boom", six.text_type(ex))
        mock_parse.assert_called_once_with(
            'ClusterCollectRequest', req, {'identity': cid, 'path': path})
        self.assertFalse(mock_call.called)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test_collect_failed_engine(self, mock_call, mock_parse, mock_enforce):
        self._mock_enforce_setup(mock_enforce, 'collect', True)
        req = mock.Mock(context=self.context)
        cid = 'aaaa-bbbb-cccc'
        path = 'foo.bar'
        obj = mock.Mock()
        mock_parse.return_value = obj
        mock_call.side_effect = senlin_exc.BadRequest(msg='Boom')

        ex = self.assertRaises(senlin_exc.BadRequest,
                               self.controller.collect,
                               req, cluster_id=cid, path=path)

        mock_parse.assert_called_once_with(
            'ClusterCollectRequest', req, {'identity': cid, 'path': path})
        self.assertEqual("The request is malformed: Boom.", six.text_type(ex))
        mock_call.assert_called_once_with(
            req.context, 'cluster_collect2', obj)

    def test_collect_denied_policy(self, mock_enforce):
        self._mock_enforce_setup(mock_enforce, 'collect', False)
        cid = 'aaaa-bbbb-cccc'
        path = 'foo.bar'
        req = self._get('/clusters/%(cid)s/attrs/%(path)s' %
                        {'cid': cid, 'path': path}, version='1.2')
        mock_call = self.patchobject(rpc_client.EngineClient, 'call2')

        resp = shared.request_with_middleware(fault.FaultWrapper,
                                              self.controller.collect,
                                              req, cluster_id=cid, path=path)

        self.assertEqual(403, resp.status_int)
        self.assertIn('403 Forbidden', six.text_type(resp))
        self.assertEqual(0, mock_call.call_count)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test_delete(self, mock_call, mock_parse, mock_enforce):
        self._mock_enforce_setup(mock_enforce, 'delete', True)
        req = mock.Mock(context=self.context)
        cid = 'aaaa-bbbb-cccc'
        obj = mock.Mock()
        mock_parse.return_value = obj
        mock_call.return_value = {'action': 'FAKE_ID'}

        res = self.controller.delete(req, cluster_id=cid)

        result = {'location': '/actions/FAKE_ID'}
        self.assertEqual(result, res)
        mock_parse.assert_called_once_with(
            'ClusterDeleteRequest', req, {'identity': cid})

        mock_call.assert_called_with(req.context, 'cluster_delete2', obj)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test_delete_failed_request(self, mock_call, mock_parse, mock_enforce):
        self._mock_enforce_setup(mock_enforce, 'delete', True)
        cid = 'fake-cluster'
        req = mock.Mock(context=self.context)
        mock_parse.side_effect = exc.HTTPBadRequest('Boom')

        ex = self.assertRaises(exc.HTTPBadRequest,
                               self.controller.delete,
                               req, cluster_id=cid)

        self.assertEqual("Boom", six.text_type(ex))
        mock_parse.assert_called_once_with(
            'ClusterDeleteRequest', req, {'identity': cid})
        self.assertFalse(mock_call.called)

    @mock.patch.object(util, 'parse_request')
    @mock.patch.object(rpc_client.EngineClient, 'call2')
    def test_delete_failed_engine(self, mock_call, mock_parse, mock_enforce):
        self._mock_enforce_setup(mock_enforce, 'delete', True)
        req = mock.Mock(context=self.context)
        cid = 'aaaa-bbbb-cccc'
        req = self._delete('/clusters/%s' % cid)
        error = senlin_exc.ResourceNotFound(type='cluster', id=cid)
        mock_call.side_effect = shared.to_remote_error(error)
        obj = mock.Mock()
        mock_parse.return_value = obj

        resp = shared.request_with_middleware(fault.FaultWrapper,
                                              self.controller.delete,
                                              req, cluster_id=cid)

        self.assertEqual(404, resp.json['code'])
        self.assertEqual('ResourceNotFound', resp.json['error']['type'])

    def test_delete_err_denied_policy(self, mock_enforce):
        self._mock_enforce_setup(mock_enforce, 'delete', False)
        cid = 'aaaa-bbbb-cccc'
        req = self._delete('/clusters/%s' % cid)
        resp = shared.request_with_middleware(fault.FaultWrapper,
                                              self.controller.delete,
                                              req, cluster_id=cid)

        self.assertEqual(403, resp.status_int)
        self.assertIn('403 Forbidden', six.text_type(resp))
