#include <gst/app/gstappsrc.h>
#include <gst/gst.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <exception>
#include <memory>
#include <mutex>
#include <sstream>
#include <string>
#include <thread>

#include <gz/common/Console.hh>
#include <gz/common/Event.hh>
#include <gz/msgs/boolean.pb.h>
#include <gz/msgs/image.pb.h>
#include <gz/msgs/stringmsg.pb.h>
#include <gz/plugin/Register.hh>
#include <gz/sim/EntityComponentManager.hh>
#include <gz/sim/EventManager.hh>
#include <gz/sim/Sensor.hh>
#include <gz/sim/System.hh>
#include <gz/sim/Util.hh>
#include <gz/sim/rendering/Events.hh>
#include <gz/transport/Node.hh>

#include <opencv2/imgproc.hpp>

namespace blueboat_camera_manager
{
namespace
{
constexpr double kMaximumLagSeconds = 30.0;
constexpr double kDelayQueueMarginSeconds = 2.0;
}

struct StreamConfig
{
  unsigned int width{256};
  unsigned int height{256};
  double fps{16.0};
  unsigned int bitrateKbps{800};
  bool preserveAspect{false};
  double lagSeconds{0.0};
};

class BlueBoatGstCameraPlugin final:
  public gz::sim::System,
  public gz::sim::ISystemConfigure,
  public gz::sim::ISystemPreUpdate
{
public:
  BlueBoatGstCameraPlugin() = default;

  ~BlueBoatGstCameraPlugin() override
  {
    this->Shutdown();
  }

  void Configure(
    const gz::sim::Entity &_entity,
    const std::shared_ptr<const sdf::Element> &_sdf,
    gz::sim::EntityComponentManager &_ecm,
    gz::sim::EventManager &_eventMgr) override
  {
    this->parentSensor = gz::sim::Sensor(_entity);
    if (!this->parentSensor.Valid(_ecm))
    {
      gzerr << "BlueBoatGstCameraPlugin must be attached to a camera sensor.\n";
      return;
    }

    if (_sdf->HasElement("udp_host"))
      this->udpHost = _sdf->Get<std::string>("udp_host");
    if (_sdf->HasElement("udp_port"))
      this->udpPort = _sdf->Get<int>("udp_port");
    if (_sdf->HasElement("image_topic"))
      this->imageTopic = _sdf->Get<std::string>("image_topic");
    if (_sdf->HasElement("enable_topic"))
      this->enableTopic = _sdf->Get<std::string>("enable_topic");
    if (_sdf->HasElement("config_topic"))
      this->configTopic = _sdf->Get<std::string>("config_topic");
    if (_sdf->HasElement("trigger_topic"))
      this->triggerTopic = _sdf->Get<std::string>("trigger_topic");

    StreamConfig initial;
    if (_sdf->HasElement("output_width"))
      initial.width = _sdf->Get<unsigned int>("output_width");
    if (_sdf->HasElement("output_height"))
      initial.height = _sdf->Get<unsigned int>("output_height");
    if (_sdf->HasElement("output_fps"))
      initial.fps = _sdf->Get<double>("output_fps");
    if (_sdf->HasElement("bitrate_kbps"))
      initial.bitrateKbps = _sdf->Get<unsigned int>("bitrate_kbps");
    if (_sdf->HasElement("preserve_aspect"))
      initial.preserveAspect = _sdf->Get<bool>("preserve_aspect");
    if (_sdf->HasElement("lag_seconds"))
      initial.lagSeconds = _sdf->Get<double>("lag_seconds");

    if (!this->ValidateConfig(initial))
    {
      gzerr << "BlueBoatGstCameraPlugin received invalid initial configuration.\n";
      return;
    }
    {
      std::lock_guard<std::mutex> lock(this->configMutex);
      this->config = initial;
    }

    this->renderTeardownConnection =
      _eventMgr.Connect<gz::sim::events::RenderTeardown>(
        [this]() { this->Shutdown(); });

    gzmsg << "BlueBoatGstCameraPlugin configured for UDP "
          << this->udpHost << ":" << this->udpPort
          << " with " << initial.lagSeconds << " seconds lag\n";
  }

  void PreUpdate(
    const gz::sim::UpdateInfo &_info,
    gz::sim::EntityComponentManager &_ecm) override
  {
    if (!this->initialized)
    {
      if (this->imageTopic.empty())
      {
        const auto topic = this->parentSensor.Topic(_ecm);
        if (!topic.has_value())
          return;
        this->imageTopic = topic.value();
      }
      if (this->enableTopic.empty())
        this->enableTopic = this->imageTopic + "/enable_streaming";
      if (this->configTopic.empty())
        this->configTopic = this->imageTopic + "/stream_config";
      if (this->triggerTopic.empty())
        this->triggerTopic = this->imageTopic + "/trigger";

      const bool enableOk = this->node.Subscribe(
        this->enableTopic,
        &BlueBoatGstCameraPlugin::OnEnable,
        this);
      const bool configOk = this->node.Subscribe(
        this->configTopic,
        &BlueBoatGstCameraPlugin::OnConfig,
        this);
      this->triggerPublisher =
        this->node.Advertise<gz::msgs::Boolean>(this->triggerTopic);

      if (!enableOk || !configOk || !this->triggerPublisher)
      {
        gzerr << "BlueBoatGstCameraPlugin failed to initialize control topics.\n";
        return;
      }

      this->initialized = true;
      gzmsg << "BlueBoatGstCameraPlugin image topic: " << this->imageTopic << "\n"
            << "BlueBoatGstCameraPlugin enable topic: " << this->enableTopic << "\n"
            << "BlueBoatGstCameraPlugin config topic: " << this->configTopic << "\n"
            << "BlueBoatGstCameraPlugin trigger topic: " << this->triggerTopic << "\n";
    }

    if (!this->streamingRequested || _info.paused)
      return;

    StreamConfig current;
    {
      std::lock_guard<std::mutex> lock(this->configMutex);
      current = this->config;
    }

    const double now = std::chrono::duration_cast<std::chrono::duration<double>>(
      _info.simTime).count();
    const double period = 1.0 / current.fps;
    bool publishTrigger = false;
    {
      std::lock_guard<std::mutex> lock(this->triggerMutex);
      if (this->lastTriggerTime < 0.0 || now < this->lastTriggerTime ||
          (now - this->lastTriggerTime) + 1e-9 >= period)
      {
        this->lastTriggerTime = now;
        publishTrigger = true;
      }
    }
    if (publishTrigger)
    {
      gz::msgs::Boolean trigger;
      trigger.set_data(true);
      this->triggerPublisher.Publish(trigger);
    }
  }

private:
  bool ValidateConfig(const StreamConfig &_cfg) const
  {
    return _cfg.width >= 16 && _cfg.height >= 16 &&
      (_cfg.width % 2u) == 0u && (_cfg.height % 2u) == 0u &&
      std::isfinite(_cfg.fps) && _cfg.fps > 0.0 && _cfg.fps <= 60.0 &&
      _cfg.bitrateKbps >= 100 && _cfg.bitrateKbps <= 50000 &&
      std::isfinite(_cfg.lagSeconds) && _cfg.lagSeconds >= 0.0 &&
      _cfg.lagSeconds <= kMaximumLagSeconds;
  }

  static std::string Trim(std::string _value)
  {
    const auto first = _value.find_first_not_of(" \t\r\n");
    if (first == std::string::npos)
      return {};
    const auto last = _value.find_last_not_of(" \t\r\n");
    return _value.substr(first, last - first + 1);
  }

  static bool ParseBool(const std::string &_value, bool &_out)
  {
    const std::string value = Trim(_value);
    if (value == "true" || value == "1" || value == "yes")
    {
      _out = true;
      return true;
    }
    if (value == "false" || value == "0" || value == "no")
    {
      _out = false;
      return true;
    }
    return false;
  }

  bool ParseConfig(const std::string &_text, StreamConfig &_out) const
  {
    StreamConfig candidate;
    {
      std::lock_guard<std::mutex> lock(this->configMutex);
      candidate = this->config;
    }

    std::stringstream stream(_text);
    std::string item;
    while (std::getline(stream, item, ';'))
    {
      const auto equals = item.find('=');
      if (equals == std::string::npos)
        continue;
      const std::string key = Trim(item.substr(0, equals));
      const std::string value = Trim(item.substr(equals + 1));
      try
      {
        if (key == "width")
          candidate.width = static_cast<unsigned int>(std::stoul(value));
        else if (key == "height")
          candidate.height = static_cast<unsigned int>(std::stoul(value));
        else if (key == "fps")
          candidate.fps = std::stod(value);
        else if (key == "bitrate_kbps")
          candidate.bitrateKbps = static_cast<unsigned int>(std::stoul(value));
        else if (key == "lag_seconds")
          candidate.lagSeconds = std::stod(value);
        else if (key == "preserve_aspect")
        {
          if (!ParseBool(value, candidate.preserveAspect))
            return false;
        }
      }
      catch (const std::exception &)
      {
        return false;
      }
    }

    if (!this->ValidateConfig(candidate))
      return false;
    _out = candidate;
    return true;
  }

  void OnConfig(const gz::msgs::StringMsg &_msg)
  {
    if (this->shuttingDown)
      return;

    StreamConfig next;
    if (!this->ParseConfig(_msg.data(), next))
    {
      gzerr << "BlueBoatGstCameraPlugin rejected config: " << _msg.data() << "\n";
      return;
    }

    {
      std::lock_guard<std::mutex> lock(this->configMutex);
      this->config = next;
      this->lastFrameTime = -1.0;
    }
    {
      std::lock_guard<std::mutex> lock(this->triggerMutex);
      this->lastTriggerTime = -1.0;
    }
    if (this->streamingRequested)
      this->restartRequested = true;

    gzmsg << "BlueBoatGstCameraPlugin config set to "
          << next.width << "x" << next.height << " @ " << next.fps
          << " Hz, bitrate " << next.bitrateKbps << " kbps, lag "
          << next.lagSeconds << " seconds\n";
  }

  void OnEnable(const gz::msgs::Boolean &_msg)
  {
    if (this->shuttingDown)
      return;
    if (_msg.data())
      this->EnableImageSubscription();
    else
      this->DisableImageSubscription();
  }

  void EnableImageSubscription()
  {
    if (this->shuttingDown)
      return;
    this->streamingRequested = true;
    {
      std::lock_guard<std::mutex> lock(this->triggerMutex);
      this->lastTriggerTime = -1.0;
    }
    if (!this->imageSubscribed.exchange(true))
    {
      if (!this->node.Subscribe(
          this->imageTopic,
          &BlueBoatGstCameraPlugin::OnImage,
          this))
      {
        this->imageSubscribed = false;
        this->streamingRequested = false;
        gzerr << "BlueBoatGstCameraPlugin failed to subscribe to "
              << this->imageTopic << "\n";
        return;
      }
    }
    gzmsg << "BlueBoatGstCameraPlugin stream enabled on UDP port "
          << this->udpPort << "\n";
  }

  void DisableImageSubscription()
  {
    this->streamingRequested = false;
    this->restartRequested = false;
    if (this->imageSubscribed.exchange(false))
      this->node.Unsubscribe(this->imageTopic);
    this->StopPipeline();
    gzmsg << "BlueBoatGstCameraPlugin stream disabled on UDP port "
          << this->udpPort << "\n";
  }

  double MessageTime(const gz::msgs::Image &_msg) const
  {
    const auto &stamp = _msg.header().stamp();
    const double messageTime = static_cast<double>(stamp.sec()) +
      static_cast<double>(stamp.nsec()) * 1e-9;
    if (messageTime > 0.0)
      return messageTime;
    return std::chrono::duration<double>(
      std::chrono::steady_clock::now().time_since_epoch()).count();
  }

  bool ShouldSendFrame(const gz::msgs::Image &_msg, const StreamConfig &_cfg)
  {
    const double now = this->MessageTime(_msg);
    std::lock_guard<std::mutex> lock(this->configMutex);
    const double period = 1.0 / _cfg.fps;
    if (this->lastFrameTime >= 0.0 && now >= this->lastFrameTime &&
        (now - this->lastFrameTime) + 1e-6 < period)
    {
      return false;
    }
    this->lastFrameTime = now;
    return true;
  }

  cv::Mat ResizeFrame(const cv::Mat &_source, const StreamConfig &_cfg) const
  {
    if (!_cfg.preserveAspect)
    {
      cv::Mat resized;
      cv::resize(_source, resized,
        cv::Size(static_cast<int>(_cfg.width), static_cast<int>(_cfg.height)),
        0.0, 0.0, cv::INTER_AREA);
      return resized;
    }

    const double scale = std::min(
      static_cast<double>(_cfg.width) / _source.cols,
      static_cast<double>(_cfg.height) / _source.rows);
    const int scaledWidth = std::max(2, static_cast<int>(_source.cols * scale));
    const int scaledHeight = std::max(2, static_cast<int>(_source.rows * scale));
    cv::Mat scaled;
    cv::resize(_source, scaled, cv::Size(scaledWidth, scaledHeight),
      0.0, 0.0, cv::INTER_AREA);

    cv::Mat output(
      static_cast<int>(_cfg.height), static_cast<int>(_cfg.width),
      CV_8UC3, cv::Scalar(0, 0, 0));
    const int x = (output.cols - scaled.cols) / 2;
    const int y = (output.rows - scaled.rows) / 2;
    scaled.copyTo(output(cv::Rect(x, y, scaled.cols, scaled.rows)));
    return output;
  }

  void OnImage(const gz::msgs::Image &_msg)
  {
    if (!this->streamingRequested)
      return;

    StreamConfig current;
    {
      std::lock_guard<std::mutex> lock(this->configMutex);
      current = this->config;
    }

    if (this->restartRequested.exchange(false))
    {
      this->StopPipeline();
      this->StartPipeline(current);
      return;
    }
    if (!this->pipelineThreadRunning)
    {
      this->StartPipeline(current);
      return;
    }
    if (!this->ShouldSendFrame(_msg, current))
      return;

    const std::size_t expected =
      static_cast<std::size_t>(_msg.width()) * _msg.height() * 3u;
    if (_msg.data().size() < expected)
    {
      gzerr << "BlueBoatGstCameraPlugin received an undersized RGB frame.\n";
      return;
    }

    cv::Mat source(
      static_cast<int>(_msg.height()), static_cast<int>(_msg.width()),
      CV_8UC3,
      reinterpret_cast<unsigned char *>(
        const_cast<char *>(_msg.data().data())));
    cv::Mat output = this->ResizeFrame(source, current);
    cv::Mat yuv;
    cv::cvtColor(output, yuv, cv::COLOR_RGB2YUV_I420);

    const std::size_t byteCount = yuv.total() * yuv.elemSize();
    GstBuffer *buffer = gst_buffer_new_allocate(nullptr, byteCount, nullptr);
    if (!buffer)
      return;

    GstMapInfo map;
    if (!gst_buffer_map(buffer, &map, GST_MAP_WRITE))
    {
      gst_buffer_unref(buffer);
      return;
    }
    std::memcpy(map.data, yuv.data, byteCount);
    gst_buffer_unmap(buffer, &map);

    GstFlowReturn result = GST_FLOW_FLUSHING;
    {
      std::lock_guard<std::mutex> lock(this->gstMutex);
      if (this->appSource)
        result = gst_app_src_push_buffer(GST_APP_SRC(this->appSource), buffer);
      else
        gst_buffer_unref(buffer);
    }

    if (result != GST_FLOW_OK && result != GST_FLOW_FLUSHING)
      gzwarn << "BlueBoatGstCameraPlugin appsrc push returned " << result << "\n";
  }

  void StartPipeline(const StreamConfig &_cfg)
  {
    std::unique_lock<std::mutex> lifecycleLock(this->lifecycleMutex);
    if (this->pipelineThreadRunning || !this->streamingRequested)
      return;

    std::thread staleThread;
    if (this->pipelineThread.joinable())
      staleThread = std::move(this->pipelineThread);
    lifecycleLock.unlock();
    if (staleThread.joinable())
      staleThread.join();
    lifecycleLock.lock();

    if (this->pipelineThreadRunning || !this->streamingRequested)
      return;
    this->pipelineStopRequested = false;
    this->pipelineThreadRunning = true;
    this->pipelineThread = std::thread(
      &BlueBoatGstCameraPlugin::PipelineMain, this, _cfg);
  }

  void PipelineMain(StreamConfig _cfg)
  {
    static std::once_flag gstInitFlag;
    std::call_once(gstInitFlag, []() { gst_init(nullptr, nullptr); });

    const unsigned int capsFps = std::max(
      1u, static_cast<unsigned int>(std::round(_cfg.fps)));
    const unsigned int keyInterval = capsFps;
    const auto lagNanoseconds = static_cast<std::int64_t>(
      std::llround(_cfg.lagSeconds * static_cast<double>(GST_SECOND)));
    const auto queueNanoseconds = static_cast<std::uint64_t>(
      std::llround(
        (_cfg.lagSeconds + kDelayQueueMarginSeconds) *
        static_cast<double>(GST_SECOND)));

    std::ostringstream pipelineText;
    pipelineText
      << "appsrc name=blueboat_source is-live=true block=false "
      << "do-timestamp=true format=time "
      << "caps=video/x-raw,format=I420,width=" << _cfg.width
      << ",height=" << _cfg.height
      << ",framerate=" << capsFps << "/1 "
      << "! queue max-size-buffers=2 leaky=downstream "
      << "! videoconvert "
      << "! x264enc tune=zerolatency speed-preset=ultrafast bitrate="
      << _cfg.bitrateKbps << " key-int-max=" << keyInterval << " "
      << "! h264parse config-interval=-1 "
      << "! rtph264pay config-interval=1 pt=96 ";

    if (lagNanoseconds > 0)
    {
      pipelineText
        << "! queue max-size-buffers=0 max-size-bytes=0 max-size-time="
        << queueNanoseconds << " leaky=downstream "
        << "! udpsink host=" << this->udpHost
        << " port=" << this->udpPort
        << " sync=true async=false ts-offset=" << lagNanoseconds;
    }
    else
    {
      // Preserve the pre-lag zero-latency sink path exactly when lag is disabled.
      pipelineText
        << "! udpsink host=" << this->udpHost
        << " port=" << this->udpPort
        << " sync=false async=false";
    }

    GError *error = nullptr;
    GstElement *pipeline = gst_parse_launch(pipelineText.str().c_str(), &error);
    if (!pipeline)
    {
      gzerr << "BlueBoatGstCameraPlugin could not build GStreamer pipeline: "
            << (error ? error->message : "unknown error") << "\n";
      if (error)
        g_error_free(error);
      this->pipelineThreadRunning = false;
      return;
    }
    if (error)
      g_error_free(error);

    GstElement *source = gst_bin_get_by_name(GST_BIN(pipeline), "blueboat_source");
    GMainLoop *loop = g_main_loop_new(nullptr, FALSE);
    if (!source || !loop)
    {
      gzerr << "BlueBoatGstCameraPlugin could not initialize appsrc or GLib loop.\n";
      if (source)
        gst_object_unref(source);
      if (loop)
        g_main_loop_unref(loop);
      gst_object_unref(pipeline);
      this->pipelineThreadRunning = false;
      return;
    }
    {
      std::lock_guard<std::mutex> lock(this->gstMutex);
      this->pipeline = pipeline;
      this->appSource = source;
      this->gstLoop = loop;
    }

    const GstStateChangeReturn stateResult =
      gst_element_set_state(pipeline, GST_STATE_PLAYING);
    if (stateResult == GST_STATE_CHANGE_FAILURE)
    {
      gzerr << "BlueBoatGstCameraPlugin failed to start GStreamer pipeline.\n";
      this->pipelineStopRequested = true;
    }

    if (!this->pipelineStopRequested)
      g_main_loop_run(loop);

    gst_element_set_state(pipeline, GST_STATE_NULL);
    {
      std::lock_guard<std::mutex> lock(this->gstMutex);
      this->appSource = nullptr;
      this->pipeline = nullptr;
      this->gstLoop = nullptr;
    }
    gst_object_unref(source);
    g_main_loop_unref(loop);
    gst_object_unref(pipeline);
    this->pipelineThreadRunning = false;
  }

  void StopPipeline()
  {
    std::unique_lock<std::mutex> lifecycleLock(this->lifecycleMutex);
    this->pipelineStopRequested = true;
    GMainLoop *loop = nullptr;
    {
      std::lock_guard<std::mutex> lock(this->gstMutex);
      loop = this->gstLoop;
      if (loop)
        g_main_loop_ref(loop);
    }
    if (loop)
    {
      g_main_loop_quit(loop);
      g_main_loop_unref(loop);
    }

    std::thread threadToJoin;
    if (this->pipelineThread.joinable())
      threadToJoin = std::move(this->pipelineThread);
    lifecycleLock.unlock();

    if (threadToJoin.joinable())
    {
      if (threadToJoin.get_id() == std::this_thread::get_id())
        threadToJoin.detach();
      else
        threadToJoin.join();
    }
    this->pipelineThreadRunning = false;
  }

  void Shutdown()
  {
    if (this->shuttingDown.exchange(true))
      return;
    this->streamingRequested = false;
    if (this->imageSubscribed.exchange(false) && !this->imageTopic.empty())
      this->node.Unsubscribe(this->imageTopic);
    this->StopPipeline();
    if (!this->enableTopic.empty())
      this->node.Unsubscribe(this->enableTopic);
    if (!this->configTopic.empty())
      this->node.Unsubscribe(this->configTopic);
  }

  gz::sim::Sensor parentSensor;
  gz::transport::Node node;
  gz::transport::Node::Publisher triggerPublisher;
  gz::common::ConnectionPtr renderTeardownConnection;

  std::string udpHost{"127.0.0.1"};
  int udpPort{5600};
  std::string imageTopic;
  std::string enableTopic;
  std::string configTopic;
  std::string triggerTopic;

  std::atomic<bool> initialized{false};
  std::atomic<bool> shuttingDown{false};
  std::atomic<bool> streamingRequested{false};
  std::atomic<bool> imageSubscribed{false};
  std::atomic<bool> restartRequested{false};

  mutable std::mutex configMutex;
  StreamConfig config;
  double lastFrameTime{-1.0};

  std::mutex triggerMutex;
  double lastTriggerTime{-1.0};

  std::mutex lifecycleMutex;
  std::thread pipelineThread;
  std::atomic<bool> pipelineThreadRunning{false};
  std::atomic<bool> pipelineStopRequested{false};

  std::mutex gstMutex;
  GstElement *pipeline{nullptr};
  GstElement *appSource{nullptr};
  GMainLoop *gstLoop{nullptr};
};
}  // namespace blueboat_camera_manager

GZ_ADD_PLUGIN(
  blueboat_camera_manager::BlueBoatGstCameraPlugin,
  gz::sim::System,
  gz::sim::ISystemConfigure,
  gz::sim::ISystemPreUpdate)

GZ_ADD_PLUGIN_ALIAS(
  blueboat_camera_manager::BlueBoatGstCameraPlugin,
  "BlueBoatGstCameraPlugin")
