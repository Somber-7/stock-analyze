import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import Mock
from backend.ai.operation_api import router, get_operation


class OperationApiTests(unittest.TestCase):
    def setUp(self):
        self.service = Mock()
        self.service.snapshot.return_value = {'version':1,'running':False,'busy':False}
        self.service.analyze.return_value = {'version':2,'busy':True}
        self.service.execute.return_value = {'version':2}
        self.service.control.return_value = {'version':2}
        self.service.holdings.return_value = [{'code':'0011T0','name':'채비','quantity':1}]
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_operation] = lambda: self.service
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def post(self, path, body):
        return self.client.post('/api/ai/operation'+path, json=body, headers={'X-AI-Action':'manage'})

    def test_read_only_poll_does_not_start_analysis(self):
        self.assertEqual(self.client.get('/api/ai/operation').status_code, 200)
        self.service.analyze.assert_not_called()
        self.service.execute.assert_not_called()
        self.service.holdings.assert_not_called()
        self.assertEqual(self.client.get('/api/ai/operation/holdings').json()[0]['name'], '채비')

    def test_header_and_strict_inputs_prevent_accidental_mutation(self):
        self.assertEqual(self.client.post('/api/ai/operation/analyze',json={'version':1}).status_code,422)
        for body in ({'version':'1'}, {'version':1,'api_key':'secret-test'}, {'version':True}):
            response = self.post('/analyze', body)
            self.assertEqual(response.status_code,422)
            self.assertNotIn('secret-test', response.text)
        self.service.analyze.assert_not_called()
        self.assertEqual(self.post('/analyze',{'version':1}).status_code,200)
        self.service.analyze.assert_called_once_with(1)

    def test_execution_mode_cannot_be_overridden_by_body(self):
        response = self.post('/runs/a/execute',{'version':2,'code':'0011T0','mode':'live'})
        self.assertEqual(response.status_code,422)
        self.assertEqual(self.post('/runs/a/execute',{'version':2,'code':'0011T0'}).status_code,200)
        self.service.execute.assert_called_once_with('a',version=2,code='0011T0',live_acknowledged=False)

    def test_unexpected_errors_do_not_echo_secrets(self):
        self.service.snapshot.side_effect = RuntimeError('secret-test')
        response = self.client.get('/api/ai/operation')
        self.assertEqual(response.status_code,502)
        self.assertNotIn('secret-test',response.text)

    def test_observations_are_explicit_and_do_not_accept_order_or_version_fields(self):
        self.service.observe.return_value={'status':'ready','items':[]}
        self.service.inputs.return_value={'schema_version':1}
        self.assertEqual(self.client.get('/api/ai/operation/runs/a/inputs').json(),{'schema_version':1})
        self.assertEqual(self.client.post('/api/ai/operation/runs/a/outcomes',json={}).status_code,422)
        self.assertEqual(self.post('/runs/a/outcomes',{'version':1}).status_code,422)
        self.assertEqual(self.post('/runs/a/outcomes',{}).status_code,200)
        self.service.observe.assert_called_once_with('a')
        self.service.analyze.assert_not_called()
        self.service.execute.assert_not_called()


if __name__ == '__main__': unittest.main()
