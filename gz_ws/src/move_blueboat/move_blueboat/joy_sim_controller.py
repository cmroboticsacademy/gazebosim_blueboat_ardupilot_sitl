# Copyright 2024, Markus Buchholz

import rclpy
from rclpy.node import Node
from rclpy.callback_groups import ReentrantCallbackGroup
from sensor_msgs.msg import Joy
from std_msgs.msg import Float64
import threading
import time


class BlueBoatJoystickController(Node):

    def __init__(self):
        super().__init__('blue_boat_joystick_controller')

        self.callback_group = ReentrantCallbackGroup()

        self.declare_parameter('target_model', 'blueboat')
        self.declare_parameter('joy_topic', '/joy')
        self.declare_parameter('axis_forward', 4)
        self.declare_parameter('axis_turn', 0)
        self.declare_parameter('thrust_scale', 15.0)
        self.declare_parameter('publish_rate_hz', 10.0)
        self.declare_parameter('deadman_button', -1)

        self.target_model = self.get_parameter('target_model').value
        self.joy_topic = self.get_parameter('joy_topic').value
        self.axis_forward = int(self.get_parameter('axis_forward').value)
        self.axis_turn = int(self.get_parameter('axis_turn').value)
        self.factor = float(self.get_parameter('thrust_scale').value)
        self.publish_rate_hz = float(self.get_parameter('publish_rate_hz').value)
        self.deadman_button = int(self.get_parameter('deadman_button').value)

        port_topic = f'/model/{self.target_model}/joint/motor_port_joint/cmd_thrust'
        stbd_topic = f'/model/{self.target_model}/joint/motor_stbd_joint/cmd_thrust'

        self.motor_port_publisher = self.create_publisher(
            Float64,
            port_topic,
            10,
            callback_group=self.callback_group
        )

        self.motor_stbd_publisher = self.create_publisher(
            Float64,
            stbd_topic,
            10,
            callback_group=self.callback_group
        )

        self.subscription = self.create_subscription(
            Joy,
            self.joy_topic,
            self.handle_joy,
            qos_profile=rclpy.qos.qos_profile_sensor_data,
            callback_group=self.callback_group
        )

        self.port_thrust = 0.0
        self.stbd_thrust = 0.0
        self.enabled = False if self.deadman_button >= 0 else True
        self.lock = threading.Lock()

        self.get_logger().info(
            f'BlueBoatJoystickController initialized for model={self.target_model}. '
            f'Publishing port={port_topic}, stbd={stbd_topic}, joy_topic={self.joy_topic}'
        )

        self.running_event = threading.Event()
        self.running_event.set()

        self.update_thread = threading.Thread(target=self.update_thrust, daemon=True)
        self.update_thread.start()

    def update_thrust(self):
        sleep_time = 1.0 / max(self.publish_rate_hz, 1.0)
        while self.running_event.is_set():
            with self.lock:
                if self.enabled:
                    port_thrust_value = self.port_thrust * self.factor
                    stbd_thrust_value = self.stbd_thrust * self.factor
                else:
                    port_thrust_value = 0.0
                    stbd_thrust_value = 0.0

                self.motor_port_publisher.publish(Float64(data=port_thrust_value))
                self.motor_stbd_publisher.publish(Float64(data=stbd_thrust_value))

            time.sleep(sleep_time)

    def handle_joy(self, msg):
        with self.lock:
            if self.deadman_button >= 0:
                self.enabled = (
                    len(msg.buttons) > self.deadman_button and
                    msg.buttons[self.deadman_button] == 1
                )

            if len(msg.axes) <= max(self.axis_forward, self.axis_turn):
                self.get_logger().warn(
                    'Joystick message does not have enough axes for the configured axis_forward/axis_turn settings.'
                )
                self.port_thrust = 0.0
                self.stbd_thrust = 0.0
                return

            forward_backward = msg.axes[self.axis_forward]
            left_right = msg.axes[self.axis_turn]

            self.port_thrust = max(min(forward_backward + left_right, 1.0), -1.0)
            self.stbd_thrust = max(min(forward_backward - left_right, 1.0), -1.0)

    def destroy_node(self):
        self.running_event.clear()
        if self.update_thread.is_alive():
            self.update_thread.join(timeout=1.0)
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    blue_boat_joystick_controller = BlueBoatJoystickController()

    try:
        rclpy.spin(blue_boat_joystick_controller)
    except KeyboardInterrupt:
        pass
    finally:
        blue_boat_joystick_controller.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
