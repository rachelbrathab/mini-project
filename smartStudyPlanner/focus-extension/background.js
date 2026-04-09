const DEFAULT_BLOCKED_DOMAINS = [
  "netflix.com",
  "youtube.com",
  "instagram.com",
  "primevideo.com"
];

const DNR_RULE_IDS = [1001, 1002, 1003, 1004];
const EMERGENCY_UNLOCK_MINUTES = 5;
const STUDY_KEYWORDS = [
  "study",
  "lecture",
  "tutorial",
  "course",
  "class",
  "homework",
  "assignment",
  "revision",
  "exam",
  "math",
  "physics",
  "chemistry",
  "biology",
  "science",
  "coding",
  "programming",
  "python",
  "javascript",
  "datastructures",
  "algorithms",
  "history",
  "geography",
  "english",
  "grammar"
];
const MIN_LEARNED_KEYWORD_COUNT = 2;

function isPlannerUrl(url) {
  if (!url) {
    return false;
  }

  return url.startsWith("http://127.0.0.1:") || url.startsWith("http://localhost:");
}

function parseJsonArray(value) {
  if (!value) {
    return [];
  }

  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch (_err) {
    return [];
  }
}

function isFutureIsoDatetime(value) {
  if (!value) {
    return false;
  }

  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) && timestamp > Date.now();
}

function isEmergencyUnlockActive(state) {
  return isFutureIsoDatetime(state.emergencyUnlockUntil);
}

function getEffectiveBlockedDomains(state) {
  if (!state.focusMode || isEmergencyUnlockActive(state)) {
    return [];
  }

  if (Array.isArray(state.plannerBlockedDomains)) {
    return state.plannerBlockedDomains;
  }

  return list(DEFAULT_BLOCKED_DOMAINS);
}

function getRuntimeState() {
  return chrome.storage.local
    .get([
      "focusMode",
      "allowYoutube",
      "plannerProgressPercent",
      "plannerHasSchedule",
      "plannerActiveSubject",
      "plannerBlockedDomains",
      "plannerAllowedDomains",
      "plannerRewardActive",
      "plannerRewardRemainingSeconds",
      "emergencyUnlockUntil",
      "emergencyUnlockDate",
      "plannerHardMode",
      "plannerEmergencyRemaining",
      "youtubeLearnedKeywords",
      "youtubeSessionAllowlist",
      "blockedDomainHits"
    ])
    .then((stored) => ({
      focusMode: Boolean(stored.focusMode),
      allowYoutube: Boolean(stored.allowYoutube),
      plannerProgressPercent: Number(stored.plannerProgressPercent || 0),
      plannerHasSchedule: stored.plannerHasSchedule !== false,
      plannerActiveSubject: stored.plannerActiveSubject || "",
      plannerBlockedDomains: Array.isArray(stored.plannerBlockedDomains) ? stored.plannerBlockedDomains : list(DEFAULT_BLOCKED_DOMAINS),
      plannerAllowedDomains: Array.isArray(stored.plannerAllowedDomains) ? stored.plannerAllowedDomains : [],
      plannerRewardActive: Boolean(stored.plannerRewardActive),
      plannerRewardRemainingSeconds: Number(stored.plannerRewardRemainingSeconds || 0),
      emergencyUnlockUntil: stored.emergencyUnlockUntil || null,
      emergencyUnlockDate: stored.emergencyUnlockDate || null,
      plannerHardMode: stored.plannerHardMode === true,
      plannerEmergencyRemaining: Number(stored.plannerEmergencyRemaining || 0),
      youtubeLearnedKeywords: stored.youtubeLearnedKeywords && typeof stored.youtubeLearnedKeywords === "object"
        ? stored.youtubeLearnedKeywords
        : {},
      youtubeSessionAllowlist: Array.isArray(stored.youtubeSessionAllowlist) ? stored.youtubeSessionAllowlist : [],
      blockedDomainHits: stored.blockedDomainHits && typeof stored.blockedDomainHits === "object" ? stored.blockedDomainHits : {}
    }));
}

