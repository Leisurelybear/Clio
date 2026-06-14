// Global application state
const state = {
  config: null,
  configRaw: null,
  source: 'compressed',
  videos: [],
  currentEntity: 'video',  // 'video' | 'plan' | 'run' | 'config'
  currentVideo: null,
  currentDay: 'day1',
  availablePlans: [],
  currentTab: 'texts',
  texts: null,
  voiceover: null,
  transcript: null,
  plan: null,
  dirty: false,
  projectName: null,
  projects: [],
  currentProject: null,
  currentProjectName: null,
  lastProject: null,
  groups: {},
  expandedGroups: {},
  // preview playback
  previewActive: false,
  previewIndex: -1,
  _previewEndTime: null,
};

export { state };
