#include <atomic>
#include <chrono>
#include <cmath>
#include <exception>
#include <memory>
#include <mutex>
#include <sstream>
#include <string>

#include <gz/common/Console.hh>
#include <gz/msgs/boolean.pb.h>
#include <gz/msgs/stringmsg.pb.h>
#include <gz/plugin/Register.hh>
#include <gz/sim/EntityComponentManager.hh>
#include <gz/sim/EventManager.hh>
#include <gz/sim/Sensor.hh>
#include <gz/sim/System.hh>
#include <gz/transport/Node.hh>

namespace blueboat_camera_manager
{
class BlueBoatCameraTriggerPlugin final:
  public gz::sim::System,
  public gz::sim::ISystemConfigure,
  public gz::sim::ISystemPreUpdate
{
public:
  BlueBoatCameraTriggerPlugin() = default;

  ~BlueBoatCameraTriggerPlugin() override
  {
    this->Shutdown();
  }

  void Configure(
    const gz::sim::Entity &_entity,
    const std::shared_ptr<const sdf::Element> &_sdf,
    gz::sim::EntityComponentManager &_ecm,
    gz::sim::EventManager &_eventMgr) override
  {
    (void)_eventMgr;
    this->parentSensor = gz::sim::Sensor(_entity);
    if (!this->parentSensor.Valid(_ecm))
    {
      gzerr << "BlueBoatCameraTriggerPlugin must be attached to a camera sensor.\n";
      return;
    }

    if (_sdf->HasElement("enable_topic"))
      this->enableTopic = _sdf->Get<std::string>("enable_topic");
    if (_sdf->HasElement("config_topic"))
      this->configTopic = _sdf->Get<std::string>("config_topic");
    if (_sdf->HasElement("trigger_topic"))
      this->triggerTopic = _sdf->Get<std::string>("trigger_topic");
    if (_sdf->HasElement("output_fps"))
      this->fps = _sdf->Get<double>("output_fps");

    if (!this->ValidFps(this->fps))
    {
      gzerr << "BlueBoatCameraTriggerPlugin received invalid output_fps.\n";
      return;
    }
  }

  void PreUpdate(
    const gz::sim::UpdateInfo &_info,
    gz::sim::EntityComponentManager &_ecm) override
  {
    if (!this->initialized)
    {
      if (this->enableTopic.empty() || this->configTopic.empty() ||
          this->triggerTopic.empty())
      {
        const auto topic = this->parentSensor.Topic(_ecm);
        if (!topic.has_value())
          return;

        std::string prefix = topic.value();
        const std::string suffix = "/image_raw";
        if (prefix.size() >= suffix.size() &&
            prefix.compare(prefix.size() - suffix.size(), suffix.size(), suffix) == 0)
        {
          prefix.erase(prefix.size() - suffix.size());
        }

        if (this->enableTopic.empty())
          this->enableTopic = prefix + "/enable_streaming";
        if (this->configTopic.empty())
          this->configTopic = prefix + "/stream_config";
        if (this->triggerTopic.empty())
          this->triggerTopic = prefix + "/trigger";
      }

      const bool enableOk = this->node.Subscribe(
        this->enableTopic,
        &BlueBoatCameraTriggerPlugin::OnEnable,
        this);
      const bool configOk = this->node.Subscribe(
        this->configTopic,
        &BlueBoatCameraTriggerPlugin::OnConfig,
        this);
      this->triggerPublisher =
        this->node.Advertise<gz::msgs::Boolean>(this->triggerTopic);

      if (!enableOk || !configOk || !this->triggerPublisher)
      {
        gzerr << "BlueBoatCameraTriggerPlugin failed to initialize topics.\n";
        return;
      }

      this->initialized = true;
      gzmsg << "BlueBoatCameraTriggerPlugin enable topic: "
            << this->enableTopic << "\n"
            << "BlueBoatCameraTriggerPlugin config topic: "
            << this->configTopic << "\n"
            << "BlueBoatCameraTriggerPlugin trigger topic: "
            << this->triggerTopic << "\n";
    }

    if (!this->enabled.load() || _info.paused)
      return;

    const double now = std::chrono::duration_cast<std::chrono::duration<double>>(
      _info.simTime).count();
    {
      std::lock_guard<std::mutex> lock(this->mutex);
      const double period = 1.0 / this->fps;
      if (this->lastTriggerTime >= 0.0 && now >= this->lastTriggerTime &&
          (now - this->lastTriggerTime) + 1e-9 < period)
      {
        return;
      }
      this->lastTriggerTime = now;
    }
    gz::msgs::Boolean trigger;
    trigger.set_data(true);
    this->triggerPublisher.Publish(trigger);
  }

private:
  static bool ValidFps(double _fps)
  {
    return std::isfinite(_fps) && _fps > 0.0 && _fps <= 60.0;
  }

  static std::string Trim(std::string _value)
  {
    const auto first = _value.find_first_not_of(" \t\r\n");
    if (first == std::string::npos)
      return {};
    const auto last = _value.find_last_not_of(" \t\r\n");
    return _value.substr(first, last - first + 1);
  }

  void OnEnable(const gz::msgs::Boolean &_message)
  {
    if (this->shuttingDown)
      return;
    const bool enabled = _message.data();
    this->enabled.store(enabled);
    {
      std::lock_guard<std::mutex> lock(this->mutex);
      this->lastTriggerTime = -1.0;
    }
    gzmsg << "BlueBoat camera sensor "
          << (enabled ? "enabled" : "disabled") << "\n";
  }

  void OnConfig(const gz::msgs::StringMsg &_message)
  {
    if (this->shuttingDown)
      return;

    double nextFps = 0.0;
    {
      std::lock_guard<std::mutex> lock(this->mutex);
      nextFps = this->fps;
    }

    std::stringstream stream(_message.data());
    std::string item;
    while (std::getline(stream, item, ';'))
    {
      const auto equals = item.find('=');
      if (equals == std::string::npos)
        continue;
      const std::string key = Trim(item.substr(0, equals));
      const std::string value = Trim(item.substr(equals + 1));
      if (key != "fps")
        continue;
      try
      {
        nextFps = std::stod(value);
      }
      catch (const std::exception &)
      {
        gzerr << "BlueBoatCameraTriggerPlugin rejected fps value: "
              << value << "\n";
        return;
      }
    }

    if (!this->ValidFps(nextFps))
    {
      gzerr << "BlueBoatCameraTriggerPlugin rejected fps outside (0, 60].\n";
      return;
    }

    {
      std::lock_guard<std::mutex> lock(this->mutex);
      this->fps = nextFps;
      this->lastTriggerTime = -1.0;
    }
    gzmsg << "BlueBoat camera trigger rate set to " << nextFps << " Hz\n";
  }

  void Shutdown()
  {
    if (this->shuttingDown.exchange(true))
      return;
    this->enabled.store(false);
    if (!this->enableTopic.empty())
      this->node.Unsubscribe(this->enableTopic);
    if (!this->configTopic.empty())
      this->node.Unsubscribe(this->configTopic);
  }

  gz::sim::Sensor parentSensor;
  gz::transport::Node node;
  gz::transport::Node::Publisher triggerPublisher;

  std::string enableTopic;
  std::string configTopic;
  std::string triggerTopic;

  std::atomic<bool> initialized{false};
  std::atomic<bool> shuttingDown{false};
  std::atomic<bool> enabled{false};
  std::mutex mutex;
  double fps{16.0};
  double lastTriggerTime{-1.0};
};
}  // namespace blueboat_camera_manager

GZ_ADD_PLUGIN(
  blueboat_camera_manager::BlueBoatCameraTriggerPlugin,
  gz::sim::System,
  gz::sim::ISystemConfigure,
  gz::sim::ISystemPreUpdate)

GZ_ADD_PLUGIN_ALIAS(
  blueboat_camera_manager::BlueBoatCameraTriggerPlugin,
  "BlueBoatCameraTriggerPlugin")