function setRuntimeState(nextState) {
  return chrome.storage.local.set({
    focusMode: Boolean(nextState.focusMode),
    allowYoutube: Boolean(nextState.allowYoutube),
    plannerProgressPercent: Number(nextState.plannerProgressPercent || 0),
    plannerHasSchedule: Boolean(nextState.plannerHasSchedule),
    plannerActiveSubject: String(nextState.plannerActiveSubject || ""),
    plannerBlockedDomains: Array.isArray(nextState.plannerBlockedDomains) ? nextState.plannerBlockedDomains : list(DEFAULT_BLOCKED_DOMAINS),
    plannerAllowedDomains: Array.isArray(nextState.plannerAllowedDomains) ? nextState.plannerAllowedDomains : [],
    plannerRewardActive: Boolean(nextState.plannerRewardActive),
    plannerRewardRemainingSeconds: Number(nextState.plannerRewardRemainingSeconds || 0),
    emergencyUnlockUntil: nextState.emergencyUnlockUntil || null,
    emergencyUnlockDate: nextState.emergencyUnlockDate || null,
    plannerHardMode: Boolean(nextState.plannerHardMode),
    plannerEmergencyRemaining: Number(nextState.plannerEmergencyRemaining || 0),
    youtubeLearnedKeywords: nextState.youtubeLearnedKeywords && typeof nextState.youtubeLearnedKeywords === "object"
      ? nextState.youtubeLearnedKeywords
      : {},
    youtubeSessionAllowlist: Array.isArray(nextState.youtubeSessionAllowlist) ? nextState.youtubeSessionAllowlist : [],
    blockedDomainHits: nextState.blockedDomainHits && typeof nextState.blockedDomainHits === "object" ? nextState.blockedDomainHits : {}
  });
}

function buildStudyKeywords(state) {
  const learned = [];
  const learnedMap = state.youtubeLearnedKeywords && typeof state.youtubeLearnedKeywords === "object"
    ? state.youtubeLearnedKeywords
    : {};

  Object.keys(learnedMap).forEach((keyword) => {
    if (Number(learnedMap[keyword] || 0) >= MIN_LEARNED_KEYWORD_COUNT) {
      learned.push(keyword);
    }
  });

  return Array.from(new Set([...STUDY_KEYWORDS, ...learned]));
}

function extractLearningKeywords(text) {
  const normalized = String(text || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();

  if (!normalized) {
    return [];
  }

  const stopWords = new Set(["video", "youtube", "the", "and", "for", "with", "from", "that", "this", "your", "about"]);
  const tokens = normalized.split(/\s+/).filter((token) => token.length >= 4 && !stopWords.has(token));
  return Array.from(new Set(tokens)).slice(0, 8);
}

function getYoutubeAllowKey(url) {
  try {
    const parsed = new URL(url);
    const videoId = parsed.searchParams.get("v");
    if (videoId) {
      return `video:${videoId}`;
    }

    if (parsed.hostname === "youtu.be") {
      return `video:${(parsed.pathname || "").replace(/^\//, "")}`;
    }

    return `path:${parsed.pathname || "/"}?${parsed.searchParams.toString()}`;
  } catch (_err) {
    return String(url || "").trim();
  }
}

function isYoutubeAllowedOnce(url, state) {
  const key = getYoutubeAllowKey(url);
  return Array.isArray(state.youtubeSessionAllowlist) && state.youtubeSessionAllowlist.includes(key);
}

async function rememberYoutubeLearning(state, url, title) {
  const signals = gatherYoutubeSignals(url, title);
  const keywords = extractLearningKeywords(signals);
  if (keywords.length === 0) {
    return;
  }

  const nextLearned = {
    ...(state.youtubeLearnedKeywords || {})
  };

  keywords.forEach((keyword) => {
    nextLearned[keyword] = Number(nextLearned[keyword] || 0) + 1;
  });

  await setRuntimeState({
    ...state,
    youtubeLearnedKeywords: nextLearned
  });
}

async function allowYoutubeUrlOnce(url, title) {
  const state = await getRuntimeState();
  const key = getYoutubeAllowKey(url);
  const nextAllowlist = Array.from(new Set([...(state.youtubeSessionAllowlist || []), key]));

  await setRuntimeState({
    ...state,
    youtubeSessionAllowlist: nextAllowlist
  });

  await rememberYoutubeLearning({ ...state, youtubeSessionAllowlist: nextAllowlist }, url, title || "");
}

function notifyPlannerDomainHit(domain) {
  chrome.tabs.query({}, async (tabs) => {
    const plannerTab = tabs.find((tab) => isPlannerUrl(tab.url) && typeof tab.id === "number");
    if (!plannerTab || typeof plannerTab.id !== "number") {
      return;
    }

    try {
      await chrome.scripting.executeScript({
        target: { tabId: plannerTab.id },
        func: (blockedDomain) => {
          fetch("/analytics/domain-hit", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ domain: blockedDomain })
          }).catch(() => {});
        },
        args: [domain]
      });
    } catch (_err) {
      // Ignore transient planner tab script errors.
    }
  });
}

