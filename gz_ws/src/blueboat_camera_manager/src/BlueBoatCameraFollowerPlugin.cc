#include <memory>
#include <mutex>
#include <string>

#include <gz/common/Console.hh>
#include <gz/math/Pose3.hh>
#include <gz/msgs/stringmsg.pb.h>
#include <gz/plugin/Register.hh>
#include <gz/sim/EntityComponentManager.hh>
#include <gz/sim/EventManager.hh>
#include <gz/sim/Model.hh>
#include <gz/sim/System.hh>
#include <gz/sim/Util.hh>
#include <gz/sim/components/Model.hh>
#include <gz/sim/components/Name.hh>
#include <gz/transport/Node.hh>

namespace blueboat_camera_manager
{
class BlueBoatCameraFollowerPlugin final:
  public gz::sim::System,
  public gz::sim::ISystemConfigure,
  public gz::sim::ISystemPreUpdate
{
public:
  void Configure(
    const gz::sim::Entity &_entity,
    const std::shared_ptr<const sdf::Element> &_sdf,
    gz::sim::EntityComponentManager &,
    gz::sim::EventManager &) override
  {
    this->cameraModel = gz::sim::Model(_entity);
    this->targetTopic = _sdf->Get<std::string>(
      "target_topic", "/camera_pod/target").first;
    this->targetName = _sdf->Get<std::string>(
      "default_target", "blueboat").first;
    this->offset = _sdf->Get<gz::math::Pose3d>(
      "offset", gz::math::Pose3d(0.55, 0.0, 0.28, 0.0, 0.0, 0.0)).first;

    if (!this->node.Subscribe(
        this->targetTopic,
        &BlueBoatCameraFollowerPlugin::OnTarget,
        this))
    {
      gzerr << "BlueBoatCameraFollowerPlugin could not subscribe to "
            << this->targetTopic << "\n";
      return;
    }
    this->configured = true;
    gzmsg << "BlueBoatCameraFollowerPlugin target topic: "
          << this->targetTopic << "\n";
  }

  void PreUpdate(
    const gz::sim::UpdateInfo &,
    gz::sim::EntityComponentManager &_ecm) override
  {
    if (!this->configured || !this->cameraModel.Valid(_ecm))
      return;

    std::string target;
    {
      std::lock_guard<std::mutex> lock(this->targetMutex);
      target = this->targetName;
    }

    const gz::sim::Entity targetEntity = _ecm.EntityByComponents(
      gz::sim::components::Model(),
      gz::sim::components::Name(target));
    if (targetEntity == gz::sim::kNullEntity)
    {
      if (target != this->lastMissingTarget)
      {
        gzwarn << "BlueBoatCameraFollowerPlugin cannot find model ["
               << target << "]\n";
        this->lastMissingTarget = target;
      }
      return;
    }

    this->lastMissingTarget.clear();
    const gz::math::Pose3d desired = gz::sim::worldPose(targetEntity, _ecm) *
      this->offset;
    this->cameraModel.SetWorldPoseCmd(_ecm, desired);
  }

private:
  void OnTarget(const gz::msgs::StringMsg &_msg)
  {
    if (_msg.data().empty())
      return;
    {
      std::lock_guard<std::mutex> lock(this->targetMutex);
      this->targetName = _msg.data();
    }
    gzmsg << "BlueBoat camera pod now follows [" << _msg.data() << "]\n";
  }

  gz::sim::Model cameraModel;
  gz::transport::Node node;
  std::string targetTopic;
  gz::math::Pose3d offset;
  std::mutex targetMutex;
  std::string targetName{"blueboat"};
  std::string lastMissingTarget;
  bool configured{false};
};
}  // namespace blueboat_camera_manager

GZ_ADD_PLUGIN(
  blueboat_camera_manager::BlueBoatCameraFollowerPlugin,
  gz::sim::System,
  gz::sim::ISystemConfigure,
  gz::sim::ISystemPreUpdate)

GZ_ADD_PLUGIN_ALIAS(
  blueboat_camera_manager::BlueBoatCameraFollowerPlugin,
  "BlueBoatCameraFollowerPlugin")
