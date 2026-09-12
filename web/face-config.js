// 离线索引与手机查询共用模型、预处理与距离定义。
export function faceConfig(modelBasePath, backend = 'webgl') {
  return {
    backend, modelBasePath, async: false, cacheSensitivity: 0, skipAllowed: false,
    filter: {enabled: false, return: false},
    face: {
      enabled: true,
      detector: {rotation: true, maxDetected: 50, minConfidence: 0.6, minSize: 24, skipFrames: 0, skipTime: 0},
      mesh: {enabled: true}, iris: {enabled: false}, emotion: {enabled: false},
      description: {enabled: true, minConfidence: 0.5, skipFrames: 0, skipTime: 0},
      antispoof: {enabled: false}, liveness: {enabled: false},
    },
    body: {enabled: false}, hand: {enabled: false}, object: {enabled: false},
    gesture: {enabled: false}, segmentation: {enabled: false},
  };
}