async function recordBlockedDomainHit(domain) {
  const state = await getRuntimeState();
  const nextHits = {
    ...(state.blockedDomainHits || {})
  };
  nextHits[domain] = Number(nextHits[domain] || 0) + 1;
  await setRuntimeState({
    ...state,
    blockedDomainHits: nextHits
  });
  notifyPlannerDomainHit(domain);
}

function buildBlockingRules(state) {
  const activeDomains = getEffectiveBlockedDomains(state).filter((domain) => !isYoutubeDomain(domain));
  return activeDomains.map((domain, index) => ({
    id: DNR_RULE_IDS[index],
    priority: 1,
    action: { type: "block" },
    condition: {
      urlFilter: `||${domain}`,
      resourceTypes: ["main_frame", "sub_frame"]
    }
  }));
}

function applyBlockingRules(state) {
  return chrome.declarativeNetRequest.updateDynamicRules({
    removeRuleIds: DNR_RULE_IDS,
    addRules: buildBlockingRules(state)
  });
}

function getHostname(url) {
  if (!url) {
    return "";
  }

  try {
    return new URL(url).hostname.toLowerCase();
  } catch (_err) {
    return "";
  }
}

function isYoutubeDomain(hostname) {
  if (!hostname) {
    return false;
  }

  return hostname === "youtube.com" || hostname.endsWith(".youtube.com") || hostname === "youtu.be" || hostname.endsWith(".youtu.be");
}

function gatherYoutubeSignals(url, tabTitle) {
  const signals = [];

  try {
    const parsedUrl = new URL(url);
    const searchQuery = parsedUrl.searchParams.get("search_query") || parsedUrl.searchParams.get("q") || "";
    const playlistTitle = parsedUrl.searchParams.get("title") || "";
    signals.push(parsedUrl.pathname || "");
    signals.push(searchQuery);
    signals.push(playlistTitle);
  } catch (_err) {
    // Ignore malformed URLs and use only title signal below.
  }

  if (tabTitle) {
    signals.push(tabTitle);
  }

  return signals
    .join(" ")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ");
}

function isStudyRelatedYoutubePage(url, tabTitle, state) {
  const signals = gatherYoutubeSignals(url, tabTitle);
  if (!signals.trim()) {
    return false;
  }

  const keywords = buildStudyKeywords(state);
  return keywords.some((keyword) => signals.includes(keyword));
}

function isYoutubeDiscoveryPage(url) {
  try {
    const parsedUrl = new URL(url);
    const path = parsedUrl.pathname || "/";

    if (path === "/" || path === "/results") {
      return true;
    }

    return false;
  } catch (_err) {
    return false;
  }
}

async function getTabTitle(tabId) {
  try {
    const tab = await chrome.tabs.get(tabId);
    return tab && typeof tab.title === "string" ? tab.title : "";
  } catch (_err) {
    return "";
  }
}

function shouldBlockHost(hostname, state) {
  if (!hostname) {
    return false;
  }

  const domains = getEffectiveBlockedDomains(state);
  for (const domain of domains) {
    const isDomainMatch = hostname === domain || hostname.endsWith(`.${domain}`);
    if (isDomainMatch) {
      return true;
    }
  }

  return false;
}

