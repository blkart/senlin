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

import mock

from oslo_messaging.rpc import dispatcher as rpc
from oslo_utils import uuidutils
import six

from senlin.common import consts
from senlin.common import exception as exc
from senlin.engine import service
from senlin.objects import event as eo
from senlin.objects.requests import events as oreo
from senlin.tests.unit.common import base
from senlin.tests.unit.common import utils


class EventTest(base.SenlinTestCase):

    def setUp(self):
        super(EventTest, self).setUp()
        self.ctx = utils.dummy_context(project='event_test_project')
        self.eng = service.EngineService('host-a', 'topic-a')

    @mock.patch.object(eo.Event, 'get')
    def test_event_find_by_uuid(self, mock_get):
        x_event = mock.Mock()
        mock_get.return_value = x_event
        aid = uuidutils.generate_uuid()

        result = self.eng.event_find(self.ctx, aid)

        self.assertEqual(x_event, result)
        mock_get.assert_called_once_with(self.ctx, aid, project_safe=True)

    @mock.patch.object(eo.Event, 'get_by_short_id')
    @mock.patch.object(eo.Event, 'get')
    def test_event_find_by_short_id(self, mock_get, mock_shortid):
        mock_get.return_value = None
        x_event = mock.Mock()
        mock_shortid.return_value = x_event
        aid = uuidutils.generate_uuid()

        result = self.eng.event_find(self.ctx, aid, False)

        self.assertEqual(x_event, result)
        mock_get.assert_called_once_with(self.ctx, aid, project_safe=False)
        mock_shortid.assert_called_once_with(self.ctx, aid, project_safe=False)

    @mock.patch.object(eo.Event, 'get_by_short_id')
    def test_event_find_by_short_id_directly(self, mock_shortid):
        x_event = mock.Mock()
        mock_shortid.return_value = x_event
        aid = 'abcdef'

        result = self.eng.event_find(self.ctx, aid)

        self.assertEqual(x_event, result)
        mock_shortid.assert_called_once_with(self.ctx, aid, project_safe=True)

    @mock.patch.object(eo.Event, 'get_by_short_id')
    def test_event_find_not_found(self, mock_shortid):
        mock_shortid.return_value = None

        ex = self.assertRaises(exc.ResourceNotFound,
                               self.eng.event_find,
                               self.ctx, 'BOGUS')
        self.assertEqual("The event (BOGUS) could not be found.",
                         six.text_type(ex))
        mock_shortid.assert_called_once_with(self.ctx, 'BOGUS',
                                             project_safe=True)

    @mock.patch.object(eo.Event, 'get_all')
    def test_event_list(self, mock_load):
        obj_1 = mock.Mock()
        obj_1.as_dict.return_value = {'level': '10'}
        obj_2 = mock.Mock()
        obj_2.as_dict.return_value = {'level': '20'}

        mock_load.return_value = [obj_1, obj_2]

        result = self.eng.event_list(self.ctx)

        self.assertEqual([{'level': 'DEBUG'}, {'level': 'INFO'}], result)
        mock_load.assert_called_once_with(self.ctx, filters=None, sort=None,
                                          limit=None, marker=None,
                                          project_safe=True)

    @mock.patch.object(eo.Event, 'get_all')
    def test_event_list_with_params(self, mock_load):
        obj_1 = mock.Mock()
        obj_1.as_dict.return_value = {'level': '10'}
        obj_2 = mock.Mock()
        obj_2.as_dict.return_value = {'level': '20'}

        mock_load.return_value = [obj_1, obj_2]

        result = self.eng.event_list(self.ctx, filters='FFF', sort='level',
                                     limit=123, marker='MMM',
                                     project_safe=True)

        self.assertEqual([{'level': 'DEBUG'}, {'level': 'INFO'}], result)
        mock_load.assert_called_once_with(self.ctx,
                                          filters='FFF', sort='level',
                                          limit=123, marker='MMM',
                                          project_safe=True)

    def test_event_list_bad_limit(self):
        ex = self.assertRaises(rpc.ExpectedException,
                               self.eng.event_list,
                               self.ctx, limit='MANY')

        self.assertEqual(exc.InvalidParameter, ex.exc_info[0])
        self.assertEqual("Invalid value 'MANY' specified for 'limit'",
                         six.text_type(ex.exc_info[1]))

    def test_event_list_bad_sort(self):
        ex = self.assertRaises(rpc.ExpectedException,
                               self.eng.event_list,
                               self.ctx, sort='crazykey')

        self.assertEqual(exc.InvalidParameter, ex.exc_info[0])
        self.assertEqual("Invalid value 'crazykey' specified for 'sort key'",
                         six.text_type(ex.exc_info[1]))

    def test_event_list_bad_project_safe(self):
        ex = self.assertRaises(rpc.ExpectedException,
                               self.eng.event_list,
                               self.ctx, project_safe='yes')

        self.assertEqual(exc.InvalidParameter, ex.exc_info[0])
        self.assertEqual("Invalid value 'yes' specified for 'project_safe'",
                         six.text_type(ex.exc_info[1]))

    @mock.patch.object(eo.Event, 'get_all')
    def test_event_list_with_project_safe(self, mock_load):
        mock_load.return_value = []

        result = self.eng.event_list(self.ctx)
        self.assertEqual([], result)
        mock_load.assert_called_once_with(self.ctx, filters=None, limit=None,
                                          sort=None, marker=None,
                                          project_safe=True)
        mock_load.reset_mock()

        ex = self.assertRaises(rpc.ExpectedException,
                               self.eng.event_list,
                               self.ctx, project_safe=False)
        self.assertEqual(exc.Forbidden, ex.exc_info[0])

        self.ctx.is_admin = True

        result = self.eng.event_list(self.ctx)
        self.assertEqual([], result)
        mock_load.assert_called_once_with(self.ctx, filters=None, limit=None,
                                          sort=None, marker=None,
                                          project_safe=True)
        mock_load.reset_mock()

        result = self.eng.event_list(self.ctx, project_safe=True)
        self.assertEqual([], result)
        mock_load.assert_called_once_with(self.ctx, filters=None, limit=None,
                                          sort=None, marker=None,
                                          project_safe=True)
        mock_load.reset_mock()

        result = self.eng.event_list(self.ctx, project_safe=False)
        self.assertEqual([], result)
        mock_load.assert_called_once_with(self.ctx, filters=None, limit=None,
                                          sort=None, marker=None,
                                          project_safe=False)

    @mock.patch.object(eo.Event, 'get_all')
    def test_event_list_empty(self, mock_load):
        mock_load.return_value = []

        result = self.eng.event_list(self.ctx)

        self.assertEqual([], result)
        mock_load.assert_called_once_with(self.ctx, filters=None, sort=None,
                                          limit=None, marker=None,
                                          project_safe=True)

    @mock.patch.object(eo.Event, 'get_all')
    def test_event_list2(self, mock_load):
        obj_1 = mock.Mock()
        obj_1.as_dict.return_value = {'level': consts.EVENT_LEVELS['DEBUG']}
        obj_2 = mock.Mock()
        obj_2.as_dict.return_value = {'level': consts.EVENT_LEVELS['INFO']}

        mock_load.return_value = [obj_1, obj_2]

        req = oreo.EventListRequest()
        result = self.eng.event_list2(self.ctx, req.obj_to_primitive())
        expected = [{'level': 'DEBUG'}, {'level': 'INFO'}]

        self.assertEqual(expected, result)
        mock_load.assert_called_once_with(self.ctx, project_safe=True)

    @mock.patch.object(eo.Event, 'get_all')
    def test_event_list2_with_params(self, mock_load):
        obj_1 = mock.Mock()
        obj_1.as_dict.return_value = {'level': consts.EVENT_LEVELS['DEBUG']}
        obj_2 = mock.Mock()
        obj_2.as_dict.return_value = {'level': consts.EVENT_LEVELS['INFO']}

        mock_load.return_value = [obj_1, obj_2]

        marker_uuid = '8216a86c-1bdc-442e-b493-329385d37cbc'
        req = oreo.EventListRequest(level=['DEBUG', 'INFO'],
                                    limit=123,
                                    marker=marker_uuid,
                                    sort=consts.EVENT_TIMESTAMP,
                                    project_safe=True)
        result = self.eng.event_list2(self.ctx, req.obj_to_primitive())
        expected = [{'level': 'DEBUG'}, {'level': 'INFO'}]
        self.assertEqual(expected, result)

        filters = {'level': [consts.EVENT_LEVELS['DEBUG'],
                             consts.EVENT_LEVELS['INFO']]}
        mock_load.assert_called_once_with(self.ctx, filters=filters,
                                          sort=consts.EVENT_TIMESTAMP,
                                          limit=123,
                                          marker=marker_uuid,
                                          project_safe=True)

    def test_event_list2_with_bad_params(self):
        req = oreo.EventListRequest(project_safe=False)
        ex = self.assertRaises(rpc.ExpectedException,
                               self.eng.event_list2,
                               self.ctx, req.obj_to_primitive())
        self.assertEqual(exc.Forbidden, ex.exc_info[0])

    @mock.patch.object(eo.Event, 'get_all')
    def test_event_list2_with_Auth(self, mock_load):
        mock_load.return_value = []

        req = oreo.EventListRequest(project_safe=True)
        result = self.eng.event_list2(self.ctx, req.obj_to_primitive())
        self.assertEqual([], result)
        mock_load.assert_called_once_with(self.ctx, project_safe=True)

        self.ctx.is_admin = True

        mock_load.reset_mock()
        req = oreo.EventListRequest(project_safe=True)
        result = self.eng.event_list2(self.ctx, req.obj_to_primitive())
        self.assertEqual([], result)
        mock_load.assert_called_once_with(self.ctx, project_safe=True)

        mock_load.reset_mock()
        req = oreo.EventListRequest(project_safe=False)
        result = self.eng.event_list2(self.ctx, req.obj_to_primitive())
        self.assertEqual([], result)
        mock_load.assert_called_once_with(self.ctx, project_safe=False)

    @mock.patch.object(service.EngineService, 'event_find')
    def test_event_get(self, mock_find):
        x_event = mock.Mock()
        x_event.as_dict.return_value = {'level': '30'}
        mock_find.return_value = x_event

        res = self.eng.event_get(self.ctx, 'level')

        self.assertEqual({'level': 'WARNING'}, res)
        mock_find.assert_called_once_with(self.ctx, 'level')

    @mock.patch.object(service.EngineService, 'event_find')
    def test_event_get_not_found(self, mock_find):
        mock_find.side_effect = exc.ResourceNotFound(type='event', id='BOGUS')

        ex = self.assertRaises(rpc.ExpectedException,
                               self.eng.event_get,
                               self.ctx, 'BOGUS')

        self.assertEqual(exc.ResourceNotFound, ex.exc_info[0])
        mock_find.assert_called_once_with(self.ctx, 'BOGUS')

    @mock.patch.object(service.EngineService, 'event_find')
    def test_event_get2(self, mock_find):
        x_event = mock.Mock()
        x_event.as_dict.return_value = {'level': consts.EVENT_LEVELS['DEBUG']}
        mock_find.return_value = x_event

        req = oreo.EventGetRequest(identity='EVENT_ID')
        result = self.eng.event_get2(self.ctx, req.obj_to_primitive())

        self.assertEqual({'level': 'DEBUG'}, result)
        mock_find.assert_called_once_with(self.ctx, 'EVENT_ID')

    @mock.patch.object(service.EngineService, 'event_find')
    def test_event_get2_not_found(self, mock_find):
        mock_find.side_effect = exc.ResourceNotFound(type='event', id='BOGUS')
        req = oreo.EventGetRequest(identity='BOGUS')
        ex = self.assertRaises(rpc.ExpectedException,
                               self.eng.event_get2,
                               self.ctx, req.obj_to_primitive())

        self.assertEqual(exc.ResourceNotFound, ex.exc_info[0])
        mock_find.assert_called_once_with(self.ctx, 'BOGUS')
