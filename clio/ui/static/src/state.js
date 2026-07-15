// Global application state
const state = {
  config: null,
  configRaw: null,
  configGlobal: null,
  configProject: null,
  configTab: 'project',  // 'project' | 'global' | 'merged' | 'prompts'
  promptPayload: null,
  currentPromptName: null,
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
  currentProjectDir: null,
  lastProject: null,
  lastProjectDir: null,
  groups: {},
  expandedGroups: {},
  // preview playback
  previewActive: false,
  previewIndex: -1,
  _previewEndTime: null,
  selectionMode: false,
  selectedFiles: [],
  refining: null,  // {type: 'texts'|'scripts', file: string} when AI refine in progress
};

function clearSelection() {
  state.selectionMode = false;
  state.selectedFiles = [];
}

export { state, clearSelection };