async function enforceTabIfNeeded(tabId, url) {
  if (typeof tabId !== "number" || !url) {
    return;
  }

  if (url.startsWith(chrome.runtime.getURL(""))) {
    return;
  }

  const state = await getRuntimeState();
  const host = getHostname(url);
  const isYoutubeHost = isYoutubeDomain(host);

  const youtubeExplicitlyAllowed = state.plannerAllowedDomains.includes("youtube.com");

  if (isYoutubeHost && shouldBlockHost("youtube.com", state) && !youtubeExplicitlyAllowed) {
    if (isYoutubeDiscoveryPage(url)) {
      return;
    }

    if (isYoutubeAllowedOnce(url, state)) {
      const allowedTitle = await getTabTitle(tabId);
      await rememberYoutubeLearning(state, url, allowedTitle);
      return;
    }

    const tabTitle = await getTabTitle(tabId);
    if (isStudyRelatedYoutubePage(url, tabTitle, state)) {
      await rememberYoutubeLearning(state, url, tabTitle);
      return;
    }

    await recordBlockedDomainHit("youtube.com");
    const blockedUrl = `${chrome.runtime.getURL("blocked.html")}?domain=${encodeURIComponent(host)}&reason=youtube-study&url=${encodeURIComponent(url)}&title=${encodeURIComponent(tabTitle || "")}`;
    await chrome.tabs.update(tabId, { url: blockedUrl });
    return;
  }

  if (!shouldBlockHost(host, state)) {
    return;
  }

  await recordBlockedDomainHit(host);
  const blockedUrl = `${chrome.runtime.getURL("blocked.html")}?domain=${encodeURIComponent(host)}&reason=domain-block`;
  await chrome.tabs.update(tabId, { url: blockedUrl });
}

async function enforceAllTabsIfNeeded() {
  const tabs = await chrome.tabs.query({});
  await Promise.all(
    tabs.map((tab) => {
      return enforceTabIfNeeded(tab.id, tab.url);
    })
  );
}

async function setStateAndRules(nextState) {
  const currentState = await getRuntimeState();
  const mergedState = {
    focusMode: Object.prototype.hasOwnProperty.call(nextState, "focusMode") ? Boolean(nextState.focusMode) : currentState.focusMode,
    allowYoutube: Object.prototype.hasOwnProperty.call(nextState, "allowYoutube") ? Boolean(nextState.allowYoutube) : currentState.allowYoutube,
    plannerProgressPercent: Object.prototype.hasOwnProperty.call(nextState, "plannerProgressPercent")
      ? Number(nextState.plannerProgressPercent || 0)
      : currentState.plannerProgressPercent,
    plannerHasSchedule: Object.prototype.hasOwnProperty.call(nextState, "plannerHasSchedule")
      ? Boolean(nextState.plannerHasSchedule)
      : currentState.plannerHasSchedule,
    plannerActiveSubject: Object.prototype.hasOwnProperty.call(nextState, "plannerActiveSubject")
      ? String(nextState.plannerActiveSubject || "")
      : currentState.plannerActiveSubject,
    plannerBlockedDomains: Object.prototype.hasOwnProperty.call(nextState, "plannerBlockedDomains")
      ? (Array.isArray(nextState.plannerBlockedDomains) ? nextState.plannerBlockedDomains : list(DEFAULT_BLOCKED_DOMAINS))
      : currentState.plannerBlockedDomains,
    plannerAllowedDomains: Object.prototype.hasOwnProperty.call(nextState, "plannerAllowedDomains")
      ? (Array.isArray(nextState.plannerAllowedDomains) ? nextState.plannerAllowedDomains : [])
      : currentState.plannerAllowedDomains,
    plannerRewardActive: Object.prototype.hasOwnProperty.call(nextState, "plannerRewardActive")
      ? Boolean(nextState.plannerRewardActive)
      : currentState.plannerRewardActive,
    plannerRewardRemainingSeconds: Object.prototype.hasOwnProperty.call(nextState, "plannerRewardRemainingSeconds")
      ? Number(nextState.plannerRewardRemainingSeconds || 0)
      : currentState.plannerRewardRemainingSeconds,
    emergencyUnlockUntil: Object.prototype.hasOwnProperty.call(nextState, "emergencyUnlockUntil")
      ? (nextState.emergencyUnlockUntil || null)
      : currentState.emergencyUnlockUntil,
    emergencyUnlockDate: Object.prototype.hasOwnProperty.call(nextState, "emergencyUnlockDate")
      ? (nextState.emergencyUnlockDate || null)
      : currentState.emergencyUnlockDate,
    plannerHardMode: Object.prototype.hasOwnProperty.call(nextState, "plannerHardMode")
      ? Boolean(nextState.plannerHardMode)
      : currentState.plannerHardMode,
    plannerEmergencyRemaining: Object.prototype.hasOwnProperty.call(nextState, "plannerEmergencyRemaining")
      ? Number(nextState.plannerEmergencyRemaining || 0)
      : currentState.plannerEmergencyRemaining,
    youtubeLearnedKeywords: Object.prototype.hasOwnProperty.call(nextState, "youtubeLearnedKeywords")
      ? (nextState.youtubeLearnedKeywords && typeof nextState.youtubeLearnedKeywords === "object" ? nextState.youtubeLearnedKeywords : {})
      : currentState.youtubeLearnedKeywords,
    youtubeSessionAllowlist: Object.prototype.hasOwnProperty.call(nextState, "youtubeSessionAllowlist")
      ? (Array.isArray(nextState.youtubeSessionAllowlist) ? nextState.youtubeSessionAllowlist : [])
      : currentState.youtubeSessionAllowlist,
    blockedDomainHits: Object.prototype.hasOwnProperty.call(nextState, "blockedDomainHits")
      ? (nextState.blockedDomainHits && typeof nextState.blockedDomainHits === "object" ? nextState.blockedDomainHits : {})
      : currentState.blockedDomainHits
  };

  if (!mergedState.plannerHasSchedule) {
    mergedState.focusMode = false;
  }

  if (!isEmergencyUnlockActive(mergedState) && mergedState.emergencyUnlockUntil) {
    mergedState.emergencyUnlockUntil = null;
  }

  await setRuntimeState(mergedState);
  await applyBlockingRules(mergedState);
  await enforceAllTabsIfNeeded();
}

