"""Check mission model routing and sensor contracts without a ROS installation."""

import ast
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / 'SITL_Models/Gazebo/models'
WORLDS = ROOT / 'gz_ws/src/asv_wave_sim/gz-waves-models/worlds'
LAUNCHES = ROOT / 'gz_ws/src/move_blueboat/launch'
MISSION_LEVELS = {'0': 1, '1a': 1, '1b': 2, '2a': 3, '2b': 4, '3': 5}


def model(name):
    return ET.parse(MODELS / name / 'model.sdf').getroot().find('model')


def calls(tree, name):
    return [node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name) and node.func.id == name]


def keyword(call, name):
    return next(item.value for item in call.keywords if item.arg == name)


class MissionModelTests(unittest.TestCase):
    def test_single_boat_worlds_preserve_runtime_name(self):
        for mission, level in MISSION_LEVELS.items():
            with self.subTest(mission=mission):
                world = ET.parse(WORLDS / f'level{level}.sdf').getroot().find('world')
                boats = [inc for inc in world.findall('include')
                         if inc.findtext('uri', '').startswith('model://blueboat')]
                self.assertEqual(len(boats), 1)
                resource = 'blueboat_lite' if level < 5 else 'blueboat_qgc'
                self.assertEqual(boats[0].findtext('uri'), f'model://{resource}')
                self.assertEqual(boats[0].findtext('name'), 'blueboat')
                sdf = model(resource)
                self.assertEqual(sdf.get('name'), resource)
                self.assertEqual(sdf.findtext("plugin[@name='ArduPilotPlugin']/fdm_port_in").strip(), '9002')
                self.assertEqual(sdf.findtext("plugin[@name='ArduPilotPlugin']/imuName"), 'imu_link::imu_sensor')

    def test_lite_has_navigation_but_no_lidar_or_dangling_joints(self):
        sdf = model('blueboat_lite')
        types = {sensor.get('type') for sensor in sdf.findall('.//sensor')}
        self.assertEqual(types, {'camera', 'imu', 'navsat'})
        self.assertIsNone(sdf.find("link[@name='bathymetry_link']"))
        self.assertIsNone(sdf.find("joint[@name='bathymetry_joint']"))
        for resource in ('blueboat_lite', 'blueboat_qgc'):
            sdf = model(resource)
            links = {link.get('name') for link in sdf.findall('link')}
            for joint in sdf.findall('joint'):
                with self.subTest(resource=resource, joint=joint.get('name')):
                    self.assertIn(joint.findtext('parent'), links)
                    self.assertIn(joint.findtext('child'), links)

    def test_mission3_retains_current_bathymetry_configuration(self):
        for tag in ('link', 'joint'):
            name = 'bathymetry_link' if tag == 'link' else 'bathymetry_joint'
            xpath = f"{tag}[@name='{name}']"
            self.assertEqual(ET.tostring(model('blueboat_qgc').find(xpath)),
                             ET.tostring(model('blueboat').find(xpath)))
        self.assertEqual(model('blueboat_qgc').findtext('.//sensor[@type="gpu_lidar"]/topic'), 'bathymetry/scan')

    def test_qgc_cameras_match_launch_enable_topics(self):
        for resource in ('blueboat_lite', 'blueboat_qgc'):
            with self.subTest(resource=resource):
                camera = model(resource).find('.//sensor[@type="camera"]')
                self.assertEqual(camera.findtext('topic'), '/camera')
                self.assertIsNone(camera.find('camera/trigger_topic'))
                self.assertNotEqual(camera.findtext('camera/triggered'), 'true')
                self.assertEqual(camera.findtext('update_rate'), '16')
                self.assertEqual(camera.findtext('camera/image/width'), '256')
                self.assertEqual(camera.findtext('camera/image/height'), '256')
                plugins = camera.findall('plugin')
                self.assertEqual(len(plugins), 1)
                self.assertEqual(plugins[0].get('filename'), 'libGstCameraPlugin.so')
                self.assertEqual(plugins[0].findtext('udp_host'), '127.0.0.1')
                self.assertEqual(plugins[0].findtext('udp_port'), '5600')
                self.assertEqual(plugins[0].findtext('use_basic_pipeline'), 'true')

    def test_model_configs_and_shared_mesh_assets_resolve(self):
        for resource in ('blueboat_lite', 'blueboat_qgc'):
            config = ET.parse(MODELS / resource / 'model.config').getroot()
            self.assertTrue((MODELS / resource / config.findtext('sdf')).is_file())
            uris = model(resource).findall('.//mesh/uri')
            self.assertTrue(uris)
            for uri in uris:
                with self.subTest(resource=resource, uri=uri.text):
                    self.assertTrue(uri.text.startswith('model://blueboat/meshes/'))
                    self.assertTrue((MODELS / uri.text.removeprefix('model://')).is_file())

    def test_launch_world_and_delayed_stream_activation(self):
        for mission, level in MISSION_LEVELS.items():
            with self.subTest(mission=mission):
                tree = ast.parse((LAUNCHES / f'mission{mission}_sim.launch.py').read_text())
                commands = [ast.literal_eval(keyword(call, 'cmd'))
                            for call in calls(tree, 'ExecuteProcess')]
                gazebo = next(cmd for cmd in commands if 'sim' in cmd)
                self.assertEqual(gazebo[-1], f'level{level}.sdf')
                timers = calls(tree, 'TimerAction')
                self.assertEqual(len(timers), 1)
                self.assertEqual(ast.literal_eval(keyword(timers[0], 'period')), 10.0)
                self.assertIn(['gz', 'topic', '-t', '/camera/enable_streaming',
                               '-m', 'gz.msgs.Boolean', '-p', 'data: true'], commands)
                nodes = calls(tree, 'Node')
                packages = [ast.literal_eval(keyword(node, 'package')) for node in nodes]
                self.assertNotIn('blueboat_camera_manager', packages)
                bridge = next(node for node in nodes
                              if ast.literal_eval(keyword(node, 'executable')) == 'parameter_bridge')
                args = ast.literal_eval(keyword(bridge, 'arguments'))
                self.assertFalse(any('qgc_camera_link' in arg or '/laser_scan' in arg for arg in args))
                if mission != '3':
                    self.assertIn('/camera@sensor_msgs/msg/Image[ignition.msgs.Image', args)
                    self.assertFalse(any('bathymetry' in arg for arg in args))
                else:
                    self.assertIn('/bathymetry/scan@sensor_msgs/msg/LaserScan@ignition.msgs.LaserScan', args)
                    mapper = next(node for node in nodes
                                  if ast.literal_eval(keyword(node, 'executable')) == 'bathymetry_mapper')
                    params = ast.literal_eval(keyword(mapper, 'parameters'))[0]
                    self.assertEqual(params['scan_topic'], '/bathymetry/scan')
                    self.assertEqual(params['odom_topic'], '/model/blueboat/odometry')
                    self.assertIn('rviz2', packages)

    def test_fleet_world_keeps_camera_app_models(self):
        world = ET.parse(WORLDS / 'level6.sdf').getroot().find('world')
        uris = [inc.findtext('uri') for inc in world.findall('include')
                if inc.findtext('uri', '').startswith('model://blueboat')]
        self.assertEqual(uris, ['model://blueboat', 'model://blueboat2',
                                'model://blueboat3', 'model://blueboat4'])
        for resource in ('blueboat', 'blueboat2', 'blueboat3', 'blueboat4'):
            with self.subTest(resource=resource):
                sdf = model(resource)
                camera = sdf.find('.//sensor[@type="camera"]')
                self.assertEqual(camera.findtext('topic'), f'/{resource}/camera/image_raw')
                self.assertEqual(camera.findtext('camera/triggered'), 'true')
                self.assertEqual(camera.find('plugin').get('filename'), 'libBlueBoatCameraTriggerPlugin.so')
                self.assertIsNotNone(sdf.find('.//sensor[@type="gpu_lidar"]'))


if __name__ == '__main__':
    unittest.main()
