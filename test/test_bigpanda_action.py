#!/usr/bin/python
import pytest
import subprocess
import os
import time
import sys
import ConfigParser

import server

PORT = 8000
SCRIPT_TIMEOUT = 10

current_dir = os.path.dirname(__file__)

def run_script(args, timeout=SCRIPT_TIMEOUT):
    env = dict(BP_BASE_URL='http://localhost:%d' % PORT)
    cmd = "%s/../bigpanda-alert/bigpanda_alert.py" % current_dir
    script = subprocess.Popen([cmd] + args, env=env)
    
    if timeout:
        ret = timed_poll(script, timeout)
        if ret is None:
            script.kill()

    return script

def timed_poll(proc, timeout):
    "Poll a subprocess.Popen instance with a timeout."

    wait_time = 0
    while wait_time < timeout:
        status = proc.poll()
        if status is not None:
            return status
        time.sleep(1)
        wait_time += 1

@pytest.fixture()
def config_file(request):
    config_path = "%s/../bigpanda-alert/config.ini" % current_dir
    os.rename(config_path, config_path + '.test_orig')
    new_config = file(config_path, 'w', buffering=0)

    def fin():
        new_config.close()
        os.remove(config_path)
        os.rename(config_path + '.test_orig', config_path)
    request.addfinalizer(fin)

    return new_config

@pytest.fixture()
def config_obj():
    config = ConfigParser.SafeConfigParser()
    config.add_section('base')
    config.set('base', 'api_token', '')
    config.set('base', 'app_key', '')
    config.set('base', 'logging', 'no')

    return config

def mkargs(alert_info):
    args = []
    for k in ["app_name", "app_id", "pvn_alert_time", "priority", "severity", "tag", "health_rule_name", "health_rule_id", "pvn_time_period_in_minutes", "affected_entity_type", "affected_entity_name", "affected_entity_id"]:
        args.append(alert_info[k])

    number_of_evaluation_entities = len(alert_info['evaluation_entities'])
    args.append(number_of_evaluation_entities)
    if number_of_evaluation_entities:
        for entity in alert_info['evaluation_entities']:
            for k in ["evaluation_entity_type", "evaluation_entity_name", "evaluation_entity_id"]:
                args.append(entity[k])
            number_of_triggered_conditions = len(entity['triggered_conditions'])
            args.append(number_of_triggered_conditions)
            if number_of_triggered_conditions:
                for condition in entity['triggered_conditions']:
                    for k in ["scope_type", "scope_name", "scope_id", "condition_name", "condition_id", "operator", "condition_unit_type", "use_default_baseline", "baseline_name", "baseline_id", "threshold_value", "observed_value"]:
                        if k in condition:
                            args.append(condition[k])

    for k in ["summary_message", "incident_id", "deep_link_url", "event_type"]:
        args.append(alert_info[k])

    args = [ '"%s"' % str(x) for x in args ]
    return args