function readPlannerStateFromPage() {
  return {
    focusMode: localStorage.getItem("plannerFocusMode"),
    sessionActive: localStorage.getItem("plannerSessionActive"),
    progressPercent: localStorage.getItem("plannerProgressPercent"),
    hasSchedule: localStorage.getItem("plannerHasSchedule"),
    activeSubject: localStorage.getItem("plannerActiveSubject"),
    blockedDomains: localStorage.getItem("plannerBlockedDomains"),
    allowedDomains: localStorage.getItem("plannerAllowedDomains"),
    rewardActive: localStorage.getItem("plannerRewardActive"),
    rewardRemainingSeconds: localStorage.getItem("plannerRewardRemainingSeconds"),
    hardMode: localStorage.getItem("plannerHardMode"),
    emergencyRemaining: localStorage.getItem("plannerEmergencyRemaining")
  };
}

function hasValidPlannerState(plannerState) {
  if (!plannerState) {
    return false;
  }

  const focusValue = plannerState.focusMode;
  const sessionValue = plannerState.sessionActive;

  const validFocus = focusValue === "on" || focusValue === "off";
  const validSession = sessionValue === "active" || sessionValue === "inactive";

  return validFocus && validSession;
}

function syncStateFromPlannerTabs() {
  chrome.tabs.query({}, async (tabs) => {
    if (!tabs || tabs.length === 0) {
      return;
    }

    const plannerTab = tabs.find((tab) => isPlannerUrl(tab.url) && typeof tab.id === "number");
    if (!plannerTab || typeof plannerTab.id !== "number") {
      return;
    }

    try {
      const results = await chrome.scripting.executeScript({
        target: { tabId: plannerTab.id },
        func: readPlannerStateFromPage
      });

      if (!results || !results[0] || !results[0].result) {
        return;
      }

      const plannerState = results[0].result;
      if (!hasValidPlannerState(plannerState)) {
        return;
      }

      const progress = Number(plannerState.progressPercent || 0);
      const hasSchedule = plannerState.hasSchedule !== "no";
      const blockedDomains = parseJsonArray(plannerState.blockedDomains);
      const allowedDomains = parseJsonArray(plannerState.allowedDomains);
      const rewardActive = plannerState.rewardActive === "yes";
      const rewardRemainingSeconds = Number(plannerState.rewardRemainingSeconds || 0);
      const hardMode = plannerState.hardMode === "yes";
      const emergencyRemaining = Number(plannerState.emergencyRemaining || 0);

      let focusMode = plannerState.focusMode === "on" && plannerState.sessionActive === "active" && hasSchedule;
      await setStateAndRules({
        focusMode,
        allowYoutube: allowedDomains.includes("youtube.com"),
        plannerProgressPercent: progress,
        plannerHasSchedule: hasSchedule,
        plannerActiveSubject: plannerState.activeSubject || "",
        plannerBlockedDomains: blockedDomains.length ? blockedDomains : list(DEFAULT_BLOCKED_DOMAINS),
        plannerAllowedDomains: allowedDomains,
        plannerRewardActive: rewardActive,
        plannerRewardRemainingSeconds: rewardRemainingSeconds,
        plannerHardMode: hardMode,
        plannerEmergencyRemaining: emergencyRemaining
      });
    } catch (_err) {
      // Ignore transient script-injection errors when tabs are loading.
    }
  });
}

chrome.runtime.onInstalled.addListener(async () => {
  await setStateAndRules({
    focusMode: false,
    allowYoutube: false,
    plannerProgressPercent: 0,
    plannerHasSchedule: true,
    plannerActiveSubject: "",
    plannerBlockedDomains: list(DEFAULT_BLOCKED_DOMAINS),
    plannerAllowedDomains: [],
    plannerRewardActive: false,
    plannerRewardRemainingSeconds: 0,
    emergencyUnlockUntil: null,
    emergencyUnlockDate: null,
    plannerHardMode: false,
    plannerEmergencyRemaining: 1,
    youtubeLearnedKeywords: {},
    youtubeSessionAllowlist: [],
    blockedDomainHits: {}
  });
  chrome.alarms.create("planner-sync", { periodInMinutes: 1 });
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message) {
    return;
  }

  if (message.type === "SET_FOCUS_MODE") {
    setStateAndRules({
      focusMode: Boolean(message.focusMode)
    })
      .then(() => sendResponse({ ok: true }))
      .catch(() => sendResponse({ ok: false }));

    return true;
  }

  if (message.type === "TRIGGER_EMERGENCY_UNLOCK") {
    getRuntimeState()
      .then(async (state) => {
        const emergencyRemaining = Number(state.plannerEmergencyRemaining || 0);
        if (state.plannerHardMode && emergencyRemaining <= 0) {
          sendResponse({ ok: false, reason: "hard-mode-limit" });
          return;
        }

        const unlockUntil = new Date(Date.now() + EMERGENCY_UNLOCK_MINUTES * 60 * 1000).toISOString();
        await setStateAndRules({
          focusMode: true,
          emergencyUnlockUntil: unlockUntil,
          emergencyUnlockDate: null,
          plannerEmergencyRemaining: state.plannerHardMode ? Math.max(0, emergencyRemaining - 1) : emergencyRemaining
        });

        sendResponse({
          ok: true,
          unlockUntil,
          emergencyRemaining: state.plannerHardMode ? Math.max(0, emergencyRemaining - 1) : emergencyRemaining
        });
      })
      .catch(() => sendResponse({ ok: false, reason: "runtime-error" }));

    return true;
  }

  if (message.type === "ALLOW_YOUTUBE_URL_ONCE") {
    allowYoutubeUrlOnce(String(message.url || ""), String(message.title || ""))
      .then(() => sendResponse({ ok: true }))
      .catch(() => sendResponse({ ok: false }));

    return true;
  }
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "planner-sync") {
    syncStateFromPlannerTabs();
  }
});

chrome.tabs.onUpdated.addListener((_tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete" && isPlannerUrl(tab.url)) {
    syncStateFromPlannerTabs();
  }

  const candidateUrl = changeInfo.url || tab.url;
  if (typeof tab.id === "number" && candidateUrl) {
    enforceTabIfNeeded(tab.id, candidateUrl);
  }
});

chrome.tabs.onCreated.addListener((tab) => {
  if (typeof tab.id === "number" && tab.url) {
    enforceTabIfNeeded(tab.id, tab.url);
  }
});

getRuntimeState().then((state) => {
  applyBlockingRules(state);
  chrome.alarms.create("planner-sync", { periodInMinutes: 1 });
  syncStateFromPlannerTabs();
  enforceAllTabsIfNeeded();
});

function list(values) {
  return Array.isArray(values) ? [...values] : [];
}