def get_alert_info(event_type, condition_unit_type=None, baseline_name_id=None, num_entities=1, num_conditions=1):
    alert_info = {
        "app_name": "app",
        "app_id": "4",
        "pvn_alert_time": "Sun Mar 22 16:29:22 UTC 2015",
        "priority": "1",
        "severity": "WARN",
        "tag": "sometag",
        "health_rule_name": "healthrule1",
        "health_rule_id": "21",
        "pvn_time_period_in_minutes": "1",
        "affected_entity_type": "APPLICATION_COMPONENT",
        "affected_entity_name": "tier1",
        "affected_entity_id": "12",
        "evaluation_entities": [],
        "summary_message": "some message summary",
        "incident_id": "71",
        "deep_link_url": "http://appdynamics:8090/controller/#location=APP_INCIDENT_DETAIL&incident=",
        "event_type": event_type,
    }

    for entity in xrange(num_entities):
        e_id = str(10 + entity)
        e_name = "node%s" % e_id
        eval_entity = {
            "evaluation_entity_type": "APPLICATION_COMPONENT_NODE",
            "evaluation_entity_name": e_name,
            "evaluation_entity_id": e_id,
            "triggered_conditions": []
        }
        for condition in xrange(num_conditions):
            c_id = str(14 + condition)
            c_name = "condition%s" % c_id
            triggered_condition = {
                "scope_type": "APPLICATION_COMPONENT_NODE",
                "scope_name": e_name,
                "scope_id": e_id,
                "condition_name": c_name,
                "condition_id": c_id,
                "operator": "GREATER_THAN",
            }
            if not condition_unit_type:
                raise ValueError("Missing condition unit type")
            triggered_condition['condition_unit_type'] = condition_unit_type
            if condition_unit_type.startswith("BASELINE_"):
                if baseline_name_id:
                    triggered_condition['use_default_baseline'] = False
                    triggered_condition['baseline_name'] = baseline_name_id[0]
                    triggered_condition['baseline_id'] = str(baseline_name_id[1])
                else:
                    triggered_condition['use_default_baseline'] = True
            triggered_condition['threshold_value'] = "10.0"
            triggered_condition['observed_value'] = "13.0"

            eval_entity['triggered_conditions'].append(triggered_condition)
        alert_info['evaluation_entities'].append(eval_entity)

    return alert_info


httpd = server.MockServer(PORT)

class TestAppdAction:
    @pytest.fixture(autouse=True, scope='class')
    def mock_httpd(self):
        httpd.serve_forever()

    @pytest.fixture(autouse=True, scope='function')
    def clean_request_info(self):
        httpd.request_info = dict()

    def test_run_no_args(self):
        script = run_script([])
        
        assert script.returncode == 0

        # No request was made
        assert httpd.request_info == dict()

    def test_run_healthrule_absolute_open(self):
        alert_info = get_alert_info('POLICY_OPEN_WARNING', 'ABSOLUTE')
        script_args = mkargs(alert_info)

        script = run_script(script_args)

        assert script.returncode == 0
        body = server.to_json(httpd.request_info)

        assert body == alert_info

    def test_run_healthrule_absolute_close(self):
        alert_info = get_alert_info('POLICY_CLOSE_WARNING', 'ABSOLUTE', num_entities=0)
        script_args = mkargs(alert_info)

        script = run_script(script_args)

        assert script.returncode == 0
        body = server.to_json(httpd.request_info)

        assert body == alert_info

    def test_run_healthrule_absolute_cancel(self):
        alert_info = get_alert_info('POLICY_CANCELED_WARNING', 'ABSOLUTE', num_entities=0)
        script_args = mkargs(alert_info)

        script = run_script(script_args)

        assert script.returncode == 0
        body = server.to_json(httpd.request_info)

        assert body == alert_info

    def test_run_healthrule_baseline_default(self):
        alert_info = get_alert_info('POLICY_OPEN_WARNING', 'BASELINE_PERCENTAGE')
        script_args = mkargs(alert_info)

        script = run_script(script_args)

        assert script.returncode == 0
        body = server.to_json(httpd.request_info)

        assert body == alert_info

    def test_run_healthrule_baseline_custom(self):
        alert_info = get_alert_info('POLICY_OPEN_WARNING', 'BASELINE_PERCENTAGE', ['baseline', 1234])
        script_args = mkargs(alert_info)

        script = run_script(script_args)

        assert script.returncode == 0
        body = server.to_json(httpd.request_info)

        assert body == alert_info

    def test_request_metadata(self, config_file, config_obj):
        app_key = 'key123'
        api_token = 'token123'
        config_obj.set('base', 'app_key', app_key)
        config_obj.set('base', 'api_token', api_token)
        config_obj.write(config_file)

        alert_info = get_alert_info('POLICY_OPEN_WARNING', 'ABSOLUTE')
        script_args = mkargs(alert_info)

        script = run_script(script_args)

        assert script.returncode == 0
        assert httpd.request_info['command'] == 'POST'
        assert httpd.request_info['path'] == '/data/integrations/appdynamics?app_key=' + app_key
        assert httpd.request_info['headers']['authorization'] == 'Bearer ' + api_token
